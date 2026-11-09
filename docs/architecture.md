# Architecture

One container image with three roles on Cloud Run. Gemini runs on Vertex AI. Brand knowledge is loaded by key, with no vector retrieval (see 方案规划 §6).

```mermaid
flowchart LR
    CA[Client Advisor] -->|截图 / 客户信息 / 场景| WEB[olvene-copilot<br/>Cloud Run · Streamlit]
    WEB -->|POST /v1/parse<br/>POST /v1/generate<br/>ID token| API[huashu-api<br/>Cloud Run · FastAPI]

    subgraph PIPE[huashu-api pipeline · api/pipeline/run.py]
      P1[① 截图解析 + 对话分析<br/>Gemini Flash 多模态<br/>parse_screenshot.py] --> P2[② 上下文组装 · 确定性<br/>brand_guide + rules + catalog facts<br/>+ client + dialog + festivals<br/>context.py]
      P2 --> P3[③ 一次生成 3 条<br/>Gemini Pro · response_schema<br/>按场景强制 3 个角度<br/>generate.py]
      P3 --> P4[④ 合规检查<br/>L1 规则：brand_rules.yaml + catalog 事实比对<br/>L2 Gemini Flash 审查<br/>guardrails.py]
      P4 -- 不通过：只改写失败的那条 · ≤2 轮 --> P3
    end
    API --- PIPE

    KB[(brand/<br/>brand_guide.md · brand_rules.yaml<br/>catalog.yaml · festivals.yaml)] --> P2
    KB --> P4
    PIPE -.-> VAI[Vertex AI<br/>Gemini Pro / Flash]

    EVAL[huashu-eval<br/>Cloud Run Job] -->|50 用例 · run_pipeline| PIPE
    EVAL -->|LLM judge · 不同 prompt| VAI
    EVAL --> GCS[(GCS bucket 挂载卷<br/>v1/v2 .jsonl .csv .xlsx)]
```

| Component | Code | Notes |
|---|---|---|
| API | `api/main.py` | `/v1/parse` lets the CA correct the parsed dialog before generating. `/v1/generate` runs the full pipeline. |
| ① Parse | `api/pipeline/parse_screenshot.py`, `api/prompts/v1/parse_system.md` | Bubble colour and side give the speaker. Also extracts sentiment, refusals and open questions. Accepts screenshots, plain text or a pre-structured dialog. |
| ② Context | `api/pipeline/context.py` | Takes product facts from `catalog.yaml` only. Switches to care/restraint angles when the client is negative or has refused. |
| ③ Generate | `api/pipeline/generate.py`, `api/prompts/v1/generate_*.md` | One call returns three candidates, one per angle (`api/schemas.py: SCENARIO_ANGLES`). |
| ④ Guardrails | `api/pipeline/guardrails.py` | **L1:** forbidden phrases and regexes, discount wording outside refusals, length, punctuation, emoji, gender and salutation, prices against facts, event date and time against the catalog, scenario rules, pairwise similarity. **L2:** an LLM reviewer checks for fabrication, pushiness, ignored questions and tone. |
| UI | `web/app.py` | Calls the API over HTTP when `API_URL` is set. Otherwise runs the pipeline in-process. |
| Eval | `eval/run_eval.py`, `eval/judge.py`, `eval/report.py`, `eval/human_review.py` | Results are tagged with `prompt_version` and `brand_version`. |
| Test data | `eval/cases/cases.yaml`, `eval/render_wechat.py` | 50 fictional cases. Screenshots are rendered with Pillow. |
