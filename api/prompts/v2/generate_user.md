## 任务
场景：$scenario_label（$scenario）
今天：$today$occasion_line
CA 的名字：$ca_name

三条候选的角度（按顺序）：
$angles

$special_instruction

<client>
$client
</client>

<dialog>
摘要：$dialog_summary
客户情绪：$client_sentiment
客户尚未被回应的问题/情绪：$open_questions
记录：
$dialog
</dialog>

<dialog_state>
$dialog_state
</dialog_state>

<facts>
$facts
</facts>

<calendar>
$calendar
</calendar>

$extra

## 写之前先想清楚（不要输出这一步）
1. 看 <dialog_state>：要不要以称呼开头？要不要先为回复晚道歉？
2. 客户有没有没被回答的问题或没被回应的情绪？有的话，每条消息都必须先回应它。
3. 现在发这条消息时机合适吗？有没有敏感情境（哀伤、投诉、拒绝）？需要多克制？
4. 每条要不要用客户细节、用哪个？只用此刻自然会想到的，宁缺毋滥。
5. 按给定的三个角度分别写，每条先承接再展开，确保三条读起来明显不同。
6. 写完读一遍：像真人 CA 在微信上打的字吗？有没有对客户下指令、刻意提商品、声称知道语音内容？
