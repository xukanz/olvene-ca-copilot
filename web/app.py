"""olvene-copilot: Streamlit UI for Client Advisors.

If API_URL is set, calls huashu-api over HTTP (with a Google ID token when the API is
private on Cloud Run). Otherwise runs the pipeline in-process (single-container mode).
"""
from __future__ import annotations

import base64
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from api.brand import load_brand  # noqa: E402
from api.cases import case_to_request, load_cases, screenshot_paths  # noqa: E402
from api.schemas import SCENARIO_ANGLES, SCENARIO_LABELS, DialogTurn, GenerateRequest  # noqa: E402

API_URL = os.environ.get("API_URL", "").rstrip("/")
FEEDBACK_LOG = Path(os.environ.get("FEEDBACK_LOG", "/tmp/olvene_feedback.jsonl"))

st.set_page_config(page_title="Olvène CA Copilot", page_icon="🌿", layout="wide")
brand = load_brand()


# ------------------------------------------------------------------ backend calls
def _id_token() -> dict:
    if not API_URL.startswith("https://"):
        return {}
    try:
        import google.auth.transport.requests
        import google.oauth2.id_token

        tok = google.oauth2.id_token.fetch_id_token(google.auth.transport.requests.Request(), API_URL)
        return {"Authorization": f"Bearer {tok}"}
    except Exception:
        return {}


def call(path: str, req: GenerateRequest) -> dict:
    if API_URL:
        import httpx

        r = httpx.post(f"{API_URL}{path}", json=req.model_dump(), headers=_id_token(), timeout=180)
        r.raise_for_status()
        return r.json()
    from api.config import get_settings
    from api.llm import LLM, CallStats
    from api.pipeline.parse_screenshot import analyze_dialog
    from api.pipeline.run import run_pipeline

    if path == "/v1/parse":
        s = get_settings()
        return {"analysis": analyze_dialog(req, LLM(s), s, CallStats()).model_dump()}
    return run_pipeline(req).model_dump()


# ------------------------------------------------------------------ state helpers
ss = st.session_state
DIALOG_COLS = ["speaker", "time", "text", "type", "transcript"]
ss.setdefault("dialog_df", pd.DataFrame(columns=DIALOG_COLS))
ss.setdefault("analysis", None)
ss.setdefault("result", None)
ss.setdefault("shots", [])
for _k, _v in {"scenario": "birthday_festive", "relationship": "熟悉", "gender": "F", "today": date.today(),
               "event_id": "（无）", "product_ids": [], "no_emoji": False}.items():
    ss.setdefault(_k, _v)

CASES = {c["id"]: c for c in load_cases()}


def load_case(cid: str) -> None:
    c = CASES[cid]
    cl = c["client"]
    ss.update(
        {
            "scenario": c["scenario"],
            "name": cl["name"],
            "preferred_name": cl.get("preferred_name") or "",
            "gender": cl.get("gender") or "F",
            "city": cl.get("city") or "",
            "relationship": cl.get("relationship") or "熟悉",
            "purchases": "\n".join(f"{p['product']} | {p.get('date') or ''}" for p in cl.get("purchases") or []),
            "preferences": "、".join(cl.get("preferences") or []),
            "important_dates": "、".join(cl.get("important_dates") or []),
            "notes": cl.get("notes") or "",
            "comm_style": cl.get("comm_style") or "",
            "no_emoji": bool(cl.get("no_emoji")),
            "last_interaction": cl.get("last_interaction") or "",
            "product_ids": c.get("product_ids") or [],
            "event_id": c.get("event_id") or "（无）",
            "today": date.fromisoformat(str(c["context"]["today"])),
            "occasion": c["context"].get("occasion") or "",
            "ca_name": c["context"].get("ca_name") or "",
            "dialog_df": pd.DataFrame(c.get("dialog") or [], columns=DIALOG_COLS).astype(object).fillna(""),
            "shots": [str(p) for p in screenshot_paths(cid)] if c.get("screenshot") else [],
            "analysis": None,
            "result": None,
        }
    )
    ss.pop("dialog_editor", None)


def build_request(with_dialog: bool = True) -> GenerateRequest:
    purchases = []
    for line in (ss.get("purchases") or "").splitlines():
        if line.strip():
            prod, _, d = line.partition("|")
            purchases.append({"product": prod.strip(), "date": d.strip() or None})
    split = lambda s: [x.strip() for x in (s or "").replace(",", "、").replace("，", "、").split("、") if x.strip()]  # noqa: E731
    dialog = None
    if with_dialog:
        df = ss.dialog_df.fillna("")
        dialog = [
            DialogTurn(
                speaker=r["speaker"] or "client",
                time=str(r["time"]) or None,
                text=str(r["text"]),
                type=r["type"] or "text",
                transcript=str(r.get("transcript") or "") or None,
            )
            for _, r in df.iterrows()
            if str(r["text"]).strip()
        ]
    return GenerateRequest(
        scenario=ss.scenario,
        client={
            "name": ss.name or "客户",
            "preferred_name": ss.preferred_name or None,
            "gender": ss.gender,
            "city": ss.city or None,
            "relationship": ss.relationship,
            "purchases": purchases,
            "preferences": split(ss.preferences),
            "important_dates": split(ss.important_dates),
            "notes": ss.notes or None,
            "comm_style": ss.comm_style or None,
            "no_emoji": ss.no_emoji,
            "last_interaction": ss.last_interaction or None,
        },
        dialog=dialog,
        product_ids=ss.product_ids,
        event_id=None if ss.event_id == "（无）" else ss.event_id,
        context={"today": ss.today.isoformat(), "occasion": ss.occasion or None, "ca_name": ss.ca_name or None},
    )


# ------------------------------------------------------------------ layout
st.markdown("### 🌿 Olvène CA Copilot · 微信话术助手")
st.caption("Maison Olvène 欧薇恩为虚构品牌；所有客户、产品、活动均为虚构。工具只生成草稿，由 CA 选择、修改后发送。")

left, mid, right = st.columns([1.05, 1.25, 1.5], gap="large")

with left:
    st.markdown("**① 客户与场景**")
    st.selectbox(
        "载入测试用例（可选，选中即自动填充）",
        ["—"] + list(CASES),
        key="case_pick",
        format_func=lambda k: k if k == "—" else f"{k} · {CASES[k].get('title', '')}",
        # Callbacks run before the script body, the supported way to set other widgets' state.
        on_change=lambda: load_case(ss.case_pick) if ss.case_pick != "—" else None,
    )

    st.selectbox(
        "场景", list(SCENARIO_LABELS), key="scenario", format_func=lambda k: f"{SCENARIO_LABELS[k]}（{' / '.join(SCENARIO_ANGLES[k])}）"
    )
    c1, c2 = st.columns(2)
    c1.text_input("称呼", key="name", placeholder="周女士")
    c2.text_input("称呼偏好", key="preferred_name", placeholder="如 Grace")
    c1.selectbox("性别", ["F", "M"], key="gender", format_func=lambda g: "女" if g == "F" else "男")
    c2.selectbox("关系阶段", ["初识", "熟悉", "挚交"], key="relationship")
    c1.text_input("城市", key="city")
    c2.text_input("沟通偏好", key="comm_style", placeholder="简短、不用表情")
    st.text_area("购买历史（每行：产品 | 日期）", key="purchases", height=68)
    st.text_input("偏好（、分隔）", key="preferences")
    st.text_input("重要日期", key="important_dates", placeholder="生日 11-10")
    st.text_area("CA 笔记", key="notes", height=68)
    st.text_input("最近一次互动", key="last_interaction")
    st.checkbox("客户不喜欢表情", key="no_emoji")

    prods = {p["id"]: f"{p['name_cn']} {p.get('variant', '')} · ¥{p.get('price', p.get('price_from')):,}" for p in brand.catalog["products"]}
    st.multiselect("相关产品", list(prods), key="product_ids", format_func=lambda k: f"{k} {prods[k]}")
    events = {"（无）": "（无）", **{e["id"]: f"{e['id']} {e['name']} {e['date']}" for e in brand.catalog["events"]}}
    st.selectbox("活动", list(events), key="event_id", format_func=lambda k: events[k])
    c1, c2 = st.columns(2)
    c1.date_input("今天", key="today")
    c2.text_input("场合/节日", key="occasion")
    st.text_input("CA 名字", key="ca_name")

with mid:
    st.markdown("**② 对话记录**")
    ups = st.file_uploader("上传微信截图（可多张，按顺序）", type=["png", "jpg", "jpeg"], accept_multiple_files=True)
    if ups:
        ss.shots = ["data:%s;base64,%s" % (u.type, base64.b64encode(u.getvalue()).decode()) for u in ups]
    if ss.shots:
        st.image([s if not s.startswith("data:") else base64.b64decode(s.split(",", 1)[1]) for s in ss.shots], width=150)
        if st.button("解析截图 →", type="secondary"):
            req = build_request(with_dialog=False)
            req.dialog_screenshots = ss.shots
            with st.spinner("Gemini 正在读取截图…"):
                try:
                    an = call("/v1/parse", req)["analysis"]
                    ss.analysis = an
                    ss.dialog_df = pd.DataFrame(an["dialog"], columns=DIALOG_COLS).astype(object).fillna("")
                except Exception as e:
                    st.error(f"解析失败：{e}")
    if ss.analysis:
        a = ss.analysis
        st.info(f"{a['summary']}\n\n情绪：{a['client_sentiment']} · 置信度：{a['parse_confidence']}"
                + (f"\n\n未回应：{'；'.join(a['open_questions'])}" if a["open_questions"] else ""))
    st.caption("解析结果可直接修改（speaker: client / ca / other）；也可以手动输入对话。")
    ss.dialog_df = st.data_editor(
        ss.dialog_df,
        num_rows="dynamic",
        width="stretch",
        column_config={
            "speaker": st.column_config.SelectboxColumn("说话人", options=["client", "ca", "other"], required=True),
            "time": st.column_config.TextColumn("时间", width="small"),
            "text": st.column_config.TextColumn("内容", width="large"),
            "type": st.column_config.SelectboxColumn("类型", options=["text", "image", "voice", "sticker", "recall"]),
            "transcript": st.column_config.TextColumn("语音转文字", help="语音消息在微信里“转文字”后的内容；没有就留空"),
        },
        key="dialog_editor",
    )

with right:
    st.markdown("**③ 话术候选**")
    if st.button("生成 3 条话术", type="primary", width="stretch") or (ss.result and st.session_state.get("_regen")):
        ss._regen = False
        with st.spinner("生成并检查中…"):
            try:
                ss.result = call("/v1/generate", build_request())
            except Exception as e:
                st.error(f"生成失败：{e}")
    res = ss.result
    if res:
        st.caption(
            f"{res['meta']['prompt_version']} · {res['meta']['brand_version']} · {res['meta']['model']} · "
            f"{res['meta']['latency_ms']} ms · 改写 {res['checks']['retries']} 轮"
        )
        if res["open_questions"]:
            st.warning("客户尚未被回应：" + "；".join(res["open_questions"]))
        flags = res["checks"]["flags"]
        for f in flags:
            if f["code"] in ("care_mode", "parse_confidence", "unseen_media"):
                st.warning(f["detail"])
        for i, c in enumerate(res["candidates"]):
            with st.container(border=True):
                status = "✅ 通过检查" if c["passed"] else "⚠️ 需人工确认"
                st.markdown(f"**{i + 1} · {c['angle']}** &nbsp; <small>{status} · {c['char_count']} 字</small>", unsafe_allow_html=True)
                st.code(c["text"], language=None, wrap_lines=True)
                st.caption(c["rationale"])
                mine = [f for f in flags if f["candidate"] == i and f["level"] != "info"]
                if mine:
                    with st.expander(f"检查提示（{len(mine)}）"):
                        for f in mine:
                            st.write(f"[{f['level']}] {f['code']}：{f['detail']}")
                if st.button("选用这条", key=f"pick{i}"):
                    FEEDBACK_LOG.parent.mkdir(parents=True, exist_ok=True)
                    with FEEDBACK_LOG.open("a") as fh:
                        fh.write(json.dumps({"request_id": res["request_id"], "picked": i, "text": c["text"], "ts": time.time()}, ensure_ascii=False) + "\n")
                    st.toast("已记录你的选择，用于积累优秀话术库")
        if st.button("不满意，重新生成"):
            ss._regen = True
            st.rerun()
        with st.expander("模型的判断（plan）"):
            st.json(res.get("plan"))
