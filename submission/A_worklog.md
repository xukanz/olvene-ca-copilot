# A. Work log

Screenshots live in [`assets/worklog/`](assets/worklog/), named `stepNN_<topic>.png`. Paths in this table are relative to the repository root.

| Step | What you did | Input | Output | Tool or agent used | Screenshots |
|---|---|---|---|---|---|
| 1 | Read the brief, broke down requirements and hidden constraints, assessed feasibility of a GCP + Vertex AI + Cloud Run approach | Challenge brief (PDF) | Requirement breakdown, risk list (mainland China access to Cloud Run, over-engineering, cost abuse), decision to use a bounded workflow rather than a free-running multi-agent system | Claude Code | `step01_brief_analysis.png` |
| 2 | Invented the fictional brand and wrote its rules | Step 1 analysis | `brand/brand_guide.md` (assumptions, voice, red lines, six scenario playbooks, few-shot examples), `brand/brand_rules.yaml`, `brand/catalog.yaml` | Claude Code | `step02_brand.png` |
| 3 | Self-tested the rule checker against the good/bad examples in the brand guide | Brand guide examples, rule file | Found and fixed 2 regex defects: a correct refusal (「确实没办法打折」) flagged as a discount, and 「不一定保真」 not caught as disparaging daigou | Claude Code, Python | `step03_rule_test.png` |
| 4 | Set up the repository | Brand files | GitHub repository | Claude Code, GitHub | `step04_repo.png` |
| 5 | Drafted this submission framework | Brief's required elements | `SUBMISSION.md` | Claude Code | `step05_framework.png` |
| 6 | Designed and wrote the 50-case test set; rendered each conversation history as a WeChat-style screenshot | Brand guide, catalog, coverage matrix (B2) | `test_set/cases/*.yaml`, `test_set/cases.json`, 50 screenshots in `test_set/screenshots/`, index `test_set/README.md`; validator checks IDs, catalog references, colours, dates | Claude Code, Python, Playwright | `step06_test_set.png` |
| 7 | _TODO: build generation pipeline (incl. screenshot reading)_ | | | | |
| 8 | _TODO: run v1 on all cases_ | | | | |
| 9 | _TODO: evaluate v1 (rules + LLM judge + human review)_ | | | | |
| 10 | _TODO: fix defects, run v2_ | | | | |
| 11 | _TODO: deploy to Cloud Run, record demo_ | | | | |
| 12 | _TODO: architecture diagram, final write-up_ | | | | |
