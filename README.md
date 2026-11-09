# Olvène CA Copilot

> **Reviewers: start at [`submission/SUBMISSION.md`](submission/SUBMISSION.md).** It contains the work log, methodology, test cases, evaluation report, defects and the architecture diagram.

An AI tool that drafts three on-brand Chinese WeChat messages for luxury Client Advisors (CAs), across six scenarios: birthday/festive greetings, product recommendation, post-purchase care, reactivation, event invitation, and price objection.

The brand **Maison Olvène 欧薇恩** and all products, boutiques, events and clients in this repository are fictional.

## Repository layout

| Path | What it is |
|---|---|
| `submission/` | Deliverables: main document, results spreadsheet, architecture diagram, screenshots |
| `brand/` | Fictional brand foundation (inputs to the tool) |
| `eval/cases/` | The 50 test cases (`cases.yaml`) and their WeChat-style chat screenshots |
| `eval/results/` | Every evaluation run (v1, v1_j2, v2, v2.1), reports, human review notes |
| `archive/` | Early draft of the test set, superseded by `eval/cases/` |

## Code

| Path | Purpose |
|---|---|
| `brand/` | Brand guide (voice, red lines, playbooks, few-shot examples), machine-checkable rules, catalog (the only allowed source of product and event facts), festival calendar |
| `api/` | FastAPI service and the four-step pipeline (`api/pipeline/`), versioned prompts (`api/prompts/v1/`, `v2/`), CLI |
| `web/` | Streamlit UI for CAs |
| `eval/` | 50 test cases, WeChat screenshot renderer, batch runner, LLM judge, report, human-review agreement |
| `tests/` | Rule-checker tests against the brand guide examples, mock-mode end-to-end tests |
| `docs/architecture.md` | Architecture diagram and component map |

## Run locally

```bash
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt

# Offline (no credentials): deterministic mock LLM, for plumbing and UI
LLM_MODE=mock .venv/bin/python -m pytest -q
LLM_MODE=mock .venv/bin/streamlit run web/app.py

# Real Gemini on Vertex AI
gcloud auth application-default login
export GOOGLE_CLOUD_PROJECT=<project> GOOGLE_CLOUD_LOCATION=global
.venv/bin/python -m api.cli eval/cases/cases.yaml S6-02          # one test case
.venv/bin/uvicorn api.main:app --reload                          # API on :8000
.venv/bin/streamlit run web/app.py                               # UI, runs pipeline in-process
```

Environment variables: `GEN_MODEL` (default `gemini-2.5-pro`), `FAST_MODEL` / `JUDGE_MODEL` (default `gemini-2.5-flash`), `GEN_TEMPERATURE`, `MAX_REWRITES`, `LLM_REVIEW=0|1`, `PROMPT_VERSION`, `LOG_DIR`, `API_URL` (UI → API).

## Evaluate

```bash
.venv/bin/python -m eval.render_wechat                 # (re)render screenshots for cases with a `screenshot` block
.venv/bin/python -m eval.run_eval --version v1         # 50 cases → eval/results/v1.{jsonl,csv,xlsx}
.venv/bin/python -m eval.human_review sample v1        # 15-case sheet to score by hand
.venv/bin/python -m eval.human_review agree v1         # judge vs human agreement
# change prompts → api/prompts/v2/, then
PROMPT_VERSION=v2 .venv/bin/python -m eval.run_eval --version v2
.venv/bin/python -m eval.report v1 v2                  # D1/D2 tables, charts, worst-10, red-line list
```

## Deploy (Cloud Run)

```bash
PROJECT=<project>; REGION=us-central1
gcloud services enable run.googleapis.com aiplatform.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com
gcloud artifacts repositories create olvene --repository-format docker --location $REGION
gcloud iam service-accounts create huashu-sa
gcloud projects add-iam-policy-binding $PROJECT --role roles/aiplatform.user \
  --member serviceAccount:huashu-sa@$PROJECT.iam.gserviceaccount.com
gcloud storage buckets create gs://$PROJECT-olvene-eval --location $REGION
# web: Google sign-in + daily caps (counters in Firestore)
gcloud services enable firestore.googleapis.com secretmanager.googleapis.com
gcloud firestore databases create --location $REGION
gcloud projects add-iam-policy-binding $PROJECT --role roles/datastore.user \
  --member serviceAccount:huashu-sa@$PROJECT.iam.gserviceaccount.com
# OAuth client (console only): Google Auth Platform → Clients → Web application,
# redirect URI https://olvene-copilot-<PROJECT_NUMBER>.$REGION.run.app/oauth2callback; publish the app (In production).
# Fill .streamlit/secrets.toml.example, then:
gcloud secrets create olvene-web-auth --data-file .streamlit/secrets.toml
gcloud secrets add-iam-policy-binding olvene-web-auth --role roles/secretmanager.secretAccessor \
  --member serviceAccount:huashu-sa@$PROJECT.iam.gserviceaccount.com
gcloud storage buckets add-iam-policy-binding gs://$PROJECT-olvene-eval --role roles/storage.objectAdmin \
  --member serviceAccount:huashu-sa@$PROJECT.iam.gserviceaccount.com
gcloud builds submit --config cloudbuild.yaml --substitutions _REGION=$REGION
gcloud run jobs execute huashu-eval --region $REGION --args="--version,v1"
```

The build deploys `huashu-api` (private), `olvene-copilot` (public, calls the API with its service account's ID token) and the `huashu-eval` job (results go to the mounted GCS bucket). The Cloud Build service account needs `run.admin` and `iam.serviceAccountUser`.
