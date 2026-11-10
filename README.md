# 慢慢说 · 情感陪伴 Agent

根据 [技术计划](docs/technical-plan.md) 实现的首版开发工程：Flutter Android 客户端、FastAPI API、独立 Worker、PostgreSQL 17 / pgvector。界面明确标识 AI；照片仅用作头像。

已实现验证码开发登录、头像清洗与私有短时地址、人物风格和授权例句、隔离试聊、文字聊天、会话历史、停止与重试、可回放 SSE、候选记忆确认/编辑/移除、资料导出、异步清除全部聊天与记忆。默认模拟模型不调用付费服务，可切换百炼模型。

## 用 Docker 启动

在项目根目录的 PowerShell 中执行；需要 Docker Desktop 的 Linux 容器引擎：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start-dev.ps1
```

脚本首次生成忽略提交的 `deploy/.env.local` 和独立随机密钥，构建后端镜像，等待数据库，单独执行 Alembic 迁移，再启动 API 和 Worker。打开 [交互接口文档](http://127.0.0.1:8000/docs)。登录接口 `POST /v1/auth/otp/request` 在开发环境返回 `development_code`，用于下一步验证码验证；它不会发送真实短信。

```powershell
# 观察任务处理
docker compose --env-file deploy/.env.local -f deploy/compose.app.yml logs -f api worker
# 停止，保留数据库与照片
powershell -ExecutionPolicy Bypass -File scripts/stop-dev.ps1
```

API 和 Worker 启动后，可在 `backend` 目录运行 `uv run python ../scripts/smoke.py`，验证登录、独立 Worker 回复、记忆确认和清理闭环；该脚本只接受模拟模型模式。

数据库不发布到宿主机。API 默认仅监听本机；真机访问时可在 `.env.local` 将 `API_BIND` 改为 `0.0.0.0`，并配置局域网防火墙。此 Compose 是本地开发配置。

## 运行 Android 客户端

安装 Flutter stable（Flutter ≥ 3.47、Dart ≥ 3.13）、Android SDK 和 JDK 17，然后：

```powershell
cd mobile
flutter pub get
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000
```

模拟器通过 `10.0.2.2` 访问电脑。真机使用电脑的局域网地址。HTTP 仅用于 debug，release 强制 HTTPS。Android 平台工程和 Gradle wrapper 已包含；发布签名需另行配置。客户端说明见 [mobile/README.md](mobile/README.md)。

## 在本机开发后端

需要 Python 3.12、uv 和 PostgreSQL 17 / pgvector；也可只启动 [数据库 Compose](deploy/compose.infra.yml)。迁移由 Alembic 执行，Compose 不再通过初始化 SQL 创建业务表。

```powershell
Copy-Item deploy/.env.example backend/.env
# 编辑 backend/.env 的 DATABASE_URL，连接实际数据库。
cd backend
uv sync --frozen
uv run alembic upgrade head
uv run python -m app.main
# 在另一个终端，同样进入 backend：
uv run python -m app.worker
```

`python -m app.main` 和 Worker 均处理 Windows psycopg 的 Selector 事件循环要求。原生 API 默认监听 `127.0.0.1:8000`，可通过 `API_HOST` / `API_PORT` 修改。令牌、手机号密钥和模型密钥仅保存在服务端。当前锁文件的依赖源为阿里云 PyPI 镜像；如需改回官方源，执行 `uv lock --default-index https://pypi.org/simple` 后同步。

旧目录若曾通过 `docs/schema.sql` 初始化数据库，请先备份，并核对现有表、索引和约束与 `backend/migrations/versions/0001_schema.sql` 一致，再执行 `uv run alembic stamp 0001`。不要直接在有业务表的旧数据库重复运行初始迁移。

## 接入百炼

在实际使用的服务端 `.env` 中设置：

```dotenv
PROVIDER_MODE=live
DASHSCOPE_API_KEY=你的服务端密钥
LLM_BASE_URL=从百炼控制台复制的兼容接口根地址
LLM_MODEL=qwen-plus
```

重启 API 和 Worker。Key、工作空间和地域必须匹配；云适配器要求 HTTPS。运行模式为 `live` 时，路由、生成、检查、记忆抽取与向量化会产生实际请求。模拟向量与真实模型向量使用不同命名空间，不混合比较；切换模式后，可通过编辑并重新确认已有记忆触发新模型索引。

## 验证

后端单元测试 `cd backend; uv run pytest -q`；数据库相关用例在没有 `TEST_DATABASE_URL` 时明确跳过。完整测试使用独立真实数据库，测试名必须以 `_test` 结尾；测试会清空该数据库的业务数据：

```powershell
docker compose -f deploy/compose.test.yml up -d --wait
$env:TEST_DATABASE_URL='postgresql+psycopg://companion_dev:companion-test-local-only@127.0.0.1:15484/companion_test'
$env:DATABASE_URL=$env:TEST_DATABASE_URL
cd backend
uv run alembic upgrade head
uv run pytest -q
uv run ruff check .
```

测试覆盖重复/并发提交、单会话活动任务、账户隔离、SSE 回放、取消重试、Worker 失联与租约 fencing、旧向量写回、清除资料隔离、图片清洗、模型协议故障和输出检查。客户端运行 `flutter analyze` 与 `flutter test`。具体执行结果见 [实施与验证记录](docs/implementation-status.md)。

## 当前范围

这是可本地验证的首版工程。语音识别与朗读、OSS、真实短信、值守联络、上线监控、备份恢复和真机试点仍属于后续任务。风险输入使用受控回应和内部记录，不会声称已联系家属或救援。生产启动会拒绝开发验证码和模拟供应商，当前必须先接入真实短信服务才能开放生产环境。

模型输出检查由规则和模型复核组成，仍需固定案例与目标用户评测。尚未完成真实云端调用、4 并发 100 轮性能验证和 200 案例人工评测；目标机型及正式 APK 的验收结果以验证记录为准。
