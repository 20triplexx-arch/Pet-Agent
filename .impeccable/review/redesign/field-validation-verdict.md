# FV1 修复裁定

disposition: **ship**

实际范围：仅对 field-validation-review.md 的 FV1 做 verdict pass。**FV1：resolved。** 原 F1–F4 保持 resolved，不重新搜索其他问题。

## 1. 覆盖及证据有效性

核对 hooks.tsx 的 validationScope、Chat 的 chatRootRef 与 send 调用，以及 redesign.spec.ts 的真实后端错误恢复测试。逐张以 detail original 查看 field-errors-chat-verdict-desktop.png、field-errors-chat-verdict-mobile.png：桌面 1280×900，手机 1170×2532（390×844、DPR 3）。两图均是错误定位后的真实视口，分钟输入、错误文字和焦点清楚，证据有效。

本轮固定副本不会被后台全量测试覆盖。reviewer 没有启动浏览器、测试或 UI 修改。

## 2. 方向与完成度

useAction.run 可接受明确控件范围。Chat send 指定 .chat-layout 的引用，包含提问表单及照护侧栏；其他调用继续以各自 form/panel 为范围。修复直接补齐原验收门槛，没有改变设计方向、接口或增加素材。

## 3. 质量与功能风险

提供的针对性桌面/手机两项测试已通过（8.4 秒），构建通过。测试实际发送 available_minutes=1，未 mock 此 422，随后修改为 30 再发送并得到真实演示回复。先前 40 项全量已通过；本裁定时新的 42 项全量仍在运行，因此不报告其已通过。

不对应可编辑控件的路径、跨字段及业务错误仍保留总提示，这一边界不扩写为任意 422 都有字段映射。

## 4. 原发现评分

| 编号 | 评分 | 验收结果 |
|---|---|---|
| FV1 对话侧栏字段未进入关联范围 | **resolved** | Chat 显式控件范围包含 name=available_minutes 的侧栏输入。两视口的真实 422 验证该输入取得 aria-invalid、对应 accessibleDescription 及焦点，失败时没有回答。原尺寸截图显示提示就在分钟输入下方。修改为 30 后得到一条真实回复、逐字段提示消失、aria-invalid 清理；Feedback 的属性恢复逻辑继续保留。 |

## 5. 最终处置

**ship：FV1 已 resolved。** 字段关联专项中已确认的档案、营养及对话场景均支持交付；原 F1–F4 保持已解决。该 finding 无需追加修复或截图轮次。最终全量回归结果由构建线程另行记录，本裁定不代替其尚在运行的结果。
