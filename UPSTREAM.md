# 上游与改造
基线：https://github.com/fastapi/full-stack-fastapi-template/tree/0.12.0 （MIT，保留根 LICENSE）。
复用 backend/app/core/security.py 的 JWT 和 pwdlib 密码散列，frontend/src/components/ui/button.tsx 和 frontend/src/lib/utils.ts 的 UI 基础。
backend/app/api/deps.py 保留 OAuth2/session 依赖结构，适配 Python 3.13 和中文错误。
复用登录接口设计、React + Vite、SQLModel、Alembic、pytest、Playwright 工作方式；API 客户端为适合本 MVP 的 TypeScript 类型和集中请求层。
官方模板的 PostgreSQL、邮件、Traefik、示例 Items、云服务部署配置没有纳入本地运行路径。
业务实体、Agent、知识检索、提醒、七个中文页面和验收测试是本项目实现，不能靠上游模板直接获得。

