"""L1 rule checker vs. the good / unacceptable examples in brand_guide.md §7."""
import pytest

from api.brand import load_brand
from api.pipeline.context import build_context
from api.pipeline.guardrails import check_candidate
from api.schemas import DialogAnalysis, GenerateRequest

BRAND = load_brand()


def _req(scenario, **client):
    c = {"name": "周女士", "gender": "F", **client}
    return GenerateRequest(scenario=scenario, client=c, dialog=[], context={"today": "2026-11-09"})


def _hard(scenario, text, req=None, keep_copy=False, **client):
    req = req or _req(scenario, **client)
    ctx = build_context(BRAND, req, DialogAnalysis(), "v1")
    # The guide's own examples are used as inputs here, so ignore the copy check except where tested.
    return sorted({f.code for f in check_candidate(BRAND, req, ctx, 0, text) if f.level == "hard"} - {"copied_example"} | (
        {"copied_example"} if keep_copy and any(f.code == "copied_example" for f in check_candidate(BRAND, req, ctx, 0, text)) else set()))


GOOD = [
    ("birthday_festive", "周女士", "周女士，生日快乐🌿 记得您说今年想把院子里的月季再扩一片，愿新的一岁花开得比去年更好。天凉了，出门记得多添件衣裳。"),
    ("post_purchase_care", "林小姐", "林小姐，沙漏包用了两周，还顺手吗？新皮子前一两个月会慢慢变软，形状也会更贴合您的使用习惯。最近上海雨多，万一淋到，用干的软布轻轻按干就好，别用吹风机。有任何问题随时找我。"),
    ("reactivation", "王女士", "王女士，最近好吗？今年秋冬的经纬丝巾出了一款雾霾蓝，我第一眼就想到您以前很喜欢的那条湖蓝色。不知道您最近还常系丝巾吗？您有兴趣的话，我拍几张实物给您看看。"),
    ("price_objection", "周女士", "理解的，同一只包两地价格不一样，换作是我也会比一比。各地价格会受税费和汇率影响，我们这边是按品牌统一定价执行的，确实没办法打折，这点要跟您说实话。在国内专柜购买的话，可以免费烫上您的姓名缩写，之后的清洁保养也一直由我们负责。您不着急，想再试背一次随时告诉我。"),
]


@pytest.mark.parametrize("scenario,name,text", GOOD)
def test_good_examples_pass(scenario, name, text):
    purchases = [{"product": "沙漏包 迷你款 黑色"}] if scenario == "post_purchase_care" else []
    assert _hard(scenario, text, name=name, purchases=purchases) == []


def test_bad_birthday():
    text = "尊敬的周女士，欧薇恩祝您生日快乐！！感谢您一直以来的支持，生日当月到店购物可享专属礼遇哦～"
    assert {"exclamation", "repeated_punct"} <= set(_hard("birthday_festive", text))


def test_bad_reactivation():
    text = "王女士，您已经快两年没来店里了，我们都很想念您！新品已经到店，欢迎您本周来看看。"
    assert {"absence_blame", "demand_visit"} <= set(_hard("reactivation", text, name="王女士"))


def test_bad_price_objection():
    text = "我帮您跟店长申请一下看看能不能有点优惠～另外香港代购的东西不一定保真哦，还是在我们这里买放心。"
    assert {"discount_promise", "disparage_channel", "discount_mention"} <= set(_hard("price_objection", text))


def test_unknown_price_and_product_push():
    req = _req("product_recommendation")
    req.product_ids = ["P05"]
    assert "unknown_price" in _hard("product_recommendation", "周女士，这条丝巾 ¥4,800，很适合您。", req=req)
    assert _hard("product_recommendation", "周女士，这条经纬丝巾 ¥5,200，湖蓝很适合您秋天系。", req=req) == []
    assert "product_push" in _hard("birthday_festive", "周女士，生日快乐。新到的沙漏包也很适合您，有空来看看。")


def test_event_facts():
    req = _req("event_invitation")
    req.event_id = "E01"
    ok = "周女士，11月28日 14:00 在上海店有一场里昂丝织工艺展，印染师傅会现场演示手工丝网印刷，您可以亲手完成一道套色。想到您喜欢丝巾，就先来问问您。"
    assert _hard("event_invitation", ok, req=req) == []
    bad = ok.replace("11月28日", "11月29日").replace("14:00", "15:00")
    assert {"event_date", "event_time"} <= set(_hard("event_invitation", bad, req=req))


def test_gender_and_emoji():
    assert "wrong_gender" in _hard("birthday_festive", "周先生，生日快乐，愿新的一年一切顺遂，天冷了多添衣。")
    assert "emoji_not_allowed" in _hard("birthday_festive", "周女士，生日快乐🎉 新的一岁一切顺遂，天冷了多添衣。")
    assert "emoji_count" in _hard(
        "birthday_festive", "周女士，生日快乐🌿 新的一岁一切顺遂，天冷了多添衣。", no_emoji=True
    )


def test_copied_example_detected():
    copied = "王女士，最近好吗？今年秋冬的经纬丝巾出了一款雾霾蓝，我第一眼就想到您以前很喜欢的那条湖蓝色。您有兴趣的话我拍几张给您。"
    assert "copied_example" in _hard("reactivation", copied, keep_copy=True, name="王女士")
    own = "王女士，最近好吗？店里刚到了一款雾霾蓝的经纬丝巾，颜色比湖蓝更沉静一些，您有兴趣的话我拍几张实物给您看看。"
    assert "copied_example" not in _hard("reactivation", own, keep_copy=True, name="王女士")
