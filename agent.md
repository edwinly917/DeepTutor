# agent.md

## 目的

本文件面向在本仓库内工作的代码代理，目标不是介绍项目，而是约束执行方式，减少误改、漏改和跨层不一致。

本文件基于当前代码扫描结果编写，适用于这个仓库当前的实际结构。

## 优先级

执行时遵循以下优先级：

1. 用户当前明确指令
2. 仓库中的 `AGENTS.md`
3. 本文件

如果本文件与 `AGENTS.md` 不冲突，按本文件更严格的规则执行。

## 项目事实

不要对项目结构做猜测，先接受以下事实：

- 后端是 `FastAPI + Python 3.10+`
- 前端是 `Next.js 16 + React 19 + TypeScript`
- 主入口已经偏向 `Notebook`，根页面 `web/app/page.tsx` 会跳转到 `/notebooks`
- 后端入口是 `src/api/run_server.py`
- FastAPI app 在 `src/api/main.py`
- 配置主入口是 `src/services/config/loader.py`
- 端口来自环境变量，不来自 YAML
- `config/agents.yaml` 是 agent `temperature` 和 `max_tokens` 的单一来源
- `data/user/` 是运行产物根目录，并通过 `/api/outputs` 暴露静态访问
- Notebook 仍然是文件存储，核心在 `src/api/utils/notebook_manager.py`
- PPT v2 的项目、页面、任务与页级聊天记录存储在 PostgreSQL
- 对象存储使用 MinIO，配置不完整时应用可能仍能启动，但相关能力不一定可用

## 先读这些文件

开始任何中大型改动前，至少先读这些文件中的相关部分：

1. `scripts/start_web.py`
2. `src/api/run_server.py`
3. `src/api/main.py`
4. `src/services/config/loader.py`
5. `config/main.yaml`
6. `config/agents.yaml`
7. `src/services/storage/db.py`
8. `src/services/storage/ppt_store.py`
9. `src/api/utils/notebook_manager.py`
10. `web/lib/api.ts`

如果任务与 PPT 相关，再额外读：

1. `src/api/routers/ppt.py`
2. `src/services/export/ppt_project_service.py`
3. `src/services/export/ppt_task_manager.py`
4. `src/services/export/banana_ppt_service.py`
5. `web/lib/pptApi.ts`
6. `tests/ppt/`

## 禁止事项

以下行为默认禁止，除非用户明确要求：

- 不要修改 `web/.next/`
- 不要修改 `web/node_modules/`
- 不要修改 `data/` 下的运行产物来“伪修复”问题
- 不要修改 `tests/**/__pycache__/`
- 不要修改 `web/tsconfig.tsbuildinfo`
- 不要把端口、模型、API base URL、温度参数重新硬编码进业务代码
- 不要在前端页面里手写后端 URL，统一走 `web/lib/api.ts` 或其上层封装
- 不要绕过 `config/agents.yaml` 直接在 agent 里硬编码 `temperature` 或 `max_tokens`
- 不要在未知影响范围的情况下直接改数据库表结构
- 不要因为本地缓存或生成文件脏了，就顺手清理用户已有改动

## 改动前必须做的事

开始写代码前，默认完成以下动作：

1. 先看 `git status --short`
2. 明确任务属于哪条主链路
3. 找到该链路的后端入口、服务编排、持久化层、前端 API 封装、页面入口
4. 区分源码、缓存、构建产物、运行产物
5. 确认改动是否会影响已有 API contract、数据库字段、前端类型或导出路径

如果这 5 步没做完，不要开始编辑。

## 改动后必须做的事

改动完成后，默认完成以下动作：

1. 运行与改动区域最接近的最小验证
2. 检查是否漏改同链路的调用方和消费者
3. 检查路径、字段名、状态值、任务类型是否前后端一致
4. 检查是否误改了生成物或无关文件
5. 如果无法验证，明确写出阻塞原因，不要假装验证过

## 主链路映射

### 后端启动链路

- `scripts/start_web.py`
- `src/api/run_server.py`
- `src/api/main.py`
- `src/services/setup/init.py`

改启动、端口、环境加载时，必须一起检查：

- `.env.example`
- `src/services/config/loader.py`
- `src/services/setup/init.py`
- `web/lib/api.ts`

### Agent 链路

公共基类：

- `src/agents/base_agent.py`

模块目录：

- `src/agents/solve/`
- `src/agents/research/`
- `src/agents/question/`
- `src/agents/guide/`
- `src/agents/ideagen/`
- `src/agents/co_writer/`
- `src/agents/chat/`

改 agent 行为时，必须检查：

1. 对应模块 agent 源码
2. `config/agents.yaml`
3. Prompt 加载路径
4. 该 agent 被哪个 router 或 service 调用
5. 是否影响 token 统计、日志、流式输出

### Notebook 链路

关键文件：

- `src/api/utils/notebook_manager.py`
- `src/api/routers/notebook.py`
- `web/app/notebooks/page.tsx`
- `web/app/notebooks/[id]/page.tsx`

改 Notebook 时，必须注意：

- 数据当前是 JSON 文件，不是数据库
- 会话和 notebook 有兼容性负担，不能轻易破坏旧字段
- 前端主入口就在这条链路上，回归成本高

### PPT v2 链路

关键文件：

- `src/api/routers/ppt.py`
- `src/services/export/ppt_project_service.py`
- `src/services/export/ppt_task_manager.py`
- `src/services/export/banana_ppt_service.py`
- `src/services/export/ppt_generator.py`
- `src/services/export/pdf_generator.py`
- `src/services/storage/ppt_store.py`
- `src/services/storage/db.py`
- `web/lib/pptApi.ts`
- `web/components/ppt/`
- `tests/ppt/`

改 PPT 时，必须检查以下联动点：

1. API request/response 模型是否变了
2. task 状态、progress 结构是否变了
3. `ppt_store` 的字段映射是否同步
4. `db.py` 与 `_ensure_additive_schema()` 是否需要同步
5. 前端 `pptApi.ts` 和页面调用是否仍匹配
6. 导出地址是否仍能通过 `/api/outputs` 访问

### 存储链路

数据库和对象存储关键文件：

- `src/services/storage/db.py`
- `src/services/storage/__init__.py`
- `src/services/storage/object_store.py`
- `src/services/storage/file_store.py`

改存储时，必须遵守：

- PostgreSQL 结构变更优先走增量兼容方式
- 如果新增列，优先同步到 `_ensure_additive_schema()`
- 不要假设 MinIO 一定在线
- 不要把运行态文件路径和对象存储键混为一谈

## 严格规则

### 配置规则

- 端口配置只从环境变量读取
- LLM 与 Embedding 默认通过配置和 provider 机制解析，不要旁路
- agent 参数优先从 `config/agents.yaml` 读取
- 用户可配置项优先放在 `.env` 或 `config/`，不要散落在业务代码

### API 规则

- 新增或修改后端接口时，必须同步检查前端 API 封装
- 新增或修改字段时，必须检查前端类型与页面消费逻辑
- WebSocket 或轮询任务结构变化时，必须检查状态展示层

### 路径规则

- 可下载、可预览的用户产物默认应落在 `data/user/`
- 如果前端需要直接访问文件，路径必须能映射到 `/api/outputs`
- 不要返回只有后端本机可识别的裸绝对路径给前端

### 数据兼容规则

- Notebook JSON 字段尽量追加，不要轻易删除或重命名
- PPT 数据库表结构尽量追加，不要破坏旧记录读取
- 枚举值、状态值、task type 改名会产生跨层影响，必须全链路排查

### 前端规则

- API 请求统一走 `web/lib/api.ts` 及其上层包装
- 不要在页面组件里复制后端协议常量
- 改页面前先确认是路由页、容器组件还是纯展示组件

### 后端规则

- router 负责协议边界，service 负责编排，store 负责持久化，职责不要混写
- 启动逻辑与业务逻辑分离，不要把一次性初始化塞进普通请求处理
- 长耗时 PPT 任务走现有任务机制，不要偷偷改成阻塞接口

## 验证矩阵

以下是最低验证标准，不是理想标准。

### 改 Python 业务逻辑

至少做一项：

- 运行对应 `pytest` 文件
- 如果没有现成测试，执行最小手工路径并说明结果

### 改 PPT 链路

最低要求：

- `pytest tests/ppt -q`

如果接口或前端也改了，再补至少一项：

- 检查 `web/lib/pptApi.ts`
- 手工验证 project 创建或 task 轮询链路

### 改前端页面或组件

最低要求：

- `npm run lint --prefix web`

如果改了接口调用：

- 同时检查对应的后端 router 返回结构

### 改数据库或存储

最低要求：

- 检查 `db.py`、store 封装、调用方是否一致
- 说明是否需要迁移或兼容逻辑

### 关于 skipped tests

- `skipped` 不是 `passed`
- 如果测试被跳过，必须在结果里说明

## 常用命令

后端：

- `pip install -r requirements.txt`
- `python src/api/run_server.py`
- `python scripts/start_web.py`

前端：

- `npm install --prefix web`
- `npm run dev --prefix web`
- `npm run lint --prefix web`

测试：

- `pytest tests -q`
- `pytest tests/ppt -q`

容器：

- `docker compose up --build -d`

## 完成标准

一个改动只有在满足以下条件后，才算完成：

1. 改动落在正确的源码层
2. 同链路的关键消费者已经排查
3. 最小验证已经执行，或阻塞原因已说明
4. 没有顺手污染生成目录
5. 没有覆盖用户现有未提交改动

## 一句话原则

在这个仓库里做事，不要只改“看到的那一层”，必须沿着 `router -> service -> store -> frontend API -> page/component` 这条链路检查到位，尤其是 Notebook 主入口和 PPT v2 主链路。
