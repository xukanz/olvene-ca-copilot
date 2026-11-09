# Olvène CA Copilot

An AI tool that drafts three on-brand Chinese WeChat messages for luxury Client Advisors (CAs), across six scenarios: birthday/festive greetings, product recommendation, post-purchase care, reactivation, event invitation, and price objection.

The brand **Maison Olvène 欧薇恩** and all products, boutiques, events and clients in this repository are fictional.

## Brand foundation

| File | Purpose |
|---|---|
| `brand/brand_guide.md` | Brand assumptions, voice, personalization rules, red lines, per-scenario playbooks, few-shot examples |
| `brand/brand_rules.yaml` | Machine-checkable rules (hard-fail phrases and regexes, soft penalties, length and format limits) |
| `brand/catalog.yaml` | Fictional products, services, price policy, boutiques and events: the only allowed source of product facts |
