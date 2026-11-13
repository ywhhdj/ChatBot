# ChatBot API 参考（dev 分支 · 官方契约基线）

> **生成文件，请勿手工编辑。**
> 生成命令：`python scripts/api/generate_api_contract.py`
> 契约源：`scripts/api/generate_api_contract.py::ENDPOINTS` → `resources/configs/api/endpoints.json`、`resources/configs/api/groups.json`、本文件。
> 源码基线：`ywhhdj/ChatBot` dev 分支 `a6c38fefb98a4d82acb616bc4c9b98f405b83be9`；Python 源码目录 `src/modules/`（历史文档记作 `src_py/`）。
> 格式口径：项目契约（ADR-002、`FrontendBackendContract.md`）+ OpenAPI 3.1 字段语义；每个端点给出 path / query / requestBody / responses / errors / example。
> 端点总数：**121**（启用 121）；分组数：**18**；基线 commit 的 `endpoints.json` 仅注册 50 条，本次按控制器与各管理器能力补齐。

---

## 1. 概览

### 1.1 服务地址与传输

| 项 | 值 |
|---|---|
| REST / SSE Base URL | `http://127.0.0.1:8000/api` |
| WebSocket | `ws://<host>:<port>/`（由 `controllers/websocket` 注册，不是 `/ws`） |
| 桌面 Bridge | 进程内 `ApiGateway.call(op)`，仅 `desktop=true` 端点注册 |
| 默认监听 | `127.0.0.1:8000`（`resources/configs/app.conf` 的 `[Web]` 段为权威） |
| 认证 | 本地回环默认无认证；远程监听必须显式启用认证与严格来源限制 |
| 内容类型 | `application/json`；SSE 为 `text/event-stream`；二进制一律 base64 |

**最终 URL = `/api` + 资源路径**。`endpoints.json` 内 `http.path` 一律为资源相对路径，不得再带 `/api`；`/api` 只在 `register_all_routers(app, prefix="/api")` 添加一次。控制器内声明的 `APIRouter(prefix=...)` 为历史遗留，`all_routers()` 只返回 loader 生成的 router。

### 1.2 状态标记

| 标记 | 含义 |
|---|---|
| 现行 | 基线 `endpoints.json` 已注册且路径正确 |
| 修正 | 基线已注册但存在缺陷（如 save 组 `/api/api/...` 重复前缀），本次更正 |
| 新增 | 控制器中已有 handler 或本次新增 handler，但基线未注册，本次补齐 |

文档只描述**已注册端点**；设计目标、待办与不兼容变更统一放 §7，不混写为「已实现」。

### 1.3 端点与 op 命名

`op` 统一为 `<group>.<action>`（如 `generate.chat`、`session.create`），与 `groups.json` 的 `ops` 一一对应。`desktop=true` 的端点同时注册为 `ApiGateway` 的 op，桌面端 `call(op)` 与 REST 复用同一 handler 与 DTO。相比基线 `<module>.<func>` 形式的 op，本次为**破坏性重命名**；前端 service 已由 `scripts/api/generate_frontend_services.py` 按同一契约重新生成，每个请求显式携带 `opName` 与 `pathParams`，bridge 不再依赖路径推导（见 §4.3 / §6）。

### 1.4 分组总览

| group / tag | 名称 | 路径前缀 | 端点数 | 说明 |
|---|---|---|---|---|
| `generate` | 生成与推理 | `/` | 11 | 对话、语音、图像、OCR、向量、工具命令及生成任务辅助；handler 统一在 controllers/greater.py |
| `system` | 系统 | `/system` | 5 | 健康、版本、统计、GC 与连通性探测 |
| `config` | 配置 | `/config` | 5 | 配置读取、局部更新、重载、持久化与 schema |
| `logger` | 日志 | `/logger` | 7 | 日志级别、统计、记录与排空 |
| `device` | 设备 | `/device` | 1 | CPU/GPU/内存与推荐帧率 |
| `provider` | 供应商 | `/provider` | 8 | provider 目录、状态、切换、停止与模型下载 |
| `service` | 服务 | `/service` | 11 | 服务注册、启停、配置、工具与 UI 描述 |
| `skill` | 技能 | `/skill` | 7 | 技能目录、启停、提示词与受控执行 |
| `workspace` | 工作区 | `/workspace` | 4 | 工作区选择、权限档位与敏感确认 |
| `audit` | 能力审计 | `/audit` | 2 | 可调用能力树与工具清单（非安全事件日志） |
| `session` | 会话 | `/session` | 8 | 会话生命周期、消息追加与落盘 |
| `save` | 存档 | `/save` | 16 | 存档槽、分段更新、同步与恢复 |
| `character` | 角色 | `/character` | 10 | 角色 CRUD、预设、切换与状态 |
| `memory` | 记忆 | `/memory` | 12 | 分层记忆、检索、压缩、统计、衰减与删除 |
| `task` | 任务 | `/task` | 2 | 后台任务查询与取消 |
| `ppt` | PPT | `/ppt` | 6 | 模板、大纲、渲染任务与产物下载 |
| `hotkeys` | 热键 | `/hotkeys` | 5 | 快捷键清单、校验、批量更新与重置 |
| `catalog` | 接口目录 | `/catalog` | 1 | 端点清单 + OpenAPI schema，供前端动态表单使用 |

---

## 2. 通用约定

### 2.1 路由与注册链路

~~~text
ENDPOINTS（契约源）
   ├─→ resources/configs/api/endpoints.json   EndpointLoader._validate() → add_api_route()
   ├─→ resources/configs/api/groups.json     前端能力目录（catalog）
   └─→ docs/api.md                          本文（同一契约生成）
EndpointLoader.register_gateway() → desktop=true 端点注册为 ApiGateway op
register_all_routers(app, prefix="/api") → 最终 URL
~~~

`EndpointSpec` 字段：`op`、`handler`（`modules.api.controllers.<module>:<func>`）、`http{method,path,status_code,summary,deprecated}`、`tags`、`desktop`、`dispatch`、`timeout`、`enabled`、`meta`。启动期 `_validate()` 校验 handler 可 import 且 `METHOD + path` 不冲突；生成脚本同样做静态自检。

`dispatch`：`loop`（默认，网关已在调度器 loop）/ `thread`（`asyncio.to_thread`，用于文件 IO、模型加载、渲染）/ `main`（Qt 主线程派发，当前 dispatcher 接口待对齐，本次未启用）。

### 2.2 统一响应信封

成功与失败共用一套信封，前端只判 `ok` 与业务 `code`：

~~~json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {},
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.123
}
~~~

| 字段 | 类型 | 说明 |
|---|---|---|
| `ok` | boolean | 业务是否成功 |
| `code` | integer | 业务码，成功固定 **200** |
| `message` | string | 可展示文本，失败时不得含内部异常详情 |
| `data` | object / array / string / null | 业务数据，结构见各端点 `T` |
| `request_id` | string | 16 字符请求标识，`X-Request-ID` 由中间件注入并回写响应头 |
| `ts` | number | Unix 秒（float） |

HTTP status 保留语义（2xx / 4xx / 5xx），业务 `code` 表示应用错误种类；`/api` 下的 404 / 405 也返回同构信封。SSE 与 WebSocket 不走该信封，见 §4。

### 2.3 错误码

| code | HTTP | 含义 | 客户端建议 |
|---:|---:|---|---|
| 200 | 200 | 成功 | 读取 `data` |
| 1001 | 400 | 参数校验失败 | 修正输入 |
| 1002 | 404 | 资源不存在 | 刷新资源或确认 ID |
| 1003 | 409 | 状态冲突 | 查询当前状态后决定 |
| 2001 | 503 | 依赖未初始化 | 配置 / 初始化依赖 |
| 2002 | 504 | 处理超时 | 先查任务状态；仅幂等操作可重试 |
| 3001 | 500 | 内部异常 | 用 `request_id` 排障 |
| 3002 | 503 | 主线程忙或不可用 | 稍后重试 |

统一错误对象建议包含 `kind`（validation / not_found / conflict / not_ready / timeout / cancelled / network / internal）、`code`、`status`、`request_id`、`retryable` 与安全处理后的 `message`。非幂等 POST/PUT/DELETE 默认不自动重试；长任务创建重试必须携带幂等键。

> 已闭环（P0）：桌面 bridge 的 `http.ts` 现判 `code === 200`，与 REST 共用同一信封判定；`response.py::_unhandled_handler` 与 `gateway.py::_invoke` 的兜底只回稳定 `message` + `request_id`，异常类型仅写入本地脱敏日志；外部 `X-Request-ID` 经 `normalize_request_id()` 限制为 `[A-Za-z0-9._-]{1,64}`。

### 2.4 请求标识与隔离维度

| 字段 | 生命周期 | 规则 |
|---|---|---|
| `request_id` | 一个入站请求 | 日志与错误定位；外部传入须限制长度与字符集 |
| `trace_id` | 一条完整业务链路 | 串联路由、memory retrieve、LLM、tool、持久化 |
| `stream_id` | 一次流式传输 | 关联 SSE / WS chunk、done / error / cancel |
| `task_id` | 一个后台工作 | 持续到 succeeded / failed / cancelled / timeout 终态 |
| `session_id` | 一段对话会话 | 上下文、检索、写入必须显式传入并按其过滤 |
| `character_id` | 当前角色实体 | 上下文与角色状态隔离维度 |
| `operation_id` | 长事务型操作 | 存档创建 / 恢复 / 索引重建的幂等查询键 |

`request_id` ≠ `task_id`；一次 POST 可能只创建 task，之后用 `task_id` 查询。

### 2.5 长任务、超时与限流

- 模型下载、PPT 渲染、批量生成等长操作返回 `task_id`，通过 `GET /api/task/{task_id}`、`GET /api/ppt/job/{task_id}` 或 `POST /api/progress-stream/{task_id}` 观察。
- 取消对同步线程不保证强制终止；超时只标记放弃等待，终态以服务端为准。
- 每个端点在 `endpoints.json` 声明 `timeout`；chat / image / PPT 为 300–600s，语音 120s，技能执行 30s，其余 60s。
- chat / audio / 文件 / PPT / 工具请求限制 body size、音频时长、并发数与输出大小；单 WebSocket 连接在途请求上限 8。

### 2.6 安全约束

- 默认只绑定 `127.0.0.1`；远程监听必须启用认证与严格来源限制。
- 配置密钥默认掩码；不在 URL、日志、前端持久化明文凭据。`config.raw=true` 仅在 `CHATBOT_ALLOW_RAW_CONFIG=1` 且本地 debug 模式下放行（`_raw_allowed()`），否则返回 1003 状态冲突，不回显任何原值。
- 所有服务产出与 shell / 技能执行受 `security/workspace` 工作区边界约束；文件参数只接受 `basename`，经 `realpath` + `is_within` 复验。
- 工作区档位：`read_only` / `writable` / `unrestricted`；未选择时惰性使用 `<用户数据目录>/workspace`（writable）。
- 日志不保存 key、完整 prompt、音频或私人记忆正文；健康检查不得触发模型加载、全量索引重建或全盘扫描。

### 2.7 版本与兼容策略

- 契约版本记录在 `endpoints.json` / `groups.json` 的 `version` 字段（本次为 2）。
- 新增字段保持向后兼容；删除 / 重命名 op 或路径须给出兼容期、旧路径别名与移除标准，并在同一变更中更新前端 service / types 与契约测试。
- 生成文件标头必须含生成命令与源文件；禁止手工编辑生成结果。

---

## 3. REST 接口参考

> 每小节字段顺序遵循 OpenAPI 口径：路径 → 参数 → requestBody → responses → errors → example。`data` 字段表由 `src/modules/api/requests.py` / `dto.py` 的 Pydantic 模型经 AST 提取，与源码同步。


### 3.1 生成与推理（tag: `generate`，11 个端点）

对话、语音、图像、OCR、向量、工具命令及生成任务辅助；handler 统一在 controllers/greater.py。路径前缀 `/`。

#### GET `/api/status`

**查询 LLM/TTS/ASR/图像/OCR/向量能力就绪状态**

| 项 | 值 |
|---|---|
| op | `generate.status` |
| 分组 / tag | `generate`（生成与推理） |
| handler | `modules.api.controllers.greater:status` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 新增 |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `GenerationStatusData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `llm` | AbilityStatus | 否 | [] | — |
| `tts` | AbilityStatus | 否 | [] | — |
| `asr` | AbilityStatus | 否 | [] | — |
| `image` | AbilityStatus | 否 | [] | — |
| `ocr` | AbilityStatus | 否 | [] | — |
| `embedding` | AbilityStatus | 否 | [] | — |
| `ready` | boolean | 否 | false | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "llm": "",
    "tts": "",
    "asr": "",
    "image": "<base64-png>",
    "ocr": "",
    "embedding": "",
    "ready": true
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/status'
```

> **备注**：只读探测，不触发模型加载、索引重建或全盘扫描。

---

#### POST `/api/chat`

**非流式对话，一次返回完整回复**

| 项 | 值 |
|---|---|
| op | `generate.chat` |
| 分组 / tag | `generate`（生成与推理） |
| handler | `modules.api.controllers.greater:chat_once` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 600 s |
| 状态 | 新增 |

**请求体** `application/json` · `ChatRequest`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `text` | string | 是 | — | — |
| `source` | string（枚举："text", "asr", "ocr"） | 否 | "text" | — |
| `session_id` | string | 否 | "default" | — |
| `route` | string，可空 | 否 | — | — |
| `stream` | boolean | 否 | false | — |
| `max_tokens` | integer | 否 | 1024 | — |
| `temperature` | number | 否 | 0.7 | — |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `ChatResultData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `text` | string | 否 | "" | — |
| `route` | string | 否 | "" | — |
| `character_id` | string | 否 | "" | — |
| `mood` | integer | 否 | 4 | — |
| `commands_executed` | array<any> | 否 | [] | — |
| `tokens_estimate` | integer | 否 | 0 | — |
| `elapsed_ms` | integer | 否 | 0 | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "text": "你好",
    "route": "",
    "character_id": "qingmei",
    "mood": 4,
    "commands_executed": [],
    "tokens_estimate": 8,
    "elapsed_ms": 8
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/chat' \
  -H 'Content-Type: application/json' \
  -d '{"text": "你好", "session_id": "default", "source": "text"}'
```

> **备注**：route 为空时由意图路由自动判定 pure_chat / tool_call / mixed。

---

#### POST `/api/chat/stream`

**SSE 流式对话**

| 项 | 值 |
|---|---|
| op | `generate.chat_stream` |
| 分组 / tag | `generate`（生成与推理） |
| handler | `modules.api.controllers.greater:chat_stream` |
| desktop bridge | 否（仅 HTTP） |
| dispatch | `loop` |
| 超时 | 600 s |
| 状态 | 新增 |

**请求体** `application/json` · `ChatStreamRequest`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `text` | string | 是 | — | — |
| `source` | string（枚举："text", "asr", "ocr"） | 否 | "text" | — |
| `session_id` | string | 否 | "default" | — |
| `route` | string，可空 | 否 | — | — |
| `stream` | boolean | 否 | true | — |
| `max_tokens` | integer | 否 | 1024 | — |
| `temperature` | number | 否 | 0.7 | — |

**响应** `text/event-stream`（非统一信封；逐帧 `event:` + `data:`，字段见 §4.1）

```text
event: chunk
data: {"type":"chunk","text":"你好","stream_id":"s1","request_id":"r1","seq":1,"ts":1760000000.1}

event: done
data: {"type":"done","session_id":"sess_001","elapsed_ms":1234,"result":{"route":"pure_chat"},"stream_id":"s1","request_id":"r1","seq":2,"ts":1760000001.2}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -N -X POST 'http://127.0.0.1:8000/api/chat/stream' \
  -H 'Content-Type: application/json' \
  -H 'Accept: text/event-stream' \
  -d '{"text": "讲个短故事"}'
```

> **备注**：每帧 `event:` + `data:`（含 stream_id / request_id / seq / ts）；终态恰为 done / error / cancelled 之一，见 §4.1。

---

#### POST `/api/tts`

**文本转语音，返回 base64 音频**

| 项 | 值 |
|---|---|
| op | `generate.tts` |
| 分组 / tag | `generate`（生成与推理） |
| handler | `modules.api.controllers.greater:tts` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 120 s |
| 状态 | 新增 |

**请求体** `application/json` · `TTSRequest`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `text` | string | 是 | — | — |
| `format` | string | 否 | "mp3" | — |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `TTSResultData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `audio` | string | 否 | "" | — |
| `format` | string | 否 | "mp3" | — |
| `bytes` | integer | 否 | 0 | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "audio": "<base64-wav>",
    "format": "mp3",
    "bytes": 8
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/tts' \
  -H 'Content-Type: application/json' \
  -d '{"text": "你好呀", "format": "mp3"}'
```

> **备注**：二进制一律 base64；日志不记录音频内容。

---

#### POST `/api/asr`

**语音转文本，audio 为 base64 音频**

| 项 | 值 |
|---|---|
| op | `generate.asr` |
| 分组 / tag | `generate`（生成与推理） |
| handler | `modules.api.controllers.greater:asr` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 120 s |
| 状态 | 新增 |

**请求体** `application/json` · `ASRRequest`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `audio` | string | 是 | — | base64 编码的音频字节 |
| `format` | string | 否 | "wav" | — |
| `is_final` | boolean | 否 | true | — |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `ASRResultData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `text` | string | 否 | "" | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "text": "你好"
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/asr' \
  -H 'Content-Type: application/json' \
  -d '{"audio": "<base64-wav>", "format": "wav", "is_final": true}'
```

> **备注**：需限制请求体大小、音频时长与解码资源。

---

#### POST `/api/image/generations`

**图像生成（OpenAI / Stability / ComfyUI 协议）**

| 项 | 值 |
|---|---|
| op | `generate.image` |
| 分组 / tag | `generate`（生成与推理） |
| handler | `modules.api.controllers.greater:image_generate` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 600 s |
| 状态 | 新增 |

**请求体** `application/json` · `ImageGenerateRequest`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `prompt` | string | 是 | — | — |
| `size` | string | 否 | "1024x1024" | — |
| `n` | integer | 否 | 1 | — |
| `response_format` | string | 否 | "url" | — |
| `provider` | string，可空 | 否 | — | — |
| `model_id` | string，可空 | 否 | — | — |
| `extra` | object | 否 | {} | — |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `ImageGenerateData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `urls` | array<string> | 否 | [] | — |
| `b64_json` | array<string> | 否 | [] | — |
| `raw` | object | 否 | {} | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "urls": [],
    "b64_json": [],
    "raw": {}
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/image/generations' \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "一只在窗台晒太阳的猫", "size": "1024x1024", "n": 1, "response_format": "url"}'
```

> **备注**：provider/model_id 必须落在 Registry 白名单；extra 展开为供应商原生参数。

---

#### POST `/api/ocr`

**图片文字识别**

| 项 | 值 |
|---|---|
| op | `generate.ocr` |
| 分组 / tag | `generate`（生成与推理） |
| handler | `modules.api.controllers.greater:ocr` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 120 s |
| 状态 | 新增 |

**请求体** `application/json` · `OCRRecognizeRequest`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `image` | string | 是 | — | base64 编码的图片字节 |
| `format` | string | 否 | "png" | — |
| `provider` | string，可空 | 否 | — | — |
| `model_id` | string，可空 | 否 | — | — |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `OCRResultData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `text` | string | 否 | "" | — |
| `provider` | string | 否 | "" | — |
| `model` | string | 否 | "" | — |
| `raw` | object | 否 | {} | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "text": "你好",
    "provider": "",
    "model": "",
    "raw": {}
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/ocr' \
  -H 'Content-Type: application/json' \
  -d '{"image": "<base64-png>", "format": "png"}'
```

---

#### POST `/api/embedding`

**批量文本向量化**

| 项 | 值 |
|---|---|
| op | `generate.embedding` |
| 分组 / tag | `generate`（生成与推理） |
| handler | `modules.api.controllers.greater:embedding` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 120 s |
| 状态 | 新增 |

**请求体** `application/json` · `EmbeddingRequest`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `texts` | array<string> | 是 | — | —；约束：min_length=1, max_length=64 |
| `model_id` | string，可空 | 否 | — | — |
| `dim` | integer，可空 | 否 | — | — |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `EmbeddingData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `vectors` | array<array<number>> | 否 | [] | — |
| `dim` | integer | 否 | 0 | — |
| `model` | string | 否 | "" | — |
| `count` | integer | 否 | 0 | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "vectors": [],
    "dim": 8,
    "model": "",
    "count": 8
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/embedding' \
  -H 'Content-Type: application/json' \
  -d '{"texts": ["你好", "世界"]}'
```

> **备注**：开发态无模型时走 hash 兜底，fingerprint 明确标记，禁止与真实向量混用。

---

#### POST `/api/command`

**执行工具命令文本（策略/沙箱/工作区约束）**

| 项 | 值 |
|---|---|
| op | `generate.command` |
| 分组 / tag | `generate`（生成与推理） |
| handler | `modules.api.controllers.greater:command` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 120 s |
| 状态 | 新增 |

**请求体** `application/json` · `CommandRunRequest`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `text` | string | 是 | — | 命令文本，如 `skill --id weather --city 深圳` |
| `wait` | boolean | 否 | true | — |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `CommandResultData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `success` | boolean | 否 | false | — |
| `results` | array<object> | 否 | [] | — |
| `summary` | string | 否 | "" | — |
| `rounds` | integer | 否 | 0 | — |
| `stop_reason` | string | 否 | "" | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "success": true,
    "results": [],
    "summary": "",
    "rounds": 8,
    "stop_reason": ""
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/command' \
  -H 'Content-Type: application/json' \
  -d '{"text": "skill --id weather --city 深圳", "wait": true}'
```

> **备注**：命令文本只认 `--id`；shell 与未隔离语言默认拒绝，见 §4.4。

---

#### GET `/api/folder/{type}`

**打开受支持的本地数据目录**

| 项 | 值 |
|---|---|
| op | `generate.open_folder` |
| 分组 / tag | `generate`（生成与推理） |
| handler | `modules.api.controllers.greater:open_folder` |
| desktop bridge | 是 |
| dispatch | `thread` |
| 超时 | 60 s |
| 状态 | 新增 |

**路径参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `type` | string | 路径资源标识 |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` 类型：`Dict[str, Any]`（动态对象，字段由运行时决定）。

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {},
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1002 资源不存在（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/folder/'
```

> **备注**：type 白名单：images / roles / memory / workspace；禁止任意路径。

---

#### POST `/api/progress-stream/{task_id}`

**SSE 任务进度流**

| 项 | 值 |
|---|---|
| op | `generate.progress_stream` |
| 分组 / tag | `generate`（生成与推理） |
| handler | `modules.api.controllers.greater:progress_stream` |
| desktop bridge | 否（仅 HTTP） |
| dispatch | `loop` |
| 超时 | 600 s |
| 状态 | 修正 |

**路径参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `task_id` | string | 路径资源标识 |

**请求体**：本端点不声明 Pydantic 请求模型；参数由 handler 直接绑定（见下表查询参数 / 备注）。

**响应** `text/event-stream`（非统一信封；逐帧 `event:` + `data:`，字段见 §4.1）

```text
event: progress
data: {"type":"progress","task_id":"task_001","status":"running","percent":42.5,"stream_id":"s1","request_id":"r1","seq":1,"ts":1760000000.1}

event: done
data: {"type":"progress","task_id":"task_001","status":"done","percent":100.0,"stream_id":"s1","request_id":"r1","seq":2,"ts":1760000001.2}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1002 资源不存在 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -N -X POST 'http://127.0.0.1:8000/api/progress-stream/task_001' \
  -H 'Content-Type: application/json' \
  -H 'Accept: text/event-stream' \
  -d '{}'
```

> **备注**：生产者调用 greater.set_progress(task_id, data) 写入；0.3s 轮询、终态清理、有 deadline；事件名随 status，帧带 stream_id / request_id / seq / ts。

---



### 3.2 系统（tag: `system`，5 个端点）

健康、版本、统计、GC 与连通性探测。路径前缀 `/system`。

#### GET `/api/system/health`

**Web、调度器、主线程、记忆与服务健康状态**

| 项 | 值 |
|---|---|
| op | `system.health` |
| 分组 / tag | `system`（系统） |
| handler | `modules.api.controllers.system:health` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 现行 |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `HealthData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `status` | string | 否 | "healthy" | — |
| `web` | object | 否 | {} | — |
| `scheduler` | object | 否 | {} | — |
| `main_thread` | object | 否 | {} | — |
| `memory` | object | 否 | {} | — |
| `services` | object | 否 | {} | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "status": "healthy",
    "web": {},
    "scheduler": {},
    "main_thread": {},
    "memory": {},
    "services": {}
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/system/health'
```

---

#### GET `/api/system/info`

**版本、配置路径与数据目录**

| 项 | 值 |
|---|---|
| op | `system.info` |
| 分组 / tag | `system`（系统） |
| handler | `modules.api.controllers.system:info` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 现行 |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `InfoData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `name` | string | 否 | "ChatBot" | — |
| `version` | string | 否 | "0.1.0" | — |
| `config_path` | string | 否 | "" | — |
| `data_dir` | string | 否 | "" | — |
| `log_dir` | string | 否 | "" | — |
| `python` | string | 否 | "" | — |
| `adapters` | object | 否 | {} | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "name": "示例",
    "version": "0.1.0",
    "config_path": "",
    "data_dir": "",
    "log_dir": "",
    "python": "",
    "adapters": {}
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/system/info'
```

---

#### GET `/api/system/stats`

**uptime、日志、任务、连接与记忆统计**

| 项 | 值 |
|---|---|
| op | `system.stats` |
| 分组 / tag | `system`（系统） |
| handler | `modules.api.controllers.system:stats` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 现行 |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `StatsData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `uptime_sec` | number | 否 | 0.0 | — |
| `log` | object | 否 | {} | — |
| `scheduler` | object | 否 | {} | — |
| `websocket` | object | 否 | {} | — |
| `memory` | object | 否 | {} | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "uptime_sec": 0.7,
    "log": {},
    "scheduler": {},
    "websocket": {},
    "memory": {}
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/system/stats'
```

---

#### POST `/api/system/gc`

**触发记忆衰减/清理与日志排空**

| 项 | 值 |
|---|---|
| op | `system.gc` |
| 分组 / tag | `system`（系统） |
| handler | `modules.api.controllers.system:gc` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 现行 |

**请求体** `application/json` · `GcRequest`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `decay` | boolean | 否 | true | — |
| `flush_log` | boolean | 否 | true | — |
| `flush_memory` | boolean | 否 | true | — |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `GcData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `decay` | boolean | 否 | false | — |
| `log_flushed` | boolean | 否 | false | — |
| `memory_flushed` | boolean | 否 | false | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "decay": true,
    "log_flushed": true,
    "memory_flushed": true
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/system/gc' \
  -H 'Content-Type: application/json' \
  -d '{"decay": true, "flush_log": true, "flush_memory": true}'
```

---

#### GET `/api/system/ping`

**轻量连通性探测**

| 项 | 值 |
|---|---|
| op | `system.ping` |
| 分组 / tag | `system`（系统） |
| handler | `modules.api.controllers.system:ping` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 现行 |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` 类型：`str`（动态对象，字段由运行时决定）。

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": "pong",
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/system/ping'
```

---



### 3.3 配置（tag: `config`，5 个端点）

配置读取、局部更新、重载、持久化与 schema。路径前缀 `/config`。

#### GET `/api/config`

**读取配置，可按 section 过滤**

| 项 | 值 |
|---|---|
| op | `config.get` |
| 分组 / tag | `config`（配置） |
| handler | `modules.api.controllers.config:get_config_api` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 现行 |

**查询参数**

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `section` | string，可空 | 否 | — | 只取某个配置段 |
| `raw` | boolean | 否 | false | true 时返回 api_key 等敏感字段原值 |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` 类型：`Dict[str, Any]`（动态对象，字段由运行时决定）。

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {},
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/config'
```

> **备注**：涉及密钥时默认遮蔽；raw 明文回显仅限本地受控调试，属待收敛项。

---

#### GET `/api/config/schema`

**配置字段描述**

| 项 | 值 |
|---|---|
| op | `config.schema` |
| 分组 / tag | `config`（配置） |
| handler | `modules.api.controllers.config:schema` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 现行 |

**查询参数**

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `section` | string，可空 | 否 | — | 只取某段的字段说明 |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` 类型：`Dict[str, Any]`（动态对象，字段由运行时决定）。

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {},
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/config/schema'
```

---

#### POST `/api/config/reload`

**从配置文件重新加载**

| 项 | 值 |
|---|---|
| op | `config.reload` |
| 分组 / tag | `config`（配置） |
| handler | `modules.api.controllers.config:reload` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 现行 |

**请求体**：本端点不声明 Pydantic 请求模型；参数由 handler 直接绑定（见下表查询参数 / 备注）。

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` 类型：`Dict[str, Any]`（动态对象，字段由运行时决定）。

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {},
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/config/reload' \
  -H 'Content-Type: application/json' \
  -d '{}'
```

---

#### POST `/api/config/save`

**持久化配置到磁盘**

| 项 | 值 |
|---|---|
| op | `config.save` |
| 分组 / tag | `config`（配置） |
| handler | `modules.api.controllers.config:save` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 现行 |

**请求体** `application/json` · `ConfigSaveRequest`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `file_path` | string，可空 | 否 | — | — |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` 类型：`Dict[str, Any]`（动态对象，字段由运行时决定）。

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {},
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/config/save' \
  -H 'Content-Type: application/json' \
  -d '{"file_path": ""}'
```

---

#### PATCH `/api/config/{section}`

**局部更新配置段**

| 项 | 值 |
|---|---|
| op | `config.patch_section` |
| 分组 / tag | `config`（配置） |
| handler | `modules.api.controllers.config:patch_section` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 现行 |

**路径参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `section` | string | 路径资源标识 |

**查询参数**

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `values` | object，可空 | 否 | — | — |

**请求体** `application/json` · `ConfigPatchRequest`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `values` | object | 否 | {} | — |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` 类型：`Dict[str, Any]`（动态对象，字段由运行时决定）。

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {},
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1002 资源不存在 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X PATCH 'http://127.0.0.1:8000/api/config/' \
  -H 'Content-Type: application/json' \
  -d '{"values": {}}'
```

---



### 3.4 日志（tag: `logger`，7 个端点）

日志级别、统计、记录与排空。路径前缀 `/logger`。

#### GET `/api/logger/level`

**当前日志级别**

| 项 | 值 |
|---|---|
| op | `logger.get_level` |
| 分组 / tag | `logger`（日志） |
| handler | `modules.api.controllers.logger:get_level` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 新增 |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `LoggerLevelData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `level` | string | 否 | "INFO" | — |
| `levels` | array<string> | 否 | [] | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "level": "INFO",
    "levels": []
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/logger/level'
```

---

#### PUT `/api/logger/level`

**设置日志级别**

| 项 | 值 |
|---|---|
| op | `logger.set_level` |
| 分组 / tag | `logger`（日志） |
| handler | `modules.api.controllers.logger:set_level` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 新增 |

**请求体** `application/json` · `LoggerLevelRequest`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `level` | string | 否 | "INFO" | — |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `LoggerLevelData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `level` | string | 否 | "INFO" | — |
| `levels` | array<string> | 否 | [] | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "level": "INFO",
    "levels": []
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X PUT 'http://127.0.0.1:8000/api/logger/level' \
  -H 'Content-Type: application/json' \
  -d '{"level": "INFO"}'
```

---

#### GET `/api/logger/levels`

**可用日志级别列表**

| 项 | 值 |
|---|---|
| op | `logger.list_levels` |
| 分组 / tag | `logger`（日志） |
| handler | `modules.api.controllers.logger:list_levels` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 新增 |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` 类型：`Dict[str, Any]`（动态对象，字段由运行时决定）。

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {},
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/logger/levels'
```

---

#### GET `/api/logger/stats`

**日志计数与按级别统计**

| 项 | 值 |
|---|---|
| op | `logger.stats` |
| 分组 / tag | `logger`（日志） |
| handler | `modules.api.controllers.logger:stats` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 新增 |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `LoggerStatsData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `total` | integer | 否 | 0 | — |
| `dropped` | integer | 否 | 0 | — |
| `queue` | integer | 否 | 0 | — |
| `file_enabled` | boolean | 否 | false | — |
| `by_level` | object | 否 | {} | — |
| `console_enabled` | boolean | 否 | true | — |
| `running` | boolean | 否 | false | — |
| `event_push_failures` | integer | 否 | 0 | — |
| `handler_errors` | integer | 否 | 0 | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "total": 8,
    "dropped": 8,
    "queue": 8,
    "file_enabled": true,
    "by_level": {},
    "console_enabled": true,
    "running": true,
    "event_push_failures": 8
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/logger/stats'
```

---

#### GET `/api/logger/records`

**最近日志记录**

| 项 | 值 |
|---|---|
| op | `logger.records` |
| 分组 / tag | `logger`（日志） |
| handler | `modules.api.controllers.logger:records` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 新增 |

**查询参数**

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `limit` | integer | 否 | 100 | — |
| `level` | string，可空 | 否 | — | 按级别过滤，如 ERROR |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` 类型：`Dict[str, Any]`（动态对象，字段由运行时决定）。

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {},
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/logger/records'
```

> **备注**：limit / level 为查询参数；正文限长，不回传凭据。

---

#### POST `/api/logger/flush`

**排空日志缓冲**

| 项 | 值 |
|---|---|
| op | `logger.flush` |
| 分组 / tag | `logger`（日志） |
| handler | `modules.api.controllers.logger:flush` |
| desktop bridge | 是 |
| dispatch | `thread` |
| 超时 | 60 s |
| 状态 | 新增 |

**请求体**：本端点不声明 Pydantic 请求模型；参数由 handler 直接绑定（见下表查询参数 / 备注）。

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` 类型：`Dict[str, Any]`（动态对象，字段由运行时决定）。

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {},
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/logger/flush' \
  -H 'Content-Type: application/json' \
  -d '{}'
```

---

#### POST `/api/logger/append`

**接收前端 LogForwarder 批量日志**

| 项 | 值 |
|---|---|
| op | `logger.append` |
| 分组 / tag | `logger`（日志） |
| handler | `modules.api.controllers.logger:append_log` |
| desktop bridge | 是 |
| dispatch | `thread` |
| 超时 | 60 s |
| 状态 | 新增 |

**请求体** `application/json` · `LogAppendRequest`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `records` | array<object> | 否 | [] | —；约束：max_length=100 |
| `no_frontend_push` | boolean | 否 | true | — |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `LogAppendData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `accepted` | integer | 否 | 0 | — |
| `dropped` | integer | 否 | 0 | — |
| `total` | integer | 否 | 0 | — |
| `no_frontend_push` | boolean | 否 | true | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "accepted": 1,
    "dropped": 0,
    "total": 1,
    "no_frontend_push": true
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/logger/append' \
  -H 'Content-Type: application/json' \
  -d '{"records": [{"level": "info", "message": "ui ready", "source": "frontend"}], "no_frontend_push": true}'
```

> **备注**：单次上限 100 条、字段白名单、正文 4000 / 堆栈 12000 字符；no_frontend_push=true 不广播 GET_LOG，避免日志回环。

---



### 3.5 设备（tag: `device`，1 个端点）

CPU/GPU/内存与推荐帧率。路径前缀 `/device`。

#### GET `/api/device/info`

**设备与平台信息（CPU/GPU/内存/推荐帧率）**

| 项 | 值 |
|---|---|
| op | `device.info` |
| 分组 / tag | `device`（设备） |
| handler | `modules.api.controllers.device:device_info` |
| desktop bridge | 是 |
| dispatch | `thread` |
| 超时 | 60 s |
| 状态 | 新增 |

**查询参数**

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `refresh` | boolean | 否 | false | — |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `DeviceInfoData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `cpu` | CPUInfoData | 否 | [] | — |
| `gpu` | GPUInfoData | 否 | [] | — |
| `overall` | object | 否 | {} | — |
| `recommended_fps` | integer | 否 | 0 | — |
| `ram_mb` | integer | 否 | 0 | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "cpu": "",
    "gpu": "",
    "overall": {},
    "recommended_fps": 8,
    "ram_mb": 8
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/device/info'
```

---



### 3.6 供应商（tag: `provider`，8 个端点）

provider 目录、状态、切换、停止与模型下载。路径前缀 `/provider`。

#### GET `/api/provider/adapters`

**能力、可选 provider、当前选中与用量**

| 项 | 值 |
|---|---|
| op | `provider.list_adapters` |
| 分组 / tag | `provider`（供应商） |
| handler | `modules.api.controllers.providers:list_adapters` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 新增 |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` 类型：`Dict[str, Any]`（动态对象，字段由运行时决定）。

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {},
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/provider/adapters'
```

---

#### GET `/api/provider/configs`

**各能力供应商配置（敏感字段已掩码）**

| 项 | 值 |
|---|---|
| op | `provider.all_configs` |
| 分组 / tag | `provider`（供应商） |
| handler | `modules.api.controllers.providers:all_configs` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 新增 |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` 类型：`Dict[str, Any]`（动态对象，字段由运行时决定）。

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {},
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/provider/configs'
```

---

#### GET `/api/provider/adapters/{adapter}/providers`

**某能力下的 provider 清单**

| 项 | 值 |
|---|---|
| op | `provider.list_providers` |
| 分组 / tag | `provider`（供应商） |
| handler | `modules.api.controllers.providers:list_providers` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 新增 |

**路径参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `adapter` | string | 路径资源标识 |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` 类型：`Dict[str, Any]`（动态对象，字段由运行时决定）。

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {},
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1002 资源不存在（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/provider/adapters//providers'
```

---

#### GET `/api/provider/adapters/{adapter}/providers/{provider}`

**读取 provider 配置（已掩码）**

| 项 | 值 |
|---|---|
| op | `provider.get` |
| 分组 / tag | `provider`（供应商） |
| handler | `modules.api.controllers.providers:get_provider` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 新增 |

**路径参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `adapter` | string | 路径资源标识 |
| `provider` | string | 路径资源标识 |

**查询参数**

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `model_id` | string，可空 | 否 | — | 指定模型；缺省用第一个模型 |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` 类型：`Dict[str, Any]`（动态对象，字段由运行时决定）。

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {},
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1002 资源不存在（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/provider/adapters//providers/'
```

---

#### GET `/api/provider/adapters/{adapter}/providers/{provider}/status`

**provider 完整状态与本地模型文件状态**

| 项 | 值 |
|---|---|
| op | `provider.status` |
| 分组 / tag | `provider`（供应商） |
| handler | `modules.api.controllers.providers:status` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 新增 |

**路径参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `adapter` | string | 路径资源标识 |
| `provider` | string | 路径资源标识 |

**查询参数**

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `model_id` | string，可空 | 否 | — | — |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `ProviderStatusData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `capability` | string | 否 | "" | — |
| `name` | string | 否 | "" | — |
| `label` | string | 否 | "" | — |
| `deployment` | string | 否 | "" | — |
| `transport` | string | 否 | "" | — |
| `protocol` | string | 否 | "" | — |
| `runtime` | string | 否 | "" | — |
| `selected_model` | string，可空 | 否 | — | — |
| `models` | array<object> | 否 | [] | — |
| `params` | object | 否 | {} | — |
| `ui` | object | 否 | {} | — |
| `download` | object，可空 | 否 | — | — |
| `download_status` | DownloadStatusData | 否 | [] | — |
| `available` | boolean | 否 | false | — |
| `missing_env` | array<string> | 否 | [] | — |
| `warnings` | array<string> | 否 | [] | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "capability": "",
    "name": "示例",
    "label": "",
    "deployment": "",
    "transport": "",
    "protocol": "",
    "runtime": "",
    "selected_model": ""
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1002 资源不存在（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/provider/adapters//providers//status'
```

---

#### POST `/api/provider/adapters/{adapter}/switch`

**切换 provider / 模型**

| 项 | 值 |
|---|---|
| op | `provider.switch` |
| 分组 / tag | `provider`（供应商） |
| handler | `modules.api.controllers.providers:switch` |
| desktop bridge | 是 |
| dispatch | `thread` |
| 超时 | 120 s |
| 状态 | 新增 |

**路径参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `adapter` | string | 路径资源标识 |

**请求体** `application/json` · `ProviderSwitchRequest`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `provider` | string | 是 | — | — |
| `config` | object，可空 | 否 | — | — |
| `model_id` | string，可空 | 否 | — | 指定模型 id；缺省用该 provider 的第一个模型 |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `SwitchResultData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `success` | boolean | 否 | false | — |
| `type` | string | 否 | "" | — |
| `name` | string | 否 | "" | — |
| `model` | string，可空 | 否 | — | — |
| `config` | object，可空 | 否 | — | — |
| `errors` | array<string> | 否 | [] | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "success": true,
    "type": "",
    "name": "示例",
    "model": "",
    "config": {},
    "errors": []
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1002 资源不存在 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/provider/adapters//switch' \
  -H 'Content-Type: application/json' \
  -d '{"provider": ""}'
```

> **备注**：先初始化新实例并健康检查，成功后才切流量；配置覆盖走白名单。

---

#### POST `/api/provider/adapters/{adapter}/stop`

**停止当前 provider，保留能力门面**

| 项 | 值 |
|---|---|
| op | `provider.stop` |
| 分组 / tag | `provider`（供应商） |
| handler | `modules.api.controllers.providers:stop_adapter` |
| desktop bridge | 是 |
| dispatch | `thread` |
| 超时 | 60 s |
| 状态 | 新增 |

**路径参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `adapter` | string | 路径资源标识 |

**请求体**：本端点不声明 Pydantic 请求模型；参数由 handler 直接绑定（见下表查询参数 / 备注）。

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` 类型：`Dict[str, Any]`（动态对象，字段由运行时决定）。

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {},
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1002 资源不存在 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/provider/adapters//stop' \
  -H 'Content-Type: application/json' \
  -d '{}'
```

---

#### POST `/api/provider/adapters/{adapter}/providers/{provider}/download`

**触发本地模型下载（进度走 WebSocket）**

| 项 | 值 |
|---|---|
| op | `provider.download` |
| 分组 / tag | `provider`（供应商） |
| handler | `modules.api.controllers.providers:download_model` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 30 s |
| 状态 | 新增 |

**路径参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `adapter` | string | 路径资源标识 |
| `provider` | string | 路径资源标识 |

**请求体** `application/json` · `ProviderDownloadRequest`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `model_id` | string，可空 | 否 | — | — |
| `force` | boolean | 否 | false | — |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `DownloadStartData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `task_id` | string | 否 | "" | — |
| `capability` | string | 否 | "" | — |
| `provider` | string | 否 | "" | — |
| `model_id` | string，可空 | 否 | — | — |
| `status` | string | 否 | "started" | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "task_id": "task_001",
    "capability": "",
    "provider": "",
    "model_id": "",
    "status": "started"
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1002 资源不存在 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/provider/adapters//providers//download' \
  -H 'Content-Type: application/json' \
  -d '{"model_id": "", "force": false}'
```

> **备注**：返回 task_id；已安装且未 force 时返回 1001「模型已存在」。

---



### 3.7 服务（tag: `service`，11 个端点）

服务注册、启停、配置、工具与 UI 描述。路径前缀 `/service`。

#### GET `/api/service`

**服务列表（支持 running_only）**

| 项 | 值 |
|---|---|
| op | `service.list` |
| 分组 / tag | `service`（服务） |
| handler | `modules.api.controllers.service:list_services` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 现行 |

**查询参数**

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `running_only` | boolean | 否 | false | 只返回运行中的服务 |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `ServiceListData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `services` | array<ServiceInfoData> | 否 | [] | — |
| `total` | integer | 否 | 0 | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "services": [],
    "total": 8
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/service'
```

---

#### GET `/api/service/tools`

**所有服务工具定义**

| 项 | 值 |
|---|---|
| op | `service.list_tools` |
| 分组 / tag | `service`（服务） |
| handler | `modules.api.controllers.service:list_tools` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 现行 |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `ToolData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `services` | object | 否 | {} | — |
| `total` | integer | 否 | 0 | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "services": {},
    "total": 8
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/service/tools'
```

---

#### GET `/api/service/{service_id}`

**服务详情**

| 项 | 值 |
|---|---|
| op | `service.get` |
| 分组 / tag | `service`（服务） |
| handler | `modules.api.controllers.service:get_service` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 现行 |

**路径参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `service_id` | string | 路径资源标识 |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `ServiceInfoData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `id` | string | 是 | — | — |
| `name` | string | 否 | "" | — |
| `description` | string | 否 | "" | — |
| `state` | string | 否 | "stopped" | — |
| `main_thread` | boolean | 否 | false | — |
| `config` | object，可空 | 否 | — | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "id": "",
    "name": "示例",
    "description": "",
    "state": "stopped",
    "main_thread": true,
    "config": {}
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1002 资源不存在（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/service/browser'
```

---

#### GET `/api/service/{service_id}/tools`

**单服务工具定义**

| 项 | 值 |
|---|---|
| op | `service.tools` |
| 分组 / tag | `service`（服务） |
| handler | `modules.api.controllers.service:service_tools` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 现行 |

**路径参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `service_id` | string | 路径资源标识 |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `ToolData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `services` | object | 否 | {} | — |
| `total` | integer | 否 | 0 | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "services": {},
    "total": 8
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1002 资源不存在（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/service/browser/tools'
```

---

#### GET `/api/service/{service_id}/ui`

**服务 UI 描述**

| 项 | 值 |
|---|---|
| op | `service.ui` |
| 分组 / tag | `service`（服务） |
| handler | `modules.api.controllers.service:service_ui` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 现行 |

**路径参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `service_id` | string | 路径资源标识 |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `ServiceUIDescription`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `id` | string | 是 | — | — |
| `name` | string | 否 | "" | — |
| `description` | string | 否 | "" | — |
| `fields` | array<object> | 否 | [] | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "id": "",
    "name": "示例",
    "description": "",
    "fields": []
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1002 资源不存在（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/service/browser/ui'
```

---

#### POST `/api/service/{service_id}/register`

**注册服务实例**

| 项 | 值 |
|---|---|
| op | `service.register` |
| 分组 / tag | `service`（服务） |
| handler | `modules.api.controllers.service:register_service` |
| desktop bridge | 是 |
| dispatch | `thread` |
| 超时 | 60 s |
| 状态 | 新增 |

**路径参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `service_id` | string | 路径资源标识 |

**请求体**：本端点不声明 Pydantic 请求模型；参数由 handler 直接绑定（见下表查询参数 / 备注）。

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {},
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1002 资源不存在 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/service/browser/register' \
  -H 'Content-Type: application/json' \
  -d '{}'
```

---

#### POST `/api/service/{service_id}/start`

**启动服务**

| 项 | 值 |
|---|---|
| op | `service.start` |
| 分组 / tag | `service`（服务） |
| handler | `modules.api.controllers.service:start_service` |
| desktop bridge | 是 |
| dispatch | `thread` |
| 超时 | 120 s |
| 状态 | 现行 |

**路径参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `service_id` | string | 路径资源标识 |

**请求体** `application/json` · `ServiceStartRequest`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `kwargs` | object，可空 | 否 | — | — |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `ServiceActionData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `id` | string | 是 | — | — |
| `state` | string | 是 | — | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "id": "",
    "state": ""
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1002 资源不存在 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/service/browser/start' \
  -H 'Content-Type: application/json' \
  -d '{"kwargs": {}}'
```

---

#### POST `/api/service/{service_id}/stop`

**停止服务**

| 项 | 值 |
|---|---|
| op | `service.stop` |
| 分组 / tag | `service`（服务） |
| handler | `modules.api.controllers.service:stop_service` |
| desktop bridge | 是 |
| dispatch | `thread` |
| 超时 | 60 s |
| 状态 | 现行 |

**路径参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `service_id` | string | 路径资源标识 |

**请求体**：本端点不声明 Pydantic 请求模型；参数由 handler 直接绑定（见下表查询参数 / 备注）。

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `ServiceActionData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `id` | string | 是 | — | — |
| `state` | string | 是 | — | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "id": "",
    "state": ""
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1002 资源不存在 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/service/browser/stop' \
  -H 'Content-Type: application/json' \
  -d '{}'
```

---

#### GET `/api/service/{service_id}/config`

**读取服务配置**

| 项 | 值 |
|---|---|
| op | `service.get_config` |
| 分组 / tag | `service`（服务） |
| handler | `modules.api.controllers.service:get_config` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 现行 |

**路径参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `service_id` | string | 路径资源标识 |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` 类型：`Dict[str, Any]`（动态对象，字段由运行时决定）。

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {},
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1002 资源不存在（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/service/browser/config'
```

---

#### PUT `/api/service/{service_id}/config`

**更新服务配置**

| 项 | 值 |
|---|---|
| op | `service.update_config` |
| 分组 / tag | `service`（服务） |
| handler | `modules.api.controllers.service:update_config` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 现行 |

**路径参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `service_id` | string | 路径资源标识 |

**请求体** `application/json` · `ServiceConfigUpdateRequest`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `id` | string | 是 | — | 服务 ID |
| `config` | object | 否 | {} | — |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` 类型：`Dict[str, Any]`（动态对象，字段由运行时决定）。

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {},
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1002 资源不存在 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X PUT 'http://127.0.0.1:8000/api/service/browser/config' \
  -H 'Content-Type: application/json' \
  -d '{"id": ""}'
```

---

#### PUT `/api/service/{service_id}/config/apply`

**应用配置（停 → 启）**

| 项 | 值 |
|---|---|
| op | `service.apply_config` |
| 分组 / tag | `service`（服务） |
| handler | `modules.api.controllers.service:apply_config` |
| desktop bridge | 是 |
| dispatch | `thread` |
| 超时 | 120 s |
| 状态 | 现行 |

**路径参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `service_id` | string | 路径资源标识 |

**请求体**：本端点不声明 Pydantic 请求模型；参数由 handler 直接绑定（见下表查询参数 / 备注）。

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` 类型：`Dict[str, Any]`（动态对象，字段由运行时决定）。

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {},
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1002 资源不存在 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X PUT 'http://127.0.0.1:8000/api/service/browser/config/apply' \
  -H 'Content-Type: application/json' \
  -d '{}'
```

---



### 3.8 技能（tag: `skill`，7 个端点）

技能目录、启停、提示词与受控执行。路径前缀 `/skill`。

#### GET `/api/skill`

**技能列表（支持 active_only）**

| 项 | 值 |
|---|---|
| op | `skill.list` |
| 分组 / tag | `skill`（技能） |
| handler | `modules.api.controllers.skill:list_skills` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 现行 |

**查询参数**

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `active_only` | boolean | 否 | false | 只返回已启用技能 |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `SkillListData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `skills` | array<SkillInfoData> | 否 | [] | — |
| `total` | integer | 否 | 0 | — |
| `pending` | object | 否 | {} | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "skills": [],
    "total": 8,
    "pending": {}
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/skill'
```

---

#### GET `/api/skill/prompt`

**给模型使用的技能提示词**

| 项 | 值 |
|---|---|
| op | `skill.prompt` |
| 分组 / tag | `skill`（技能） |
| handler | `modules.api.controllers.skill:prompt` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 现行 |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` 类型：`Dict[str, Any]`（动态对象，字段由运行时决定）。

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {},
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/skill/prompt'
```

---

#### POST `/api/skill/reload`

**重新扫描技能目录**

| 项 | 值 |
|---|---|
| op | `skill.reload` |
| 分组 / tag | `skill`（技能） |
| handler | `modules.api.controllers.skill:reload` |
| desktop bridge | 是 |
| dispatch | `thread` |
| 超时 | 60 s |
| 状态 | 现行 |

**请求体**：本端点不声明 Pydantic 请求模型；参数由 handler 直接绑定（见下表查询参数 / 备注）。

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` 类型：`Dict[str, Any]`（动态对象，字段由运行时决定）。

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {},
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/skill/reload' \
  -H 'Content-Type: application/json' \
  -d '{}'
```

---

#### GET `/api/skill/{skill_id}`

**技能详情**

| 项 | 值 |
|---|---|
| op | `skill.get` |
| 分组 / tag | `skill`（技能） |
| handler | `modules.api.controllers.skill:get_skill` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 现行 |

**路径参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `skill_id` | string | 路径资源标识 |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `SkillInfoData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `id` | string | 是 | — | — |
| `name` | string | 否 | "" | — |
| `description` | string | 否 | "" | — |
| `version` | string | 否 | "" | — |
| `author` | string | 否 | "" | — |
| `license` | string | 否 | "" | — |
| `exec_type` | string | 否 | "none" | — |
| `active` | boolean | 否 | false | — |
| `executable` | boolean | 否 | true | — |
| `reason` | string | 否 | "" | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "id": "",
    "name": "示例",
    "description": "",
    "version": "",
    "author": "",
    "license": "",
    "exec_type": "none",
    "active": true
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1002 资源不存在（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/skill/weather'
```

---

#### POST `/api/skill/{skill_id}/activate`

**启用技能**

| 项 | 值 |
|---|---|
| op | `skill.activate` |
| 分组 / tag | `skill`（技能） |
| handler | `modules.api.controllers.skill:activate` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 现行 |

**路径参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `skill_id` | string | 路径资源标识 |

**请求体**：本端点不声明 Pydantic 请求模型；参数由 handler 直接绑定（见下表查询参数 / 备注）。

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `SkillInfoData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `id` | string | 是 | — | — |
| `name` | string | 否 | "" | — |
| `description` | string | 否 | "" | — |
| `version` | string | 否 | "" | — |
| `author` | string | 否 | "" | — |
| `license` | string | 否 | "" | — |
| `exec_type` | string | 否 | "none" | — |
| `active` | boolean | 否 | false | — |
| `executable` | boolean | 否 | true | — |
| `reason` | string | 否 | "" | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "id": "",
    "name": "示例",
    "description": "",
    "version": "",
    "author": "",
    "license": "",
    "exec_type": "none",
    "active": true
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1002 资源不存在 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/skill/weather/activate' \
  -H 'Content-Type: application/json' \
  -d '{}'
```

---

#### POST `/api/skill/{skill_id}/deactivate`

**停用技能**

| 项 | 值 |
|---|---|
| op | `skill.deactivate` |
| 分组 / tag | `skill`（技能） |
| handler | `modules.api.controllers.skill:deactivate` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 现行 |

**路径参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `skill_id` | string | 路径资源标识 |

**请求体**：本端点不声明 Pydantic 请求模型；参数由 handler 直接绑定（见下表查询参数 / 备注）。

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `SkillInfoData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `id` | string | 是 | — | — |
| `name` | string | 否 | "" | — |
| `description` | string | 否 | "" | — |
| `version` | string | 否 | "" | — |
| `author` | string | 否 | "" | — |
| `license` | string | 否 | "" | — |
| `exec_type` | string | 否 | "none" | — |
| `active` | boolean | 否 | false | — |
| `executable` | boolean | 否 | true | — |
| `reason` | string | 否 | "" | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "id": "",
    "name": "示例",
    "description": "",
    "version": "",
    "author": "",
    "license": "",
    "exec_type": "none",
    "active": true
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1002 资源不存在 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/skill/weather/deactivate' \
  -H 'Content-Type: application/json' \
  -d '{}'
```

---

#### POST `/api/skill/{skill_id}/execute`

**执行技能（超时 30s，AST 白名单沙盒）**

| 项 | 值 |
|---|---|
| op | `skill.execute` |
| 分组 / tag | `skill`（技能） |
| handler | `modules.api.controllers.skill:execute` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 30 s |
| 状态 | 现行 |

**路径参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `skill_id` | string | 路径资源标识 |

**请求体** `application/json` · `SkillExecuteRequest`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `params` | object | 否 | {} | — |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `SkillExecuteData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `id` | string | 是 | — | — |
| `ok` | boolean | 否 | false | — |
| `result` | object，可空 | 否 | — | — |
| `error` | string，可空 | 否 | — | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "id": "",
    "ok": true,
    "result": {},
    "error": ""
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1002 资源不存在 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/skill/weather/execute' \
  -H 'Content-Type: application/json' \
  -d '{"params": {}}'
```

> **备注**：shell / javascript 类型可见但不支持执行；输出限制到 <workspace>/skill/<skill_id>/。

---



### 3.9 工作区（tag: `workspace`，4 个端点）

工作区选择、权限档位与敏感确认。路径前缀 `/workspace`。

#### GET `/api/workspace`

**当前工作区、权限档位与输出目录**

| 项 | 值 |
|---|---|
| op | `workspace.info` |
| 分组 / tag | `workspace`（工作区） |
| handler | `modules.api.controllers.workspace:info` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 新增 |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` 类型：`Dict[str, Any]`（动态对象，字段由运行时决定）。

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {},
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/workspace'
```

---

#### POST `/api/workspace/select`

**选择目录与权限档位**

| 项 | 值 |
|---|---|
| op | `workspace.select` |
| 分组 / tag | `workspace`（工作区） |
| handler | `modules.api.controllers.workspace:select` |
| desktop bridge | 是 |
| dispatch | `thread` |
| 超时 | 60 s |
| 状态 | 新增 |

**请求体**：本端点不声明 Pydantic 请求模型；参数由 handler 直接绑定（见下表查询参数 / 备注）。

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` 类型：`Dict[str, Any]`（动态对象，字段由运行时决定）。

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {},
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/workspace/select' \
  -H 'Content-Type: application/json' \
  -d '{}'
```

---

#### POST `/api/workspace/confirm`

**显式确认敏感原文暴露**

| 项 | 值 |
|---|---|
| op | `workspace.confirm` |
| 分组 / tag | `workspace`（工作区） |
| handler | `modules.api.controllers.workspace:confirm` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 新增 |

**请求体**：本端点不声明 Pydantic 请求模型；参数由 handler 直接绑定（见下表查询参数 / 备注）。

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` 类型：`Dict[str, Any]`（动态对象，字段由运行时决定）。

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {},
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/workspace/confirm' \
  -H 'Content-Type: application/json' \
  -d '{}'
```

---

#### DELETE `/api/workspace`

**撤销选择，回到默认工作区**

| 项 | 值 |
|---|---|
| op | `workspace.clear` |
| 分组 / tag | `workspace`（工作区） |
| handler | `modules.api.controllers.workspace:clear` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 新增 |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` 类型：`Dict[str, Any]`（动态对象，字段由运行时决定）。

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {},
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1002 资源不存在（完整映射见 §2.3）。

**请求示例**

```bash
curl -X DELETE 'http://127.0.0.1:8000/api/workspace' \
  -H 'Content-Type: application/json' \
  -d '{}'
```

---



### 3.10 能力审计（tag: `audit`，2 个端点）

可调用能力树与工具清单（非安全事件日志）。路径前缀 `/audit`。

#### GET `/api/audit/tree`

**服务 → 方法 → 参数 能力树**

| 项 | 值 |
|---|---|
| op | `audit.tree` |
| 分组 / tag | `audit`（能力审计） |
| handler | `modules.api.controllers.audit:tree` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 新增 |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `AuditTreeData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `services` | array<AuditServiceData> | 否 | [] | — |
| `total_tools` | integer | 否 | 0 | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "services": [],
    "total_tools": 8
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/audit/tree'
```

---

#### GET `/api/audit/tools`

**扁平工具清单**

| 项 | 值 |
|---|---|
| op | `audit.tools` |
| 分组 / tag | `audit`（能力审计） |
| handler | `modules.api.controllers.audit:tools` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 新增 |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` 类型：`Dict[str, Any]`（动态对象，字段由运行时决定）。

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {},
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/audit/tools'
```

---



### 3.11 会话（tag: `session`，8 个端点）

会话生命周期、消息追加与落盘。路径前缀 `/session`。

#### GET `/api/session`

**会话列表**

| 项 | 值 |
|---|---|
| op | `session.list` |
| 分组 / tag | `session`（会话） |
| handler | `modules.api.controllers.session:list_sessions` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 现行 |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `SessionListData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `sessions` | array<SessionInfoData> | 否 | [] | — |
| `total` | integer | 否 | 0 | — |
| `current` | string，可空 | 否 | — | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "sessions": [],
    "total": 8,
    "current": ""
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/session'
```

---

#### POST `/api/session`

**创建会话**

| 项 | 值 |
|---|---|
| op | `session.create` |
| 分组 / tag | `session`（会话） |
| handler | `modules.api.controllers.session:create_session` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 现行 |

**请求体** `application/json` · `SessionCreateRequest`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `name` | string | 是 | — | — |
| `character_id` | string | 否 | "" | — |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `SessionInfoData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `id` | string | 是 | — | — |
| `name` | string | 否 | "" | — |
| `character_id` | string | 否 | "" | — |
| `created_at` | number | 否 | 0.0 | — |
| `updated_at` | number | 否 | 0.0 | — |
| `message_count` | integer | 否 | 0 | — |
| `metadata` | object | 否 | {} | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "id": "",
    "name": "示例",
    "character_id": "qingmei",
    "created_at": 0.7,
    "updated_at": 0.7,
    "message_count": 8,
    "metadata": {}
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/session' \
  -H 'Content-Type: application/json' \
  -d '{"name": "示例"}'
```

---

#### POST `/api/session/flush`

**等待会话后台写入落盘**

| 项 | 值 |
|---|---|
| op | `session.flush` |
| 分组 / tag | `session`（会话） |
| handler | `modules.api.controllers.session:flush` |
| desktop bridge | 是 |
| dispatch | `thread` |
| 超时 | 60 s |
| 状态 | 现行 |

**请求体** `application/json` · `FlushRequest`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `session_id` | string，可空 | 否 | — | — |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` 类型：`Dict[str, Any]`（动态对象，字段由运行时决定）。

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {},
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/session/flush' \
  -H 'Content-Type: application/json' \
  -d '{"session_id": "sess_001"}'
```

---

#### GET `/api/session/{session_id}`

**会话详情**

| 项 | 值 |
|---|---|
| op | `session.get` |
| 分组 / tag | `session`（会话） |
| handler | `modules.api.controllers.session:get_session` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 现行 |

**路径参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `session_id` | string | 路径资源标识 |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `SessionInfoData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `id` | string | 是 | — | — |
| `name` | string | 否 | "" | — |
| `character_id` | string | 否 | "" | — |
| `created_at` | number | 否 | 0.0 | — |
| `updated_at` | number | 否 | 0.0 | — |
| `message_count` | integer | 否 | 0 | — |
| `metadata` | object | 否 | {} | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "id": "",
    "name": "示例",
    "character_id": "qingmei",
    "created_at": 0.7,
    "updated_at": 0.7,
    "message_count": 8,
    "metadata": {}
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1002 资源不存在（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/session/sess_001'
```

---

#### DELETE `/api/session/{session_id}`

**删除会话**

| 项 | 值 |
|---|---|
| op | `session.delete` |
| 分组 / tag | `session`（会话） |
| handler | `modules.api.controllers.session:delete_session` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 现行 |

**路径参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `session_id` | string | 路径资源标识 |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` 类型：`Dict[str, Any]`（动态对象，字段由运行时决定）。

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {},
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1002 资源不存在（完整映射见 §2.3）。

**请求示例**

```bash
curl -X DELETE 'http://127.0.0.1:8000/api/session/sess_001' \
  -H 'Content-Type: application/json' \
  -d '{}'
```

---

#### POST `/api/session/{session_id}/switch`

**切换当前会话**

| 项 | 值 |
|---|---|
| op | `session.switch` |
| 分组 / tag | `session`（会话） |
| handler | `modules.api.controllers.session:switch_session` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 现行 |

**路径参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `session_id` | string | 路径资源标识 |

**请求体**：本端点不声明 Pydantic 请求模型；参数由 handler 直接绑定（见下表查询参数 / 备注）。

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `SessionInfoData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `id` | string | 是 | — | — |
| `name` | string | 否 | "" | — |
| `character_id` | string | 否 | "" | — |
| `created_at` | number | 否 | 0.0 | — |
| `updated_at` | number | 否 | 0.0 | — |
| `message_count` | integer | 否 | 0 | — |
| `metadata` | object | 否 | {} | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "id": "",
    "name": "示例",
    "character_id": "qingmei",
    "created_at": 0.7,
    "updated_at": 0.7,
    "message_count": 8,
    "metadata": {}
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1002 资源不存在 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/session/sess_001/switch' \
  -H 'Content-Type: application/json' \
  -d '{}'
```

> **备注**：切换是状态边界：先取消旧 session 的活动 stream 再加载新数据。

---

#### GET `/api/session/{session_id}/messages`

**会话消息列表**

| 项 | 值 |
|---|---|
| op | `session.messages` |
| 分组 / tag | `session`（会话） |
| handler | `modules.api.controllers.session:messages` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 现行 |

**路径参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `session_id` | string | 路径资源标识 |

**查询参数**

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `limit` | integer | 否 | 50 | — |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `MessageListData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `messages` | array<MessageItem> | 否 | [] | — |
| `total` | integer | 否 | 0 | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "messages": [],
    "total": 8
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1002 资源不存在（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/session/sess_001/messages'
```

---

#### POST `/api/session/{session_id}/messages`

**追加一条消息**

| 项 | 值 |
|---|---|
| op | `session.append` |
| 分组 / tag | `session`（会话） |
| handler | `modules.api.controllers.session:append_message` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 现行 |

**路径参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `session_id` | string | 路径资源标识 |

**请求体** `application/json` · `MessageAppendRequest`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `role` | string | 否 | "Role.USER" | — |
| `content` | string | 否 | "" | — |
| `source` | string | 否 | "text" | — |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` 类型：`Dict[str, Any]`（动态对象，字段由运行时决定）。

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {},
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1002 资源不存在 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/session/sess_001/messages' \
  -H 'Content-Type: application/json' \
  -d '{"role": "Role.USER", "content": "", "source": "text"}'
```

---



### 3.12 存档（tag: `save`，16 个端点）

存档槽、分段更新、同步与恢复。路径前缀 `/save`。

#### GET `/api/save`

**全量存档槽（含未激活）**

| 项 | 值 |
|---|---|
| op | `save.all` |
| 分组 / tag | `save`（存档） |
| handler | `modules.api.controllers.save:all_slots` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 新增 |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `SlotListData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `slots` | array<SlotInfoData> | 否 | [] | — |
| `total` | integer | 否 | 0 | — |
| `current` | string，可空 | 否 | — | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "slots": [],
    "total": 8,
    "current": ""
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/save'
```

---

#### GET `/api/save/snapshot/status`

**恢复事务、自动存档与调度器 gate 状态**

| 项 | 值 |
|---|---|
| op | `save.snapshot_status` |
| 分组 / tag | `save`（存档） |
| handler | `modules.api.controllers.save:snapshot_status` |
| desktop bridge | 是 |
| dispatch | `thread` |
| 超时 | 60 s |
| 状态 | 新增 |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `SnapshotActionData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `ok` | boolean | 否 | false | — |
| `slot_id` | string | 否 | "" | — |
| `revision` | string | 否 | "" | — |
| `action` | string | 否 | "" | — |
| `code` | string | 否 | "" | — |
| `raw` | object | 否 | {} | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "ok": true,
    "slot_id": "slot_001",
    "revision": "",
    "action": "record",
    "code": "",
    "raw": {}
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/save/snapshot/status'
```

> **备注**：组合根未由应用层装配时返回 2001，不假造成功。

---

#### GET `/api/save/snapshot/graph`

**revision DAG（parent_revision / branch_id）**

| 项 | 值 |
|---|---|
| op | `save.snapshot_graph` |
| 分组 / tag | `save`（存档） |
| handler | `modules.api.controllers.save:snapshot_graph` |
| desktop bridge | 是 |
| dispatch | `thread` |
| 超时 | 60 s |
| 状态 | 新增 |

**查询参数**

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `slot_id` | string | 否 | "" | — |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `SnapshotActionData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `ok` | boolean | 否 | false | — |
| `slot_id` | string | 否 | "" | — |
| `revision` | string | 否 | "" | — |
| `action` | string | 否 | "" | — |
| `code` | string | 否 | "" | — |
| `raw` | object | 否 | {} | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "ok": true,
    "slot_id": "slot_001",
    "revision": "",
    "action": "record",
    "code": "",
    "raw": {}
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/save/snapshot/graph'
```

> **备注**：slot_id 为 query 参数，缺省取当前槽。

---

#### POST `/api/save/snapshot/preview`

**恢复预演（只读、无副作用）**

| 项 | 值 |
|---|---|
| op | `save.snapshot_preview` |
| 分组 / tag | `save`（存档） |
| handler | `modules.api.controllers.save:snapshot_preview` |
| desktop bridge | 是 |
| dispatch | `thread` |
| 超时 | 60 s |
| 状态 | 新增 |

**查询参数**

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `slot_id` | string | 否 | "" | — |
| `revision` | string | 否 | "" | — |

**请求体**：本端点不声明 Pydantic 请求模型；参数由 handler 直接绑定（见下表查询参数 / 备注）。

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `SnapshotActionData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `ok` | boolean | 否 | false | — |
| `slot_id` | string | 否 | "" | — |
| `revision` | string | 否 | "" | — |
| `action` | string | 否 | "" | — |
| `code` | string | 否 | "" | — |
| `raw` | object | 否 | {} | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "ok": true,
    "slot_id": "slot_001",
    "revision": "",
    "action": "record",
    "code": "",
    "raw": {}
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/save/snapshot/preview' \
  -H 'Content-Type: application/json' \
  -d '{}'
```

> **备注**：slot_id / revision 为 query 参数；Preview → Prepare → Commit → Verify 中不改动运行态。

---

#### POST `/api/save/snapshot`

**创建不可变 Snapshot revision**

| 项 | 值 |
|---|---|
| op | `save.snapshot` |
| 分组 / tag | `save`（存档） |
| handler | `modules.api.controllers.save:snapshot` |
| desktop bridge | 是 |
| dispatch | `thread` |
| 超时 | 300 s |
| 状态 | 新增 |

**请求体** `application/json` · `SnapshotRequest`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `slot_id` | string | 否 | "" | — |
| `revision` | string | 否 | "" | — |
| `branch_id` | string | 否 | "main" | — |
| `label` | string | 否 | "" | — |
| `trigger` | string | 否 | "manual" | — |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `SnapshotActionData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `ok` | boolean | 否 | false | — |
| `slot_id` | string | 否 | "" | — |
| `revision` | string | 否 | "" | — |
| `action` | string | 否 | "" | — |
| `code` | string | 否 | "" | — |
| `raw` | object | 否 | {} | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "ok": true,
    "slot_id": "slot_001",
    "revision": "",
    "action": "record",
    "code": "",
    "raw": {}
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/save/snapshot' \
  -H 'Content-Type: application/json' \
  -d '{"slot_id": "slot_001", "label": "章节通关", "trigger": "manual"}'
```

> **备注**：stage → validate → publish；parent 默认取最近成功恢复的 revision。

---

#### POST `/api/save/snapshot/restore`

**执行恢复事务（失败自动回滚）**

| 项 | 值 |
|---|---|
| op | `save.snapshot_restore` |
| 分组 / tag | `save`（存档） |
| handler | `modules.api.controllers.save:snapshot_restore` |
| desktop bridge | 是 |
| dispatch | `thread` |
| 超时 | 300 s |
| 状态 | 新增 |

**请求体** `application/json` · `SnapshotRequest`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `slot_id` | string | 否 | "" | — |
| `revision` | string | 否 | "" | — |
| `branch_id` | string | 否 | "main" | — |
| `label` | string | 否 | "" | — |
| `trigger` | string | 否 | "manual" | — |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `SnapshotActionData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `ok` | boolean | 否 | false | — |
| `slot_id` | string | 否 | "" | — |
| `revision` | string | 否 | "" | — |
| `action` | string | 否 | "" | — |
| `code` | string | 否 | "" | — |
| `raw` | object | 否 | {} | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "ok": true,
    "slot_id": "slot_001",
    "revision": "",
    "action": "record",
    "code": "",
    "raw": {}
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/save/snapshot/restore' \
  -H 'Content-Type: application/json' \
  -d '{"slot_id": "slot_001", "revision": "rev_0007"}'
```

> **备注**：墓碑优先于旧快照；事务结束后恢复调度并启动 pre-restore 缓冲期计时。

---

#### GET `/api/save/slots`

**存档槽列表**

| 项 | 值 |
|---|---|
| op | `save.list_slots` |
| 分组 / tag | `save`（存档） |
| handler | `modules.api.controllers.save:list_slots` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 修正 |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `SlotListData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `slots` | array<SlotInfoData> | 否 | [] | — |
| `total` | integer | 否 | 0 | — |
| `current` | string，可空 | 否 | — | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "slots": [],
    "total": 8,
    "current": ""
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/save/slots'
```

> **备注**：修正旧端点 path 自带 /api 造成的 /api/api/... 重复前缀。

---

#### POST `/api/save/slots`

**创建存档槽**

| 项 | 值 |
|---|---|
| op | `save.create` |
| 分组 / tag | `save`（存档） |
| handler | `modules.api.controllers.save:create_slot` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 修正 |

**请求体** `application/json` · `SlotCreateRequest`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `name` | string | 是 | — | — |
| `slot_id` | string，可空 | 否 | — | — |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `SlotInfoData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `id` | string | 是 | — | — |
| `name` | string | 否 | "" | — |
| `meta` | SlotMeta | 否 | [] | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "id": "",
    "name": "示例",
    "meta": ""
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/save/slots' \
  -H 'Content-Type: application/json' \
  -d '{"name": "示例"}'
```

---

#### POST `/api/save/slots/sync`

**从会话同步到存档槽**

| 项 | 值 |
|---|---|
| op | `save.sync` |
| 分组 / tag | `save`（存档） |
| handler | `modules.api.controllers.save:sync_from_sessions` |
| desktop bridge | 是 |
| dispatch | `thread` |
| 超时 | 60 s |
| 状态 | 修正 |

**请求体** `application/json` · `SlotSyncRequest`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `session_id` | string，可空 | 否 | — | — |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` 类型：`Dict[str, Any]`（动态对象，字段由运行时决定）。

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {},
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/save/slots/sync' \
  -H 'Content-Type: application/json' \
  -d '{"session_id": "sess_001"}'
```

---

#### POST `/api/save/slots/restore`

**从存档槽恢复到会话**

| 项 | 值 |
|---|---|
| op | `save.restore` |
| 分组 / tag | `save`（存档） |
| handler | `modules.api.controllers.save:restore_to_sessions` |
| desktop bridge | 是 |
| dispatch | `thread` |
| 超时 | 60 s |
| 状态 | 修正 |

**请求体**：本端点不声明 Pydantic 请求模型；参数由 handler 直接绑定（见下表查询参数 / 备注）。

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` 类型：`Dict[str, Any]`（动态对象，字段由运行时决定）。

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {},
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/save/slots/restore' \
  -H 'Content-Type: application/json' \
  -d '{}'
```

---

#### GET `/api/save/slots/{slot_id}`

**存档槽详情**

| 项 | 值 |
|---|---|
| op | `save.get` |
| 分组 / tag | `save`（存档） |
| handler | `modules.api.controllers.save:get_slot` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 修正 |

**路径参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `slot_id` | string | 路径资源标识 |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `SlotInfoData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `id` | string | 是 | — | — |
| `name` | string | 否 | "" | — |
| `meta` | SlotMeta | 否 | [] | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "id": "",
    "name": "示例",
    "meta": ""
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1002 资源不存在（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/save/slots/slot_001'
```

---

#### DELETE `/api/save/slots/{slot_id}`

**删除存档槽**

| 项 | 值 |
|---|---|
| op | `save.delete` |
| 分组 / tag | `save`（存档） |
| handler | `modules.api.controllers.save:delete_slot` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 修正 |

**路径参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `slot_id` | string | 路径资源标识 |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `SlotActionData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `id` | string | 是 | — | — |
| `ok` | boolean | 是 | — | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "id": "",
    "ok": true
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1002 资源不存在（完整映射见 §2.3）。

**请求示例**

```bash
curl -X DELETE 'http://127.0.0.1:8000/api/save/slots/slot_001' \
  -H 'Content-Type: application/json' \
  -d '{}'
```

---

#### POST `/api/save/slots/{slot_id}/toggle`

**切换激活存档槽**

| 项 | 值 |
|---|---|
| op | `save.toggle` |
| 分组 / tag | `save`（存档） |
| handler | `modules.api.controllers.save:toggle_slot` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 修正 |

**路径参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `slot_id` | string | 路径资源标识 |

**请求体**：本端点不声明 Pydantic 请求模型；参数由 handler 直接绑定（见下表查询参数 / 备注）。

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `SlotActionData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `id` | string | 是 | — | — |
| `ok` | boolean | 是 | — | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "id": "",
    "ok": true
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1002 资源不存在 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/save/slots/slot_001/toggle' \
  -H 'Content-Type: application/json' \
  -d '{}'
```

---

#### POST `/api/save/slots/{slot_id}/save`

**写入存档**

| 项 | 值 |
|---|---|
| op | `save.save` |
| 分组 / tag | `save`（存档） |
| handler | `modules.api.controllers.save:save_slot` |
| desktop bridge | 是 |
| dispatch | `thread` |
| 超时 | 60 s |
| 状态 | 修正 |

**路径参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `slot_id` | string | 路径资源标识 |

**请求体**：本端点不声明 Pydantic 请求模型；参数由 handler 直接绑定（见下表查询参数 / 备注）。

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `SlotActionData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `id` | string | 是 | — | — |
| `ok` | boolean | 是 | — | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "id": "",
    "ok": true
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1002 资源不存在 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/save/slots/slot_001/save' \
  -H 'Content-Type: application/json' \
  -d '{}'
```

---

#### POST `/api/save/slots/{slot_id}/load`

**加载存档**

| 项 | 值 |
|---|---|
| op | `save.load` |
| 分组 / tag | `save`（存档） |
| handler | `modules.api.controllers.save:load_slot` |
| desktop bridge | 是 |
| dispatch | `thread` |
| 超时 | 60 s |
| 状态 | 修正 |

**路径参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `slot_id` | string | 路径资源标识 |

**请求体**：本端点不声明 Pydantic 请求模型；参数由 handler 直接绑定（见下表查询参数 / 备注）。

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `SlotActionData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `id` | string | 是 | — | — |
| `ok` | boolean | 是 | — | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "id": "",
    "ok": true
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1002 资源不存在 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/save/slots/slot_001/load' \
  -H 'Content-Type: application/json' \
  -d '{}'
```

---

#### PUT `/api/save/slots/{slot_id}/section`

**更新存档分段**

| 项 | 值 |
|---|---|
| op | `save.update_section` |
| 分组 / tag | `save`（存档） |
| handler | `modules.api.controllers.save:update_section` |
| desktop bridge | 是 |
| dispatch | `thread` |
| 超时 | 60 s |
| 状态 | 修正 |

**路径参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `slot_id` | string | 路径资源标识 |

**请求体** `application/json` · `SlotSectionUpdateRequest`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `data` | object | 否 | {} | — |
| `slot_id` | string | 否 | "" | — |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` 类型：`Dict[str, Any]`（动态对象，字段由运行时决定）。

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {},
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1002 资源不存在 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X PUT 'http://127.0.0.1:8000/api/save/slots/slot_001/section' \
  -H 'Content-Type: application/json' \
  -d '{"data": {}, "slot_id": ""}'
```

---



### 3.13 角色（tag: `character`，10 个端点）

角色 CRUD、预设、切换与状态。路径前缀 `/character`。

#### GET `/api/character`

**角色列表**

| 项 | 值 |
|---|---|
| op | `character.list` |
| 分组 / tag | `character`（角色） |
| handler | `modules.api.controllers.character:list_characters` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 新增 |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `CharacterListData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `characters` | array<CharacterInfoData> | 否 | [] | — |
| `total` | integer | 否 | 0 | — |
| `current` | string，可空 | 否 | — | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "characters": [],
    "total": 8,
    "current": ""
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/character'
```

---

#### GET `/api/character/presets`

**角色预设（情绪映射等）**

| 项 | 值 |
|---|---|
| op | `character.presets` |
| 分组 / tag | `character`（角色） |
| handler | `modules.api.controllers.character:presets` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 新增 |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` 类型：`Dict[str, Any]`（动态对象，字段由运行时决定）。

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {},
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/character/presets'
```

> **备注**：静态路径必须先于 /character/{character_id} 注册。

---

#### GET `/api/character/current`

**当前角色**

| 项 | 值 |
|---|---|
| op | `character.current` |
| 分组 / tag | `character`（角色） |
| handler | `modules.api.controllers.character:current` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 新增 |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `CharacterInfoData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `id` | string | 是 | — | — |
| `name` | string | 否 | "" | — |
| `status` | string | 否 | "idle" | — |
| `attributes` | CharacterAttributesData，可空 | 否 | — | — |
| `state` | CharacterStateData，可空 | 否 | — | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "id": "",
    "name": "示例",
    "status": "idle",
    "attributes": "",
    "state": ""
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/character/current'
```

---

#### POST `/api/character`

**创建角色**

| 项 | 值 |
|---|---|
| op | `character.create` |
| 分组 / tag | `character`（角色） |
| handler | `modules.api.controllers.character:create_character` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 新增 |

**请求体** `application/json` · `CharacterCreateRequest`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `id` | string | 是 | — | — |
| `name` | string | 是 | — | — |
| `title` | string | 否 | "" | — |
| `nickname_for_user` | string | 否 | "" | — |
| `personality` | string | 否 | "" | — |
| `background` | string | 否 | "" | — |
| `speech_style` | string | 否 | "" | — |
| `topics_allowed` | array<string>，可空 | 否 | — | — |
| `topics_forbidden` | array<string>，可空 | 否 | — | — |
| `catchphrases` | array<string>，可空 | 否 | — | — |
| `rules` | array<string>，可空 | 否 | — | — |
| `random_words` | array<string>，可空 | 否 | — | — |
| `action_verbs` | array<string>，可空 | 否 | — | — |
| `emotion_adjectives` | array<string>，可空 | 否 | — | — |
| `mood_modifiers` | object，可空 | 否 | — | — |
| `affection` | integer | 否 | 50 | — |
| `mood` | integer | 否 | 4 | — |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `CharacterInfoData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `id` | string | 是 | — | — |
| `name` | string | 否 | "" | — |
| `status` | string | 否 | "idle" | — |
| `attributes` | CharacterAttributesData，可空 | 否 | — | — |
| `state` | CharacterStateData，可空 | 否 | — | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "id": "",
    "name": "示例",
    "status": "idle",
    "attributes": "",
    "state": ""
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/character' \
  -H 'Content-Type: application/json' \
  -d '{"id": "", "name": "示例"}'
```

---

#### GET `/api/character/{character_id}`

**角色详情**

| 项 | 值 |
|---|---|
| op | `character.get` |
| 分组 / tag | `character`（角色） |
| handler | `modules.api.controllers.character:get_character` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 新增 |

**路径参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `character_id` | string | 路径资源标识 |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `CharacterInfoData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `id` | string | 是 | — | — |
| `name` | string | 否 | "" | — |
| `status` | string | 否 | "idle" | — |
| `attributes` | CharacterAttributesData，可空 | 否 | — | — |
| `state` | CharacterStateData，可空 | 否 | — | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "id": "",
    "name": "示例",
    "status": "idle",
    "attributes": "",
    "state": ""
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1002 资源不存在（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/character/qingmei'
```

---

#### PUT `/api/character/{character_id}`

**更新角色**

| 项 | 值 |
|---|---|
| op | `character.update` |
| 分组 / tag | `character`（角色） |
| handler | `modules.api.controllers.character:update_character` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 新增 |

**路径参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `character_id` | string | 路径资源标识 |

**请求体** `application/json` · `CharacterUpdateRequest`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `name` | string，可空 | 否 | — | — |
| `title` | string，可空 | 否 | — | — |
| `nickname_for_user` | string，可空 | 否 | — | — |
| `personality` | string，可空 | 否 | — | — |
| `background` | string，可空 | 否 | — | — |
| `speech_style` | string，可空 | 否 | — | — |
| `catchphrases` | array<string>，可空 | 否 | — | — |
| `rules` | array<string>，可空 | 否 | — | — |
| `topics_allowed` | array<string>，可空 | 否 | — | — |
| `topics_forbidden` | array<string>，可空 | 否 | — | — |
| `affection_level` | integer，可空 | 否 | — | — |
| `mood_modifiers` | object，可空 | 否 | — | — |
| `random_words` | array<string>，可空 | 否 | — | — |
| `action_verbs` | array<string>，可空 | 否 | — | — |
| `emotion_adjectives` | array<string>，可空 | 否 | — | — |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `CharacterInfoData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `id` | string | 是 | — | — |
| `name` | string | 否 | "" | — |
| `status` | string | 否 | "idle" | — |
| `attributes` | CharacterAttributesData，可空 | 否 | — | — |
| `state` | CharacterStateData，可空 | 否 | — | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "id": "",
    "name": "示例",
    "status": "idle",
    "attributes": "",
    "state": ""
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1002 资源不存在 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X PUT 'http://127.0.0.1:8000/api/character/qingmei' \
  -H 'Content-Type: application/json' \
  -d '{"name": "示例", "title": "", "nickname_for_user": "", "personality": "", "background": "", "speech_style": ""}'
```

---

#### DELETE `/api/character/{character_id}`

**删除角色**

| 项 | 值 |
|---|---|
| op | `character.delete` |
| 分组 / tag | `character`（角色） |
| handler | `modules.api.controllers.character:delete_character` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 现行 |

**路径参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `character_id` | string | 路径资源标识 |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` 类型：`Dict[str, Any]`（动态对象，字段由运行时决定）。

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {},
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1002 资源不存在（完整映射见 §2.3）。

**请求示例**

```bash
curl -X DELETE 'http://127.0.0.1:8000/api/character/qingmei' \
  -H 'Content-Type: application/json' \
  -d '{}'
```

---

#### POST `/api/character/{character_id}/switch`

**切换当前角色**

| 项 | 值 |
|---|---|
| op | `character.switch` |
| 分组 / tag | `character`（角色） |
| handler | `modules.api.controllers.character:switch_character` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 现行 |

**路径参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `character_id` | string | 路径资源标识 |

**请求体**：本端点不声明 Pydantic 请求模型；参数由 handler 直接绑定（见下表查询参数 / 备注）。

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `CharacterInfoData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `id` | string | 是 | — | — |
| `name` | string | 否 | "" | — |
| `status` | string | 否 | "idle" | — |
| `attributes` | CharacterAttributesData，可空 | 否 | — | — |
| `state` | CharacterStateData，可空 | 否 | — | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "id": "",
    "name": "示例",
    "status": "idle",
    "attributes": "",
    "state": ""
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1002 资源不存在 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/character/qingmei/switch' \
  -H 'Content-Type: application/json' \
  -d '{}'
```

---

#### GET `/api/character/{character_id}/state`

**角色运行状态**

| 项 | 值 |
|---|---|
| op | `character.get_state` |
| 分组 / tag | `character`（角色） |
| handler | `modules.api.controllers.character:get_state` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 现行 |

**路径参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `character_id` | string | 路径资源标识 |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `CharacterStateData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `mood` | integer | 否 | 4 | — |
| `affection` | integer | 否 | 50 | — |
| `total_messages` | integer | 否 | 0 | — |
| `total_tasks` | integer | 否 | 0 | — |
| `last_interaction` | number | 否 | 0.0 | — |
| `pending_tasks` | integer | 否 | 0 | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "mood": 4,
    "affection": 50,
    "total_messages": 8,
    "total_tasks": 8,
    "last_interaction": 0.7,
    "pending_tasks": 8
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1002 资源不存在（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/character/qingmei/state'
```

---

#### PUT `/api/character/{character_id}/state`

**更新角色状态**

| 项 | 值 |
|---|---|
| op | `character.update_state` |
| 分组 / tag | `character`（角色） |
| handler | `modules.api.controllers.character:update_state` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 现行 |

**路径参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `character_id` | string | 路径资源标识 |

**请求体** `application/json` · `CharacterStateUpdateRequest`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `mood` | integer，可空 | 否 | — | — |
| `affection` | integer，可空 | 否 | — | — |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `CharacterStateData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `mood` | integer | 否 | 4 | — |
| `affection` | integer | 否 | 50 | — |
| `total_messages` | integer | 否 | 0 | — |
| `total_tasks` | integer | 否 | 0 | — |
| `last_interaction` | number | 否 | 0.0 | — |
| `pending_tasks` | integer | 否 | 0 | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "mood": 4,
    "affection": 50,
    "total_messages": 8,
    "total_tasks": 8,
    "last_interaction": 0.7,
    "pending_tasks": 8
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1002 资源不存在 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X PUT 'http://127.0.0.1:8000/api/character/qingmei/state' \
  -H 'Content-Type: application/json' \
  -d '{"mood": 8, "affection": 8}'
```

---



### 3.14 记忆（tag: `memory`，12 个端点）

分层记忆、检索、压缩、统计、衰减与删除。路径前缀 `/memory`。

#### GET `/api/memory/layers`

**分层记忆（short_term / long_term / detailed）**

| 项 | 值 |
|---|---|
| op | `memory.layers` |
| 分组 / tag | `memory`（记忆） |
| handler | `modules.api.controllers.memories:layers` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 新增 |

**查询参数**

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `session_id` | string | 否 | "default" | — |
| `query` | string | 否 | "" | 留空则不检索详细层，延迟更低 |
| `detail_top_k` | integer | 否 | 8 | — |
| `summary_limit` | integer | 否 | 8 | — |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `MemoryLayersData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `short_term` | string | 否 | "" | — |
| `long_term` | string | 否 | "" | — |
| `detailed` | array<DetailedMemoryItem> | 否 | [] | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "short_term": "",
    "long_term": "",
    "detailed": []
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/memory/layers'
```

---

#### GET `/api/memory/short`

**短期记忆摘要**

| 项 | 值 |
|---|---|
| op | `memory.short_term` |
| 分组 / tag | `memory`（记忆） |
| handler | `modules.api.controllers.memories:short_term` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 新增 |

**查询参数**

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `session_id` | string | 否 | "default" | — |
| `limit` | integer | 否 | 10 | — |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `MemoryShortTermData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `session_id` | string | 否 | "default" | — |
| `summary` | string | 否 | "" | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "session_id": "sess_001",
    "summary": ""
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/memory/short'
```

---

#### GET `/api/memory/long`

**长期记忆**

| 项 | 值 |
|---|---|
| op | `memory.long_term` |
| 分组 / tag | `memory`（记忆） |
| handler | `modules.api.controllers.memories:long_term` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 新增 |

**查询参数**

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `session_id` | string | 否 | "default" | — |
| `query` | string | 否 | "" | 提供时按语义检索 |
| `limit` | integer | 否 | 12 | — |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `MemoryLongTermData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `session_id` | string | 否 | "default" | — |
| `summary` | string | 否 | "" | — |
| `query` | string | 否 | "" | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "session_id": "sess_001",
    "summary": "",
    "query": "最近聊了什么"
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/memory/long'
```

---

#### POST `/api/memory/search`

**语义 / 相关记忆检索**

| 项 | 值 |
|---|---|
| op | `memory.search` |
| 分组 / tag | `memory`（记忆） |
| handler | `modules.api.controllers.memories:search` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 新增 |

**请求体** `application/json` · `MemorySearchRequest`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `query` | string | 是 | — | — |
| `top_k` | integer | 否 | 8 | — |
| `session_id` | string | 否 | "default" | — |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `MemorySearchData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `query` | string | 否 | "" | — |
| `items` | array<DetailedMemoryItem> | 否 | [] | — |
| `total` | integer | 否 | 0 | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "query": "最近聊了什么",
    "items": [],
    "total": 8
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/memory/search' \
  -H 'Content-Type: application/json' \
  -d '{"query": "最近聊了什么"}'
```

> **备注**：必须先按 session_id 过滤再查询存储。

---

#### GET `/api/memory/compressed`

**压缩记忆列表**

| 项 | 值 |
|---|---|
| op | `memory.compressed` |
| 分组 / tag | `memory`（记忆） |
| handler | `modules.api.controllers.memories:compressed` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 新增 |

**查询参数**

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `session_id` | string | 否 | "default" | — |
| `limit` | integer | 否 | 24 | — |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `MemoryCompressedListData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `items` | array<CompressedItem> | 否 | [] | — |
| `total` | integer | 否 | 0 | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "items": [],
    "total": 8
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/memory/compressed'
```

---

#### GET `/api/memory/stats`

**记忆容量统计**

| 项 | 值 |
|---|---|
| op | `memory.stats` |
| 分组 / tag | `memory`（记忆） |
| handler | `modules.api.controllers.memories:stats` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 新增 |

**查询参数**

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `session_id` | string | 否 | "default" | — |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `MemoryStatsData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `records` | integer | 否 | 0 | — |
| `compressed` | integer | 否 | 0 | — |
| `tokens_estimate` | integer | 否 | 0 | — |
| `backend` | string | 否 | "" | — |
| `short_term_days` | integer | 否 | 2 | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "records": 8,
    "compressed": 8,
    "tokens_estimate": 8,
    "backend": "",
    "short_term_days": 2
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/memory/stats'
```

---

#### POST `/api/memory/decay`

**手动触发记忆衰减**

| 项 | 值 |
|---|---|
| op | `memory.decay` |
| 分组 / tag | `memory`（记忆） |
| handler | `modules.api.controllers.memories:decay` |
| desktop bridge | 是 |
| dispatch | `thread` |
| 超时 | 60 s |
| 状态 | 新增 |

**请求体**：本端点不声明 Pydantic 请求模型；参数由 handler 直接绑定（见下表查询参数 / 备注）。

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `MemoryDecayData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `decayed` | boolean | 否 | false | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "decayed": true
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/memory/decay' \
  -H 'Content-Type: application/json' \
  -d '{}'
```

---

#### POST `/api/memory/flush`

**等待后台写入完成**

| 项 | 值 |
|---|---|
| op | `memory.flush` |
| 分组 / tag | `memory`（记忆） |
| handler | `modules.api.controllers.memories:flush` |
| desktop bridge | 是 |
| dispatch | `thread` |
| 超时 | 60 s |
| 状态 | 新增 |

**查询参数**

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `timeout` | number | 否 | 5.0 | — |

**请求体**：本端点不声明 Pydantic 请求模型；参数由 handler 直接绑定（见下表查询参数 / 备注）。

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `MemoryFlushData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `flushed` | boolean | 否 | false | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "flushed": true
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/memory/flush' \
  -H 'Content-Type: application/json' \
  -d '{}'
```

---

#### POST `/api/memory/retention`

**设置记忆保留期 / 层级（默认预演）**

| 项 | 值 |
|---|---|
| op | `memory.retention` |
| 分组 / tag | `memory`（记忆） |
| handler | `modules.api.controllers.memories:retention` |
| desktop bridge | 是 |
| dispatch | `thread` |
| 超时 | 60 s |
| 状态 | 新增 |

**请求体** `application/json` · `MemoryActionRequest`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `memory_id` | string | 是 | — | — |
| `session_id` | string | 否 | "default" | — |
| `pinned` | boolean | 否 | true | — |
| `dry_run` | boolean | 否 | true | — |
| `retention_days` | number | 否 | 0.0 | — |
| `layer` | string | 否 | "" | — |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `MemoryActionData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `memory_id` | integer | 否 | 0 | — |
| `session_id` | string | 否 | "" | — |
| `action` | string | 否 | "" | — |
| `applied` | boolean | 否 | false | — |
| `code` | string | 否 | "ok" | — |
| `before` | object | 否 | {} | — |
| `after` | object | 否 | {} | — |
| `warnings` | array<string> | 否 | [] | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "memory_id": 8,
    "session_id": "sess_001",
    "action": "record",
    "applied": true,
    "code": "ok",
    "before": {},
    "after": {},
    "warnings": []
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/memory/retention' \
  -H 'Content-Type: application/json' \
  -d '{"memory_id": "42", "session_id": "default", "retention_days": 30, "dry_run": true}'
```

> **备注**：静态路径必须先于 /memory/{memory_id} 注册；dry_run 默认 true，code 为稳定拒绝码（bad_scope / not_found / no_change…），不是 HTTP 错误。

---

#### POST `/api/memory/pin`

**固定 / 取消固定一条记忆**

| 项 | 值 |
|---|---|
| op | `memory.pin` |
| 分组 / tag | `memory`（记忆） |
| handler | `modules.api.controllers.memories:pin` |
| desktop bridge | 是 |
| dispatch | `thread` |
| 超时 | 60 s |
| 状态 | 新增 |

**请求体** `application/json` · `MemoryActionRequest`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `memory_id` | string | 是 | — | — |
| `session_id` | string | 否 | "default" | — |
| `pinned` | boolean | 否 | true | — |
| `dry_run` | boolean | 否 | true | — |
| `retention_days` | number | 否 | 0.0 | — |
| `layer` | string | 否 | "" | — |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `MemoryActionData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `memory_id` | integer | 否 | 0 | — |
| `session_id` | string | 否 | "" | — |
| `action` | string | 否 | "" | — |
| `applied` | boolean | 否 | false | — |
| `code` | string | 否 | "ok" | — |
| `before` | object | 否 | {} | — |
| `after` | object | 否 | {} | — |
| `warnings` | array<string> | 否 | [] | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "memory_id": 8,
    "session_id": "sess_001",
    "action": "record",
    "applied": true,
    "code": "ok",
    "before": {},
    "after": {},
    "warnings": []
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/memory/pin' \
  -H 'Content-Type: application/json' \
  -d '{"memory_id": "42", "pinned": true, "dry_run": false}'
```

---

#### POST `/api/memory/revive`

**唤醒 faded / archived 记忆**

| 项 | 值 |
|---|---|
| op | `memory.revive` |
| 分组 / tag | `memory`（记忆） |
| handler | `modules.api.controllers.memories:revive` |
| desktop bridge | 是 |
| dispatch | `thread` |
| 超时 | 60 s |
| 状态 | 新增 |

**请求体** `application/json` · `MemoryActionRequest`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `memory_id` | string | 是 | — | — |
| `session_id` | string | 否 | "default" | — |
| `pinned` | boolean | 否 | true | — |
| `dry_run` | boolean | 否 | true | — |
| `retention_days` | number | 否 | 0.0 | — |
| `layer` | string | 否 | "" | — |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `MemoryActionData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `memory_id` | integer | 否 | 0 | — |
| `session_id` | string | 否 | "" | — |
| `action` | string | 否 | "" | — |
| `applied` | boolean | 否 | false | — |
| `code` | string | 否 | "ok" | — |
| `before` | object | 否 | {} | — |
| `after` | object | 否 | {} | — |
| `warnings` | array<string> | 否 | [] | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "memory_id": 8,
    "session_id": "sess_001",
    "action": "record",
    "applied": true,
    "code": "ok",
    "before": {},
    "after": {},
    "warnings": []
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/memory/revive' \
  -H 'Content-Type: application/json' \
  -d '{"memory_id": "42", "dry_run": false}'
```

> **备注**：复用 MemoryAPI.retention_service，提升稳定度但不重置时间轴；scope 先按 session_id 校验。

---

#### DELETE `/api/memory/{memory_id}`

**删除单条记忆（墓碑协议）**

| 项 | 值 |
|---|---|
| op | `memory.delete` |
| 分组 / tag | `memory`（记忆） |
| handler | `modules.api.controllers.memories:delete_memory` |
| desktop bridge | 是 |
| dispatch | `thread` |
| 超时 | 60 s |
| 状态 | 新增 |

**路径参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `memory_id` | string | 路径资源标识 |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `MemoryDeleteData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `id` | string | 否 | "" | — |
| `deleted` | boolean | 否 | false | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "id": "",
    "deleted": true
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1002 资源不存在（完整映射见 §2.3）。

**请求示例**

```bash
curl -X DELETE 'http://127.0.0.1:8000/api/memory/' \
  -H 'Content-Type: application/json' \
  -d '{}'
```

---



### 3.15 任务（tag: `task`，2 个端点）

后台任务查询与取消。路径前缀 `/task`。

#### GET `/api/task/{task_id}`

**查询后台任务状态与结果**

| 项 | 值 |
|---|---|
| op | `task.get` |
| 分组 / tag | `task`（任务） |
| handler | `modules.api.controllers.task:get_task` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 新增 |

**路径参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `task_id` | string | 路径资源标识 |

**查询参数**

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `wait` | boolean | 否 | false | true 时阻塞等待任务完成 |
| `timeout` | number | 否 | 30.0 | — |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `TaskStatusData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `task_id` | string | 是 | — | — |
| `state` | string | 否 | "pending" | — |
| `result` | any | 否 | — | — |
| `error` | string，可空 | 否 | — | — |
| `elapsed_ms` | integer | 否 | 0 | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "task_id": "task_001",
    "state": "pending",
    "result": "",
    "error": "",
    "elapsed_ms": 8
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1002 资源不存在（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/task/task_001'
```

---

#### POST `/api/task/{task_id}/cancel`

**取消任务（尽力而为）**

| 项 | 值 |
|---|---|
| op | `task.cancel` |
| 分组 / tag | `task`（任务） |
| handler | `modules.api.controllers.task:cancel_task` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 新增 |

**路径参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `task_id` | string | 路径资源标识 |

**请求体** `application/json` · `TaskCancelRequest`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `reason` | string | 否 | "" | — |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `TaskStatusData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `task_id` | string | 是 | — | — |
| `state` | string | 否 | "pending" | — |
| `result` | any | 否 | — | — |
| `error` | string，可空 | 否 | — | — |
| `elapsed_ms` | integer | 否 | 0 | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "task_id": "task_001",
    "state": "pending",
    "result": "",
    "error": "",
    "elapsed_ms": 8
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1002 资源不存在 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/task/task_001/cancel' \
  -H 'Content-Type: application/json' \
  -d '{"reason": ""}'
```

> **备注**：同步线程不保证强制终止；超时只标记放弃等待。

---



### 3.16 PPT（tag: `ppt`，6 个端点）

模板、大纲、渲染任务与产物下载。路径前缀 `/ppt`。

#### GET `/api/ppt/templates`

**PPT 模板列表**

| 项 | 值 |
|---|---|
| op | `ppt.templates` |
| 分组 / tag | `ppt`（PPT） |
| handler | `modules.api.controllers.ppt:templates` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 新增 |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `PptTemplateListData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `total` | integer | 否 | 0 | — |
| `templates` | array<object> | 否 | [] | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "total": 8,
    "templates": []
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/ppt/templates'
```

---

#### POST `/api/ppt/outline`

**生成内容大纲（不渲染）**

| 项 | 值 |
|---|---|
| op | `ppt.outline` |
| 分组 / tag | `ppt`（PPT） |
| handler | `modules.api.controllers.ppt:outline` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 300 s |
| 状态 | 新增 |

**请求体** `application/json` · `PptOutlineRequest`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `topic` | string | 是 | — | — |
| `pages` | integer | 否 | 10 | — |
| `template_id` | string | 否 | "" | — |
| `audience` | string | 否 | "" | — |
| `scenario` | string | 否 | "" | — |
| `style` | string | 否 | "" | — |
| `material` | string | 否 | "" | — |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `PptOutlineData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `title` | string | 否 | "" | — |
| `subtitle` | string | 否 | "" | — |
| `slide_count` | integer | 否 | 0 | — |
| `deck` | object | 否 | {} | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "title": "",
    "subtitle": "",
    "slide_count": 8,
    "deck": {}
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/ppt/outline' \
  -H 'Content-Type: application/json' \
  -d '{"topic": "人工智能简介"}'
```

---

#### POST `/api/ppt/render`

**提交渲染后台任务，返回 task_id**

| 项 | 值 |
|---|---|
| op | `ppt.render` |
| 分组 / tag | `ppt`（PPT） |
| handler | `modules.api.controllers.ppt:render` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 600 s |
| 状态 | 新增 |

**请求体** `application/json` · `PptRenderRequest`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `deck` | object | 否 | {} | — |
| `topic` | string | 否 | "" | — |
| `pages` | integer | 否 | 10 | — |
| `template_id` | string | 否 | "" | — |
| `style` | string | 否 | "" | — |
| `colors` | object | 否 | {} | — |
| `file_name` | string | 否 | "" | — |
| `material` | string | 否 | "" | — |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `PptRenderData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `ok` | boolean | 否 | false | — |
| `file_path` | string | 否 | "" | — |
| `file_name` | string | 否 | "" | — |
| `slide_count` | integer | 否 | 0 | — |
| `template_id` | string | 否 | "" | — |
| `message` | string | 否 | "" | — |
| `task_id` | string | 否 | "" | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "ok": true,
    "file_path": "",
    "file_name": "deck.pptx",
    "slide_count": 8,
    "template_id": "",
    "message": "",
    "task_id": "task_001"
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/ppt/render' \
  -H 'Content-Type: application/json' \
  -d '{"deck": {}, "topic": "", "pages": 10, "template_id": "", "style": "", "colors": {}}'
```

---

#### POST `/api/ppt/render/async`

**提交渲染后台任务（render 的显式异步别名）**

| 项 | 值 |
|---|---|
| op | `ppt.render_async` |
| 分组 / tag | `ppt`（PPT） |
| handler | `modules.api.controllers.ppt:render_async` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 600 s |
| 状态 | 新增 |

**请求体** `application/json` · `PptRenderRequest`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `deck` | object | 否 | {} | — |
| `topic` | string | 否 | "" | — |
| `pages` | integer | 否 | 10 | — |
| `template_id` | string | 否 | "" | — |
| `style` | string | 否 | "" | — |
| `colors` | object | 否 | {} | — |
| `file_name` | string | 否 | "" | — |
| `material` | string | 否 | "" | — |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `PptRenderData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `ok` | boolean | 否 | false | — |
| `file_path` | string | 否 | "" | — |
| `file_name` | string | 否 | "" | — |
| `slide_count` | integer | 否 | 0 | — |
| `template_id` | string | 否 | "" | — |
| `message` | string | 否 | "" | — |
| `task_id` | string | 否 | "" | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "ok": true,
    "file_path": "",
    "file_name": "deck.pptx",
    "slide_count": 8,
    "template_id": "",
    "message": "",
    "task_id": "task_001"
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/ppt/render/async' \
  -H 'Content-Type: application/json' \
  -d '{"deck": {}, "topic": "", "pages": 10, "template_id": "", "style": "", "colors": {}}'
```

> **备注**：与 /ppt/render 共用同一实现、DTO 与 task_id 语义；保留别名兼容旧前端 renderAsync 调用，不新建第二套队列。

---

#### GET `/api/ppt/job/{task_id}`

**查询渲染任务**

| 项 | 值 |
|---|---|
| op | `ppt.status` |
| 分组 / tag | `ppt`（PPT） |
| handler | `modules.api.controllers.ppt:job_status` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 新增 |

**路径参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `task_id` | string | 路径资源标识 |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `PptJobData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `task_id` | string | 否 | "" | — |
| `state` | string | 否 | "pending" | — |
| `result` | object | 否 | {} | — |
| `error` | string | 否 | "" | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "task_id": "task_001",
    "state": "pending",
    "result": {},
    "error": ""
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1002 资源不存在（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/ppt/job/task_001'
```

---

#### GET `/api/ppt/download/{file_name}`

**取回产出文件（base64 + 路径）**

| 项 | 值 |
|---|---|
| op | `ppt.download` |
| 分组 / tag | `ppt`（PPT） |
| handler | `modules.api.controllers.ppt:download` |
| desktop bridge | 是 |
| dispatch | `thread` |
| 超时 | 60 s |
| 状态 | 新增 |

**路径参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `file_name` | string | 路径资源标识 |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `PptDownloadData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `file_name` | string | 否 | "" | — |
| `file_path` | string | 否 | "" | — |
| `size` | integer | 否 | 0 | — |
| `content_base64` | string | 否 | "" | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "file_name": "deck.pptx",
    "file_path": "",
    "size": 8,
    "content_base64": ""
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1002 资源不存在（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/ppt/download/deck.pptx'
```

> **备注**：只接受 basename，并再次经工作区边界复验；产出固定落在 <workspace>/ppt/。

---



### 3.17 热键（tag: `hotkeys`，5 个端点）

快捷键清单、校验、批量更新与重置。路径前缀 `/hotkeys`。

#### GET `/api/hotkeys`

**快捷键清单与 revision**

| 项 | 值 |
|---|---|
| op | `hotkeys.list` |
| 分组 / tag | `hotkeys`（热键） |
| handler | `modules.api.controllers.hotkeys:list_hotkeys` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 新增 |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `HotkeyListData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `version` | integer | 否 | 1 | — |
| `revision` | integer | 否 | 0 | — |
| `platform` | string | 否 | "" | — |
| `key_format` | string | 否 | "" | — |
| `actions` | array<HotkeyActionData> | 否 | [] | — |
| `reserved` | array<string> | 否 | [] | — |
| `config_path` | string | 否 | "" | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "version": 1,
    "revision": 8,
    "platform": "",
    "key_format": "",
    "actions": [],
    "reserved": [],
    "config_path": ""
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/hotkeys'
```

---

#### POST `/api/hotkeys/validate`

**录制中实时校验组合键**

| 项 | 值 |
|---|---|
| op | `hotkeys.validate` |
| 分组 / tag | `hotkeys`（热键） |
| handler | `modules.api.controllers.hotkeys:validate_hotkey` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 新增 |

**请求体** `application/json` · `HotkeyValidateRequest`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `combo` | string | 否 | "" | — |
| `action` | string | 否 | "" | — |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `HotkeyValidateData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `valid` | boolean | 否 | false | — |
| `code` | string | 否 | "" | — |
| `reason` | string | 否 | "" | — |
| `normalized` | string | 否 | "" | — |
| `display` | string | 否 | "" | — |
| `conflict_with` | string | 否 | "" | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "valid": true,
    "code": "",
    "reason": "",
    "normalized": "",
    "display": "",
    "conflict_with": ""
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/hotkeys/validate' \
  -H 'Content-Type: application/json' \
  -d '{"combo": "", "action": ""}'
```

---

#### POST `/api/hotkeys/reset`

**恢复默认快捷键**

| 项 | 值 |
|---|---|
| op | `hotkeys.reset` |
| 分组 / tag | `hotkeys`（热键） |
| handler | `modules.api.controllers.hotkeys:reset_hotkeys` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 新增 |

**请求体** `application/json` · `HotkeyResetRequest`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `revision` | integer，可空 | 否 | — | — |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `HotkeyListData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `version` | integer | 否 | 1 | — |
| `revision` | integer | 否 | 0 | — |
| `platform` | string | 否 | "" | — |
| `key_format` | string | 否 | "" | — |
| `actions` | array<HotkeyActionData> | 否 | [] | — |
| `reserved` | array<string> | 否 | [] | — |
| `config_path` | string | 否 | "" | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "version": 1,
    "revision": 8,
    "platform": "",
    "key_format": "",
    "actions": [],
    "reserved": [],
    "config_path": ""
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X POST 'http://127.0.0.1:8000/api/hotkeys/reset' \
  -H 'Content-Type: application/json' \
  -d '{"revision": 8}'
```

---

#### PUT `/api/hotkeys`

**批量更新快捷键**

| 项 | 值 |
|---|---|
| op | `hotkeys.batch_update` |
| 分组 / tag | `hotkeys`（热键） |
| handler | `modules.api.controllers.hotkeys:update_hotkeys` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 新增 |

**请求体** `application/json` · `HotkeyBatchUpdateRequest`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `bindings` | object | 否 | {} | — |
| `revision` | integer，可空 | 否 | — | — |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `HotkeyListData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `version` | integer | 否 | 1 | — |
| `revision` | integer | 否 | 0 | — |
| `platform` | string | 否 | "" | — |
| `key_format` | string | 否 | "" | — |
| `actions` | array<HotkeyActionData> | 否 | [] | — |
| `reserved` | array<string> | 否 | [] | — |
| `config_path` | string | 否 | "" | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "version": 1,
    "revision": 8,
    "platform": "",
    "key_format": "",
    "actions": [],
    "reserved": [],
    "config_path": ""
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X PUT 'http://127.0.0.1:8000/api/hotkeys' \
  -H 'Content-Type: application/json' \
  -d '{"bindings": {}, "revision": 8}'
```

> **备注**：带 revision 乐观并发；冲突 / 保留键 / 过期版本均拒绝且状态不变。

---

#### PUT `/api/hotkeys/{action}`

**更新单个快捷键**

| 项 | 值 |
|---|---|
| op | `hotkeys.update` |
| 分组 / tag | `hotkeys`（热键） |
| handler | `modules.api.controllers.hotkeys:update_hotkey` |
| desktop bridge | 是 |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 新增 |

**路径参数**

| 参数 | 类型 | 说明 |
|---|---|---|
| `action` | string | 路径资源标识 |

**请求体** `application/json` · `HotkeyUpdateRequest`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `combo` | string | 否 | "" | — |
| `revision` | integer，可空 | 否 | — | — |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

`data` · `HotkeyListData`

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `version` | integer | 否 | 1 | — |
| `revision` | integer | 否 | 0 | — |
| `platform` | string | 否 | "" | — |
| `key_format` | string | 否 | "" | — |
| `actions` | array<HotkeyActionData> | 否 | [] | — |
| `reserved` | array<string> | 否 | [] | — |
| `config_path` | string | 否 | "" | — |

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {
    "version": 1,
    "revision": 8,
    "platform": "",
    "key_format": "",
    "actions": [],
    "reserved": [],
    "config_path": ""
  },
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常 / 1002 资源不存在 / 1003 状态冲突（完整映射见 §2.3）。

**请求示例**

```bash
curl -X PUT 'http://127.0.0.1:8000/api/hotkeys/record' \
  -H 'Content-Type: application/json' \
  -d '{"combo": "", "revision": 8}'
```

---



### 3.18 接口目录（tag: `catalog`，1 个端点）

端点清单 + OpenAPI schema，供前端动态表单使用。路径前缀 `/catalog`。

#### GET `/api/catalog`

**端点清单 + OpenAPI schema（动态表单用）**

| 项 | 值 |
|---|---|
| op | `catalog.api` |
| 分组 / tag | `catalog`（接口目录） |
| handler | `modules.api.controllers.catelog:api` |
| desktop bridge | 否（仅 HTTP） |
| dispatch | `loop` |
| 超时 | 60 s |
| 状态 | 新增 |

**响应** `application/json` · 统一信封 `ApiResponse<T>`（见 §2.2）

**示例响应**

```json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {},
  "request_id": "a1b2c3d4e5f6a7b8",
  "ts": 1760000000.0
}
```

**错误码**：1001 参数校验失败 / 2001 依赖未初始化 / 2002 处理超时 / 3001 内部异常（完整映射见 §2.3）。

**请求示例**

```bash
curl 'http://127.0.0.1:8000/api/catalog'
```

> **备注**：返回 {total, groups, endpoints[]}；不计入 desktop bridge op。

---



---

## 4. SSE、WebSocket 与桌面 Bridge

### 4.1 SSE 事件（`text/event-stream`）

`POST /api/chat/stream` 与 `POST /api/progress-stream/{task_id}` 返回 SSE。**目标事件信封已落地**（`response.sse(event, event_name=..., **meta)`）；每帧带 `event:` 行，data 内含 `stream_id`、`request_id`、`seq`、`ts` 与兼容用的 `type`：

~~~text
event: chunk
data: {"type":"chunk","text":"你好","stream_id":"s1","request_id":"r1","seq":1,"ts":1760000000.1}

event: done
data: {"type":"done","session_id":"sess_001","elapsed_ms":1234,"result":{"route":"pure_chat"},"stream_id":"s1","request_id":"r1","seq":3,"ts":1760000001.2}

event: error
data: {"type":"error","code":2002,"error":{"code":2002,"kind":"timeout","message":"处理超时"},"stream_id":"s1","request_id":"r1","seq":4,"ts":1760000001.3}
~~~

| 事件名 | 流 | 语义 |
|---|---|---|
| `chunk` / `progress` / `pending` | chat / progress | 增量帧，`seq` 单调递增 |
| `done` / `finished` | 两者 | 成功终态 |
| `error` | 两者 | 失败终态，data 带 `code` 与结构化 `error` |
| `cancelled` | chat | 客户端断连终态，同时 `ref.cancel()` 向上传播取消 |
| `timeout` | progress | 超过 `STREAM_TIMEOUT` 的终态 |

进度流帧 data 为 `{task_id, status, percent, sent, total, files_done, files_total, error, type, stream_id, request_id, seq, ts}`；`status` 取 `pending` / `running` / `done` / `error` / `cancelled` / `timeout` / `finished`；生产者调用 `greater.set_progress(task_id, data)` 写入，终态到达后 `clear_progress(task_id)`。

约束：每流**恰好一个终态**（done / error / cancelled / timeout）；旧客户端忽略 `event:` 行仍可解析 `data:`；服务端有 max lifetime（600s）；断连传播取消；不伪装支持 replay。

### 4.2 WebSocket

路径 `ws://<host>:<port>/`（`app.websocket("/")` 注册，旧文档的 `/ws` 作废）。

**入站帧** `WebSocketRequest {type, data, client_id, request_id, stream_id}`（由 `model_validate()` 解析 `receive_json()` 返回的 dict）。`type` 必填，取值与 `src/modules/events/types.py::WebSocketEventType` 逐字一致：`websocket.connect` / `websocket.error` / `websocket.heartbeat` / `result` / `chat` / `get_log` 等；前端 `web/typings/enums.ts` 与 `web/typings/types/api.d.ts` 已同步。业务帧的 `data.client_id` 必须与连接分配一致，否则回错误但**不切断连接**；控制帧与心跳不强制该字段。心跳 `websocket.heartbeat` 单独响应，不进入业务派发；空闲 90s 由 `__cleanup_stale_connections()` 清理。

| type | 载荷 | 说明 |
|---|---|---|
| `chat` | `WsChatPayload {text, session_id, source, route}` | 对话 |
| `record.audio_chunk` | `WsAsrPayload {audio(base64), is_final}` | 语音分片 |
| `tts` / `WsTtsPayload` | `{text}` | 语音合成 |
| `download_model` | `WsDownloadModelPayload {model_name, force}` | 本地模型下载 |
| `subscribe` | `{events: string[]}` | 订阅**固定 allowlist**：`get_log` / `get_audit_logs` / `qq_bot.info`；回当前订阅清单 |
| `unsubscribe` | `{events: string[]}` | 退订，回剩余订阅清单 |
| `cancel` | `{request_id}` | 按 request_id 精确取消**本连接**在途任务，回 `{request_id, cancelled}` |

`request_id` 关联单次请求，`stream_id` 关联一条流，两者与 `task_id` 严格区分；帧级字段由 `websocket/context.py` 的 ContextVar 承载，`send_json` / `broadcast` 自动继承，同一连接并发的多条流不会串线。业务帧以独立任务派发并 `track_request()` 绑定，单连接在途上限 8；控制帧即时执行、不占 inflight。

**出站帧** `WebSocketAPIResponse<T> {type, ok, message, data, from_id, request_id, stream_id, ts}`。敏感事件未订阅则直接丢弃（不推送、不报错）。下载事件 DTO：`WsDownloadStartedData`（STARTED）、`WsDownloadProgressData`（RUNNING）、`WsDownloadCompletedData`（COMPLETED）、`WsDownloadFailedData`（FAILED）、`WsDownloadErrorData`（ERROR）；单连接在途下载上限 2。

`model_name` 新格式 `capability:provider[:model_id]`（如 `ocr:paddle`、`image:comfyui-local`），兼容别名 `paddle_ocr → ocr:paddle`、`whisper → asr:whisper`；已安装且未 `force` 直接回 `ERROR "模型已存在"`。

### 4.3 桌面 Bridge

`EndpointLoader.register_gateway()` 把 `desktop=true` 端点注册为 op；`call_sync()` 在无运行中 loop 的线程里复用调度器 loop。Web 与 Qt bridge 已统一：同一信封、同一成功 `code=200`、同一 DTO、同一 decoder（`web/api/http.ts` 判 `ok === true && code === 200`）。

`loader._wrap()` 现在是**契约适配层**：按 `EndpointSpec.http.path` 与 handler 的 `get_type_hints()`，把平铺的 `{pathParams + query + body}` 绑定成具名参数，遇到 Pydantic 请求模型自动 `model_validate()`，校验失败返回 1001（而非过去被兜底成 3001 的 `AttributeError`）。`dispatch=thread/main` 不再把裸 dict 塞给 handler；`dispatch=main` 走 `run_async_on_main_thread()`，本次仍未启用该档位。

`gateway._ok()` 对 `ApiResponse` 直接展开，避免 bridge 出现 `data` 里再套一层信封；未知 op 返回 1002，内部异常只回稳定 message + `request_id`。

### 4.4 shell 与工具命令契约（非独立 HTTP 资源）

- 命令文本由模型直接写原生命令原文，不需要 `shell --command` 包装；只认 `--id`（技能名可重复，id 才唯一）。
- 命中 `shell/commands.py` 白名单且不属于 skill / 已注册服务命令的行，转成 `service="shell", method="run", params={"command":"<整行>"}`；其它行保留为自然语言。
- 平台映射：Windows `cmd.exe /C`，Linux/macOS `/bin/sh -c`；`dir→ls`、`copy→cp`、`del/erase→rm`、`type→cat`、`move→mv`、`cls→clear`。
- 拒绝 `rm` / `rmdir` / `del` / `format` / `mkfs` / `dd` / `shutdown` / `sudo` / `chmod` / `chown` / `kill` / `reg` / `diskpart` 及 `|` `;` `&` 反引号 `>` `>>` 拼接与重定向。
- 执行边界：cwd 锁定工作区、路径经 `realpath` + `is_within` 复验、环境变量净化、超时与输出上限；`shell` / `javascript` 技能暂不支持执行。

---

## 5. 数据模型索引

请求模型位于 `src/modules/api/requests.py`，响应 DTO 位于 `src/modules/api/dto.py`；生成类扩展模型与本次新增 DTO 亦登记于此。字段级定义见 §3 各端点的请求体 / 响应表。

| 模型 | 类别 | 文件 | 字段数 |
|---|---|---|---|
| `ASRRequest` | 请求模型 | requests.py | 3 |
| `CharacterCreateRequest` | 请求模型 | requests.py | 17 |
| `CharacterStateUpdateRequest` | 请求模型 | requests.py | 2 |
| `CharacterUpdateRequest` | 请求模型 | requests.py | 15 |
| `ChatRequest` | 请求模型 | requests.py | 7 |
| `ChatStreamRequest` | 请求模型 | requests.py | 7 |
| `CommandRunRequest` | 请求模型 | requests.py | 2 |
| `ConfigPatchRequest` | 请求模型 | requests.py | 1 |
| `ConfigSaveRequest` | 请求模型 | requests.py | 1 |
| `EmbeddingRequest` | 请求模型 | requests.py | 3 |
| `FlushRequest` | 请求模型 | requests.py | 1 |
| `GcRequest` | 请求模型 | requests.py | 3 |
| `HotkeyBatchUpdateRequest` | 请求模型 | requests.py | 2 |
| `HotkeyResetRequest` | 请求模型 | requests.py | 1 |
| `HotkeyUpdateRequest` | 请求模型 | requests.py | 2 |
| `HotkeyValidateRequest` | 请求模型 | requests.py | 2 |
| `ImageGenerateRequest` | 请求模型 | requests.py | 7 |
| `LogAppendRequest` | 请求模型 | requests.py | 2 |
| `LoggerLevelRequest` | 请求模型 | requests.py | 1 |
| `MemoryActionRequest` | 请求模型 | requests.py | 6 |
| `MemoryLayersRequest` | 请求模型 | requests.py | 4 |
| `MemorySearchRequest` | 请求模型 | requests.py | 3 |
| `MessageAppendRequest` | 请求模型 | requests.py | 3 |
| `OCRRecognizeRequest` | 请求模型 | requests.py | 4 |
| `PptOutlineRequest` | 请求模型 | requests.py | 7 |
| `PptRenderRequest` | 请求模型 | requests.py | 8 |
| `ProviderDownloadRequest` | 请求模型 | requests.py | 2 |
| `ProviderSwitchRequest` | 请求模型 | requests.py | 3 |
| `ServiceConfigUpdateRequest` | 请求模型 | requests.py | 2 |
| `ServiceStartRequest` | 请求模型 | requests.py | 1 |
| `SessionCreateRequest` | 请求模型 | requests.py | 2 |
| `SkillExecuteRequest` | 请求模型 | requests.py | 1 |
| `SlotCreateRequest` | 请求模型 | requests.py | 2 |
| `SlotSectionUpdateRequest` | 请求模型 | requests.py | 2 |
| `SlotSyncRequest` | 请求模型 | requests.py | 1 |
| `SnapshotRequest` | 请求模型 | requests.py | 5 |
| `TTSRequest` | 请求模型 | requests.py | 2 |
| `TaskCancelRequest` | 请求模型 | requests.py | 1 |
| `WebSocketRequest` | 请求模型 | requests.py | 5 |
| `ASRResultData` | 响应 DTO | dto.py | 1 |
| `AbilityStatus` | 响应 DTO | dto.py | 3 |
| `AdapterInfo` | 响应 DTO | dto.py | 3 |
| `AuditServiceData` | 响应 DTO | dto.py | 4 |
| `AuditToolData` | 响应 DTO | dto.py | 5 |
| `AuditTreeData` | 响应 DTO | dto.py | 2 |
| `CPUInfoData` | 响应 DTO | dto.py | 5 |
| `CharacterAttributesData` | 响应 DTO | dto.py | 15 |
| `CharacterInfoData` | 响应 DTO | dto.py | 5 |
| `CharacterListData` | 响应 DTO | dto.py | 3 |
| `CharacterStateData` | 响应 DTO | dto.py | 6 |
| `ChatResultData` | 响应 DTO | dto.py | 7 |
| `CommandResultData` | 响应 DTO | dto.py | 5 |
| `ComponentHealth` | 响应 DTO | dto.py | 2 |
| `CompressedItem` | 响应 DTO | dto.py | 4 |
| `ConfigSchemaItem` | 响应 DTO | dto.py | 3 |
| `DetailedMemoryItem` | 响应 DTO | dto.py | 5 |
| `DeviceInfoData` | 响应 DTO | dto.py | 5 |
| `DownloadStartData` | 响应 DTO | dto.py | 5 |
| `DownloadStatusData` | 响应 DTO | dto.py | 8 |
| `EmbeddingData` | 响应 DTO | dto.py | 4 |
| `GPUInfoData` | 响应 DTO | dto.py | 5 |
| `GcData` | 响应 DTO | dto.py | 3 |
| `GenerationStatusData` | 响应 DTO | dto.py | 7 |
| `HealthData` | 响应 DTO | dto.py | 6 |
| `HotkeyActionData` | 响应 DTO | dto.py | 10 |
| `HotkeyListData` | 响应 DTO | dto.py | 7 |
| `HotkeyValidateData` | 响应 DTO | dto.py | 6 |
| `ImageGenerateData` | 响应 DTO | dto.py | 3 |
| `InfoData` | 响应 DTO | dto.py | 7 |
| `LogAppendData` | 响应 DTO | dto.py | 4 |
| `LogRecordData` | 响应 DTO | dto.py | 5 |
| `LoggerLevelData` | 响应 DTO | dto.py | 2 |
| `LoggerStatsData` | 响应 DTO | dto.py | 9 |
| `MemoryActionData` | 响应 DTO | dto.py | 8 |
| `MemoryCompressedListData` | 响应 DTO | dto.py | 2 |
| `MemoryDecayData` | 响应 DTO | dto.py | 1 |
| `MemoryDeleteData` | 响应 DTO | dto.py | 2 |
| `MemoryFlushData` | 响应 DTO | dto.py | 1 |
| `MemoryLayersData` | 响应 DTO | dto.py | 3 |
| `MemoryLongTermData` | 响应 DTO | dto.py | 3 |
| `MemorySearchData` | 响应 DTO | dto.py | 3 |
| `MemoryShortTermData` | 响应 DTO | dto.py | 2 |
| `MemoryStatsData` | 响应 DTO | dto.py | 5 |
| `MessageItem` | 响应 DTO | dto.py | 4 |
| `MessageListData` | 响应 DTO | dto.py | 2 |
| `OCRResultData` | 响应 DTO | dto.py | 4 |
| `PptDownloadData` | 响应 DTO | dto.py | 4 |
| `PptJobData` | 响应 DTO | dto.py | 4 |
| `PptOutlineData` | 响应 DTO | dto.py | 4 |
| `PptRenderData` | 响应 DTO | dto.py | 7 |
| `PptTemplateData` | 响应 DTO | dto.py | 9 |
| `PptTemplateListData` | 响应 DTO | dto.py | 2 |
| `ProviderInfo` | 响应 DTO | dto.py | 2 |
| `ProviderStatusData` | 响应 DTO | dto.py | 16 |
| `RequestStatusData` | 响应 DTO | dto.py | 4 |
| `ServiceActionData` | 响应 DTO | dto.py | 2 |
| `ServiceInfoData` | 响应 DTO | dto.py | 6 |
| `ServiceListData` | 响应 DTO | dto.py | 2 |
| `ServiceUIDescription` | 响应 DTO | dto.py | 4 |
| `SessionInfoData` | 响应 DTO | dto.py | 7 |
| `SessionListData` | 响应 DTO | dto.py | 3 |
| `SkillExecuteData` | 响应 DTO | dto.py | 4 |
| `SkillInfoData` | 响应 DTO | dto.py | 10 |
| `SkillListData` | 响应 DTO | dto.py | 3 |
| `SlotActionData` | 响应 DTO | dto.py | 2 |
| `SlotInfoData` | 响应 DTO | dto.py | 3 |
| `SlotListData` | 响应 DTO | dto.py | 3 |
| `SlotMeta` | 响应 DTO | dto.py | 5 |
| `SnapshotActionData` | 响应 DTO | dto.py | 6 |
| `SseChunkEvent` | 响应 DTO | dto.py | 6 |
| `SseDoneEvent` | 响应 DTO | dto.py | 10 |
| `SseErrorEvent` | 响应 DTO | dto.py | 7 |
| `SseEventBase` | 响应 DTO | dto.py | 5 |
| `SseProgressEvent` | 响应 DTO | dto.py | 13 |
| `StatsData` | 响应 DTO | dto.py | 5 |
| `SwitchResultData` | 响应 DTO | dto.py | 6 |
| `TTSResultData` | 响应 DTO | dto.py | 3 |
| `TaskStatusData` | 响应 DTO | dto.py | 5 |
| `ToolData` | 响应 DTO | dto.py | 2 |
| `WsDownloadCompletedData` | 响应 DTO | dto.py | 3 |
| `WsDownloadErrorData` | 响应 DTO | dto.py | 2 |
| `WsDownloadFailedData` | 响应 DTO | dto.py | 3 |
| `WsDownloadProgressData` | 响应 DTO | dto.py | 4 |
| `WsDownloadStartedData` | 响应 DTO | dto.py | 5 |

---

## 附录 A：端点速查表

| 分组 | 方法 | 最终 URL | op | 状态 |
|---|---|---|---|---|
| `generate` | GET | `/api/status` | `generate.status` | 新增 |
| `generate` | POST | `/api/chat` | `generate.chat` | 新增 |
| `generate` | POST | `/api/chat/stream` | `generate.chat_stream` | 新增 |
| `generate` | POST | `/api/tts` | `generate.tts` | 新增 |
| `generate` | POST | `/api/asr` | `generate.asr` | 新增 |
| `generate` | POST | `/api/image/generations` | `generate.image` | 新增 |
| `generate` | POST | `/api/ocr` | `generate.ocr` | 新增 |
| `generate` | POST | `/api/embedding` | `generate.embedding` | 新增 |
| `generate` | POST | `/api/command` | `generate.command` | 新增 |
| `generate` | GET | `/api/folder/{type}` | `generate.open_folder` | 新增 |
| `generate` | POST | `/api/progress-stream/{task_id}` | `generate.progress_stream` | 修正 |
| `system` | GET | `/api/system/health` | `system.health` | 现行 |
| `system` | GET | `/api/system/info` | `system.info` | 现行 |
| `system` | GET | `/api/system/stats` | `system.stats` | 现行 |
| `system` | POST | `/api/system/gc` | `system.gc` | 现行 |
| `system` | GET | `/api/system/ping` | `system.ping` | 现行 |
| `config` | GET | `/api/config` | `config.get` | 现行 |
| `config` | GET | `/api/config/schema` | `config.schema` | 现行 |
| `config` | POST | `/api/config/reload` | `config.reload` | 现行 |
| `config` | POST | `/api/config/save` | `config.save` | 现行 |
| `config` | PATCH | `/api/config/{section}` | `config.patch_section` | 现行 |
| `logger` | GET | `/api/logger/level` | `logger.get_level` | 新增 |
| `logger` | PUT | `/api/logger/level` | `logger.set_level` | 新增 |
| `logger` | GET | `/api/logger/levels` | `logger.list_levels` | 新增 |
| `logger` | GET | `/api/logger/stats` | `logger.stats` | 新增 |
| `logger` | GET | `/api/logger/records` | `logger.records` | 新增 |
| `logger` | POST | `/api/logger/flush` | `logger.flush` | 新增 |
| `logger` | POST | `/api/logger/append` | `logger.append` | 新增 |
| `device` | GET | `/api/device/info` | `device.info` | 新增 |
| `provider` | GET | `/api/provider/adapters` | `provider.list_adapters` | 新增 |
| `provider` | GET | `/api/provider/configs` | `provider.all_configs` | 新增 |
| `provider` | GET | `/api/provider/adapters/{adapter}/providers` | `provider.list_providers` | 新增 |
| `provider` | GET | `/api/provider/adapters/{adapter}/providers/{provider}` | `provider.get` | 新增 |
| `provider` | GET | `/api/provider/adapters/{adapter}/providers/{provider}/status` | `provider.status` | 新增 |
| `provider` | POST | `/api/provider/adapters/{adapter}/switch` | `provider.switch` | 新增 |
| `provider` | POST | `/api/provider/adapters/{adapter}/stop` | `provider.stop` | 新增 |
| `provider` | POST | `/api/provider/adapters/{adapter}/providers/{provider}/download` | `provider.download` | 新增 |
| `service` | GET | `/api/service` | `service.list` | 现行 |
| `service` | GET | `/api/service/tools` | `service.list_tools` | 现行 |
| `service` | GET | `/api/service/{service_id}` | `service.get` | 现行 |
| `service` | GET | `/api/service/{service_id}/tools` | `service.tools` | 现行 |
| `service` | GET | `/api/service/{service_id}/ui` | `service.ui` | 现行 |
| `service` | POST | `/api/service/{service_id}/register` | `service.register` | 新增 |
| `service` | POST | `/api/service/{service_id}/start` | `service.start` | 现行 |
| `service` | POST | `/api/service/{service_id}/stop` | `service.stop` | 现行 |
| `service` | GET | `/api/service/{service_id}/config` | `service.get_config` | 现行 |
| `service` | PUT | `/api/service/{service_id}/config` | `service.update_config` | 现行 |
| `service` | PUT | `/api/service/{service_id}/config/apply` | `service.apply_config` | 现行 |
| `skill` | GET | `/api/skill` | `skill.list` | 现行 |
| `skill` | GET | `/api/skill/prompt` | `skill.prompt` | 现行 |
| `skill` | POST | `/api/skill/reload` | `skill.reload` | 现行 |
| `skill` | GET | `/api/skill/{skill_id}` | `skill.get` | 现行 |
| `skill` | POST | `/api/skill/{skill_id}/activate` | `skill.activate` | 现行 |
| `skill` | POST | `/api/skill/{skill_id}/deactivate` | `skill.deactivate` | 现行 |
| `skill` | POST | `/api/skill/{skill_id}/execute` | `skill.execute` | 现行 |
| `workspace` | GET | `/api/workspace` | `workspace.info` | 新增 |
| `workspace` | POST | `/api/workspace/select` | `workspace.select` | 新增 |
| `workspace` | POST | `/api/workspace/confirm` | `workspace.confirm` | 新增 |
| `workspace` | DELETE | `/api/workspace` | `workspace.clear` | 新增 |
| `audit` | GET | `/api/audit/tree` | `audit.tree` | 新增 |
| `audit` | GET | `/api/audit/tools` | `audit.tools` | 新增 |
| `session` | GET | `/api/session` | `session.list` | 现行 |
| `session` | POST | `/api/session` | `session.create` | 现行 |
| `session` | POST | `/api/session/flush` | `session.flush` | 现行 |
| `session` | GET | `/api/session/{session_id}` | `session.get` | 现行 |
| `session` | DELETE | `/api/session/{session_id}` | `session.delete` | 现行 |
| `session` | POST | `/api/session/{session_id}/switch` | `session.switch` | 现行 |
| `session` | GET | `/api/session/{session_id}/messages` | `session.messages` | 现行 |
| `session` | POST | `/api/session/{session_id}/messages` | `session.append` | 现行 |
| `save` | GET | `/api/save` | `save.all` | 新增 |
| `save` | GET | `/api/save/snapshot/status` | `save.snapshot_status` | 新增 |
| `save` | GET | `/api/save/snapshot/graph` | `save.snapshot_graph` | 新增 |
| `save` | POST | `/api/save/snapshot/preview` | `save.snapshot_preview` | 新增 |
| `save` | POST | `/api/save/snapshot` | `save.snapshot` | 新增 |
| `save` | POST | `/api/save/snapshot/restore` | `save.snapshot_restore` | 新增 |
| `save` | GET | `/api/save/slots` | `save.list_slots` | 修正 |
| `save` | POST | `/api/save/slots` | `save.create` | 修正 |
| `save` | POST | `/api/save/slots/sync` | `save.sync` | 修正 |
| `save` | POST | `/api/save/slots/restore` | `save.restore` | 修正 |
| `save` | GET | `/api/save/slots/{slot_id}` | `save.get` | 修正 |
| `save` | DELETE | `/api/save/slots/{slot_id}` | `save.delete` | 修正 |
| `save` | POST | `/api/save/slots/{slot_id}/toggle` | `save.toggle` | 修正 |
| `save` | POST | `/api/save/slots/{slot_id}/save` | `save.save` | 修正 |
| `save` | POST | `/api/save/slots/{slot_id}/load` | `save.load` | 修正 |
| `save` | PUT | `/api/save/slots/{slot_id}/section` | `save.update_section` | 修正 |
| `character` | GET | `/api/character` | `character.list` | 新增 |
| `character` | GET | `/api/character/presets` | `character.presets` | 新增 |
| `character` | GET | `/api/character/current` | `character.current` | 新增 |
| `character` | POST | `/api/character` | `character.create` | 新增 |
| `character` | GET | `/api/character/{character_id}` | `character.get` | 新增 |
| `character` | PUT | `/api/character/{character_id}` | `character.update` | 新增 |
| `character` | DELETE | `/api/character/{character_id}` | `character.delete` | 现行 |
| `character` | POST | `/api/character/{character_id}/switch` | `character.switch` | 现行 |
| `character` | GET | `/api/character/{character_id}/state` | `character.get_state` | 现行 |
| `character` | PUT | `/api/character/{character_id}/state` | `character.update_state` | 现行 |
| `memory` | GET | `/api/memory/layers` | `memory.layers` | 新增 |
| `memory` | GET | `/api/memory/short` | `memory.short_term` | 新增 |
| `memory` | GET | `/api/memory/long` | `memory.long_term` | 新增 |
| `memory` | POST | `/api/memory/search` | `memory.search` | 新增 |
| `memory` | GET | `/api/memory/compressed` | `memory.compressed` | 新增 |
| `memory` | GET | `/api/memory/stats` | `memory.stats` | 新增 |
| `memory` | POST | `/api/memory/decay` | `memory.decay` | 新增 |
| `memory` | POST | `/api/memory/flush` | `memory.flush` | 新增 |
| `memory` | POST | `/api/memory/retention` | `memory.retention` | 新增 |
| `memory` | POST | `/api/memory/pin` | `memory.pin` | 新增 |
| `memory` | POST | `/api/memory/revive` | `memory.revive` | 新增 |
| `memory` | DELETE | `/api/memory/{memory_id}` | `memory.delete` | 新增 |
| `task` | GET | `/api/task/{task_id}` | `task.get` | 新增 |
| `task` | POST | `/api/task/{task_id}/cancel` | `task.cancel` | 新增 |
| `ppt` | GET | `/api/ppt/templates` | `ppt.templates` | 新增 |
| `ppt` | POST | `/api/ppt/outline` | `ppt.outline` | 新增 |
| `ppt` | POST | `/api/ppt/render` | `ppt.render` | 新增 |
| `ppt` | POST | `/api/ppt/render/async` | `ppt.render_async` | 新增 |
| `ppt` | GET | `/api/ppt/job/{task_id}` | `ppt.status` | 新增 |
| `ppt` | GET | `/api/ppt/download/{file_name}` | `ppt.download` | 新增 |
| `hotkeys` | GET | `/api/hotkeys` | `hotkeys.list` | 新增 |
| `hotkeys` | POST | `/api/hotkeys/validate` | `hotkeys.validate` | 新增 |
| `hotkeys` | POST | `/api/hotkeys/reset` | `hotkeys.reset` | 新增 |
| `hotkeys` | PUT | `/api/hotkeys` | `hotkeys.batch_update` | 新增 |
| `hotkeys` | PUT | `/api/hotkeys/{action}` | `hotkeys.update` | 新增 |
| `catalog` | GET | `/api/catalog` | `catalog.api` | 新增 |

---

## 附录 B：架构文档索引

- [BackendDesign.md](BackendDesign.md)：模块边界、线程模型、工具链、shell 服务与工作区。
- [SecurityAndAuditDesign.md](SecurityAndAuditDesign.md)：威胁模型、工作区权限、命令准入、审计事件。
- [FrontendBackendContract.md](FrontendBackendContract.md)：REST / SSE / WS / Qt bridge 统一契约。
- [ContextArchitecture.md](ContextArchitecture.md)：session-scoped context 与 prompt 装配。
- [GameSaveArchitecture.md](GameSaveArchitecture.md)：Slot / Snapshot / restore。
- [MemoryDesign.md](MemoryDesign.md)：记忆查询、删改与向量一致性。
- [ArchitectureDecisionRecords.md](ArchitectureDecisionRecords.md)：ADR-002 契约唯一权威源。
