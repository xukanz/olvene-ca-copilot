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

<facts>
$facts
</facts>

<calendar>
$calendar
</calendar>

$extra

## 写之前先想清楚（不要输出这一步）
1. 对话停在哪里？上一条是谁发的、隔了多久？
2. 客户有没有没被回答的问题或没被回应的情绪？有的话，每条消息都必须先回应它。
3. 现在发这条消息时机合适吗？需要多克制？
4. 每条用哪个真实的客户细节？（每条至少一个，除称呼外）
5. 按给定的三个角度分别写，确保三条读起来明显不同。
