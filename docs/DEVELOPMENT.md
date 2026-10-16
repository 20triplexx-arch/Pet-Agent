# 安装与开发

## 安装与启动

需要 Python 3.13、Node.js 24、npm 和 Git。在项目根目录运行 Windows PowerShell：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
powershell -ExecutionPolicy Bypass -File scripts/start.ps1
```

安装脚本创建 `.venv`、安装依赖、构建前端、执行数据库迁移并导入示例数据。已有 `.env` 不会被覆盖。默认演示模式不调用外部模型。打开页面后可注册自己的账户。

- 页面：<http://127.0.0.1:8000>
- API 文档：<http://127.0.0.1:8000/docs>
- `Ctrl+C` 停止服务；前端修改后运行 `scripts/start.ps1 -Rebuild`。
- 需要独立端口时用 `scripts/start.ps1 -Port 8013`；Linux/macOS 可设置 `CHONGBAN_PORT=8013`。
- 需要本地标签识别时，安装用 `scripts/setup.ps1 -WithOCR`。

Linux/macOS 提供 `sh scripts/setup.sh`、`sh scripts/start.sh`；本机验收主要使用 Windows。

## 前后端开发

安装完成后，在项目根目录启动后端：

```powershell
cd backend
../.venv/Scripts/python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

另一个终端启动前端：

```powershell
cd frontend
npm run dev
```

前端开发地址为 <http://127.0.0.1:5173>，通过 Vite 代理访问后端。模型、地图和 OCR 配置见根目录 [.env.example](../.env.example)，修改服务端配置后重启。凭证只供后端读取，不放入 `VITE_*` 变量。

## 测试

在项目根目录运行：

```powershell
cd backend
../.venv/Scripts/python.exe -m pytest -q
../.venv/Scripts/python.exe -m evals.runner --mode offline
cd ../frontend
npm run build
npx playwright install chromium
npm test
```

离线测试清空外部服务凭证。Playwright 使用独立测试数据库，默认端口 8011；占用时可设置 `CHONGBAN_E2E_PORT`。完整浏览器套件需要 OCR 依赖，桌面和手机尺寸均使用 Chromium。真实模型评测另受预算和免费额度检查，不能用离线通过率代表医学准确率。实际结果见 [TEST_RESULTS.md](../TEST_RESULTS.md)。

GitHub CI 使用 Python 3.13、Node.js 24，运行 Ubuntu 24.04 完整回归、Windows/Linux 全新安装及 Linux Docker 验证。`python scripts/verify_fresh_install.py` 会将源码复制到含空格和中文的全新隔离目录，执行安装、重复安装、合成操作与重启，不修改现有配置和账户库。基础安装不依赖 OCR。报告在 `artifacts/installation/`，保留隔离副本供诊断；上传 CI 证据时只收集指定日志和汇总，不上传运行库或配置。

容器验证通过 `python scripts/verify_container.py` 执行（先构建镜像 `chongban-ci`）。知识 ID 和迁移版本按当前源码核对，新增健康字段不会造成误报；失败先收集日志，再清理本次创建的随机容器与卷。

## 数据与升级

运行文件在 `backend/storage/`，包括 SQLite 数据库和 `.secret` 登录签名密钥；配置在根目录 `.env`。升级前停止服务并备份这两处，SQLite 的 WAL/SHM 文件如仍存在也一并保留。随后在根目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start.ps1 -Rebuild
```

启动时执行 Alembic 增量迁移并按 ID 导入当前知识，保留已有账户和业务记录。不要通过删除数据库或覆盖 `.env` 升级。数据库、签名、凭证及备份均不提交 Git。

修改数据模型后，在 `backend` 目录创建并审查迁移：

```powershell
../.venv/Scripts/python.exe -m alembic revision --autogenerate -m change
../.venv/Scripts/python.exe -m alembic upgrade head
```

当前主要使用 SQLite。PostgreSQL 配置和迁移路径已提供，尚未完成真实数据库迁移及集成验收。

## 知识与 Agent

知识文件在 `backend/data/knowledge*.json`，来源与覆盖范围见 [知识说明](KNOWLEDGE.md) 和 [来源目录](SOURCE_CATALOG.md)。修改单份资料后，可在 `backend` 目录导入；首次初始化使用 `scripts.init_db`，它会先登记品种并导入全部知识。

```powershell
../.venv/Scripts/python.exe -m scripts.init_db
../.venv/Scripts/python.exe -m scripts.import_knowledge data/knowledge_care.json
../.venv/Scripts/python.exe -m scripts.export_tools
```

检索采用本地 BM25，无需向量数据库。资料摘要未经兽医审核；增加其他物种需要补齐专属知识、风险规则和验收，不能只打开能力开关。

模型自由问答只读；保存计划、创建提醒和记录要求明确授权。用户与宠物范围由后端绑定，写入使用幂等键和事务。逐段回答、上下文及引用校验见 [STREAMING_CHAT.md](STREAMING_CHAT.md)，照护与医院工具见 [AGENT_UPGRADE.md](AGENT_UPGRADE.md)。

回答质量回归保留在 `backend/evals/answer_quality_regressions.json`。本轮同模型流式对照使用 `python -m evals.quality_compare`，固定基线 `8d8bfe7`；先运行 `--preflight-only` 核验免费余额及原共享预算。额度不足时不发起模型请求。审查方法、未达项及运行切换条件见[质量修复报告](evaluations/ANSWER_QUALITY_STEP2.md)。

## 容器与源码包

```powershell
docker compose up --build
docker compose exec app python -m scripts.init_db --demo
```

Compose 默认映射本机端口并用持久卷保存数据；本机尚未完成 Docker 实际运行验收。生产部署还需 HTTPS、备份、登录限流和监控。

运行 `python scripts/package_source.py` 生成 `artifacts/chongban-mvp.zip`；打包排除凭证、本机数据库、依赖和构建产物。
