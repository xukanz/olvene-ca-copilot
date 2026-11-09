"""Request / response models (the data contract, 方案规划 §3) and LLM output schemas."""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

Scenario = Literal[
    "birthday_festive",
    "product_recommendation",
    "post_purchase_care",
    "reactivation",
    "event_invitation",
    "price_objection",
]

SCENARIO_LABELS: dict[str, str] = {
    "birthday_festive": "生日/节日问候",
    "product_recommendation": "产品推荐",
    "post_purchase_care": "售后关怀",
    "reactivation": "沉睡客户唤醒",
    "event_invitation": "活动邀请",
    "price_objection": "价格异议",
}

# Three distinct angles per scenario (brand_guide.md §6). Order = candidate order.
SCENARIO_ANGLES: dict[str, list[str]] = {
    "birthday_festive": ["简洁温暖", "记忆连接", "生活关怀"],
    "product_recommendation": ["需求匹配", "工艺故事", "轻量互动"],
    "post_purchase_care": ["使用感受", "保养知识", "搭配建议"],
    "reactivation": ["想起您", "服务提醒", "纯问候"],
    "event_invitation": ["体验亮点", "个人连接", "轻松邀约"],
    "price_objection": ["价值说明", "替代方案", "留有余地"],
}

# Fallback angles when the client is upset or has clearly declined (方案规划 §4 ③ special branch).
CARE_ANGLES = ["先回应情绪", "解决问题", "留白与尊重"]


# ---------------------------------------------------------------- input


class Purchase(BaseModel):
    product: str
    date: str | None = None


class Client(BaseModel):
    client_id: str | None = None
    name: str = Field(description="称呼，例如 周女士")
    preferred_name: str | None = Field(None, description="称呼偏好，例如英文名")
    gender: Literal["F", "M"] | None = None
    city: str | None = None
    relationship: Literal["初识", "熟悉", "挚交"] = "熟悉"
    purchases: list[Purchase] = []
    preferences: list[str] = []
    important_dates: list[str] = []
    notes: str | None = Field(None, description="CA 笔记：兴趣与生活片段")
    comm_style: str | None = Field(None, description="沟通偏好，例如 简短、不用表情")
    no_emoji: bool = False
    last_interaction: str | None = None


class DialogTurn(BaseModel):
    speaker: Literal["client", "ca", "other", "system"]
    time: str | None = None
    text: str
    type: Literal["text", "image", "voice", "sticker", "recall", "other"] = "text"


class RequestContext(BaseModel):
    today: str = Field(default_factory=lambda: date.today().isoformat())
    occasion: str | None = Field(None, description="节日/场合，例如 中秋、生日")
    ca_name: str | None = None
    extra: str | None = Field(None, description="CA 给工具的补充说明")


class GenerateRequest(BaseModel):
    brand_id: str = "olvene"
    scenario: Scenario
    client: Client
    # Conversation history, any one of (priority: dialog > dialog_text > screenshots):
    dialog: list[DialogTurn] | None = Field(None, description="已结构化/已校正的对话")
    dialog_text: str | None = Field(None, description="纯文本聊天记录")
    dialog_screenshots: list[str] = Field(
        default_factory=list, description="截图：gs:// URI、data URI / base64、或本地路径（仅 CLI）"
    )
    product_ids: list[str] = Field(default_factory=list, description="catalog.yaml 中的产品 id")
    event_id: str | None = None
    product_note: str | None = Field(None, description="补充的商品事实（会被视为可引用事实）")
    context: RequestContext = Field(default_factory=RequestContext)


# ---------------------------------------------------------------- LLM outputs


class DialogAnalysis(BaseModel):
    """Output of step ① (screenshot / text parsing + analysis)."""

    dialog: list[DialogTurn] = []
    summary: str = ""
    client_sentiment: Literal["positive", "neutral", "negative", "unknown"] = "unknown"
    client_declined: bool = Field(False, description="客户是否明确拒绝/表示不需要")
    open_questions: list[str] = Field(default_factory=list, description="客户提出但 CA 尚未回答的问题或情绪")
    parse_confidence: Literal["high", "medium", "low"] = "high"
    parse_notes: str = ""


class Candidate(BaseModel):
    angle: str
    text: str
    rationale: str


class GenerationPlan(BaseModel):
    stage: str = Field(description="对话所处阶段")
    must_address: list[str] = Field(description="消息必须先回应的问题或情绪，没有则为空")
    timing_note: str = Field(description="时机是否合适，有什么要注意")


class GenerationOutput(BaseModel):
    plan: GenerationPlan
    candidates: list[Candidate]


class RewriteOutput(BaseModel):
    text: str
    rationale: str


class CandidateReview(BaseModel):
    index: int
    fabricated_facts: list[str] = Field(description="输入中不存在的事实；无则为空")
    pushy_or_salesy: bool
    ignores_open_question: bool
    off_brand_issues: list[str] = Field(description="语气/称谓/用词问题；无则为空")
    passed: bool
    fix_instruction: str = Field(description="不通过时，给改写者的一句具体修改指令")


class ReviewOutput(BaseModel):
    candidates: list[CandidateReview]
    too_similar: bool = Field(description="三条是否角度雷同")


# ---------------------------------------------------------------- response


class Flag(BaseModel):
    candidate: int | None = None  # None = applies to the whole set
    level: Literal["hard", "soft", "llm", "info"]
    code: str
    detail: str


class CandidateOut(Candidate):
    passed: bool = True
    char_count: int = 0


class Checks(BaseModel):
    passed: bool
    retries: int
    flags: list[Flag] = []


class GenerateResponse(BaseModel):
    request_id: str
    parsed_dialog: list[DialogTurn]
    dialog_summary: str
    client_sentiment: str
    open_questions: list[str]
    plan: GenerationPlan | None
    candidates: list[CandidateOut]
    checks: Checks
    meta: dict
