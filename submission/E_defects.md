# E. Defects and next steps

## E1. Defects found and fixes

I reviewed all outputs in the first version and identify defects and corresponding fixes that should be added to the brand guide, the prompts, the code or the rule checks.

**Personalisation has to feel natural, not forced.** 

> **S1-01** before 「…您那条墨绿色的经纬丝巾，现在这个季节用刚刚好。」
> after 「…十一月的上海慢慢转凉了，您日常出门记得多添件衣裳。愿您度过一个温馨愉快的生日。」
>
> **S4-01** before 「今天在路上看到有人在手袋上系了一抹蓝色丝巾，一下子就想到了您。」
> after 「今天店里到了秋冬的雾霾蓝经纬丝巾，看到这个颜色就想起了您。记得您之前挑过湖蓝色的…」

**Care, not instructions.** .

> **S1-03** before 「…今天先放松一下，吃顿好的。」
> after 「David，生日快乐✨ 记得您月底要去跑杭马了，祝您备赛顺利，跑出好成绩。」
>
> **S1-04** before 「出门别忘了带上您那条暮紫色的披肩」 → direction: 「出门注意保暖」

**Sensitive situations.** 

> **S1-08** before 「…那条驼色披肩，一定陪伴了阿姨很多温暖时光。」
> after 「…知道您最近经历了很大的悲痛…」
>
> **S5-03** before 「…您周末带儿子打完球要是顺路，不如一起来坐坐。」
> after 「蔡先生，之前记得您对皮具养护挺好奇的，正好 12 月 19 号上午 10 点半，店里办了一场男士皮具保养工作坊。…」 (no companion named)

**A message is the next line of a conversation.** 

> **S3-01** before 「钱小姐，您那只奶白色的沙漏包，平时如果搭配深色牛仔裤背…」
> after 「钱小姐，沙漏包用了几天还习惯吗。突然想起您平时常穿牛仔裤…」
>
> **S3-05** before 「曹女士，看到您发来的照片了…」
> after 「曹女士，很抱歉昨晚没能及时回复。看到图片了…」

## E2. Future steps

**Speed**

* **Latency (~41 s median)** is too slow for live use. Most of it is Gemini 3.1 Pro thinking. Next: lower thinking level and stream the first candidate; Flash for simple greetings.

**Integrations: replace manual input with the brand's own systems**

- **Enterprise WeChat (企业微信) integration: import the conversation automatically.** CAs who use Enterprise WeChat can open the tool from the chat sidebar; with the client's consent and the brand's message-archiving permission, the tool reads the recent conversation directly, with exact timestamps, voice-to-text and who said what. This removes screenshots, and with them screenshot parsing errors such as invented timestamps on cropped images. The CA can still insert the chosen draft into the chat with one click; sending stays manual.
- **Brand website and CRM integration: purchase history, products and events.** Instead of typing the client profile and choosing IDs from a static catalog file:
  - **Purchase history** from the brand's CRM / e-commerce orders (online and boutique), so post-purchase care and reactivation know exactly what was bought, when, and its care needs;
  - **Product information** from the brand website / product information system: live price, colours, materials, craft facts, stock and lead times per boutique, which keeps every fact current and gives the fact checks one authoritative source;
  - **Event information** from the brand's events calendar: date, place, capacity, remaining places, companion rules and the guest list, so invitations only go to eligible clients and never promise a full event.
    These sources replace `brand/catalog.yaml` and the hand-filled profile; the rule that facts may only come from them stays the same.
- **Product selection.** With the full catalog connected, the tool can suggest which product to recommend (today the CA picks it): retrieve candidates by the client's history and preferences, let the model rank them, keep the CA's final choice.

**Running it for real**

- **Feedback loop:** log which candidate the CA picked and how they edited it (the UI already records the pick); use edited finals as retrieved few-shot examples per scenario and per CA.
- **Per-CA voice:** keep the brand frame, learn each CA's phrasing from their own sent messages.
- **Monitoring:** rule-flag and rewrite rates per scenario on live traffic, a sampled judge run every day, a weekly human review of the judge's disagreements.
- **Data and compliance:** client data and conversations must stay in China for a real deployment (Cloud Run here is outside China); consent for reading conversations; PII redaction before logging; access control by CA and boutique.
- **Send-time suggestions:** not only what to say but when (not late at night, not during the festival rush).
