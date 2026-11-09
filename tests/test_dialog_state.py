from api.brand import load_brand
from api.pipeline.context import build_context
from api.pipeline.dialog_state import compute_state, parse_time
from api.pipeline.guardrails import check_candidate
from api.schemas import Client, DialogAnalysis, DialogTurn, GenerateRequest

C = Client(name="周女士", gender="F")


def T(speaker, time, text, type="text"):
    return DialogTurn(speaker=speaker, time=time, text=text, type=type)


def test_parse_time_formats():
    from datetime import date

    d = date(2026, 11, 9)
    assert parse_time("11-08 22:30", d).day == 8
    assert parse_time("11月8日 晚上21:14", d).hour == 21
    assert parse_time("昨天 19:30", d).day == 8
    assert parse_time("12-30 10:00", d).year == 2025  # later in the year → last year


def test_ongoing_and_addressed_omits_salutation():
    st = compute_state([T("ca", "11-09 10:00", "周女士早，照片发您了"), T("client", "11-09 10:05", "这个颜色有现货吗")], C, "2026-11-09")
    assert st.ongoing and st.addressed_before and st.omit_salutation and st.ca_owes_reply and not st.reply_delayed


def test_delayed_reply_and_closer_and_stale():
    late = compute_state([T("client", "11-07 22:15", "边上的金线起毛了")], C, "2026-11-08")
    assert late.reply_delayed
    closed = compute_state([T("ca", "11-06 19:00", "谢谢您"), T("client", "11-06 19:30", "好的谢谢～")], C, "2026-11-09")
    assert not closed.ca_owes_reply
    stale = compute_state([T("client", "10-02 23:48", "我妈妈上个月走了")], C, "2026-11-22")
    assert not stale.reply_delayed and "重新开启" in stale.text


def _flags(dialog, text, today="2026-11-09", scenario="post_purchase_care"):
    b = load_brand()
    req = GenerateRequest(scenario=scenario, client=C, dialog=dialog, context={"today": today})
    ctx = build_context(b, req, DialogAnalysis(dialog=dialog), "v2")
    return {f.code for f in check_candidate(b, req, ctx, 0, text)}


def test_rhythm_rules():
    ongoing = [T("ca", "11-09 10:00", "周女士早，照片发您了"), T("client", "11-09 10:05", "这个颜色好看吗")]
    assert "repeat_salutation" in _flags(ongoing, "周女士，这个颜色在自然光下更柔和一些，日常搭配很容易，您喜欢的话我再拍几张细节给您。")
    assert "repeat_salutation" not in _flags(ongoing, "这个颜色在自然光下更柔和一些，日常搭配很容易，您喜欢的话我再拍几张细节给您看看。")
    late = [T("client", "11-07 22:15", "边上的金线起毛了，有点失望")]
    assert "no_delay_apology" in _flags(late, "曹女士，看到照片了，非常理解您的心情，您方便时把卡包带来店里，我们先看看实物再给您一个妥善的处理。", today="2026-11-08")
    assert "no_delay_apology" not in _flags(late, "曹女士，抱歉昨晚没来得及回您。看到照片了，非常理解您的心情，您方便时带来店里，我们先看看实物再处理。", today="2026-11-08")


def test_imperative_and_unknown_content():
    assert "imperative" in _flags([], "周女士，生日快乐🌿 今天先放松一下，吃顿好的，新的一岁一切顺遂。", scenario="birthday_festive")
    voice = [T("client", "11-08 22:31", "[语音 12″]", "voice")]
    assert "unknown_content_claim" in _flags(voice, "钟先生，抱歉昨晚没及时回复，您的语音我听了，完全理解您的感受，价格上我们确实是统一定价。", scenario="price_objection")


def test_voice_transcript_and_unseen_media():
    from api.pipeline.parse_screenshot import format_dialog

    heard = T("client", "11-03 22:08", "[语音 6″]", "voice")
    heard.transcript = "最好黑色的"
    assert "微信转文字：最好黑色的" in format_dialog([heard])
    assert "内容未知" in format_dialog([T("client", "11-03 22:08", "[语音 6″]", "voice")])
    # a claim about a transcribed voice is fine; an excuse about an untranscribed one is flagged
    text = "Kevin，抱歉前几天没顾上回。您语音里说想要黑色、能放十五寸电脑的包，工坊公文包正合适，我拍段视频给您看看？"
    assert "unknown_content_claim" not in _flags([heard], text, today="2026-11-09", scenario="product_recommendation")
    blind = [T("client", "11-03 22:08", "[语音 6″]", "voice")]
    assert "unknown_content_claim" in _flags(blind, "Kevin，抱歉前几天没顾上回。那条语音我现在不方便听，工坊公文包挺合适的，我拍段视频给您看看？", today="2026-11-09", scenario="product_recommendation")


def test_unseen_media_reminder_in_mock_pipeline():
    import os

    os.environ["LLM_MODE"] = "mock"
    from api.pipeline.run import run_pipeline

    req = GenerateRequest(scenario="product_recommendation", client=C,
                          dialog=[T("client", "11-08 22:31", "[语音 12″]", "voice")], context={"today": "2026-11-09"})
    assert any(f.code == "unseen_media" for f in run_pipeline(req).checks.flags)


def test_discount_refusal_with_long_gap_is_not_flagged():
    assert "discount_mention" not in _flags([], "陆女士，十分理解您的想法。品牌一直执行全国统一定价，确实没办法在价格上给到折扣，这点也要跟您说实话。您可以慢慢考虑，不用有压力。", scenario="price_objection")


def test_time_fallback_to_last_interaction():
    c = Client(name="程女士", gender="F", last_interaction="2026-11-06 微信")
    st = compute_state([T("client", None, "你们专柜怎么贵这么多")], c, "2026-11-07")
    assert st.days_since_last == 1 and st.reply_delayed
