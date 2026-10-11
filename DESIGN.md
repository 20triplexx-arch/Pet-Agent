---
name: "宠伴"
description: "柔白与莓果粉，完整猫狗插画陪伴清楚的日常照护。"
colors:
  ink: "#332f39"
  muted: "#6e6873"
  ground: "#fcfbfd"
  surface: "#ffffff"
  primary: "#995268"
  primary-hover: "#804056"
  berry-tint: "#f7e9ef"
  berry-soft: "#fbf4f7"
  green: "#436652"
  green-soft: "#e8f1eb"
  line: "#e8e3e8"
  control-line: "#978b99"
  danger: "#a13948"
  danger-soft: "#fff0f1"
  amber: "#865721"
  amber-soft: "#faf0df"
  sidebar: "#f6edf1"
  nav-hover: "#fff8fb"
  quiet-surface: "#f1eef3"
  danger-line: "#d099a2"
typography:
  headline:
    fontFamily: "\"Noto Sans SC Variable\", \"Microsoft YaHei\", \"PingFang SC\", sans-serif"
    fontSize: "clamp(26px, 2.2vw, 32px)"
    fontWeight: 650
    lineHeight: 1.4
    letterSpacing: "-0.025em"
  title:
    fontFamily: "\"Noto Sans SC Variable\", \"Microsoft YaHei\", \"PingFang SC\", sans-serif"
    fontSize: "20px"
    fontWeight: 600
    lineHeight: 1.5
  subtitle:
    fontFamily: "\"Noto Sans SC Variable\", \"Microsoft YaHei\", \"PingFang SC\", sans-serif"
    fontSize: "17px"
    fontWeight: 600
    lineHeight: 1.6
  body:
    fontFamily: "\"Noto Sans SC Variable\", \"Microsoft YaHei\", \"PingFang SC\", sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.7
  article:
    fontFamily: "\"Noto Sans SC Variable\", \"Microsoft YaHei\", \"PingFang SC\", sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 2
  label:
    fontFamily: "\"Noto Sans SC Variable\", \"Microsoft YaHei\", \"PingFang SC\", sans-serif"
    fontSize: "14px"
    fontWeight: 500
    lineHeight: 1.7
  action-label:
    fontFamily: "\"Noto Sans SC Variable\", \"Microsoft YaHei\", \"PingFang SC\", sans-serif"
    fontSize: "14px"
    fontWeight: 550
    lineHeight: 1.5
  meta:
    fontFamily: "\"Noto Sans SC Variable\", \"Microsoft YaHei\", \"PingFang SC\", sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.7
rounded:
  panel: "16px"
  control: "10px"
  message: "12px"
  badge: "7px"
spacing:
  space-1: "8px"
  space-2: "16px"
  space-3: "24px"
  space-4: "32px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
    typography: "{typography.action-label}"
    rounded: "{rounded.control}"
    padding: "9px 16px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
    textColor: "{colors.surface}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.action-label}"
    rounded: "{rounded.control}"
    padding: "9px 16px"
  button-secondary-hover:
    backgroundColor: "{colors.berry-soft}"
    textColor: "{colors.ink}"
  button-text:
    backgroundColor: "transparent"
    textColor: "{colors.primary}"
    typography: "{typography.action-label}"
    rounded: "{rounded.control}"
    padding: "9px 16px"
  field:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    padding: "10px 12px"
  panel:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.panel}"
    padding: "24px"
  badge:
    backgroundColor: "{colors.berry-tint}"
    textColor: "{colors.primary}"
    rounded: "{rounded.badge}"
    padding: "4px 8px"
  badge-green:
    backgroundColor: "{colors.green-soft}"
    textColor: "{colors.green}"
    rounded: "{rounded.badge}"
    padding: "4px 8px"
  badge-quiet:
    backgroundColor: "{colors.quiet-surface}"
    textColor: "{colors.muted}"
    rounded: "{rounded.badge}"
    padding: "4px 8px"
  badge-amber:
    backgroundColor: "{colors.amber-soft}"
    textColor: "{colors.amber}"
    rounded: "{rounded.badge}"
    padding: "4px 8px"
  nav-item:
    backgroundColor: "transparent"
    textColor: "{colors.muted}"
    rounded: "{rounded.control}"
    padding: "12px 16px"
  nav-item-active:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.primary}"
    rounded: "{rounded.control}"
    padding: "12px 16px"
  check-button:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.green}"
    rounded: "{rounded.control}"
    padding: "0"
    height: "44px"
    width: "44px"
  check-button-done:
    backgroundColor: "{colors.green-soft}"
    textColor: "{colors.green}"
    rounded: "{rounded.control}"
    padding: "0"
    height: "44px"
    width: "44px"
  feedback-error:
    backgroundColor: "{colors.danger-soft}"
    textColor: "{colors.danger}"
    rounded: "{rounded.control}"
    padding: "16px"
  feedback-success:
    backgroundColor: "{colors.green-soft}"
    textColor: "{colors.green}"
    rounded: "{rounded.control}"
    padding: "16px"
---

# Design System: 宠伴

## Overview

**Creative North Star: "精致轻松的宠物日常工作区"**

宠伴采用用户于 2026-10-11 确认的柔白与莓果粉视觉世界，柔和绿承载照护和完成状态。界面精致、轻松、可爱，同时让中文日常操作和阅读保持清楚。浅色工作区、白色面板、细边线与克制的状态色构成层次，完整的猫狗插画带来陪伴感。

品牌表达落在当前宠物的身份组合、统一图标和稳定的控件层级上。表单、记录、对话和知识使用适合各自内容的工作区；首页构图不扩展为全站模板。本文扫描已冻结前端，取代历史奶油棕规范，不引入新的视觉概念或营销布局。

**Key Characteristics:**

- 柔白背景、白色面板、莓果粉操作与选中态。
- 完整猫狗插画与紧凑宠物身份组合，不裁切身体。
- 本地中文可变字体，阅读正文 16px、辅助信息至少 13px。
- 平面分层，无环境阴影；细边线负责分组。
- 清楚的当前宠物、来源、专业边界、错误和保存状态。

前言令牌为规范值；提取依据为 `frontend/src/styles.css`、`App.tsx`、`components.tsx`、`pages.tsx`、`care-pages.tsx`、`hooks.tsx` 与 `icons.ts`。品牌授权来自 `PRODUCT.md`，页面表达与模式保留在 `.impeccable/surfaces/frontend-src-app-tsx.md`。侧车色阶仅用于设计面板预览，不是发布界面的新增调色板。

## Colors

莓果粉作为主要操作色，柔和绿表达照护状态，柔白和低饱和浅底让操作与长内容保持轻松。色值以顶部令牌为准；源码历史变量名 peach/orange 已映射为当前莓果体系，不代表旧世界仍在使用。

### Primary

- **莓果粉**（primary）：提交、保存、链接、选中导航、键盘焦点和光标。
- **深莓果粉**（primary-hover）：主按钮悬停及部分提示文字。
- **莓果浅色面**（berry-tint、berry-soft）：标签、选中宠物、用户消息及温和提示。

### Secondary

- **照护绿与浅绿**（green、green-soft）：完成标签、打卡、照护提示和体重趋势。
- **琥珀与浅琥珀**（amber、amber-soft）：源码 orange 标签所表达的到期状态，不能误解释为旧陶土主色。

### Tertiary

- **危险红与浅红**（danger、danger-soft）：错误、删除文字和紧急就医信息。
- **危险边线**（danger-line）：错误反馈与紧急消息的明确边界。

### Neutral

- **深灰紫正文 / 灰紫辅助字**（ink、muted）：主要文本与日期、单位、来源、补充信息。
- **柔白背景 / 白色面板**（ground、surface）：工作区和内容承载层；surface 也承担主按钮反白文字。
- **浅莓果侧栏 / 导航悬停底**（sidebar、nav-hover）：固定导航的分区和状态。
- **安静标签底**（quiet-surface）：模型模式等次级标签。
- **浅分隔线 / 控件边线**（line、control-line）：内容分组与可识别字段边界；两者用途不可互换。

**The 状态有文字 Rule.** 颜色与图标辅助辨认；完成、到期、暂停、演示模式和错误都保留明确文字，不能只用颜色传递状态。

## Typography

标题、正文、标签与控件共用本地 **Noto Sans SC Variable**，回退字族见前言。使用 Fontsource（5.3.1）提供的 unicode-range WOFF2（101 个分包），字体范围为（100–900），`font-display: swap`，`font-synthesis: none`，没有运行时字体 CDN。字体来源和 **SIL OFL 1.1** 许可证随包保存在 `frontend/public/assets/fonts/SOURCE.txt` 与 `LICENSE.txt`。

中文层级由字号、字重、行高和留白建立，不另设品牌展示字体或等宽字体。图标统一来自 **Phosphor React（2.1.10）**；`icons.ts` 的别名不改变图标家族。常见图标大小为（18–24px），具体随控件角色变化。

### Hierarchy

- **Headline**：普通页面一级标题，平衡换行；手机页面标题为（26px）。首页标题桌面为（28px）、手机（26px）、极窄屏（24px）。
- **Title / Subtitle**：普通面板二级标题与小节标题。档案身份标题（22px）、知识行标题（19px，手机 18px）、文章小节标题（21px）为已实现的局部覆盖。
- **Body**：默认界面正文；对话、知识摘要、记录正文和已保存计划依据均使用（16px）。对话和摘要行高（1.9）。
- **Article**：知识详情正文，最大行宽（70ch），段落和小节之间有清楚间隔，文章承载区最大宽（800px）。
- **Label / Action label**：字段标签与按钮分别使用既有字重；输入内容保持（16px）。辅助描述和紧凑操作可使用（14px），不将其替代主要阅读正文。
- **Meta**：日期、单位、来源、模式和字段错误等辅助信息的下限。体重图表使用实际显示（13px）的文字；ResizeObserver 将 viewBox 宽度对应到 CSS 宽度，图高（215px）。
- **数值**：体重当前值（28px、600），日期和部分数值采用 tabular-nums。

**The 阅读有基准 Rule.** 主要阅读正文使用 body 或 article，辅助信息不低于 meta；图表文字的实际显示尺寸也必须满足辅助字号，不能只检查 SVG 内部声明。

## Layout

桌面为固定侧栏（220px）与工作区，顶部宠物切换栏粘在顶部，最小高（64px）、内边距（8px 32px）。主内容最大宽（1184px），默认内边距（32px 40px 40px）；普通面板内边距由 panel 组件令牌定义。基本间距采用前言四级节奏，局部控件仍保留实际（4 / 12 / 20 / 40px）等覆盖，不能为整齐刻度改动既有布局。

普通双栏等宽、列间距（24px）；档案卡默认两列。首页今日照护与短问题为（1.8fr / 1fr）、列间距（32px），待办是横向列表，知识主题是单层入口。营养和医院分别使用（1.15fr / 1fr）和（1fr / 1.15fr）的工作区；知识列表采用有分隔线的行，详情转入阅读布局。具体页面策略保留在 surface brief，不推广成全局布局禁令。

| 已实现条件 | 布局行为 |
| --- | --- |
| 最大（1150px） | 主内容内边距为（32px 24px）；营养/医院工作区及档案卡变单列；聊天侧栏缩为（224px）。 |
| （768–1023px） | 导航缩为（80px）竖栏，图标仍带（13px）短文字；工作区左边距同宽。聊天变单列。 |
| 最大（899px） | 普通双栏变单列；首页照护/问题为（1.4fr / 1fr）、间距（24px）；登录两栏间距与内边距收紧。 |
| 最大（767px） | 侧栏隐藏，主内容（24px 16px 32px），面板（20px 16px）；首页、表单和聊天变单列。底栏为首页、AI对话、计划、知识、更多五项。顶部栏允许换行。 |
| 最大（370px） | 顶栏横向内边距（12px），首页宠物头像（56px）；待办状态允许另起一行，聊天辅助文字宽度进一步受限。 |

手机底栏最小高（72px），每项最小高（64px），底部内边距加入 safe-area-inset-bottom；页脚底部留白（96px + 安全区域）避开导航。更多使用原生 dialog、底部对话面板，包含档案、记录、设置；营养和医院由上下文入口到达。

聊天面板是有边界的纵向弹性容器：桌面高度（100dvh - 222px）、最小高（420px），手机高度（100dvh - 280px）、最小高（410px）。消息区独立滚动并保留 min-height: 0；打开历史或收到回复时定位最新消息开头。用户向上读历史时保留位置，出现“查看最新回复”入口。手机记录页将添加表单置于体重趋势前。登录从最大宽（1064px）的两栏转为最大宽（500px）的单列，手机只保留品牌与小型完整插画。

## Elevation & Depth

当前发布样式没有 box-shadow。层次来自柔白工作区、白色面板、浅莓果/浅绿状态底与（1px）边线。更多 dialog 的遮罩使用源码（rgb(51 47 57 / 0.32)），它是模态遮罩，不属于阴影。按钮包装器中没有生效的 Tailwind 阴影类不构成系统词汇。

**The 平面分层 Rule.** 延续现有无阴影的表面，用色差、细边线和间距形成层次。键盘焦点轮廓属于交互状态，不是环境阴影。

## Shapes

面板与控件分别沿用 panel、control 圆角；消息使用 message，标签使用 badge。品牌标记有局部（14px）圆角，更多 dialog 顶部采用面板圆角、底部贴边。边线一般为（1px），避免把所有控件都改为胶囊。

猫狗插画保持原比例与 object-fit: contain，完整保留耳朵、脚和尾巴。单只宠物头像使用独立素材，不裁切合照；其他物种使用爪印占位。现有三张 WebP 与逐图 `.webp.json` 来源记录保持不变：合照保留原生成 prompt，单只图记录 image_gen.imagegen 风格参考、透明背景、原始 PNG 路径和等比 WebP 转换。图像不是新配色规范的色值来源。

## Components

### Buttons

明确、柔和的操作控件。发布页面使用主按钮、普通按钮和文字按钮三类，具体颜色、字重、圆角和内边距见组件令牌。最小高（44px）、内容间隔（8px）；普通按钮边线为 control-line，悬停改为莓果边线与浅莓果底。主按钮悬停使用 primary-hover，文字按钮透明但沿用普通悬停反馈。禁用为（opacity: 0.55）及 not-allowed 光标。源码没有按压位移，不添加弹跳、缩放或新阴影。

按钮底色/边线与字段边线使用（160ms ease-out）过渡；焦点为（2px）莓果轮廓、偏移（3px）。prefers-reduced-motion: reduce 时全局关闭过渡、动画并把滚动行为改为 auto；当前没有循环动画。现有消息区 CSS 的 smooth 滚动被具体最新消息/编辑/错误定位的 instant 行为覆盖。

### Inputs / Fields

字段以白底、control-line 边线、明确标签承载内容，最小高（46px）；label 与输入间隔（8px），textarea 默认最小高（100px）、可纵向调整，聊天输入为（84–180px）。占位字使用 muted，不替代标签；焦点沿用全局可见轮廓，aria-invalid 使用 danger 边线。

API 422 保留 loc 与 msg，并在本次 form/panel 内匹配具名字段；Chat 明确使用包含提问和侧栏的共同范围。匹配到的错误直接显示在输入下方，使用稳定标签、aria-invalid 与 aria-describedby，定位并聚焦首个问题控件；新请求、成功或卸载后恢复原属性。profile 前缀及已实现的列表子项保持对应路径。跨字段、业务错误或没有匹配控件时仍保留总提示，不承诺任意错误路径都可逐字段映射。新增/编辑档案与计划将编辑区带入视口并聚焦首字段，取消后回到触发按钮。

### Chips / Tags

标签使用紧凑 badge 形状与明确文字，默认表示模式等身份信息；green、quiet、amber 分别表示照护/完成、次级模式、到期状态。它们是状态文本，不能在文档中改写为可点击筛选器。

### Cards / Containers

白色面板、轻分隔线、无阴影，内边距见组件令牌与手机覆盖。选中宠物面板使用 berry-soft 背景和 primary 边线；知识、记录、计划更多使用分隔行，不强行包装成重复卡片。空状态复用完整猫狗合照与真实空状态文字，不新增装饰素材。

### Navigation

桌面导航（14px），最小高（48px）、内边距（12px 16px），普通为 muted，悬停为 primary/nav-hover，选中为 primary/白底及（600）字重。平板保留图标和短文字；手机五项底栏使用（13px）文字，选中为莓果粉和 berry-soft 底。更多 dialog 通过 showModal 打开，支持 Escape、关闭按钮、点遮罩关闭和关闭后焦点回到更多按钮；扩展为桌面视口时关闭。

### Today task / Feedback / Sources

待办行用分隔线、任务文字、时间与状态组合，打卡按钮保持（44px × 44px）并用文字/状态说明完成结果；首页最多展示三项是页面规则，不是全局列表上限。错误反馈使用浅红、红色文字及边线，成功用浅绿和绿色文字；处理状态用浅莓果与辅助字，并分别保留 role=alert 或 role=status。

实际检索来源使用原生 details/summary 与外部链接，正文、来源机构和专业边界可辨认。知识详情保留来源、原文版本与未审核状态。侧车提供 10 个来自这些实际组件的独立 HTML/CSS 片段，无 React/Tailwind 依赖，图标内联为 Phosphor SVG；片段展示外观和 CSS 状态，不代替路由、提交或原生 dialog 的运行逻辑。

## Do's and Don'ts

### Do:

- **Do** 使用前言中的柔白、莓果粉、照护绿及对应浅底，沿用已有语义。
- **Do** 保留本地 Noto Sans SC、正文 16px、辅助至少 13px和统一 Phosphor 图标。
- **Do** 让猫狗完整显示，使用原比例与 contain；头像使用独立单只素材。
- **Do** 保留面板 16px、控件 10px圆角与 8 / 16 / 24 / 32 间距节奏，并尊重源码已存在的局部覆盖。
- **Do** 给操作提供清楚标签、可见焦点和文字状态，保持首个错误字段及编辑区可到达。
- **Do** 在手机保留五项导航与原生更多对话框，正文底部为安全区域和导航留出空间。

### Don't:

- **Don't** 恢复历史奶油棕、系统字族方案或七项手机底栏。
- **Don't** 将猫狗插画放大裁切、拉伸或在每个功能块重复装饰。
- **Don't** 给现有平面容器追加环境阴影、装饰性渐变或循环动效。
- **Don't** 把首页的双栏、最多三项待办或登录介绍构图当成每个页面的固定模板。
- **Don't** 用占位字代替字段标签，或让逐字段错误改变控件的可访问名称。
- **Don't** 把已验证场景推广为任意 422 映射、完整 WCAG 认证、真实浏览器 200% 缩放或原生 Safari 验收。
