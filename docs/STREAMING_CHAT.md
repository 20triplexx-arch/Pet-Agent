# 宠伴逐段回答与阿里免费模型池

本轮实现日期：2026-10-15。真实验收结果以 `TEST_RESULTS.md` 和 `docs/evaluations/streaming-quality-speed.json` 为准。旧阶段记录保留在 `ALIBABA_CHAT.md`，不代表当前默认模型或额度状态。

## 服务端与浏览器

`POST /api/v1/chat/stream` 沿用 `ChatInput`、登录凭证及 `Idempotency-Key`。接受后返回 SSE：

| 事件 | 含义 |
| --- | --- |
| `accepted` | 已接受或命中成功重放，不代表已保存 |
| `section` | 一个完整 JSON 段落已闭合，来源、问题编号及已知边界检查通过；仍可能因整篇失败撤回 |
| `final` | 全文检查通过且数据库事务已提交，包含兼容的完整聊天结果 |
| `error` | 本轮失败，`retract=true` 撤销临时段落，未保存半截回答 |

源模型生成正文、问题编号和本轮证据编号。服务端从规范资料生成引用、章节原文卡及实际模型名，禁止模型自写来源链接。Pydantic 的部分 JSON 验证不能证明字符串或段落闭合，因此使用增量解码器。最终还检查干净结束、全部问题覆盖和完整结构。

`GET /api/v1/chat/status` 使用同一登录和幂等键，返回 `pending`、`complete`、`failed`、`canceled`、`unknown` 或 `not_found`；成功时携带原结果。原 `POST /api/v1/chat` 完整 JSON 接口保持。独立 SQLite 请求登记保证处理中相同幂等请求不再次调用模型，原业务幂等表继续保存最终结果。进程中断导致状态未知时不自动重新推理。

浏览器先显示用户问题，随后逐段展示正文和对应来源；保存、复制等最终动作在提交后出现。支持停止、手动重试与断线查询结果。切换宠物或离开页面会终止当前请求，旧请求回调不能污染新界面。阅读历史时不强制拉回底部；手机保留输入区及停止入口。

## 质量与上下文

档案事实、本轮补充、带日期的历史摘要和资料缺口分开传入。旧消息仅用于短追问及受保护的病史、过敏和兽医限制，不能把旧话题当成新问题。明确问题不再截成前三个；同文多问题合并章节，保留适用条件和安全边界，模型不重复接收全文。知识索引和章节解析按实际正文缓存。

证据充分的普通知识问答一次无工具模型请求；需要业务资料时仍使用 Agent，重复读取复用结果并收敛，不同查询可继续。不限模型/工具次数的本机设置保持。请求输出软深度：简短约100—200字、普通约200—450字、深入按需600—1000字；上限1024/2048/4096 tokens。DeepSeek 专用评测仍保留1800上限。

新旧模型路径共用引用、实际提供章节、健康和完整性检查。服务端拒绝无就绪计算支持的喂食克数/热量、未知绝育状态被写成事实、混淆肌肉与脂肪、已发现的护理禁忌和比例条件遗漏、无来源的固定时长等。所有这些都是有限模式检查，不能证明整段语义正确，更不能代替兽医审核。真实评测发现并拦截的问题与未达指标必须保留在报告中。

2026-10-16 增加已知字段与真实缺口汇总、章节到子问题的对应检查及高频错误回归。概念题和简单追问按本次信息量展开，保持深度软目标。新构建尚受免费预留阻止，未完成真实模型资格重审；当前结果及复测方式见[质量修复报告](evaluations/ANSWER_QUALITY_STEP2.md)。

## 免费池配置与授权

2026-10-16 起，`DASHSCOPE_FREE_MODELS=auto` 读取完整官方免费额度目录，不再只查询旧的四个名称。自动发现仅接纳通用千问 Flash/Plus/Max 家族及其版本；OCR、视觉、语音、Embedding、Coder 等专用模型不直接作为聊天候选。发现、免费余额与当前构建质量资格分别检查；目录中存在不等于自动启用。显式逗号名单继续作为服务端允许范围。最新模型筛选、实际启用及未达项见[免费池扩展报告](evaluations/FREE_MODEL_POOL.md)。

后端推理继续读取原 `DASHSCOPE_API_KEY`、`DASHSCOPE_WORKSPACE_ID`。显式 `DASHSCOPE_BASE_URL` 优先，否则使用北京业务空间地址，再退到北京公共地址。原 Key 不被 CLI 登录替换，任何凭证均不进入前端。阿里显式关闭思考；SDK/Agent 不自动重试。

官方 CLI 独立安装在 `.tools/bailian/2.3.0/bl.exe`，配置位于私有 `backend/storage/bailian-cli`，profile 为 `chongban-quota`。安装包来自官方清单并核对 SHA256；不修改系统 PATH。网页登录后先核对推理环境对应业务空间确实可访问，再读取每个具体模型及快照的免费余额、到期日和用完即停状态。

从 `backend` 目录执行：

```powershell
..\.venv\Scripts\python.exe -m scripts.refresh_alibaba_quota --enable-free-only
```

该命令只为仍有免费额度的模型启用“免费额度用完即停”，不会关闭开关或购买额度。服务端每60秒尝试刷新；默认快照超过180秒、凭证/业务空间不符或额度未知时拒绝新的真实调用。CLI 授权失效时需重新完成官方登录。

`DASHSCOPE_AUTO_SELECT=true` 时，未明确保存模型选择的会话默认使用 `alibaba-auto`。用户明确保存的选择继续生效。自动池只接受当前构建已质量核验、免费额度有效且用完即停为真的模型；资格清单与额度快照分开保存。模型代码、提示、检索和校验变更会使构建哈希不符，旧资格失效。手动固定的阿里选项也必须通过免费额度检查；DeepSeek 保持独立手动选择。

当前模型持续使用到额度不足；只有尚未展示正文且服务商明确返回 `AllocationQuota.FreeTierOnly` 时才尝试下一候选。鉴权、网络、内容错误及一般权限错误不触发切换。无合格候选时明确提示，不能偷偷转付费或其他服务商。服务端另行预留在途 tokens，并扣除控制台刷新延迟窗口；未知用量保留预留。

基础候选门槛：同集至少30例、完整交付场景比例至少90%、助手复核主要结论来源支持率至少95%、当前应用校验后的严重交付错误为零。原始生成错误和被拒绝场景完整保留。基础候选资格不等于“至少20改善且其余不退步”的整体质量目标通过，也不代表模型原始输出可靠或经过医学审核。此前仅38获得的资格属于旧构建，不自动沿用到新版。

候选名不是资格证明。37/38 Flash、37 Plus/Max 按官方能力使用 JSON Schema；36/35 Flash 及旧 Flash/Plus/Max 使用 JSON Object，服务端仍校验完整结构。旧 JSON 模式发送正文对象示例，避免模型回显字段定义。切换时按实际模型调整格式，思考和自动重试继续关闭。

## 计量与复现

客户端连接按事件循环、服务商、地址、Key摘要及超时复用，计量回调保留在请求私有代理上，避免并发串账。日志记录上下文准备、检索、模型请求、首 token、首个合格段落、生成结束、校验、提交阶段。浏览器实际等待另测，不能拿模型首 token 代替首段显示。

```powershell
..\.venv\Scripts\python.exe -m evals.streaming_compare --model qwen3.7-flash-2026-07-15 --count 30
..\.venv\Scripts\python.exe -m evals.streaming_compare --model qwen3.7-flash-2026-07-15 --variant paired --count 60
..\.venv\Scripts\python.exe -m evals.runner --mode offline
```

真实对照使用独立合成数据库、同一模型、同一固定输入，按 A/B、B/A 交错执行，最多同时两路。冻结基线保存在被忽略的 `artifacts/chat-streaming-baseline`，不覆盖。若比较qwen-flash，仅给基线加该模型所需的 JSON Object 能力接线，保持原提示、检索和Agent流程，另记录覆盖层哈希。所有失败均保留；成功耗时、双方成功配对、普通/深入、缓存命中/未命中分别统计。来源对照由助手逐项进行，明确区别于临床审核。

共享账本沿用 `backend/storage/evals/stage-one-budget.sqlite`，本轮ID `alibaba-chat-streaming-20261015`：请求前同一事务检查本轮3元和累计10元。价格取24小时内官方北京阶梯价，预算估算不使用免费或缓存折扣。旧费用和未决预留全部保留；未知用量不算零。保守金额不代表现金账单或实际余额。

部署前执行 `python -m scripts.snapshot_chat_upgrade --runtime-only` 备份运行数据和私有计量文件，不迁移业务库。分发 `.env.example` 保持演示。源码仓库和源码包均排除本机环境、数据、CLI授权、账本和运行日志。

## 官方依据

- [免费额度与用完即停](https://help.aliyun.com/zh/model-studio/new-free-quota)
- [官方CLI安装与授权](https://help.aliyun.com/zh/model-studio/cli/installation)
- [CLI额度查询](https://help.aliyun.com/zh/model-studio/cli/usage-quota)
- [流式输出及用量](https://help.aliyun.com/zh/model-studio/stream)
- [上下文缓存](https://help.aliyun.com/zh/model-studio/context-cache)
- [JSON结构化输出与支持模型](https://help.aliyun.com/zh/model-studio/qwen-structured-output)
