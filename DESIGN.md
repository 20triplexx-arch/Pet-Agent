---
name: "宠伴"
description: "猫狗插画与温暖配色，让日常照护清楚、耐看。"
colors:
  ink: "#473b35"
  muted: "#73665d"
  ground: "#fbf8f3"
  surface: "#fffdf9"
  peach: "#f7e4d3"
  primary: "#ac4e2c"
  primary-hover: "#913e22"
  green: "#43634b"
  green-soft: "#eaf0e4"
  line: "#e6ded3"
  danger: "#a02f2b"
  button-foreground: "#fffaf5"
  button-line: "#d9cfc3"
  button-hover-surface: "#f4eadf"
  button-hover-line: "#bdab99"
  field-surface: "#fffefa"
  field-line: "#cfc4b8"
  field-placeholder: "#776b62"
  field-label: "#65584e"
  focus: "#628466"
  risk-surface: "#fff0e9"
  risk-line: "#d59b81"
typography:
  headline:
    fontFamily: '"Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif'
    fontSize: "28px"
    fontWeight: 700
    lineHeight: 1.5
    letterSpacing: "-0.02em"
  title:
    fontFamily: '"Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif'
    fontSize: "19px"
    fontWeight: 650
    lineHeight: 1.6
  subtitle:
    fontFamily: '"Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif'
    fontSize: "16px"
    fontWeight: 650
    lineHeight: 1.7
  body:
    fontFamily: '"Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif'
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.85
  field:
    fontFamily: '"Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif'
    fontSize: "14px"
    fontWeight: 400
  label:
    fontFamily: '"Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif'
    fontSize: "13px"
    fontWeight: 500
  action-label:
    fontFamily: '"Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif'
    fontSize: "13px"
    fontWeight: 550
  meta:
    fontFamily: '"Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif'
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.7
  article:
    fontFamily: '"Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif'
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 2
rounded:
  panel: "16px"
  control: "10px"
  content: "14px"
  icon: "12px"
  nav: "11px"
  badge: "7px"
spacing:
  control-gap: "8px"
  control-block: "10px"
  control-inline: "16px"
  field-block: "12px"
  field-inline: "14px"
  layout-gap: "22px"
  panel-padding: "25px"
  panel-mobile: "20px"
  section: "24px"
  page-inline: "36px"
  page-mobile-inline: "18px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.button-foreground}"
    typography: "{typography.action-label}"
    rounded: "{rounded.control}"
    padding: "10px 16px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
    textColor: "{colors.button-foreground}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.action-label}"
    rounded: "{rounded.control}"
    padding: "10px 16px"
  button-secondary-hover:
    backgroundColor: "{colors.button-hover-surface}"
    textColor: "{colors.ink}"
  button-text:
    backgroundColor: "transparent"
    textColor: "{colors.green}"
    typography: "{typography.action-label}"
    rounded: "{rounded.control}"
    padding: "10px 4px"
  field:
    backgroundColor: "{colors.field-surface}"
    textColor: "{colors.ink}"
    typography: "{typography.field}"
    rounded: "{rounded.control}"
    padding: "12px 14px"
  panel:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.panel}"
    padding: "25px"
  badge:
    backgroundColor: "#f6e6d4"
    textColor: "#854524"
    rounded: "{rounded.badge}"
    padding: "5px 10px"
  check-button:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
    padding: "8px"
    height: "44px"
    width: "44px"
  risk-feedback:
    backgroundColor: "{colors.risk-surface}"
    textColor: "#8e3e25"
    rounded: "{rounded.control}"
    padding: "15px 17px"
---

# Design System: 宠伴

## Overview

**Creative North Star: "温暖的日常照护日记"**

宠伴是供中文用户在桌面与手机上日常操作的本地宠物照护界面。用户已明确选择“猫狗插画与温暖配色，日常使用清晰耐看”。奶油白工作区承载阅读与填写，淡杏色承载猫狗陪伴感，暖棕文字和柔和绿色让任务、选择与反馈易于辨认。

可爱来自统一的猫狗绘本插画及柔和色面；操作区保持紧凑，标题、字段标签、时间、来源和状态文字承担信息层级。这里记录已实现的界面，不把首页欢迎区的构图推广成每个页面的模板。

**Key Characteristics:**

- 暖色纸面、轻边框与浅色分区。
- 猫狗插画形成持续的陪伴感，功能图标说明操作。
- 中文操作界面共用系统无衬线字族，正文与标签保持清楚。
- 宠物上下文、实际来源、保存状态与健康风险可见。
- 桌面侧栏、窄屏文字导航和手机底栏连贯切换。

依据：`frontend/src/styles.css`、`App.tsx`、`components.tsx`、`pages.tsx`及当前按钮组件；品牌约束来自 `PRODUCT.md`，首页表达来自 `.impeccable/surfaces/frontend-src-app-tsx.md`。前言令牌为规范值，源码是提取依据；本文件不替代独立的浏览器验收或评审结论。JSON 侧车的色阶仅为预览生成，未作为界面新增色值。

## Colors

色彩以奶油纸白、暖棕、淡杏和草木绿为主；深色用于文字与操作，浅色用于承载与状态分区。色值以顶部令牌为准。

### Primary

- **陶土橙**（`primary`）：提交、保存、生成计划及首页主要行动。
- **深陶土橙**（`primary-hover`）：主按钮悬停。
- **暖白按钮文字**（`button-foreground`）：主按钮的反白文字，不使用浅棕标签替代。

### Secondary

- **草木绿**（`green`）：文字操作、链接、字段聚焦边框及肯定状态的核心色。
- **浅草木底**（`green-soft`）：照护提示与勾选控件的浅色底。导航选中态使用源码已有的更深浅绿色，而非全屏铺满深绿色。

### Tertiary

- **风险红棕**（`danger`）：删除文字与紧急就医标题。
- **风险浅底与边线**（`risk-surface`、`risk-line`）：错误反馈和紧急消息。它们是语义提示，不扩展为普通装饰配色。

### Neutral

- **暖棕正文**（`ink`）：基础正文、页标题和普通按钮。
- **灰棕辅助字**（`muted`）：描述、单位、日期、状态补充。
- **奶油纸面与暖白面板**（`ground`、`surface`）：页面背景与内容承载层。
- **淡杏**（`peach`）：柔和陪伴色面；当前首页欢迎区使用源码已有的更浅淡杏（`--color-peach-soft`，`#fcf0e5`），保留全局淡杏令牌。
- **纸面边线**（`line`）：面板、分隔线和内容分组。
- **普通按钮边线与悬停底**（`button-line`、`button-hover-surface`、`button-hover-line`）：普通与文字按钮的状态变化。
- **字段底、边线、占位字与标签**（`field-surface`、`field-line`、`field-placeholder`、`field-label`）：字段内外的信息层级。
- **可见焦点绿**（`focus`）：键盘焦点轮廓。

### Named Rules

**The 状态带文字 Rule.** 色面与图标辅助辨认；已完成、已暂停、到期、演示模式和错误都必须有对应文字，不能只凭颜色判断。

## Typography

标题、正文、标签与控件共用已部署的系统字族；完整回退栈在前言中。没有另外部署品牌展示字族或等宽字族，也不把系统字族包装成展示字体方案。字号主要为固定像素值，当前没有比例字号公式。

### Hierarchy

- **Headline**：页面一级标题；紧凑手机页标题缩为（23px）。欢迎区标题有其独立字号，不作为普通页标题。
- **Title / Subtitle**：面板标题与小节标题。手机常规二级标题为（18px），页面特定标题覆盖仍以源码为准。
- **Body**：界面段落，辅助说明通常为（13px）；需要操作的字段使用独立的 `field` 角色，不能把段落行高强加给输入控件。
- **Label / Action label**：字段标签与按钮文字分别用现有字重区分；标签在字段上方，间隔（8px）。
- **Meta**：单位、日期、来源与补充信息；更紧凑的局部辅助字使用源码已有（11px），不推广为默认正文字号。
- **Article**：知识正文，最大行宽（70ch）；手机正文为（15px），继续保留宽松行距。
- **数值**：记录页当前体重使用等宽数字特性，为（30px、650）。

登录介绍标题在桌面为（34px、行高 1.7），窄屏为（28px），手机为（21px、行高 1.5）。这属于登录布局的实际覆盖，不新增全局 Display 角色。

### Named Rules

**The 操作字先清楚 Rule.** 插画与欢迎标题可以表达陪伴感，字段标签、正文、时间和风险文案继续使用操作界面的稳定层级。

## Layout

桌面固定左侧栏（228px），工作区留出同宽左边距；顶部栏最小高（80px），主内容最大宽（1320px），默认内边距（34px 36px 40px）。普通面板内边距采用 `panel-padding`，相邻面板的纵向距离采用 `section`；双栏与列表网格常用 `layout-gap`。这些是提取的用途值，不假设全部间距来自统一倍数刻度。

普通双栏为（1.2fr / 1fr），宠物及知识列表默认三列。首页单独保持今日照护优先的疏密关系，不将其构图推广到其他页面。

首页欢迎区为文字与右侧猫狗插画两列（minmax(0, 1fr) / 220px），列间距（24px），内边距（24px 32px），最小高（188px）。短标题下只保留当前宠物摘要，日期与档案入口另起一行；体重并入宠物摘要。欢迎区、照护区与底部健康提示之间的间距为（32px）。

今日照护与短提问区采用（minmax(0, 1.7fr) / minmax(240px, 1fr)），列间距（36px）。今日照护面板内边距（28px），到期待办最多预览三项，保留打卡控件、日期、周期和状态文字；“全部待办”进入完整列表，暂停与恢复操作留在完整列表。账户时区显示在可展开的提醒说明标题中，站内提醒范围在展开后读取。右侧为三条短问题与自由提问入口。照护知识为四个单层入口，图标与主题名称横向排列，不附副文案；底部保留一句就医提示和了解更多入口。

| 已实现的视口条件 | 布局行为 |
| --- | --- |
| 最小（1500px） | 主内容顶部间距（42px）。 |
| 最大（1150px） | 侧栏缩至（206px），主内容内边距（28px 24px）；普通双栏变单列，宠物和知识列表为两列。聊天仍有（225px）背景侧栏。 |
| 最大（1050px） | 首页今日照护在短提问区之前，改为单列；区块间距（32px），知识主题入口改为两列。 |
| 最大（850px） | 导航缩为（94px）图标加短文字竖栏，不能缩成仅图标；账户侧栏隐藏，设置页继续提供退出登录。聊天改为单列，照护背景移到聊天下方。 |
| 最大（600px） | 左栏变固定底栏，七项均显示短文字；高度为（72px + 安全区域）。顶部宠物切换栏粘在顶部，最小高（68px）。主内容内边距（25px 18px 23px），面板内边距改为（20px）；宠物、知识、表单变单列，首页主题入口保持两列。首页区块间距为（28px）；欢迎区内边距（22px 20px）、最小高（180px），右侧插画宽（104px），列间距（8px），欢迎标题为（23px）。日期与档案入口纵向排列，待办状态可另起一行。 |
| 最大（370px） | 内容横向间距（14px），宠物选择文字宽限制为（160px），标题区域允许换行。首页欢迎区内边距（20px 16px）、右侧插画宽（80px），欢迎标题为（21px）。 |

手机底部正文通过页脚的（96px + 安全区域）底部留白避开导航。

聊天是有边界的纵向弹性面板：桌面高度为（max(440px, 100dvh - 240px)），最大（740px）；手机高度为（100dvh - 250px），最小（340px）、最大（680px）。消息区可以滚动并具有（min-height: 0）；工具栏与输入区不收缩。不要恢复无限增长的聊天内容区。

手机照护记录页先显示添加记录表单，再显示体重趋势。登录页桌面为两栏、最大宽（1120px）；手机成为紧凑单列，插画缩至（104px）并置于介绍右侧，登录面板内边距（25px），保持字段和登录按钮易于到达。

## Elevation & Depth

当前系统不使用 `box-shadow`。深度来自暖白面板与奶油背景的色差、浅杏与浅绿分区，以及轻细边线。焦点轮廓是交互反馈，不是环境阴影。按钮包装器中未形成当前界面外观的额外变体不作为新的阴影或深度规则。

### Named Rules

**The 纸面分层 Rule.** 使用现有色面和细边线表达分组，延续当前面板无阴影的默认状态。

## Shapes

面板采用 `panel` 圆角，控件采用 `control` 圆角；消息与宠物插画容器共用更紧凑的 `content` 圆角，首页主题入口采用 `control` 圆角。图标小底采用 `icon`，标签采用 `badge`；导航默认采用 `nav`，手机缩为（9px）。圆形仅用于账户头像和小型记录标记，不把所有操作都变成胶囊。

面板与分组边线通常为（1px）；字段与普通按钮的边线更明确。猫狗插画保持原有比例；头像使用专用单只完整插画与 `object-fit: contain`，不能放大裁切合照或挤压图片，耳朵、脚和尾巴应完整显示。

## Components

### Buttons

亲切但明确的操作控件。主按钮使用陶土橙和暖白文字，普通按钮使用暖白底与暖棕文字；圆角与内边距以组件令牌为准，最小高度（44px）、内容间隔（8px）。文字按钮默认透明，绿色文字，悬停仍继承普通按钮的浅底和边线。

悬停改变底色与边线；点击时下移（1px），没有弹跳或装饰性缩放。禁用态为（opacity: 0.6）并取消活动反馈。当前发布页面实际使用主按钮、普通按钮及文字按钮三类，不将组件 API 中其他未呈现变体推广为现有设计语言。

### Inputs / Fields

字段使用暖白底、明确标签与细边框；最小高（46px）。输入内容和标签分开，保留现有占位字对比。聚焦边线变草木绿，键盘焦点轮廓为（3px）并向外偏移（4px），链接及按钮也必须保留可见焦点。

多行文本可垂直调整，常规最小高（96px）、行高（1.8）；聊天输入单独为最小高（82px）。错误由相邻文字反馈承担，没有提取新的“所有字段红框”规则。

### Chips

标签是信息状态，不是无文字装饰。默认为淡杏色；绿色用于已连接或当前上下文，灰纸色用于辅助信息，橙色用于到期。圆角与内边距按 `badge`。只有当前收藏筛选按钮等真实可操作控件才使用选中按钮外观，不能把静态标签误做筛选器。

### Cards / Containers

普通面板用暖白底、纸面边线及面板圆角。首页欢迎区使用淡杏底，今日照护是首页主要面板，短提问与底部就医提示保持轻量。待办与照护历史内部采用行分隔，避免层层套卡。宠物选中档案有绿色边线与浅绿纸底，并有“当前宠物”等文字状态。

### Navigation

桌面导航为图标加完整中文标签；悬停为稍深纸面，选中为浅绿底、深绿字和较重字重。窄屏和手机分别保留短文字“首页、档案、问答、知识、计划、记录、设置”，同时保留完整可访问名称。手机底栏七项均可到达。

顶部持续显示运行模式和当前宠物选择；未选宠物要明确显示“普通知识 · 未选择宠物”。账户信息和退出控件在窄屏侧栏隐藏后，退出登录仍由设置页提供。跳到主要内容链接在键盘聚焦时出现。

### Feedback / Empty / Loading

读取和处理中的反馈使用 `role="status"`，错误使用 `role="alert"` 并提供重试按钮；成功反馈用浅绿底、勾选图标和结果文字。长错误、昵称、邮件和记录内容允许换行。空态沿用猫狗插画，并说明下一步，如选择宠物或建立档案。

控件颜色过渡为（180ms ease-out），覆盖背景、边线与文字颜色。只有读取进度条使用（1.5s ease-in-out）往返动画；它说明等待，不作为装饰循环。减少动画偏好下关闭动画与过渡。

### 照护任务与聊天

打卡控件为（44px × 44px）方形圆角按钮，绿色用于悬停及状态外观；是否已完成仍以同排状态文字和完成历史为准。当前实现将暂停状态绑定到绿色勾选外观，本文件不将“暂停等于完成”确立为规范。保存与打卡显示实际请求结果；计划草稿明确“尚未保存”，预览和编辑后由明确保存按钮提交。

聊天助手消息为浅绿，用户消息为淡杏；用户消息桌面左缩进（15%）、手机为（8%）。正文保留换行，长文本可以折行。紧急消息加风险边线和“紧急就医提示”，实际来源链接在回答后显示，不生成占位来源或已审核标章。

### 猫狗插画

欢迎区、空态和登录使用 `frontend/public/assets/pet-companions.webp`，组件声明比例为（960 × 640）。猫在左、狗在右，柔和绘本质感、暖色轮廓与少量照护物件组成陪伴形象。头像分别使用 `pet-portrait-cat.webp` 和 `pet-portrait-dog.webp`（512 × 512），保留同一绘本风格，完整显示单只宠物和四周留白。装饰图片为空替代文本，宠物身份由邻近可读文字承担。

精确生成提示记录在各素材旁的 `.webp.json` 中，原始生成图保存在 `.impeccable/assets/`。独立头像由内置 imagegen 参考原合照生成，保留真实透明通道，经比例缩小转为 WebP。新增或替换栅格资源也必须保留真实来源记录，不能用通用功能图标放大替代已选猫狗插画。

## Do's and Don'ts

2026-10-10知识阅读补充：沿用已有配色与article-detail容器，正文使用四节以上的h2、p与ol，不在详情中显示原始Markdown标记。正文桌面16px/手机15px、行高2、最大70ch；分节间32px、h2字号20px/行高1.5/下间12px，列表项间8px。来源及未审核状态在独立来源区保留，列表只取首段作为三行预览。切换宠物同步知识物种，不增加一级导航或首页介绍卡片。

### Do:

- **Do** 使用前言令牌与现有组件角色，使暖白、淡杏、草木绿和暖棕文字保持连贯。
- **Do** 保留导航短文字、控件标签、可见键盘焦点和移动端安全区域。
- **Do** 让运行模式、当前宠物、日期与操作结果有明确文字；切换账户或宠物时更新对应上下文。
- **Do** 保留消息区内部滚动、稳定输入区、手机记录表单优先与紧凑登录布局。
- **Do** 按实际返回结果展示来源、保存成功和风险提示，并保留插画的来源记录。

### Don't:

- **Don't** 仅用颜色或绿色勾选区分暂停与完成，或把另一个账户、宠物的内容留作当前占位。
- **Don't** 用额外的标题前小标签、纯图标导航或放大的功能图标代替信息层级与猫狗插画。
- **Don't** 给当前纸面面板增加大面积阴影，或把待办和历史行重新套成多层卡片。
- **Don't** 把演示回答标成真实模型输出，把未经审核的知识标成兽医审核，或隐藏紧急就医提示。
- **Don't** 把预览草稿显示成已保存，或用装饰动画抢占照护操作的注意力。

