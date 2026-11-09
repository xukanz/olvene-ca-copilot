"""Public privacy notice (/privacy). Linked from the OAuth consent screen; no sign-in required."""
import streamlit as st

st.set_page_config(page_title="Privacy · Olvène CA Copilot", page_icon="🌿")
st.markdown("""
### Olvène CA Copilot · 隐私说明 / Privacy Notice

本网站是一个面试作品演示（demo），Maison Olvène 为虚构品牌，页面中的客户、产品和活动均为虚构。
This site is an interview demo. Maison Olvène is a fictional brand; all clients, products and events are fictional.

**我们收集什么 / What we collect**
- 通过 Google 登录获得的邮箱地址，仅用于识别登录状态和统计每日用量上限。
  Your Google account email, used only to keep you signed in and to count daily usage limits.
- 每个账号每天的使用次数（存储在 Google Cloud Firestore）。
  A per-account daily usage counter, stored in Google Cloud Firestore.
- 你输入或上传的内容（客户信息、对话、截图）会发送给 Google Cloud 上的 Gemini 模型生成话术；本站不长期保存这些内容。
  Text and screenshots you submit are sent to Gemini on Google Cloud to generate drafts; this site does not retain them long-term.
- 点击“选用这条”时，会记录所选话术，用于评估生成质量。
  When you pick a draft, the choice is logged to evaluate output quality.

**我们不做什么 / What we don't do**
- 不出售、不分享你的信息，不用于广告。 We do not sell or share your data or use it for advertising.
- 请不要输入真实客户的个人信息。 Please do not enter real customers' personal data.

**联系 / Contact**：请使用 Google 登录页上显示的支持邮箱。 Use the support email shown on the Google sign-in screen.
""")
