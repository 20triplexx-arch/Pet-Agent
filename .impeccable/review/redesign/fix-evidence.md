# F1–F4 单批修复证据

同一视觉方向与业务接口，未新增素材或修改后端。四项修复完成后构建一次通过；针对性桌面/手机 6 项通过（22.4 秒），最终全量 Playwright **36 passed（1.8 分钟）**。随后只补了计划阅读截图，两项编辑测试再次通过，应用代码未变。当前没有测试继续运行或覆盖截图。

| 发现 | 修复及验证 | 图片/数据 |
| --- | --- | --- |
| F1 图表辅助字缩小 | ResizeObserver 按 SVG 实际 CSS 宽度设置 viewBox，固定高度215px，轴边距44/16px，首尾日期采用 start/end 对齐。标签计算字体大小乘 getScreenCTM 垂直比例，两视口所有标签实际13px。两笔真实日期/体重，非虚构趋势。 | weight-readable-desktop.png、weight-readable-mobile.png；weight-font-desktop.json、weight-font-mobile.json；logs-*-full.png |
| F2 主要正文不足16px | 对话正文、知识摘要、日志标题/内容、保存计划依据/任务名称和营养任务说明统一16px，辅助元数据13–14px。浏览器检查对应实际元素16px，六宽度和等效缩放没有溢出。 | knowledge-desktop/mobile.png、logs-*-full.png、chat-latest-desktop/mobile.png、plan-readable-desktop/mobile.png；src/styles.css |
| F3 长对话定位 | 打开历史定位最后一条回答开头；发送后显示回复；用户在等待期间上滑阅读时不拉回，显示“查看最新回复”。以8条历史、两轮界面发送验证；阻塞第二轮响应，主动上滑后确认scrollTop保持0，点新消息入口定位回复。 | chat-latest-desktop/mobile.png、chat-unread-desktop/mobile.png；redesign.spec.ts“长对话…” |
| F4 编辑定位/焦点 | 共享useEditorFocus在展开后滚动到编辑区，聚焦首字段；取消后返回触发按钮。验证两宠物首卡编辑、新增档案，以及保存计划滚到编辑按钮后打开草稿与取消。 | edit-pet-desktop/mobile.png、edit-plan-desktop/mobile.png；redesign.spec.ts“档案与计划编辑…” |

新增修复证据均为1280×900桌面或390×844手机（DPR3），图片有效性遵循原图查看。其余同尺寸页面由最终全量测试重拍。图表手机因表单优先布局而滚动后截图；不是把全页或任意裁切冒充首屏。

素材来源复扫3个raster、0缺失。机械detector仍只执行原先一次，没有第二次运行。请仅评分F1–F4为resolved/partial/unresolved，写入verdict.md，并给出实际范围的最终disposition。
