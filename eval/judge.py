"""LLM-as-judge (SUBMISSION.md §B3 rubric). Uses a different prompt — and by default a
different model (JUDGE_MODEL) — from the generator to reduce self-preference."""
from __future__ import annotations

from pydantic import BaseModel, Field

from api.brand import load_brand
from api.config import Settings
from api.llm import LLM, CallStats
from api.schemas import SCENARIO_LABELS

# j2: adds the failure modes found in the v1 human review and a calibration instruction.
JUDGE_VERSION = "j2"

JUDGE_SYSTEM = """你是奢侈品客户关系领域的资深评审，为 CA（客户顾问）微信消息草稿打分。
你代表品牌 {brand}。品牌与话术指南如下，它是评分的唯一标准：

<brand_guide>
{guide}
</brand_guide>

## 评分维度（每条候选，1–5 分）
- personalisation 个性化：1 = 发给谁都行；3 = 用了客户细节但很表面；5 = 细节具体且自然融入
- on_brand 品牌口吻：1 = 销售腔/模板化；3 = 礼貌但普通；5 = 温润、克制、具体，像欧薇恩
- timing 时机与分寸（场景契合）：1 = 打扰或施压；3 = 可以接受；5 = 给客户留余地，分量恰当，完成了该场景的目标
- naturalness 自然度：1 = 像脚本/AI；3 = 大体自然；5 = 像真实 CA 在微信上打的字
- cta 行动号召：1 = 施压或该有却没有；3 = 有但生硬；5 = 低压力、好回复
## 硬性判定
- red_line：是否违反任何红线（折扣暗示、贬低渠道、捏造产品/活动/客户信息、虚假紧迫、敏感信息、无视投诉或情绪、在生日/节日或售后中推销、客户负面/拒绝时仍推销、不像微信消息）。违反时在 red_line_reasons 写明。
- send_ready：资深 CA 会不会不改一个字直接发送。下面任何一条成立时，send_ready 必须为 false，并在 comment 中写明：
  · 刻意的个性化：为了显得记得客户硬塞细节（如生日祝福里点名客户买过的商品"那条丝巾现在用刚好"），或巧合、戏剧化的情节
  · 对客户下指令或指手画脚（"吃顿好的""别忘了带上那条披肩""不如一起来坐坐"）
  · 敏感情境处理不当：哀伤中提商品或把逝者和物品联系起来；邀请不适合该活动的同伴（如带孩子去皮具保养工作坊）
  · 没有承接对话，一开口就讲知识或搭配，读起来生硬
  · 违反 <dialog_state>：对话进行中且已称呼过却又以称呼开头；客户等了一天以上却没有为回复晚道歉或解释
  · 照抄品牌指南示例里的原句
- 声称听过语音、看过图片的具体内容（输入中只有 [语音]/[图片] 占位符）属于捏造，red_line 为 true。
## 组级
- diversity 1–5：1 = 几乎相同；3 = 措辞不同但角度相同；5 = 三个真正不同的角度，CA 有真实选择。

## 校准
你过去打分明显偏高：几乎所有消息都得了 5 分，而人工评审在其中发现了不少需要修改的问题。请按下面的锚点打分：
- 3 分 = 合格、可用，但 CA 可能想改一两处；这是最常见的分数
- 4 分 = 好，没有明显问题
- 5 分 = 出色，资深 CA 也写不出更好的；每组三条里通常最多一条某个维度能拿 5
comment 里先写这条最主要的问题（没有就写"无明显问题"），再写亮点。"""

JUDGE_USER = """场景：{scenario}
今天：{today}；场合：{occasion}

<client>
{client}
</client>

<dialog>
{dialog}
</dialog>

<dialog_state>
{dialog_state}
</dialog_state>

<facts>
{facts}
</facts>

本用例的特别检查点：
- 必须回应：{must_address}
- 不得出现：{must_not}

待评分的三条候选：
{candidates}"""


class CandidateScore(BaseModel):
    index: int
    personalisation: int = Field(ge=1, le=5)
    on_brand: int = Field(ge=1, le=5)
    timing: int = Field(ge=1, le=5)
    naturalness: int = Field(ge=1, le=5)
    cta: int = Field(ge=1, le=5)
    red_line: bool
    red_line_reasons: list[str]
    send_ready: bool
    comment: str


class JudgeOutput(BaseModel):
    candidates: list[CandidateScore]
    diversity: int = Field(ge=1, le=5)
    set_comment: str


WEIGHTS = {"personalisation": 0.25, "on_brand": 0.25, "timing": 0.2, "naturalness": 0.2, "cta": 0.1}


def weighted(score: CandidateScore) -> float:
    return round(sum(getattr(score, k) * w for k, w in WEIGHTS.items()), 2)


def judge_case(
    case: dict,
    client_text: str,
    dialog_text: str,
    facts_text: str,
    candidates: list[dict],
    s: Settings,
    stats: CallStats,
    dialog_state: str = "",
) -> JudgeOutput:
    brand = load_brand()
    exp = case.get("expect") or {}
    ctx = case.get("context") or {}
    system = JUDGE_SYSTEM.format(brand=brand.rules["brand"]["name_en"], guide=brand.guide_md)
    prompt = JUDGE_USER.format(
        scenario=SCENARIO_LABELS[case["scenario"]],
        today=ctx.get("today"),
        occasion=ctx.get("occasion") or "无",
        client=client_text,
        dialog=dialog_text,
        dialog_state=dialog_state or "（无）",
        facts=facts_text,
        must_address="；".join(exp.get("must_address") or []) or "无",
        must_not="；".join(exp.get("must_not") or []) or "无",
        candidates="\n".join(f"[候选 {i}] 角度：{c['angle']}\n{c['text']}\n" for i, c in enumerate(candidates)),
    )
    return LLM(s).generate_json(
        task="judge", model=s.judge_model, system=system, prompt=prompt, schema=JudgeOutput, temperature=0.0, stats=stats
    )
