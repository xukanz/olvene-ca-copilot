# Architecture

## 1. Deployment (Google Cloud)

```mermaid
flowchart LR
    CA([Client Advisor<br/>browser]) -->|HTTPS| WEB

    subgraph RUN[Cloud Run · one image, three roles]
      WEB[olvene-copilot · ROLE=web<br/>Streamlit UI<br/>public URL, Google sign-in<br/>max 3 instances]
      API[huashu-api · ROLE=api<br/>FastAPI<br/>private: IAM run.invoker only]
      JOB[huashu-eval · ROLE=eval<br/>Cloud Run Job<br/>50-case batch + LLM judge]
    end

    WEB -->|POST /v1/parse<br/>POST /v1/generate<br/>Google ID token| API
    WEB <-->|daily quota<br/>20 per user · 200 total| FS[(Firestore)]
    SM[(Secret Manager<br/>OIDC secrets.toml)] -.mounted.-> WEB
    WEB -.OIDC sign-in.-> GOOG[Google accounts]

    API -->|generate · Gemini 3.1 Pro| VAI[Vertex AI<br/>global endpoint]
    API -->|read screenshots · review<br/>Gemini 3 Flash| VAI
    JOB -->|same pipeline in-process<br/>+ judge · Gemini 3 Flash| VAI
    JOB -->|v1 / v2 results<br/>jsonl · csv · xlsx| GCS[(Cloud Storage<br/>bucket mounted as volume)]

    AR[(Artifact Registry)] -.image.-> RUN
    CB[Cloud Build<br/>cloudbuild.yaml] -->|build · deploy| AR

    %% Transparent group box: the default subgraph fill hurts readability, especially in dark mode
    style RUN fill:none,stroke:#888,stroke-width:1px,stroke-dasharray:5 5
```

| Component                   | Code                                                                             | Why it is there                                                                                                                                                                                                                                     |
| --------------------------- | -------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Web UI (`olvene-copilot`) | [`web/app.py`](../web/app.py), [`web/quota.py`](../web/quota.py)               | The CA's screen: client form or a test case, screenshot upload, editable parsed chat, three candidate cards with copy, flags and "use this one". Google sign-in plus per-user and global daily caps keep a public demo from running up Gemini costs |
| API (`huashu-api`)        | [`api/main.py`](../api/main.py)                                                 | Runs the pipeline. Private: only the web service account can call it. `/v1/parse` lets the CA correct the chat before generating                                                                                                                  |
| Eval job (`huashu-eval`)  | [`eval/run_eval.py`](../eval/run_eval.py), [`eval/judge.py`](../eval/judge.py) | Runs all 50 cases through the same pipeline, scores them with the judge, writes results to the mounted bucket                                                                                                                                       |
| Brand knowledge             | [`brand/`](../brand/)                                                           | Brand guide, machine-checkable rules, product and event catalog, festival calendar. Loaded by key into every request; no vector retrieval (total < 10k tokens, so nothing can be missed)                                                            |
| CI/CD                       | [`Dockerfile`](../Dockerfile), [`cloudbuild.yaml`](../cloudbuild.yaml)         | One image; the `ROLE` variable picks API, web or eval                                                                                                                                                                                             |

## 2. Pipeline (inside the API)

```mermaid
flowchart TD
    IN[/"Request<br/>scenario · client profile · product / event IDs<br/>conversation: screenshots, text or corrected turns"/] --> P1

    P1["① Read the conversation · Gemini 3 Flash, multimodal<br/>bubbles → speaker, time, text; voice / image / sticker placeholders;<br/>WeChat voice-to-text; client mood, refusals, unanswered questions"]
    P1 --> P2

    P2["② Assemble context · deterministic, no LLM<br/>brand guide + rules · catalog facts for the given products / event ·<br/>conversation state computed in code: who spoke last, days since,<br/>CA owes a reply, client already addressed · nearby festivals ·<br/>three angles for the scenario, or care angles if the client is upset"]
    P2 --> P3

    P3["③ Generate · Gemini 3.1 Pro, one call, JSON schema<br/>plan (stage, must-address, timing) + exactly three candidates,<br/>one per angle"]
    P3 --> P4

    P4{"④ Check"}
    P4 --> L1["L1 rules · code<br/>forbidden phrases · discount wording outside a refusal ·<br/>length · emoji · punctuation · prices and event dates vs catalog ·<br/>no product in greetings · apology when overdue ·<br/>copying examples · similarity of the three"]
    P4 --> L2["L2 reviewer · Gemini 3 Flash<br/>fabrication · pushiness · ignored question ·<br/>tone notes"]
    L1 & L2 -->|hard fail or fabrication / pushiness / ignored question| RW["Rewrite only the failing candidate<br/>with the reasons · at most 2 rounds"]
    RW --> P4
    L1 & L2 -->|pass, or tone notes only| OUT[/"Three candidates + angle + rationale<br/>flags for the CA: tone notes, 'client sent a voice message you<br/>should check', 'client is upset: care mode'"/]
```

| Step          | Code                                                                                                                             | Design choice                                                                                                                                                                                                                   |
| ------------- | -------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| ① Read       | [`parse_screenshot.py`](../api/pipeline/parse_screenshot.py), prompt [`v2/parse_system.md`](../api/prompts/v2/parse_system.md) | A CA forwards screenshots, so the tool reads them. Result is shown in an editable table: a parsing mistake can be fixed before it spoils the drafts                                                                             |
| ② Context    | [`context.py`](../api/pipeline/context.py), [`dialog_state.py`](../api/pipeline/dialog_state.py)                               | Facts come only from the catalog, never from the model. Timing (who is waiting, for how long) is computed in code, because the model got date arithmetic wrong in v1                                                            |
| ③ Generate   | [`generate.py`](../api/pipeline/generate.py), prompts [`v2/generate_*.md`](../api/prompts/v2/)                                 | One call for all three, each with a fixed and different angle: diversity comes from strategy, not from sampling three times                                                                                                     |
| ④ Check      | [`guardrails.py`](../api/pipeline/guardrails.py), [`brand_rules.yaml`](../brand/brand_rules.yaml)                              | Red lines that can be checked by code are checked by code. The model reviewer covers what regexes cannot see. Only substantive problems trigger a rewrite, and only of the failing candidate, which keeps latency at about 40 s |
| Orchestration | [`run.py`](../api/pipeline/run.py)                                                                                              | Every response records model, prompt version and brand version, so each result can be traced to the exact configuration that produced it                                                                                        |

## 3. Evaluation loop

```mermaid
flowchart LR
    CASES[(50 test cases<br/>eval/cases/cases.yaml<br/>+ rendered WeChat screenshots)] --> RUN[Run pipeline]
    RUN --> SC["Score<br/>L1 rules · LLM judge (different prompt,<br/>Gemini 3 Flash, temperature 0) ·<br/>human review"]
    SC --> DEF[Defects with root cause]
    DEF --> FIX["Fix: brand guide · prompts v2 ·<br/>rules · conversation state · judge"]
    FIX --> RUN
    SC --> REP[Reports C · D · E]
```
