# 后端架构设计（dev 分支现行基线）

> 事实基线：`dev` 分支 `src_py/` 源码与 `resources/config/api/endpoints.json`。本文描述**现行实现**与**本次改造落地项**，不再把"目标设计/提议"与"已实现"混写；标注为「约束」的条目是必须满足的设计红线，不代表历史上曾经满足过。
>
> 配套阅读：[api.md](api.md)（外部接口）、[SecurityAndAuditDesign.md](SecurityAndAuditDesign.md)（威胁模型与工作区边界）、[README.md](README.md)（文档索引）。

---

## 1. 部署形态与进程/线程模型

ChatBot 是**本地优先的模块化单体**：Python 是业务真源，Rust 扩展（`src_py/native/`，编译产物 `core.pyd`/`.so`）提供调度器与内存总线，Vue 3 + TypeScript 前端通过 HTTP/SSE/WebSocket 或 Qt WebChannel Bridge 接入。

```
主线程（Qt，不跑 asyncio）
└── QApplication / UIApp（ui/setup.py、ui/views.py、ui/dispatcher.py）
     ├── QTimer(16ms)  MainThreadDispatcher.pump()   ← 工作线程投递
     ├── QTimer(200ms) 心跳 / Ctrl+C 机会
     └── Live2D 窗口、托盘

Web 线程（daemon，独立 asyncio loop）
└── uvicorn → FastAPI（api/server.py::Web）
     ├── install_request_id_middleware / install_exception_handlers
     ├── register_all_routers(app, prefix="/api")   ← endpoints.json 驱动
     └── register_websocket_routes(app)             ← app.websocket("/")

服务线程（每个非主线程服务一条 daemon thread）
└── ServiceManager.start_service() → start_original
     ├── 协程型 start：新建 loop 的 __run_loop
     └── 同步型 start：直接建线程

任务调度器 loop（core/native/scheduler.py + Rust native）
└── 对话编排、工具执行、PPT 异步生成、技能沙盒投递

专用线程池
├── CmdExec        core/tools/services/exceute.py  同步服务方法
└── SkillSandbox   core/tools/skills/sandbox.py    受限 Python 技能
```

硬约束（沿用并保留）：

1. Qt 主线程只跑 UI 事件，不运行常驻 asyncio loop。
2. 已有运行中 loop 时用 `create_task` / `run_coroutine_threadsafe` / 项目 AsyncDispatch，禁止对同一 loop 再 `asyncio.run`。
3. 主线程等待任何线程必须用 `join_with_pump()`，否则 Qt 事件泵停摆形成互等死锁。
4. 同步服务方法必须丢到 `CmdExec` 专用池；`asyncio.wait_for` 无法强杀线程，超时只标记放弃等待，不谎报"已取消"。
5. 后台任务保存强引用并取回异常；关闭顺序固定为「关窗 → 停 Web → 停 runtime → 停 dispatcher」。
6. 文件 IO、同步 SDK、索引重建不得无界阻塞 Web loop；health check 不触发模型加载或全盘扫描。

---

## 2. 源码模块地图（真实路径）

| 路径 | 现行职责 |
|---|---|
| `src_py/main.py` | 进程入口 |
| `src_py/modules/app.py` | `Application` 单例：加载配置、启动 runtime/UI、优雅停机 |
| `src_py/modules/runtime.py` | `StandardPaths` / `RuntimePath` / `RuntimeManager`；应用根、用户数据、资源、日志、存档、技能目录；工作区默认根目录 |
| `src_py/modules/api/` | `server.py`（Web/uvicorn）、`loader.py`+`registry.py`（endpoints.json → router/op）、`gateway.py`（进程内 op 表）、`response.py`/`exceptions.py`（统一信封与错误码）、`requests.py`/`dto.py`（DTO）、`controllers/*`（处理函数）、`controllers/websocket/*` |
| `src_py/modules/core/pipeline/` | 对话编排 `orchestrator.py`、`chat.py`、`debounce.py`；LLM/TTS/ASR/OCR/landmarker adapters |
| `src_py/modules/core/context/` | `assembly.py`、`prompt.py`、`budget.py`、`store.py`、`user.py`、`request.py`、`audio.py` |
| `src_py/modules/core/routes/` | `intent.py`（路由）、`words.py`、`keywords.json`、`models.py`（RouteType） |
| `src_py/modules/core/tools/` | `ctl.py`（CLTTool 编排）、`policy.py`（执行策略）、`tracer.py`、`services/`（解析/校验/执行/格式化）、`skills/`（技能管理 + AST 沙盒） |
| `src_py/modules/core/native/` | Rust 扩展的 Python 绑定、调度器、任务状态、协议 |
| `src_py/modules/services/` | `base.py`/`manager.py`/`config.py`/`keys.py`；`browser/`、`live2d/`、`obs/`、`qqbot/`、`ppt/`、`shell/`、`knowledge/`、`game/` |
| `src_py/modules/security/` | `workspace.py`：工作区权限、路径边界、敏感脱敏、轨迹保护、服务输出目录 |
| `src_py/modules/manager/` | 角色、会话、存档（saves/、Memento 快照） |
| `src_py/modules/ memory/` | 混合记忆：domain/application/compute/database/storage/vector/rag/evaluation |
| `src_py/modules/providers/` | provider 实体、工厂、适配器（shim/transports/runtimes） |
| `src_py/modules/characters/`、`events/`、`logger/`、`ui/`、`utils/`、`types/` | 角色模型、事件总线、日志与轨迹、UI 桥、文件/HTTP 工具、类型 |
| `src_py/native/` | Rust 源码（api.rs / scheduler.rs / memory.rs / runtime.rs ...） |
| `resources/config/api/` | `endpoints.json`（**路由权威源**）、`groups.json`（能力目录） |
| `src/api/`、`src/views/`、`src/stores/` | 前端 Axios service、页面、状态 |

> 兼容层：`modules/services/service/{manager,decorator}.py` 与 `modules/services/keys.py` 是本次新增的薄 re-export，用于修复历史失效导入。新代码统一使用 `modules.services.manager` / `modules.services.keys` / `modules.keys`。

---

## 3. 分层与依赖方向

```
HTTP / SSE / WebSocket / Qt WebChannel Bridge
                 │
                 ▼
API 层：EndpointLoader → controller 处理函数 → ApiResponse 信封
                 │
                 ▼
应用编排层：CLTTool / Orchestrator / ApiGateway / 各 Application 边界
      │            │            │             │
      ▼            ▼            ▼             ▼
core/pipeline  core/tools   memory/       manager/
(adapters)    (policy/     (retrieval)   (session/save/
               executor)                 character)
      │            │            │             │
      ▼            ▼            ▼             ▼
基础设施：services/ · security/workspace · SQLite/Markdown/Milvus · native Rust · 文件系统
```

| 层| 应负责| 不应负责 |
| ------------------------ | ------------------------------------------------ | ------------------------------------------ |
| `api/controllers`        | 参数绑定、调用网关/服务、响应映射                | 实现检索算法、命令执行策略或文件事务       |
| `api/loader` + `gateway` | 端点清单注册、op 分发、信封归一                  | 业务权限判断                               |
| `core/tools`             | 命令解析、格式校验、安全策略、执行与结果截断     | 直接信任 LLM 参数；自行决定输出路径        |
| `services/*`             | 单一职责的外部能力 + `get_tools()` 工具声明      | 绕过 `security/workspace` 读写工作区外文件 |
| `security/workspace`     | 路径边界、三档权限、脱敏、服务输出目录、命令准入 | 依赖 FastAPI / Qt / 具体 provider          |
| `runtime`                | 应用目录与生命周期                               | 在业务模块复制路径规则                     |

依赖朝内：领域层不依赖 FastAPI、Vue、Qt widget 或具体 LLM SDK。
---

## 4. 三种入口共用同一套契约

### 4.1 REST（HTTP）

`resources/config/api/endpoints.json` 的每一项声明 `op / handler / http{method,path} / tags / desktop / dispatch / timeout`。启动链路：

```
Web.init()
 └─ register_all_routers(app, prefix="/api")
     └─ EndpointLoader.build_router()
         └─ 逐条 add_api_route(spec.http.path, resolve_handler(spec.handler))
```

- **统一 `/api` 前缀只在此处添加一次**；`spec.http.path` 必须是资源相对路径（如 `/save/slots`）。
- `controllers/*.py` 里的 `APIRouter(prefix=...)` 是历史遗留，当前 `all_routers()` 只返回 loader 生成的 router，这些声明不会被 include。
- `EndpointLoader._validate()` 在启动时校验 handler 可 import、HTTP 路径不冲突；任一 handler 导入失败会直接抛 `RuntimeError`，因此服务模块的导入健康是启动前置条件。

### 4.2 桌面 Bridge（进程内）

`ops.register_all()` → `EndpointLoader.register_gateway()`：仅 `desktop=true` 的端点注册为 `ApiGateway` 的 op。桌面端 `JS → Bridge → gateway.call(op)` 零网络；Web 端 `HTTP → controller → gateway.call(op)`（或直接调用同一处理函数）。两端返回**同构信封**。

`dispatch` 取值：`loop`（默认，网关已在调度器 loop）、`thread`（`asyncio.to_thread`）、`main`（投递 Qt 主线程）。

### 4.3 WebSocket

`register_websocket_routes(app)` 注册在 **`app.websocket("/")`**（不是 `/ws`）。单连接最多 8 个在途请求（`MAX_INFLIGHT_PER_CLIENT`），消息模型 `WebSocketRequest{type,data}`，心跳单独处理；`data.client_id` 必须与连接分配的一致。旧文档写的 `/ws` 作废。

### 4.4 统一信封与错误码

`ApiResponse{ok, code, message, data, request_id, ts}`，成功业务 `code=200`。错误码 1001/1002/1003/2001/2002/3001/3002 及 HTTP 映射见 [api.md](api.md) §0.2。`X-Request-ID` 由中间件注入 contextvar 并回写响应头。

> 约束：未处理异常不得把 `type(exc).__name__: exc` 回传客户端，只回稳定 message + request_id；详情写脱敏本地日志。

---

## 5. 请求生命周期

1. 中间件生成/透传 `request_id`（外部传入需限制长度与字符集）。
2. Controller 绑定 `Path/Query/Body` DTO；文件大小、枚举、ID 在此校验。
3. 应用编排处理业务状态、授权、幂等、并发与总时限。
4. 耗时工作返回 `task_id` 或流式输出；同步服务方法进 `CmdExec` 池。
5. 统一信封输出；异常映射稳定错误码。
6. 请求结束清理 context、取消无用子任务、记录 latency/status，不记录秘密正文。

---

## 6. 对话路由与工具调用链（本次改造重点）

```
RouteType (PURE_CHAT / TOOL_CALL / MIXED)
   │  core/routes/intent.py
   ▼
PromptBuilder._build_task_segments + build_commands_prompt(get_tools())
   │  生成「service method --param value」命令文档 + shell 兜底说明
   ▼
LLM 输出多行命令文本（每行一条，最多 10 条）
   ▼
CommandParser.parse(text, service_names=...)         ← core/tools/services/formatter.py
   ├─ skill --id <id> --des "..."      → 内置技能通道
   ├─ error --reason "..."             → 内置失败通道
   ├─ <已注册服务> <声明方法> --k v    → 服务命令
   └─ 其余"看起来是命令"的行          → shell 兜底（整行原文，不加 shell --command）
   ▼
CommandValidator  服务是否注册 / 方法是否存在 / 必填参数
   ▼
ToolPolicy.evaluate  deny-by-default + 能力集合 + 参数规模/危险形态 + shell 命令初筛
   ▼
CommandExecutor  超时 / 专用线程池 / 结果字节上限
   ▼
service_manager.get_service(sid).method(**params)
```

关键约束：

- **LLM 只产出意图，不产出授权**。策略与命令准入都是确定性代码。
- 方法必须出现在服务 `get_tools()` 声明里才可调（deny by default）；`EXEC` 能力默认禁用。
- 工具输出、网页、文件、检索记忆都是不可信数据，回填 prompt 时带来源标签，不能覆盖 system policy。
- 统一 `request_id` 贯穿路由、工具、结果回填与最终答复；拒绝也要留下低基数 `reason_code`。
- 命令格式以 `PromptBuilder.build_commands_prompt` 生成的 `service method --param value` 为准；`obs --switch_scene ...` 这类旧注释写法无法被解析器识别。

---

## 7. 服务模型（services）

```
BaseService(ABC, 单例)          name/description/main_thread/state/stop_event
   ▲
   │ @Service(id="xxx")        ServiceDecorator：包装 __init__ 注册到 ServiceManager，
   │                            保留 start_original/stop_original/close_original
   ▼
ServiceManager(单例)            services{id:instance} / service_threads / services_config
                                start/stop/close、get_tools()（按注册表变更缓存）
                                get_service_loop(id) 供执行器跨 loop 投递
_ServiceLoop                   每个 async 服务一个 run_forever() 持久 loop 线程
services/_async.py             同步服务（PPT 大纲）共用的共享持久 loop + 停机释放
BaseServiceConfig              fields → UI 描述 / 当前值序列化；CONFIG_CLASSES 注册表
ToolFunction/ToolFunctionParameters  OpenAI 风格工具声明（core/pipeline/models.py）
```

现行服务 id（`modules/keys.py::ServiceKeys`）：`browser`、`live2d`、`obs`、`qqbot`、`ppt`、`shell`（新增）。`knowledge/`、`game/` 为未接入管理器骨架。

服务状态：`created / running / stopped / not_enabled / error`。

### 7.1 第三轮：服务运行时模型（重要）

旧 `ServiceManager.__run_loop()` 为 async 服务建一个临时 loop，`run_until_complete(start)` 一结束就取消**全部** pending task 并 `loop.close()`。后果是 OBS / QQBot 的 `asyncio.create_task(connect())` 在启动瞬间被自己取消，Browser 的 Playwright 对象留在已关闭的 loop 上，第一次 `open_page` 就跨 loop 报错。

现行模型：

| 服务类型                         | 启动                                                         | 工具方法执行                                                 |
| -------------------------------- | ------------------------------------------------------------ | ------------------------------------------------------------ |
| async（`Browser`/`OBS`/`QQBot`） | 独占 `_ServiceLoop`（`run_forever()` 线程），`start_original` 经 `run_coroutine_threadsafe` 投递并**等待完成**才回成功（60s 上限） | `CommandExecutor._invoke()` 读 `ServiceManager.get_service_loop(id)`，用 `wrap_future(run_coroutine_threadsafe(...))` 投回同一 loop |
| 同步（`PPT`/`Shell`）            | daemon 线程跑 `start_original`                               | `CmdExec` 专用线程池；需要调异步 LLM 时经 `services/_async.run_coroutine()` 走共享持久 loop |
| 主线程（`Live2D`）               | `ui.dispatcher` 投递到主线程                                 | 同上；明确拒绝异步 `start`                                   |

共享 loop 存在的理由：`httpx.AsyncClient` 按 loop 池化，同步服务若每次 `asyncio.run()` 都新建临时 loop，连接池每次重建且淘汰的 client 无法回收。停机时 `ServiceManager.stop()` 调 `shutdown_service_loop()`，先在该 loop 上 `await shutdown_clients()` 再关 loop。

`CommandExecutor` 另修两处：工具声明里的 property（如 `Browser.current_url`）不再当函数调用；裸字符串工具名在策略层也能解析出方法名。

### 7.2 第三轮：配置、控制器与 PPT 链路

- **配置**：`BaseServiceConfig.__init__` 把 `fields` 默认值（深拷贝）物化到实例，UI 只传部分字段时服务读其余字段不再 `AttributeError`；`to_dict()` 序列化**当前值**而非写死的 default；路径类默认值改惰性求值；`ServiceConfig` 改为实例属性，避免类级共享可变配置对象。
- **注入**：`set_service_config()` 把 dict 变成该服务的配置对象并立即注入已注册实例，触发 `on_config_change`；不再"只存字典、没人消费"。
- **控制器**：`register_service` 按构造签名过滤 payload（UI 字段名与构造参数不一致不再 TypeError，Live2D 的 `"1200x800"` 转 tuple）；`start` 不再把 payload 当 `start_original` 的参数；`apply_config` 回显配置对象的 `to_dict()` 而不是 `null`。
- **PPT 大纲**：旧代码 `events.emit(events.types.ProviderEventType.LLM_GENERATE)` 传字符串给只接受 `BaseEvent` 的 emit，且该事件无任何监听者、system/user 提示词从未发出 —— 整条大纲链路不可用。现改走 `providers.LLM.process_message()`，响应按「代码块 → JSON 对象」解析；不在共享 `context_profile` 上写回本次 system 提示词（避免跨请求串台）。
- **模板**：`resources/defaults/ppt_templates.yaml` 在仓库中不存在，旧 `load_defaluts()` 无条件读取 → `PptService()` 构造即 `FileNotFoundError`。现内置 5 套预设（consulting/marketing/academic/launch/funding），文件存在时仍以文件为准，单条坏配置跳过。
- **渲染 / 任务**：`PptRenderService` 不再接受目录参数；版式分派改类级表（每页少建 10 个绑定方法）；先写同目录临时文件再 `os.replace` 原子替换；图表数值非数字补 0 而非整份失败；`_JOBS` 改为有界 `OrderedDict`（64 条 / 1h TTL），终态落定后不再反复取 `TaskReference.result()`。
- **浏览器**：截图固定落 `<workspace>/browser/`（`output_path` 边界复验），不再接受任意绝对路径；滚动像素强制为 `[0,10000]` 整数，防 `page.evaluate` 的 JS 注入；`set_viewport_size` 传 dict 而非两个位置参数（旧写法被 `except` 静默吞掉）；DOM 相似度去重加 `quick_ratio()` 上界剪枝。

---

## 8. 安全沙盒与工作区

### 8.1 权限模型

`modules/security/workspace.py` 是**唯一**的路径与命令边界判定者，纯函数、无框架依赖。

| 档位           | 读   | 写   | 删   | 执行 |
| -------------- | ---- | ---- | ---- | ---- |
| `READ_ONLY`    | ✓    | ✗    | ✗    | ✗    |
| `WRITABLE`     | ✓    | ✓    | ✗    | ✗    |
| `UNRESTRICTED` | ✓    | ✓    | ✓    | ✓    |

- `resolve_in()` 用 `realpath` + `is_within()` 判定，区分 `OUTSIDE_ROOT` 与 `SYMLINK_ESCAPE`。
- `check()` 返回 `AccessVerdict{allowed, reason, path, operation, scrub_required}`；轨迹文件在任何档位下都禁止删除/截断（`TRAIL_PROTECTED`），且轨迹物理存放在应用数据目录，不在工作区内。
- `read_for_ai()` 是 AI 读文件的唯一安全入口：路径 → 权限 → 敏感文件名/内容脱敏一次做完；`allow_sensitive` 必须由 UI 显式确认翻开，且确认进轨迹。
- 默认工作区：未手动选择时惰性创建 `<用户数据目录>/workspace`，`mode=WRITABLE`（默认不允许删除）。用户可通过 `/api/workspace/*` 选择目录与档位。

### 8.2 服务输出目录规范

**任何服务/工具产生的文件都必须落在工作区内，按 service_id 分目录**：

| 产出方                       | 目录                                                       |
| ---------------------------- | ---------------------------------------------------------- |
| PPT 服务                     | `<workspace>/ppt/`                                         |
| 浏览器截图                   | `<workspace>/browser/`（第三轮接入）                       |
| 技能（tools/skills）执行输出 | `<workspace>/skill/<skill_id>/`                            |
| 其它服务                     | `<workspace>/<service_id>/`                                |
| shell 命令 cwd               | `<workspace>/`（或 `<workspace>/<service_id>/`，不得越界） |

统一入口：`service_output_dir(service_id, subpath="")`、`output_path(service_id, name)`、`make_output_writer(service_id)`。这些函数会检查工作区已选择、档位允许写、最终路径仍在 root 内，并自动建目录。

### 8.3 技能沙盒

`core/tools/skills/sandbox.py` 用 AST 白名单：`DEFAULT_ALLOWED_MODULES` 之外的 import、`__import__`/`open`/`eval`/`exec`/`getattr` 等名称、下划线属性访问一律拒绝；`RestrictedCodeExecutor` 跑在 `SkillSandbox` 专用线程池，带 watchdog 超时与 stdout 上限。`SHELL`/`JAVASCRIPT` 类型技能仍明确返回"不支持执行"，不会被静默当作"无脚本"跳过。

> 注意：shell **服务**与 shell **技能**是两件事。前者是受工作区与白名单约束的受控命令通道；后者（`.sh` 技能脚本）依旧不支持执行。

---

## 9. Provider、任务、存档与记忆（边界速览）

- **Provider**：现行链路为 `providers/adapters/registry.py`（配置唯一权威源）→ `providers/factory.py`（拆分凭据/连接/请求参数）→ `providers/adapters/adapters/shim/*`（统一接口）→ `transports/http|local`。`core/pipeline/adapters/*` 是 dev 分支的旧双轨实现，仅保留薄兼容委托层，不再参与实际调用。切换流程为「白名单校验 → 建新实例 → 初始化 client → 原子替换 → 关旧实例」，构建失败时旧实例保持可用。
- **编排**：`core/pipeline/chat.py`（入口与初始化）→ `orchestrator.py`（意图分流 / 命令规划 / 结果摘要）→ `core/tools/ctl.py`（命令执行）→ `providers/entity.py`（能力门面），详见 §9.1。
- **任务**：`core/native/*` 调度器；状态 `pending → running → succeeded/failed/cancelled/timeout`，旧 `done` 作为兼容终态。PPT 异步生成返回 `task_id`，通过 `/api/ppt/job/{task_id}` 查询。
- **存档**：`manager/saves/` 的 Slot + Memento 不可变快照；详见 [GameSaveArchitecture.md](GameSaveArchitecture.md)。
- **记忆**：`memory/` 的分层检索、衰减、压缩与向量索引；查询必须先按 session 过滤，详见 [MemoryDesign.md](MemoryDesign.md)。
- **上下文**：`core/context/` 的 PromptBuilder 按 priority + token budget 装配；`UserContext` 单例共享 deque 的跨 session 污染风险仍列为 P0 待办，详见 [ContextArchitecture.md](ContextArchitecture.md)。

### 9.1 供应商接入与对话编排

**配置层**：`resources/config/providers/{models,schemas}/<capability>.json` 由 `Registry` 一次解析、按 `(capability, provider, model)` 缓存；`${ENV}` 缺失保留占位并记录 `missing_env`，不静默换成空串。文件 mtime/size **以及被引用环境变量的"已设置/未设置"状态**共同构成热更新签名，避免"凭据已配好、describe 仍报不可用"。`flat_config()` 默认脱敏，`describe()` 只回元数据。

**接入层**：`factory.create_adapter()` 是唯一构造入口，把 kwargs 拆成三类——凭据只进 headers、连接字段只进 `HttpTransport`、其余才是请求参数；旧实现把 `base_url` / `api_key` 原样塞进 JSON payload。`shim.initialize_client()` 二次覆盖时通过 `HttpTransport.sync()` 把新配置同步到传输层。HTTP client 按 `(base_url, timeout, loop)` 复用；只对"连接未建立"重试 1 次，**生成请求不重放**（避免重复计费）。

**管理层**：`ProviderManager` 按 capability 加锁串行切换，`_current` 与 entity 自身的 `current_provider` / `current_model` 合并供 API 查询；用量取门面快照（切换前把旧 shim 计数折进总计，不丢账）。`switch` 的 config 覆盖走白名单，**不含 `base_url` / `chat_path` / `auth` / `headers` / `transport`**——端点只能由可信 JSON 决定，否则前端可把带密钥的请求引到任意地址。停机统一 await 连接池关闭任务。

**编排层**：`ensure_initialized_async()` 用 `concurrent.futures.Future` + `asyncio.wrap_future` 广播初始化结果，替代绑定单一 loop 的 `asyncio.Event`（项目里 Web / 调度器 / to_thread 多 loop 并存）。意图分流规则优先，模糊时才走一次轻量 LLM；轻量判断的缓存键与 `IntentRouter` 同构（去标点、小写），返回值先规范化成合法 JSON 再入有界 LRU——截断/带代码块的响应不再被反复当作失败重付一次。情绪分类默认纯规则（0 次额外模型调用），LLM 兜底需显式注入且带 3s 超时。任务链路在「无可执行结果」时直接短路本地回复，不发起第二次完整推理。

**留痕层**：`logger/audit.py` 实现 §5 的事件契约（不可变事件、密钥抹除、正文只留 len+hash、换行注入防护、键数与长度上限、有界缓冲 + dropped 计数、sink 失败不阻断业务）；`logger/trail.py` 提供低基数执行轨迹与 `is_trail_path()`，供工作区与 shell 服务调用。dev 分支这两处模块均不存在，所有调用点被 `except` 静默吞掉。仍需部署侧补落盘 sink、访问控制与保留期限。

---

### 9.2 第四轮：存档 / 会话系统与快捷键映射

**会话与存档分离**。旧实现把两者写进同一个 `<user_data>/saves/` 目录：会话是 `<sid>.yaml` + `<sid>.messages.pkl`，存档槽是 `index.yaml` + `<sid>.save` + `slots/<sid>/`。会话 id 取 `index` 就会覆盖存档索引，会话列表扫描目录时也会把存档文件当成会话。现会话独立到 `<user_data>/sessions/`，启动时把旧目录里属于会话的文件一次性迁移过去（排除 `index.yaml`、`*.save`、临时文件与 `slots/`）。

**id 即路径，必须先校验**。`session_id` / `slot_id` 统一白名单 `^[A-Za-z0-9_-]{1,64}$`，所有路径再经 `utils/file/atomic.safe_join()` 兜底；非法 id 返回稳定错误而不是拼出 `../../` 写任意文件。

```
前端（录制交互 / 设置页 UI）  ──组合键字符串──▶  PUT /api/hotkeys[/{action}]
                                                    │
                                          HotkeyRegistry（唯一权威）
                                           · 动作白名单 / 规范化
                                           · 保留键 / 冲突校验
                                           · revision 乐观并发
                                           · 原子写 <user_data>/config/hotkeys.json
                                                    │ subscribe 通知
                                                    ▼
                                          KeyboardDevice 重载映射（组合键 + hold/press）
```

---

### 9.3 第五轮：日志系统

**运行时模型**（`modules/logger/`）：

```
业务线程 ──LoggerRecord（已脱敏/限长）──▶ 有界 queue(maxsize)
                                          │
                                    LoggerThread（唯一消费者）
                                      ├─ 控制台：每批一次 write + flush
                                      ├─ GET_LOG 事件：缓存导入 / 异常隔离 / 失败冷却
                                      └─ 当前批次 ─▶ LogWriter（单线程池）
                                                       └─ 按日 <YYYY-MM-DD>.log，每批 flush
```

---

## 10 .App装填与UI
**启动顺序**：`Application.init()`（配置 + `logger.reconfigure()`）→ `runtime.instance().init()`（调度器 / 事件总线 / 网关 op / 存档管理器）→ `logger.start()` → 信号 → `UIApp.show()`（`QApplication` → 16ms dispatcher / 200ms 心跳 → 托盘 → 桌面窗口或 Web → `exec()`）。原来 `logger.start()` 排在 `runtime.init()` 之前，而 `events.emit()` 读的是模块全局 `runtime.manager`（此时为 None），启动期日志整段消失；现 `events._bus()` 统一惰性取 `runtime.instance()`。

**关闭顺序**：存档保存 → 关桌面窗口 → 停 Web → 停运行时 → 停 UI（dispatcher 最后）→ 停日志。`_shutdown()` 用 `_closing` 幂等守卫、每步 `_step()` 隔离；`self.ui` 可为 None，异常分支不再用 `self.ui.exit_code` 掩盖原始异常。

**运行时管理器**：`RuntimeManager.__init__` 加单例守卫；补齐 `task_manager` 别名（`api/_common.py`、`api/gateway.py`、`services/ppt/service.py` 共 13 处读取，原来根本没这个属性）；调度器不可用时 `NoopScheduler` 兜底；`stop()` 后事件总线只 clear 不置 None。

**Web 装配**：`register_all_routers()` 不再把 `add_api_route()` 的返回值（`None`）传给 `include_router`；静态资源传目录而非 `index.html` 文件；`run_web()` 以 `app.conf` 的 `[Web]` 段为权威（原硬编码 8080，而配置与前端都是 8000）；`init()` 幂等；`is_ready` 要求 `server.started`。

**UI 生命周期**：`show()` 后置 `_running=True`（原来 `stop()` / `exit()` 直接 return，托盘退出点了没反应）；托盘 `QMenu`/`QAction` 挂实例防 GC；`exit()` 只 `quit` 不清 `qt_app`；Web 启动失败自动降级 desktop；`BrowserViewManager` 派发失败时放弃跨线程 Qt 操作；`available_backends()` 结果缓存。

**Bridge 与前端**：`is_running()` 判定修正（原拼作 `is_runing` 且方法当属性用，同步 handler 全部退化到 UI 线程内联执行）；`submit()` 用位置参数调用 handler；`dumps()` 转义 U+2028/2029 与 `</`；前端插件 `install()` 去掉 `async`（避免晚于 `app.mount()`）、`App.vue` watch 参数顺序、WS 默认事件幂等、`LogForwarder` 防前后端日志回环 + teardown。

**新端点**：`POST /api/logger/append` 接收前端 `forward` 模式批量日志（数组、上限 100 条、字段白名单、正文/堆栈限长、`no_frontend_push` 防回环）。端点 94 → **95**。

---

## 11. 约束与验收清单

## 

- [ ] 未注册方法不可调用；`EXEC` 能力默认关闭，仅 shell 服务在受控条件下放行进程执行。
- [ ] 所有路径经 `realpath` + `is_within` 校验，符号链接逃逸返回 `SYMLINK_ESCAPE`。
- [ ] `rm`/`del`/`format`/`sudo` 等危险命令、重定向与命令拼接被拒绝，且拒绝带稳定原因码。
- [ ] PPT、技能、shell 产出均落在 `<workspace>/<service_id>/...`，无绝对路径越界。
- [ ] 工具命令有最大条数、超时、输出字节上限与取消传播。
- [ ] REST / Bridge / WebSocket 使用同一成功 code、同一信封、同一错误语义。
- [ ] `endpoints.json` 的 path 不含 `/api` 前缀；启动期 `_validate()` 全部通过。
- [ ] health endpoint 不加载模型、不重建索引、不扫全盘。
- [ ] async 服务的 start 与所有工具方法在同一持久 loop 上；停机 await 关闭，无孤儿线程与未关闭的 HTTP client。
- [ ] 服务配置改动后 `to_dict()` 回显当前值并注入实例；`apply_config` 不返回 `null`。
- [ ] 服务产出（含浏览器截图、PPT 临时文件）全部落在工作区，渲染失败不留下半截 `.pptx`。
- [ ] 会话与存档使用独立目录；非法 `session_id` / `slot_id` 不能写出目录边界。
- [ ] 会话消息落盘后重启可恢复；`flush` / `switch` / `delete` 不丢未落盘消息。
- [ ] `sync` → `restore` 往返可恢复会话与消息；删除存档槽同时删除主 `.save` 文件。
- [ ] 热键修改带 `revision`，冲突 / 保留键 / 过期版本均被拒绝且状态不变；设备无需重启即生效。
- [ ] `PUT /api/logger/level` 改动后底层 logger 与所有 handler 级别一致；`GET /api/logger/stats` 返回真实计数与 `by_level`。
- [ ] `POST /api/logger/flush` 在日志刚写入时也不丢消息；`logger.exception()` 的 traceback 在文件、控制台与前端事件里都可见。
- [ ] 事件总线不可用时日志仍完整打印与落盘；凭据形态（`api_key=` / `Bearer` / `sk-`）不出现在任何一路输出。
- [ ] 启动顺序为「配置 → 运行时 → 日志 → UI」，`run()` 不依赖外部先调 `init()`；日志单例配置在 `reconfigure()` 后生效。
- [ ] 关闭顺序为「存档 → 关窗 → 停 Web → 停运行时 → 停 UI → 停日志」，任一步失败不影响后续，`_shutdown()` 幂等。
- [ ] 托盘「退出」与 SIGINT 能真正退出 Qt 主循环；托盘菜单、动作与图标在应用存活期间不被 GC。
- [ ] Web 端口与 `app.conf` / 前端基址一致；静态资源挂载的是目录；`is_ready` 只在 uvicorn 真正 listen 后为真。
- [ ] desktop 模式不启 HTTP 且能加载本地 `file://` 资源；Web 启动失败可降级到桌面窗口。
- [ ] 跨线程 UI 操作派发失败时放弃而不是在非主线程碰 QWidget；Bridge 同步 handler 不占 UI 线程。
- [ ] `POST /api/logger/append` 拒绝非数组 / 超 100 条 / 超长正文；转发的日志不再回推 `GET_LOG`，无前后端回环。