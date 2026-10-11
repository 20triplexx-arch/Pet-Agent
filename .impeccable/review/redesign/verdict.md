# F1–F4 修复裁定

disposition: **ship**

实际范围：对 review.md 中四项 material findings 的 verdict pass。四项均为 **resolved**；本次没有重新执行全站缺陷搜索，也不将此结果扩写为“全站不存在任何问题”。

## 1. 覆盖及证据有效性

读取 fix-evidence.md、原 review.md、direction contract，核对 pages.tsx、hooks.tsx、styles.css 及 redesign.spec.ts 的对应实现和验收断言。逐张以 detail original 查看 weight-readable、chat-latest、chat-unread、edit-pet、edit-plan、plan-readable 的桌面/手机图，以及知识首屏和记录全页图。

新增桌面 PNG 均为 1280×900；手机为 1170×2532，对应 390×844、DPR 3。记录全页为桌面 1280×1672、手机 1170×6924，从文档顶部开始。编辑、最新回复、体重可读性与计划阅读图是完成指定动作后的真实视口；手机体重图和计划阅读图已滚动，未作为页面首屏使用。图名与内容对应，图表、回复入口、编辑区和焦点可见，无需 recapture。原审查中默认查看导致的疑似缺绘及撤回记录继续保留在 review.md。

## 2. 方向与完成度

修复保留已批准的柔白、莓果粉、照护绿、猫狗身份、导航和任务组织。没有新增素材或改变布局方向。正文与图表可读性已落实原先的 16px 正文、至少 13px 辅助字承诺；动态定位补全了原布局的操作路径。

## 3. 质量与功能风险

视觉结论来自原尺寸图片和源代码，并以对应行为断言补证。fix-evidence.md 提供构建成功、针对性 6 项通过、最终全量 36 项通过，以及仅补计划截图的 2 项再次通过；没有把测试总数当作视觉通过证明。本 reviewer 未启动浏览器或重新运行测试。素材复扫为 3 个、0 缺失，detector 未重复运行。

字段错误边界另行说明：required/min/max 等浏览器约束可定位对应输入；api.ts:136–140 将服务端 detail 数组合并为消息字符串，Feedback 在 components.tsx:53–56 以总提示展示。现有证据不支持“所有 API 422 字段错误均已关联对应字段”的表述，该能力不在 F1–F4 的修复评分范围内。如果原实施方案将通用服务端字段映射列为验收项，则该项应明确记录为未完成，不能用原生约束验证替代。

## 4. 原四项评分

| 编号 | 评分 | 核对结果与证据 |
|---|---|---|
| F1 图表标签缩小 | **resolved** | pages.tsx:1868 起按 ResizeObserver 测得的 CSS 宽度设置 viewBox；styles.css 保持图高 215px、文字 13px。两份 weight-font JSON 的全部标签实际均为 13px，断言乘入 getScreenCTM 的显示比例。桌面/手机原图中坐标、日期可读，首尾日期对齐留足边距；真实记录日期和数值保留。 |
| F2 主要正文不足 16px | **resolved** | .message-text、.article-excerpt、.journal-row p、.saved-plan p 已为 16px，计划任务名称和记录标题也保持 16px。对话、知识、记录和保存计划的实际内容截图可读，辅助时间与来源仍有层级。针对性断言检查对应元素 16px；证据包报告六宽度无新增横向溢出。 |
| F3 长对话定位 | **resolved** | pages.tsx:1114 起保留消息区引用，历史/新回复定位最后一条消息开头。用户在等待期间上滑时保留位置，显示“查看最新回复”，点击后定位回复。测试覆盖 8 条历史、两轮发送和阻塞响应期间主动上滑，验证位置保持与入口消失；chat-latest/chat-unread 两视口截图与这些状态一致。 |
| F4 编辑定位及焦点 | **resolved** | hooks.tsx:3 的 useEditorFocus 在布局提交后滚动编辑 section、聚焦首字段，并保存触发按钮供取消后恢复。档案新增/编辑和保存计划编辑均接入。edit-pet/edit-plan 桌面与手机图显示标题在顶栏下方、首字段焦点清楚；测试覆盖两宠物首卡编辑、新增档案、滚到保存计划后编辑及各自取消返回。 |

## 5. 最终处置

**ship：原 F1–F4 四项均 resolved。** 不需要再为这四项追加修改、截图轮次或 detector。可以继续 DESIGN.md、.impeccable/design.json 和交付打包步骤。向用户报告时应表述为“四项审查修复已通过复核”，并保留上述服务端字段错误关联的实际边界；本 verdict 不提供全站无障碍认证或所有接口错误映射通过的结论。
