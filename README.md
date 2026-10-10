# 宠伴 · 本地宠物照护 Agent MVP

React + TypeScript / FastAPI / SQLModel + Alembic / SQLite / Pydantic AI。官方全栈模板 0.12.0 为基线，MIT 出处与实际复用见 [UPSTREAM.md](UPSTREAM.md)。已适配并验证 Python 3.13、Node 24，使用 npm 锁文件。

## 给后续模型的接续说明

本节是项目的长期交接记录，用于在新会话或上下文丢失后恢复背景。文档更新日期：**2026-10-10（Asia/Shanghai）**。后续工作应结合用户最新要求与当前代码；这里记录的是已经确认的选择和历史状态，不代表服务此刻仍在运行。

### 项目目标与已确认选择

- 项目名称为「宠伴」，面向准备养宠的新手和已有宠物的饲养者，完成“建档 → 问答与知识查询 → 计划预览与保存 → 提醒打卡 → 照护记录 → 根据新信息确认调整”的流程。
- 用户在比较开源项目并考虑成本后，选择 **FastAPI 官方全栈模板 0.12.0 + SQLite + Pydantic AI**。当前代码复用了部分认证和 UI 基础，其余业务为本项目实现，具体出处见 [UPSTREAM.md](UPSTREAM.md)。
- 本地 MVP 优先，首版完整支持猫和狗；其他物种目前仅支持档案与人工记录。鸟、龟、鱼等后续必须细分具体物种并补齐可靠资料。
- 默认是明确标注的演示模式，不要求模型密钥，不调用付费模型，不依赖云服务器、向量数据库或 Redis。真实模型通过独立适配层按需接入。
- 界面使用简体中文，覆盖手机和桌面。模型密钥在服务端配置；用户身份和工具数据范围由服务端登录上下文确定。

### 当前交付状态

已经实现七类页面：主页、宠物档案、AI 对话、知识库列表与详情、计划与提醒、照护记录、账户与设置。后端具备登录及用户隔离、多宠物 CRUD、知识搜索与收藏、独立会话、结构化计划、记录与体重趋势、时区提醒、事务及幂等保护。

项目还包含五个 Pydantic AI 工具、系统提示词、16 条有专业来源的知识摘要、可追溯风险规则、示例猫狗档案、Alembic 初始迁移、初始化与知识导入脚本、锁定依赖、环境变量示例、Docker 配置以及源码包 `artifacts/chongban-mvp.zip`。

**完整 MVP 验收日期是 2026-10-09**：后端 25 项、Playwright 桌面与手机共 12 项全部通过；TypeScript/Vite 构建、SQLite 实际迁移、PostgreSQL 离线迁移 SQL 和 Docker Compose 配置检查通过。**2026-10-10 页面重设计后，重新执行前端构建与桌面/手机 12 项浏览器回归，全部通过。** 本轮没有重新执行后端、迁移与容器验收。各轮证据与验证边界见 [TEST_RESULTS.md](TEST_RESULTS.md)。

尚未验证：真实服务商付费模型调用与质量、PostgreSQL 实机集成、Docker 镜像实际构建与容器运行、原生 Safari。项目没有上线，知识中文摘要与风险规则没有经过专业兽医审核。

### 接续时优先阅读的文件

| 文件 | 用途 |
| --- | --- |
| [README.md](README.md)、[TEST_RESULTS.md](TEST_RESULTS.md)、[UPSTREAM.md](UPSTREAM.md) | 已确认方案、启动方式、验收边界与上游出处 |
| [backend/app/models.py](backend/app/models.py)、[backend/app/schemas.py](backend/app/schemas.py) | 数据实体、请求结构及校验 |
| [backend/app/api/routes.py](backend/app/api/routes.py)、[backend/app/services.py](backend/app/services.py) | API、用户权限、事务、幂等和业务写入 |
| [backend/app/agent.py](backend/app/agent.py)、[backend/app/agent_system.txt](backend/app/agent_system.txt) | Agent 流程、风险优先、演示问答与五个工具 |
| [backend/app/model_adapter.py](backend/app/model_adapter.py) | 兼容模型接口、调用限制、来源检查及用量记录 |
| [backend/app/knowledge.py](backend/app/knowledge.py)、[backend/data/](backend/data/) | 检索扩展接口、知识、具体物种与风险资料 |
| [backend/app/clock.py](backend/app/clock.py)、[backend/migrations/](backend/migrations/) | 当地日历与 UTC 转换、数据库迁移 |
| [frontend/src/App.tsx](frontend/src/App.tsx)、[frontend/src/pages.tsx](frontend/src/pages.tsx)、[frontend/src/hooks.tsx](frontend/src/hooks.tsx) | 页面、统一宠物切换与加载/失败/重试状态 |
| [PRODUCT.md](PRODUCT.md)、[DESIGN.md](DESIGN.md)、[frontend/src/styles.css](frontend/src/styles.css) | 产品事实、已确认视觉风格与实际设计变量；后续页面应沿用 |
| [backend/tests/](backend/tests/)、[frontend/tests/care.spec.ts](frontend/tests/care.spec.ts) | 后端关键场景及真实浏览器验收 |

### 后续修改要保持的约束

1. 切换宠物时同步切换问答、计划、提醒和记录；其他用户的数据不能通过客户端参数或模型工具访问。
2. 知识与健康回答只引用实际检索的条目。资料不足要追问或说明，猫狗方法不能套用到其他物种。紧急风险在追问和模型调用前优先提示就医；健康回答不诊断、不自行开药或给剂量。
3. 计划先预览和编辑，明确保存后才写入。写入工具必须匹配用户明确指令与结构化载荷；工具失败不能报告成功。
4. 保留事务与幂等键：重试不重复创建，同键不同载荷返回冲突；宠物与用户权限由服务端校验。
5. 提醒采用 IANA 时区和当地日历，数据库保存 UTC，保留每个周期的完成历史。站内提醒不能描述为关闭应用后仍能收到的系统推送。
6. 延续本地低成本默认方案；新增模型服务、部署或物种支持时，以用户当前任务为准，并记录配置、资料和验证边界。

### 恢复工作与更新记录

接续时先阅读本节与用户最新要求，再定位相关源码。需要运行项目时使用下方启动命令并检查实际服务状态；当前数据库和本地签名密钥位于 `backend/storage/`，继续开发应保留已有数据，不重新建立整个工程。

后续可按用户目标推进真实模型评估、知识专业审核与扩充、PostgreSQL/Docker 实机验证及其他具体物种支持；这些是待完善方向，当前没有已启动或必须自动继续的开发任务。

**用户已明确要求：随着项目推进持续更新本 README。** 每次完成有实质进展的工作时，在交付前同步更新相关内容，不等到用户再次提醒。

- 更新文档日期、已完成功能、当前状态、已知问题和下一步待办；完成的待办及时移除或标记完成。
- 架构、依赖、接口、配置或启动方式发生变化时，同步修订对应章节，避免新旧说明冲突。
- 测试结果只记录确实执行过的检查、执行日期和未验证范围，并同步维护 [TEST_RESULTS.md](TEST_RESULTS.md)；代码变化后，旧的“全部通过”记录属于历史验收。
- 区分已实现、已验证和计划中的内容，不将待办写成完成状态；源码变动后如需重新交付源码包，也应重新打包。

## 本机启动

Windows PowerShell，在项目根目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
powershell -ExecutionPolicy Bypass -File scripts/start.ps1
```

打开 http://127.0.0.1:8000 ，接口文档 http://127.0.0.1:8000/docs 。Ctrl+C 停止服务。修改前端后用 `scripts/start.ps1 -Rebuild`。安装脚本使用项目虚拟环境；只有 Node 没有 npm 时，将 npm 11.6.2 下载到项目 .tools，不修改全局环境。

示例账号：**demo@example.com / Chongban2026!**。含猫“奶糖”、狗“豆包”、带日期的体重样本和站内待办。也可以注册独立账户；示例密码仅供本机体验。安装完成后不需要云服务器或模型密钥。

Linux/macOS：准备 Python 3.13、Node 24 和 npm，执行 `sh scripts/setup.sh`、`sh scripts/start.sh`。此路径提供脚本，当前验收环境是 Windows。

手动或前端开发：

```powershell
python -m venv .venv
python -m pip --python .venv/Scripts/python.exe install -r backend/requirements.txt
Copy-Item .env.example .env  # 已有配置时不要覆盖
cd backend
../.venv/Scripts/python.exe -m scripts.init_db --demo
../.venv/Scripts/python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
# 另一终端在 frontend 目录
npm ci
npm run dev
```

开发页面 http://127.0.0.1:5173 通过 Vite 代理访问后端。同源构建页面只需一个后端进程。已有本地依赖时可使用 `node ../.tools/package/bin/npm-cli.js run build`。

## 完整体验流程

1. 登录并在右上角选择宠物，或在档案页新增。未知项留空；生日优先于估计年龄，估计年龄记录估计日期并随时间推进。
2. 提问猫狗普通知识无需档案。选中宠物后，对话按用户和宠物分开保存；切换宠物会切换会话、计划、记录和待办。
3. 知识页按物种、主题或中文关键词筛选，查看真实来源与收藏。中文摘要未经兽医审核。
4. 在计划页设置可用时间，生成草稿，修改任务、时间、周期和依据，明确保存。保存会同步创建提醒。
5. 到期待办打卡，完成历史按每个周期单独保留。暂停/结束计划会暂停关联提醒。
6. 记录带日期的体重、饮食、活动、护理与异常观察。体重按发生时间取最新值并显示趋势。
7. 修改档案后重新生成草稿，或编辑原计划，确认更新。原任务的完成历史保留，原提醒暂停，不重复执行旧任务。

账户设置支持 IANA 时区。提醒保存 UTC，重复按创建时区的当地日历推进；账户时区改变仅改变显示，新提醒使用新时区。夏令时缺口中的新建时间会拒绝；模糊时间选择首次出现（fold=0）。重复任务遇缺口向后归一到有效时间。迟到打卡只标记当前显示周期，跳过的日期不伪造完成记录。未来任务不可提前打卡。

**站内提醒只在页面打开、刷新或手动刷新待办时显示。关闭应用不会收到系统推送。**

## 模型配置与成本

默认 `DEMO_MODE=true`。无密钥时，即使设为 false，也回退到明确标注的演示模式。演示模式采用真实检索、权限与工具路径和受控中文模板；不调用模型，不产生模型费用。

在根目录 .env 配置，重启后端：

```dotenv
DEMO_MODE=false
MODEL_API_KEY=服务商密钥
MODEL_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
MODEL_NAME=qwen3.7-flash
MODEL_MAX_REQUESTS=4
MODEL_MAX_OUTPUT_TOKENS=1800
MODEL_TIMEOUT_SECONDS=35
```

这是兼容 Chat Completions 的配置示例，模型名称和服务区域须以所选服务商实际可用项为准。独立适配层在 backend/app/model_adapter.py；Pydantic AI 的 OpenAIChatModel 使用服务端环境变量。任何密钥都不应放入 VITE_*、前端配置或提交到仓库。

SDK 自动重试关闭；每轮限制模型请求次数、工具次数、输入上下文和输出量，记录成功响应的 provider token 用量。真实费用需按服务商最新价格计算，失败请求也可能被服务商计费；当前应用用量统计不代表账单。当前未使用真实密钥做付费调用；兼容接口通过本地 HTTP 模拟响应验证。默认计划生成使用受控规划器，以保证依据和适用条件稳定，模型用于普通知识的自由问答。健康相关内容使用受控观察与就医准备模板，避免模型自行诊断或给剂量。

## Agent 与工具权限

系统提示词：backend/app/agent_system.txt；五个 Pydantic AI 工具：backend/app/agent.py；可审查 JSON Schema：backend/data/tool_definitions.json。运行 `python -m scripts.export_tools` 可重新导出。

服务端在模型调用与追问前识别紧急风险，并核对当前宠物档案和物种。紧急提示不调用模型，风险规则逐条关联资料 URL 与章节。药物/诊断问题采用受控就医准备提示，不给剂量；资料不足不让模型凭空回答。

工具 get_pet_profile、search_pet_knowledge 强制使用服务端上下文。save_care_plan、create_reminder、record_care_log 还需要明确写入授权及匹配的结构化载荷。模型不能设置 user_id/pet_id 或自己产生授权。模型自由问答只具备读取权限；明确保存草稿由服务端调度写入，人工保存/创建/记录接口调用同一工具实现。知识正文、档案与会话历史没有指令权限。

保存、记录、创建、打卡及聊天写入要求 Idempotency-Key。请求指纹包括操作和载荷；同键不同载荷返回 409。同用户同键重试返回已提交结果；业务记录与幂等记录在同一数据库事务提交，异常整体回滚。工具未提交或失败不会返回完成结果。引用从本次检索条目 ID 转换，未知引用导致回答拒绝并回滚；模型正文中的外部 URL 被移除。

对话支持完整明确指令，例如「记录体重 3.6kg」「记录饮食：食欲正常」「创建提醒：检查饮水；2026-10-10 08:00；每日」及对最新草稿说「保存计划」。当前记录使用本次时刻；历史记录请在记录页指定日期。不完整或模糊的指令会要求补充，不写入。聊天写入也先检查紧急风险；同草稿再次保存返回已保存结果。

## 知识导入与扩展

backend/data/knowledge.json 含真实专业来源的简短中文摘要：AVMA、Cornell、AAHA、AAFP/ISFM、Merck Veterinary Manual、Pet Poison Helpline。每条包含题目、正文、物种、阶段、主题、关键词、来源机构与 URL、发布日期或版本、收录/更新日期及审核状态。原页没有日期时明确保存为空，不猜测。

编辑 JSON，或准备相同结构文件：

```powershell
cd backend
../.venv/Scripts/python.exe -m scripts.import_knowledge data/knowledge.json
```

导入在验证所有条目后按 ID 更新，整批提交；来源必须 HTTPS，首版仅接受 editorial_summary_unreviewed，不能借用原机构审核状态标记中文摘要。新增鸟、龟、鱼、仓鼠资料必须细分物种，而非泛用大类。
species.json 维护支持范围；MVP 个性化检索/规划只允许 cat/dog。其他物种现在可存档案与人工记录。正式上线其他物种还需专业资料、风险规则、规划模板及验收测试。knowledge.py 的 Retriever 接口保留向量检索替换点，当前无需向量库、Redis 或额外云服务。猫的年龄资料筛选依据已收录的 AAHA/AAFP 2021 生命阶段定义，老年专属条目不会用于已知幼猫。犬的生命周期随体型差异较大，首版不据统一年龄阈值推断医疗阶段。

## 数据库与迁移

默认数据目录 backend/storage，包含 SQLite 和本地自动生成的 JWT 签名密钥（.secret）。可通过 SECRET_KEY 配置固定密钥。初始迁移在 backend/migrations/versions；SQLModel.metadata.create_all 仅用于测试，应用初始化实际执行 Alembic。

```powershell
cd backend
../.venv/Scripts/python.exe -m alembic upgrade head
# 修改模型后创建新迁移，检查生成内容，再升级
../.venv/Scripts/python.exe -m alembic revision --autogenerate -m change
```

PostgreSQL 配置路径：

```dotenv
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/chongban
```

配置后执行迁移和知识导入。SQLite 与 PostgreSQL 的初始迁移 SQL 已编译验证；本机没有运行 PostgreSQL 服务，**尚未做真实 PostgreSQL 集成测试或 SQLite 数据搬迁**。字段采用通用 JSON、外键和唯一约束，无数据库专属全文语法。SQLite 外键、WAL 和 busy timeout 已开启，适合本机小规模使用；更大并发应迁移 PostgreSQL。

备份前停止应用，将 storage 中数据库与 .secret 一起备份。原始密钥不保存到浏览器，登录 bearer token 存在当前标签页 sessionStorage。页面输出使用 React 转义；本 MVP 没有邮箱找回、邮件验证、社交登录或生产级登录限流。

## 测试与验证

```powershell
cd backend
../.venv/Scripts/python.exe -m pytest -q
cd ../frontend
npm run build
npx playwright install chromium
npm test
```

Playwright 自动启动 8011 隔离测试服务器，使用独立测试数据库和每场景独立账户，不改本机演示数据。桌面和 iPhone 尺寸都使用 Chromium。报告在 frontend/playwright-report，失败保留截图与 trace。后端测试覆盖原十个验收场景，并补充 DST、并发幂等、回滚、明确授权、虚构来源、模型接口与会话混用；测试结果与限制见 TEST_RESULTS.md。

## Docker（后续部署用）

```powershell
docker compose up --build
# 可选添加体验账号
docker compose exec app python -m scripts.init_db --demo
```

默认仅映射本机 127.0.0.1:8000，持久卷保存 SQLite，容器采用普通用户。运行配置可读取根目录 .env。Docker daemon 当前未启动，因此只完成 compose 配置检查，尚未实际构建运行。生产上线需 HTTPS、备份、登录限流、监控和独立配置；本次没有购买云资源或上线。

## 目录

```text
backend/
  app/          API、实体、业务事务、Agent、模型适配
  data/         物种、知识、风险规则、工具定义
  migrations/   Alembic 迁移
  scripts/      初始化、导入、工具导出、隔离浏览器测试服务
  tests/        后端关键场景
frontend/
  src/          七类中文页面、类型化请求层、UI
  tests/        Playwright 全流程与手机布局测试
scripts/        本机安装与启动
.env.example
Dockerfile
compose.yaml
LICENSE / UPSTREAM.md
```

## 已知限制

知识库是精简种子内容，没有专业兽医对中文摘要与风险规则进行审核；规则基于关键词，无法完整理解所有否定、过去时、错别字或紧急症状。没有命中规则不代表安全。健康问题需专业兽医评估。
演示对话用有限模板和短历史关键词承接，不能替代真实模型的理解。自由语言不会被自动当作写入授权；只有明确支持的保存/记录指令和页面操作执行写入，其他表达需要人工确认输入。
当前没有向量检索、系统推送、后台定时调度、文件/图像诊断、药物处方或其他物种专属照护。无密钥功能已验证，真实服务商质量与账单、PostgreSQL 和 Docker 实际运行仍需后续环境验证。

