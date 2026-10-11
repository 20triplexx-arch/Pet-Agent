# 设计规范收尾记录

日期：2026-10-11。范围：仅刷新根 `DESIGN.md`、生成 `.impeccable/design.json`（schemaVersion 2）及本记录；未修改前端/后端/README/测试、未运行浏览器、未生成图片或调用付费工具。

## 授权与方法

用户已于 2026-10-11 批准全站替换为柔白、莓果粉和照护绿的新世界并同步更新设计规范。`PRODUCT.md` 的 Brand Commitments 和 surface direction contract 记录了该授权，已过时的奶油棕 DESIGN 被刷新，不再次发起世界或覆盖选择。本 documenter 为新鲜收尾角色，读取 impeccable `reference/document.md` 后使用 scan mode，描述语言直接沿用已确认的“精致轻松的宠物日常工作区”，没有发明新概念或营销布局。

## 检查的代码与资产证据

- `styles.css:3–35`：当前颜色、字体栈、panel/control圆角、8/16/24/32间距。侧栏、导航悬停、quiet标签及危险边线的重复组件字面值也按实际提取；旧 alias peach/orange 不等于旧世界色值。
- `styles.css:70–105`、`:126–220`：标题层级、辅助13px、focus-visible 2px/3px、字段46px、按钮44px、禁用0.55、160ms ease-out。body为16px/1.7；对话、摘要、记录及保存计划正文分别为16px，知识正文16px/2与70ch。
- `styles.css:244–459`、`:1605–2049`：220px桌面侧栏、80px平板短文字侧栏、64px顶栏、1184px主内容、1150/1023/899/767/370响应式条件、五项手机底栏、safe-area留白、reduced-motion实际规则。发布样式无box-shadow；more dialog遮罩为rgb(51 47 57 / 0.32)。
- `App.tsx`：跳到主内容、当前宠物select、模式文字、手机四个链接及更多按钮、原生showModal、Escape/关闭/遮罩行为、焦点返回，以及更多中的档案/记录/设置。
- `components.tsx:45–139` 与 `api.ts:146–166`、`hooks.tsx:67–108`：422保留loc/msg，当前form/panel或显式scope查找具名控件，profile前缀/列表路径匹配、稳定label/aria-describedby、输入下方错误、首控件焦点及属性清理；跨字段、业务或无匹配控件仍总提示。
- `hooks.tsx:3–27`、`pages.tsx:342/468/854/882/979`：编辑展开后滚动与首字段焦点、取消返回。`pages.tsx:1137–1209/1270–1387`：Chat共有scope包含侧栏分钟，历史/最新回复定位，用户上滑后新消息入口。`pages.tsx:1900–1934`：ResizeObserver和CSS宽度对应的体重viewBox，实际13px标签。
- `care-pages.tsx`：营养/医院实际工作区与具名输入、嵌套食物和计划字段、Feedback；没有新增一级导航。
- `icons.ts` 与 `package.json`：统一Phosphor React 2.1.10。片段SVG取自已安装包的regular Check/House/WarningCircle path。
- `frontend/public/assets/fonts/SOURCE.txt`、`LICENSE.txt`、`noto-sans-sc.css`：Fontsource Noto Sans SC Variable5.3.1、SIL OFL1.1、101个unicode-range WOFF2、100–900字重、swap、本地相对路径。
- `pet-companions.webp.json`、`pet-portrait-cat.webp.json`、`pet-portrait-dog.webp.json`：三个现有WebP的原prompt与来源。合照是原绘本插画，单只图以合照做风格参考、透明背景，来源记录包含原PNG与等比WebP转换；本轮未改图或来源文件。组件contain保持完整身体。

## 独立审查与验证范围

读取 `review.md`、`verdict.md`、`field-validation-review.md` 与 `field-validation-verdict.md`：初审F1–F4修复后均resolved、disposition ship；字段补审FV1修复后resolved、disposition ship。旧verdict中的“42项仍运行”是裁定时点记录，未改写它。

随后构建线程完成最终全量，`TEST_RESULTS.md` 与 `field-validation-evidence.md` 已记录 **42 passed（2.0分钟）**，桌面与iPhone13尺寸Chromium各21项；UI源码在裁定后冻结。本 documenter没有重跑测试，没有把42项测试替代设计审查。已支持档案、营养及Chat侧栏真实422的字段关联场景；不扩写为任意422映射。此前40项是中间阶段证据。

宽度验证为320/390/430/850/1280/1440px；所谓200%仅为1280→640 CSS有效viewport等效。没有真实200%浏览器缩放人工验证、原生Safari、真机或完整读屏/WCAG认证。文档保留这些边界，不提供认证措辞。

## 文档一致性检查

DESIGN使用token-bearing YAML frontmatter与八个canonical二级heading，固定顺序。schema允许的primitive只在前言出现，组件子令牌仅使用允许的八类属性；引用指向已定义令牌。sidecar为schemaVersion2，仅扩展color/typography metadata、预览色阶、空shadow词汇、实际focus/motion/breakpoints及10个可独立渲染的HTML/CSS片段，没有v1 tokens primitive数组。已有root CSS变量保持继承，片段有回退值、不依赖React/Tailwind；所有class以ds-前缀，图标内联SVG，没有img/外部包依赖。必要的input box-sizing只局限于该片段，保证独立画布上的字段宽度，不复制全局reset。

侧车northStar、overview、characteristics、三条rules及Do/Don't文本直接来自DESIGN，不另写语气。预览OKLCH色阶由hex合成、仅做预览，不冒充CSS已实现色阶。焦点与reduced-motion保留实际数值，没有编造阴影、按压位移或循环动画。

本次机械检查通过，错误数0：写入内容与生成稿一致；八个canonical二级heading顺序正确；20个颜色都存在于实际CSS；8个字体角色和17个组件令牌的引用均有定义；组件属性均在允许的八类中。sidecar JSON可解析、schemaVersion为2、没有v1 tokens或重复primitive组；20份预览色阶各8步；10个片段均有HTML/CSS、ds-类名前缀、有效refersTo（使用该字段的片段），没有React/Tailwind运行时、img、script或外部链接依赖。叙述、特征、三条规则及Do/Don't与DESIGN逐项一致；空shadow词汇与源码相符。未运行Stitch格式linter或浏览器渲染器。

## 限制

这是静态源码与既有审查/验收记录的文档提取；没有重新取computed styles，也未在浏览器打开sidecar渲染器。HTML/CSS片段独立且具备实际CSS状态，运行时提交、错误查找、导航和dialog逻辑由应用负责。未将页面特定构图或测试覆盖转成新的全局产品承诺。
