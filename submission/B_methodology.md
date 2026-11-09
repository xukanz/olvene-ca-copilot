# B. Methodology

## B1. Tool design

**Brand assumptions.** The full brand is in [`brand/brand_guide.md`](../brand/brand_guide.md) (v1.1); the parts that shape the tool:

- **Who:** Maison Olvène 欧薇恩, a fictional leather and silk house founded in Lyon in 1891 (handbags, small leather goods, silk scarves and shawls, some men's leather goods; ¥4,600 to ¥88,000+). Motto "慢一点，久一点": nothing is urgent, things are meant to last. Boutiques in Shanghai, Beijing, Chengdu, Hangzhou.
- **Clients:** age 30–55, buy for themselves and as gifts, quick to spot a mass message, prefer short messages. Segmented by relationship stage (初识 / 熟悉 / 挚交), never by spend, and the stage sets the tone.
- **Voice:** a knowledgeable, trusted friend, not a salesperson: warm, restrained, specific, leaves room. "您", short sentences, at most one exclamation mark, emoji only in greetings and invitations (a fixed set of six), no marketing formatting.
- **Pricing:** one national price, never discounted, no promotions or points. Prices differ abroad because of tax and exchange rates, which the CA may say once.
- **What a CA can offer instead:** free monogramming, lifetime basic care, a 48-hour hold, photos and videos, scarf-tying lessons, private appointments, home delivery for 挚交 clients.
- **Red lines** (§5): no discount hints or "let me ask my manager", no disparaging competitors, channels or daigou, no invented product or client facts, no false urgency, no spend, tier, age or health in a message.

**Input contract** (`POST /v1/generate`, [`api/schemas.py`](../api/schemas.py)). Example based on test case S6-02 (shown here with the conversation sent as screenshots; in the test set this case passes it as text):

```json
{
  "scenario": "price_objection",
  "client": {
    "name": "潘女士",
    "preferred_name": null,
    "gender": "F",
    "city": "北京",
    "relationship": "熟悉",
    "purchases": [
      {
        "product": "经纬丝巾 90 湖蓝",
        "date": "2025-03-01"
      }
    ],
    "preferences": [
      "奶白"
    ],
    "important_dates": [],
    "notes": "想要迷你沙漏包奶白色",
    "comm_style": null,
    "no_emoji": false,
    "last_interaction": "2026-11-08 微信"
  },
  "dialog_screenshots": [
    "<gs:// URI or base64 PNG>"
  ],
  "product_ids": [
    "P02"
  ],
  "event_id": null,
  "context": {
    "today": "2026-11-09",
    "occasion": null,
    "ca_name": "Kevin"
  }
}
```

| Field                         | Notes                                                                                                                                                                                                                                                                                                                          |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `scenario`                  | One of the six: `birthday_festive`, `product_recommendation`, `post_purchase_care`, `reactivation`, `event_invitation`, `price_objection`                                                                                                                                                                          |
| `client`                    | The profile fields from the brand guide §2. Only these facts may be used about the client                                                                                                                                                                                                                                     |
| Conversation                  | Any one of: `dialog_screenshots` (WeChat screenshots, the normal case), `dialog_text` (pasted text), or `dialog` (structured turns, e.g. after the CA corrected the parsed screenshot). Each turn: speaker, time, text, type (text, image, voice, sticker, recall) and, for voice, WeChat's voice-to-text `transcript` |
| `product_ids`, `event_id` | IDs in [`brand/catalog.yaml`](../brand/catalog.yaml). The tool pulls the facts (price, material, craft, colours, availability, event date, time, place, capacity, companion rule) from the catalog, never from the caller or the model                                                                                        |
| `context`                   | Today's date (drives festivals and conversation timing), occasion, CA name                                                                                                                                                                                                                                                     |

**Output:** three candidates, each with its angle, the message and a one-line rationale (which client detail it uses and why); the parsed conversation, summary, client mood and unanswered questions; flags for the CA (rule or reviewer notes, "client sent a voice message you should check", "client is upset: care mode"); model, prompt and brand version.

**Pipeline.** Four fixed steps; diagrams in [`architecture.md`](architecture.md).

1. **Read the conversation** (Gemini 3 Flash, multimodal). Turns screenshots into speaker, time and text, with placeholders for images, voice and stickers, and reads WeChat's voice-to-text. Also extracts the client's mood, whether they declined, and questions or complaints the CA has not answered yet. *Why:* CAs forward screenshots, and everything after this step depends on knowing who said what and what is still open. The result is shown in an editable table, so a misread can be corrected before generating.
2. **Assemble the context** (code, no LLM). Brand guide and rules, catalog facts for the given product or event, the client profile, the conversation, nearby festivals, and the **conversation state computed in code**: who spoke last, how many days ago, whether the client is waiting for a reply, whether the CA already used the client's name. Picks the three angles for the scenario, or switches to care angles (先回应情绪 / 解决问题 / 留白与尊重) when the client is upset or has declined. *Why:* facts and timing are where models go wrong; deterministic code gets them right and makes each run reproducible.
3. **Generate** (Gemini 3.1 Pro, one call, JSON schema). First a short plan (where the conversation stands, what must be answered first, timing), then exactly three candidates, one per angle. *Why:* one call that sees all three angles writes three different messages; three independent samples tend to say the same thing three times.
4. **Check, and rewrite only what fails.** L1 rules in code (forbidden phrases, discount wording outside a refusal, length, emoji, prices and event details against the catalog, no product in greetings or after-sales care, apology when the reply is late, copying the guide's examples, similarity of the three). L2 reviewer (Gemini 3 Flash): fabrication, pushiness, ignored questions, tone. A candidate with a hard rule failure, fabrication, pushiness or an ignored question is rewritten on its own with the reasons, at most twice; tone notes are only shown to the CA. *Why:* red lines that code can check should never depend on the model behaving; rewriting only the failing candidate keeps the other two and the latency.

## B2. Test set design

All 50 cases live in [`eval/cases/cases.yaml`](../eval/cases/cases.yaml), one block per case: client profile, conversation history (structured, as ground truth), product/event IDs from the catalog, the date "today", and per-case expectations (`must_address`, `must_not`). Every product, price and event in a case comes from [`brand/catalog.yaml`](../brand/catalog.yaml).

**Distribution**

| #  | Scenario                       | Cases        | 初识 / 熟悉 / 挚交 | No history | Input as screenshot |
| -- | ------------------------------ | ------------ | ------------------ | ---------- | ------------------- |
| S1 | Birthday and festive greetings | 8            | 2 / 4 / 2          | 1          | 5                   |
| S2 | Product recommendation         | 9            | 3 / 4 / 2          | 2          | 6                   |
| S3 | Post-purchase care             | 8            | 4 / 3 / 1          | 2          | 4                   |
| S4 | Reactivation                   | 8            | 2 / 5 / 1          | 3          | 3                   |
| S5 | Event invitation               | 8            | 1 / 5 / 2          | 2          | 6                   |
| S6 | Price objection                | 9            | 4 / 4 / 1          | 0          | 6                   |
|    | **Total**                | **50** | 16 / 25 / 9        | 10         | 30                  |

**Coverage dimensions.** Each scenario varies relationship stage, richness of the profile, the state of the conversation (none, warm, neutral, negative, complaint, read-but-no-reply), communication preferences (short, no emoji, English name, Chinese-English mixing, dialect) and one scenario-specific variable:

| Scenario | Scenario-specific variable                                                                                                                                                                            |
| -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| S1       | Birthday, birthday on 元旦, 春节, 中秋, 七夕, 圣诞; recent bereavement (S1-08)                                                                                                                        |
| S2       | Past purchase, gift for a parent with a budget, lifestyle, client said "not now", budget mismatch, client asks first, custom order, sparse profile                                                    |
| S3       | 3 days / 1 month / 1 year after purchase, gift purchase, stitching complaint (S3-05), belt too long (S3-07), first-time client                                                                        |
| S4       | 1 / 2 / 3 years silent, bad last experience (S4-04), moved city (S4-05), read-but-no-reply (S4-07), former 挚交 gone quiet (S4-08)                                                                    |
| S5       | All four catalog events; no plus-one but client asks to bring a friend (S5-02); client in another city (S5-05); declined last time (S5-06)                                                            |
| S6       | Too expensive, Hong Kong price, daigou, asks for 10% off, asks for a free scarf, competitor, silence after hesitating, harsh tone, 挚交 asks a second time "as an old client" via the manager (S6-09) |

**Edge and adversarial cases**

- Sensitive context: S1-08 (birthday a few weeks after the client's mother died)
- Complaint or negative history: S3-05, S4-04, S6-08
- Unanswered client question in the history: S2-02, S2-07, S3-02, S3-07, S5-02, S6-02
- Almost no information: S1-02, S2-08, S4-03, S5-08
- Event rules hidden in the data: S5-02 (no companion allowed), S5-05 (different city), S5-07 (companion allowed)
- Second discount push: S6-09; gift instead of discount: S6-05

**Conversation history as screenshots.** 30 cases also have their history rendered as WeChat screenshots ([`eval/render_wechat.py`](../eval/render_wechat.py), Pillow): green bubbles on the right for the CA, white on the left for the client, time separators, image, voice and sticker placeholders. Styles: normal 8, cropped 6, multiple images 6, heavy client emoji 4, group chat 3, blurry 3. S2-06 also shows WeChat's own voice-to-text box under a voice message. For these cases the tool receives only the screenshots, as a CA would forward them; comparing its reading with the structured history measures screenshot parsing separately from message quality. The other 20 cases pass the history as text.

**How cases were produced.** Drafted with Claude Code from the coverage matrix, checked automatically (unique IDs, catalog references, event dates after "today", screenshot cases have a history), and refined during the human review. 

## B3. Evaluation method

Every case is run end to end through the same pipeline as the live demo ([`eval/run_eval.py`](../eval/run_eval.py)), then scored in three layers:

1. **Automatic rule checks (L1)**, the same checker the tool uses before returning ([`api/pipeline/guardrails.py`](../api/pipeline/guardrails.py), [`brand/brand_rules.yaml`](../brand/brand_rules.yaml)): forbidden phrases and patterns, discount wording outside a refusal, length, punctuation and emoji limits, salutation and gender, prices and event dates and times against the catalog, scenario constraints (no product in greetings or after-sales care, no "come to the store" in reactivation), copying the guide's examples, conversation rhythm (apology when the client has waited a day or more), pairwise similarity. Results are reported **after** the tool's own rewrite loop, so this measures what a CA would actually receive.
2. **LLM judge** ([`eval/judge.py`](../eval/judge.py)): Gemini 3 Flash at temperature 0, a different model and a different prompt from the generator (Gemini 3.1 Pro). It receives the brand guide, the ground-truth history (not the tool's own reading of the screenshot), the computed conversation state, the catalog facts and the case's `must_address` / `must_not`. Per message: five 1–5 scores (rubric below), `red_line`, `send_ready`, and a comment. Per set: diversity 1–5. \
3. **Human review**: I read the outputs and annotated defects case by case.

**Weighted score** = 0.25 personalisation + 0.25 on-brand + 0.2 timing + 0.2 naturalness + 0.1 CTA.

**Grades per message:** *unacceptable* = any L1 hard fail or judge red line; *good* = send-ready and ≥ 4 on personalisation, on-brand and naturalness; otherwise *acceptable*.

**Rubric**

| Dimension            | 1                                  | 3                                       | 5                                                   |
| -------------------- | ---------------------------------- | --------------------------------------- | --------------------------------------------------- |
| Personalisation      | Generic, could be sent to anyone   | Uses a client detail, but superficially | Detail is specific and woven in naturally           |
| On-brand voice       | Salesy or template-like            | Polite but generic                      | Warm, restrained, specific — sounds like Olvène   |
| Timing and tact      | Intrusive or pushy                 | Acceptable                              | Leaves the client room; right weight for the moment |
| Naturalness          | Reads as a script                  | Mostly natural                          | Reads like a real CA typing on WeChat               |
| Call to action       | Pressuring or missing where needed | Present but clumsy                      | Low-pressure and easy to answer                     |
| Diversity (set of 3) | Near-duplicates                    | Different wording, same angle           | Three genuinely different angles                    |

## B4. What "good" and "not acceptable" mean

**Not acceptable** — any one of these fails the message:

- Promises or hints at a discount, private price, gift-in-lieu or "let me ask my manager"
- Disparages a competitor, another channel or daigou
- Invents product facts (price, stock, material, craft numbers, dates) or client facts not in the input
- Creates false scarcity or urgency
- Mentions spend, tier, age, health or other sensitive information; reveals "data" ("系统显示", "您已经 X 个月没来")
- Ignores a complaint or emotion in the conversation history
- Pushes a product in a birthday/festive greeting or a post-purchase care message
- Does not read like a WeChat message (too long, email-like, marketing formatting)
- Claims to have heard or seen content the tool cannot know (a voice message without transcript, an image)
- Mishandles a sensitive situation (grief, a complaint) or invites someone unsuited to the event

**Good:**

- Passes every hard rule
- Scores ≥ 4 on personalisation, on-brand voice and naturalness
- A CA would send it without editing
- The three candidates take genuinely different angles, so the CA has a real choice

**Targets for this submission** (results in D1): hard-fail rate after rewrites 0%; unacceptable rate 0%; send-ready ≥ 70%; mean weighted score ≥ 4.0; diversity ≥ 4. "Send-ready" is the closest proxy for the brief's goal: three drafts a CA can choose from and send.
