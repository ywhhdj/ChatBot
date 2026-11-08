# ChatBot API 契约（dev 分支现行基线）

> 权威来源：`resources/config/api/endpoints.json`（89 个启用端点）+ `api/loader.py` + `api/gateway.py` + `api/response.py` / `exceptions.py` + `src/api/services/*`。
>
> 本文按**现行源码**整理，并标注本次改造的落地项。「目标/待办」单列，不混写成已实现。不运行项目、不导出 OpenAPI，路径以 `endpoints.json` + 注册器前缀为准。
>
> **本次重构**：
> - 对话 / 语音 / 进度等请求端点由 `controllers/request.py` 迁入 `controllers/pipline.py`，op 前缀统一为 `pipline.*`。
> - 供应商（adapter / provider / 切换 / 配置 / 状态 / 下载）统一归入 `controllers/providers.py`，op 前缀统一为 `providers.*`。
> - 请求模型（`requests.py`）与响应 DTO（`dto.py`）按控制器重新分组，WebSocket 帧复用同一套 DTO。

---

## 0. 通用约定

### 0.1 路由前缀与注册机制

```
endpoints.json（每项含 op / handler / http{method,path} / tags / desktop / dispatch）
   │  EndpointLoader.build_router()  → add_api_route(spec.http.path, handler)
   ▼
register_all_routers(app, prefix="/api")     ← /api 只在这里加一次
```

- 表中「资源路径」= `spec.http.path`；**最终 URL = `/api` + 资源路径**。
- `controllers/*.py` 内声明的 `APIRouter(prefix=...)` 是历史遗留，当前 `all_routers()` 只返回 loader 生成的 router，不会被 include。
- `EndpointLoader._validate()` 启动期校验 handler 可 import、`METHOD + path` 不冲突。
- `handler` 形如 `modules.api.controllers.<module>:<func>`；`desktop=true` 的端点同时注册为 `ApiGateway` 的 op，桌面 Bridge 直接 `call(op)`。
- `dispatch`：`loop`（默认）/ `thread`（`asyncio.to_thread`）/ `main`（Qt 主线程派发）。

### 0.2 REST 响应信封

~~~json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {},
  "request_id": "16-char-id",
  "ts": 1757000000.123
}
~~~

- 成功业务 `code = 200`（`exceptions.py::CODE_OK`）；前端普通 Axios 分支判 `code === 200`。
- 失败时 HTTP status 语义化，body 仍是同构信封。
- `X-Request-ID` 由中间件注入 contextvar 并回写响应头；外部传入需限制长度/字符集。
- `ts` 为 Unix 秒（float）。
- 桌面 bridge 分支 `src/api/http.ts` 判 `code === 0` 与后端不一致，为 **P0 待办**，需共用 decoder。

### 0.3 错误码（源码为准）

| code | HTTP | 含义 | 客户端建议 |
|---:|---:|---|---|
| 200 | 200 | 成功 | 读取 `data` |
| 1001 | 400 | 参数校验失败 | 修正输入 |
| 1002 | 404 | 资源不存在 | 刷新资源或确认 ID |
| 1003 | 409 | 状态冲突 | 查询当前状态后决定 |
| 2001 | 503 | 依赖未初始化 | 配置/初始化依赖 |
| 2002 | 504 | 处理超时 | 先查任务状态；仅幂等操作可重试 |
| 3001 | 500 | 内部异常 | 用 `request_id` 排障 |
| 3002 | 503 | 主线程忙或不可用 | 稍后重试 |

不要把业务 `code` 与 HTTP status 混为一谈。所有调用端使用同一成功 code 与同一解包规则。

> 待办：`response.py::_unhandled_handler` 当前把 `type(exc).__name__: exc` 放进 `message`，应改为稳定通用信息 + `request_id`，详情写脱敏日志。`config` 类接口的 `raw=true` 原文回显应移除或限制到本地受控调试。

### 0.4 长任务

模型下载、PPT 生成等长操作返回 `task_id`，通过 `/api/task/{task_id}` 或 `/api/ppt/job/{task_id}` 查询。取消对同步线程不保证强制终止，超时只标记放弃等待。

### 0.5 通用安全约束

- 默认只绑定 `127.0.0.1`；远程监听必须显式启用认证与严格来源限制。
- chat / audio / 文件 / PPT / 工具请求限制 body size、超时、并发与输出大小。
- 产出文件只接受 `basename`，且必须落在 `security/workspace` 判定的工作区内。
- 日志不保存 key、完整 prompt、音频或私人记忆正文。

---

## 1. 系统与配置

### System（tag: system）

| 方法 | 资源路径 | op | 说明 |
|---|---|---|---|
| GET | `/system/health` | `system.health` | Web、调度器、主线程、记忆与服务健康状态 |
| GET | `/system/info` | `system.info` | 版本、配置路径、数据目录 |
| GET | `/system/stats` | `system.stats` | uptime、日志、任务、连接与记忆统计 |
| POST | `/system/gc` | `system.gc` | 触发记忆衰减/清理及日志排空 |
| GET | `/system/ping` | `system.ping` | 轻量探测 |

健康检查不得触发模型加载、全量索引重建或全盘扫描。

### Config（tag: config）

| 方法 | 资源路径 | op | 说明 |
|---|---|---|---|
| GET | `/config` | `config.get_config_api` | 读取配置；可按 section 查询 |
| PATCH | `/config/{section}` | `config.patch_section` | 局部更新配置 |
| POST | `/config/reload` | `config.reload` | 从配置文件重新加载 |
| POST | `/config/save` | `config.save` | 持久化配置 |
| GET | `/config/schema` | `config.schema` | 配置字段描述 |

配置涉及密钥时默认遮蔽；不要在 URL、日志或前端持久化明文凭据。

**请求/响应模型**：

- `ConfigPatchRequest {values: Dict[str, Any]}` / 或直接 body 传字段。
- `ConfigSaveRequest {file_path: Optional[str]}`。
- 响应 `data` 为按 section 归集的配置 dict；`schema` 响应为 `{section: [ConfigSchemaItem]}`。

### Logger（tag: logger）

| 方法 | 资源路径 | op |
|---|---|---|
| GET | `/logger/level` | `logger.get_level` |
| PUT | `/logger/level` | `logger.set_level` |
| GET | `/logger/levels` | `logger.list_levels` |
| GET | `/logger/stats` | `logger.stats` |
| GET | `/logger/records` | `logger.records` |
| POST | `/logger/flush` | `logger.flush` |

**请求/响应模型**：

- `PUT /logger/level`：`LoggerLevelRequest {level: str}`。
- 响应：`LoggerLevelData` / `LoggerStatsData` / `{records: [LogRecordData], total, capacity}`。

### Device（tag: device）

| 方法 | 资源路径 | op | 说明 |
|---|---|---|---|
| GET | `/device/info` | `device.device_info` | 设备/平台信息 |

**响应 DTO**：`DeviceInfoData {cpu: CPUInfoData, gpu: GPUInfoData, overall: Dict, recommended_fps: int, ram_mb: int}`。

---

## 2. 供应商、服务、技能与工作区

### Provider（tag: provider，handler 模块 `controllers/providers.py`）

> 本次重构：adapter / provider / 切换 / 配置 / 状态 / 下载全部由 `providers.py` 提供，op 前缀 `providers.*`。

| 方法 | 资源路径 | op | 说明 |
|---|---|---|---|
| GET | `/pipeline/adapters` | `providers.list_adapters` | adapter 类型、provider 列表、当前 provider / 模型、累计用量 |
| GET | `/pipeline/adapters/{adapter}/providers` | `providers.list_providers` | 某 adapter 的 provider 列表（label / deployment / models） |
| GET | `/pipeline/adapters/{adapter}/providers/{provider}` | `providers.get_provider` | 读取 provider 配置（敏感字段已掩码） |
| GET | `/pipeline/adapters/{adapter}/providers/{provider}/status` | `providers.status` | provider 完整状态，含本地模型文件状态 |
| POST | `/pipeline/adapters/{adapter}/switch` | `providers.switch` | 切换 provider（可指定 `model_id` 与配置覆盖） |
| POST | `/pipeline/adapters/{adapter}/stop` | `providers.stop_adapter` | 停止当前 provider，保留门面 |
| POST | `/pipeline/adapters/{adapter}/providers/{provider}/download` | `providers.download_model` | 触发本地模型下载；进度走 WebSocket |
| GET | `/pipeline/configs` | `providers.all_configs` | 各能力供应商配置（已掩码） |

**请求模型**：

- `ProviderSwitchRequest {provider: str, config: Optional[Dict], model_id: Optional[str]}`。
- `ProviderDownloadRequest {model_id: Optional[str], force: bool}`。

**响应 DTO**：

- `AdapterInfo` / `SwitchResultData` / `ProviderStatusData {capability, name, label, deployment, transport, protocol, runtime, selected_model, models, params, ui, download, download_status: DownloadStatusData, available, missing_env, warnings}`。
- `DownloadStartData {task_id, capability, provider, model_id, status}`。

> 切换应先初始化新实例并健康检查，成功后才切流量；下载进度通过 WebSocket `DOWNLOAD_MODEL` 事件回传（见 §6）。已安装且未 `force` 时直接返回 `ERROR "模型已存在"`。

### Service（tag: service）

| 方法 | 资源路径 | op | 说明 |
|---|---|---|---|
| GET | `/service` | `service.list_services` | 服务列表（支持 `running_only`） |
| GET | `/service/tools` | `service.list_tools` | 所有服务工具定义 |
| GET | `/service/{service_id}` | `service.get_service` | 服务详情 |
| GET | `/service/{service_id}/tools` | `service.service_tools` | 单服务工具定义 |
| GET | `/service/{service_id}/ui` | `service.service_ui` | 服务 UI 描述 |
| POST | `/service/{service_id}/start` | `service.start_service` | 启动服务 |
| POST | `/service/{service_id}/stop` | `service.stop_service` | 停止服务 |
| GET | `/service/{service_id}/config` | `service.get_config` | 读取服务配置 |
| PUT | `/service/{service_id}/config` | `service.update_config` | 更新服务配置 |
| PUT | `/service/{service_id}/config/apply` | `service.apply_config` | 应用配置（停 → 启） |

服务状态：`created / running / stopped / not_enabled / error`。现行服务 id：`browser`、`live2d`、`obs`、`qqbot`、`ppt`、`shell`。

> 本次修复：`start_service` 原先把"已注册"当作可启动条件、并在注册前读取服务状态（必然抛错）；现改为未注册才注册、已运行才拒绝。

**请求/响应模型**：

- `ServiceStartRequest {kwargs: Optional[Dict]}`。
- 响应：`ServiceInfoData` / `ServiceListData` / `ToolData` / `ServiceActionData {id, state}` / `ServiceUIDescription`。

### Skill（tag: skill）

| 方法 | 资源路径 | op | 说明 |
|---|---|---|---|
| GET | `/skill` | `skill.list_skills` | 技能列表（支持 `active_only`） |
| GET | `/skill/prompt` | `skill.prompt` | 给模型使用的技能提示词 |
| GET | `/skill/{skill_id}` | `skill.get_skill` | 技能详情 |
| POST | `/skill/reload` | `skill.reload` | 重新扫描技能目录 |
| POST | `/skill/{skill_id}/activate` | `skill.activate` | 启用技能 |
| POST | `/skill/{skill_id}/deactivate` | `skill.deactivate` | 停用技能 |
| POST | `/skill/{skill_id}/execute` | `skill.execute` | 执行技能（超时 30s） |

- 命令文本只认 `--id`（技能名可重复，id 才唯一）。
- `shell` / `javascript` 类型技能**仍不支持执行**：可识别、可见、可启用，执行时返回明确"不支持"，不会被静默当作无脚本。
- 技能执行体跑在 AST 白名单沙盒，输出经 `security/workspace` 限制到 `<workspace>/skill/<skill_id>/`。

**请求/响应模型**：`SkillExecuteRequest {params: Dict}`；响应 `SkillListData` / `SkillInfoData` / `SkillExecuteData {id, ok, result, error}`。

### Workspace（tag: workspace）

工作区是 `security/workspace.py` 的对外控制面，所有服务产出与 shell 命令都受它约束。

| 方法 | 资源路径 | op | 说明 |
|---|---|---|---|
| GET | `/workspace` | `workspace.info` | 当前工作区：root 标签、mode、是否已确认敏感、输出目录 |
| POST | `/workspace/select` | `workspace.select` | 选择目录与档位（`root`、`mode`） |
| POST | `/workspace/confirm` | `workspace.confirm` | 显式确认敏感原文暴露（`confirmation_id`） |
| DELETE | `/workspace` | `workspace.clear` | 撤销选择，回到默认工作区 |

`mode`：`read_only` / `writable` / `unrestricted`。未选择时系统惰性使用默认工作区 `<用户数据目录>/workspace`（`writable`）。

### Audit（tag: audit）

| 方法 | 资源路径 | op | 说明 |
|---|---|---|---|
| GET | `/audit/tree` | `audit.tree` | 服务 → 方法 → 参数 能力树（带运行状态） |
| GET | `/audit/tools` | `audit.tools` | 扁平工具清单 |

**响应 DTO**：`AuditTreeData {services: [AuditServiceData], total_tools}`；`AuditToolData {service, method, label, parameters, required}`。

> audit controller 呈现的是**可调用能力目录**，不是完整的安全事件审计日志。审计事件 schema 见 [SecurityAndAuditDesign.md](SecurityAndAuditDesign.md) §5。

---

## 3. 对话、语音与进度（tag: pipline，handler 模块 `controllers/pipline.py`）

> 本次重构：对话、TTS、ASR、状态、目录打开、进度流从 `controllers/request.py` 迁入 `controllers/pipline.py`；op 前缀统一为 `pipline.*`。所有端点使用 `requests.py` 请求模型与 `dto.py` 响应模型。

| 方法 | 资源路径 | op | 说明 |
|---|---|---|---|
| GET | `/status` | `pipline.status` | LLM/TTS/ASR 就绪状态 |
| GET | `/folder/{type}` | `pipline.open_folder` | 打开受支持的本地目录；必须限制 `type` |
| POST | `/chat` | `pipline.chat_once` | 非流式对话 |
| POST | `/chat/stream` | `pipline.chat_stream` | SSE 流式对话 |
| POST | `/tts` | `pipline.tts` | 文本转语音 |
| POST | `/asr` | `pipline.asr` | base64 音频转文字 |
| POST | `/progress-stream/{task_id}` | `pipline.progress_stream` | 任务进度流 |

**请求模型**（`requests.py`）：

```python
class ChatRequest(_Base):
    text: str
    source: Literal["text", "asr", "ocr"] = "text"
    session_id: str = "default"
    route: Optional[str] = None          # pure_chat | tool_call | mixed
    stream: bool = False
    max_tokens: int = 1024
    temperature: float = 0.7

class TTSRequest(_Base):
    text: str
    format: str = "mp3"

class ASRRequest(_Base):
    audio: str                            # base64
    format: str = "wav"
    is_final: bool = True
```

**响应 DTO**（`dto.py`）：

- `RequestStatusData {llm: AbilityStatus, tts: AbilityStatus, asr: AbilityStatus, ready: bool}`。
- `ChatResultData {text, route, character_id, mood, commands_executed, tokens_estimate, elapsed_ms}`。
- `TTSResultData {audio: base64, format, bytes}`。
- `ASRResultData {text}`。

**SSE 事件**（`text/event-stream`）：

```
data: {"type": "chunk", "text": "..."}
data: {"type": "done", "session_id": "...", "elapsed_ms": 1234}
data: {"type": "error", "message": "..."}
```

- 非流式对话常用字段：`text`、`source`、`session_id`、`route`、`stream`；`route` 逻辑枚举 `pure_chat` / `tool_call` / `mixed`。
- 旧文档出现过 `/api/request/chat/stream` 示例，属于路径笔误；注册器统一路径为 `/api/chat/stream`。
- TTS/ASR 用 base64 时必须限制请求体、音频时长、格式与解码资源；日志不记录音频内容。

---

## 4. 会话、存档、角色与记忆

### Session（tag: session）

| 方法 | 资源路径 | op |
|---|---|---|
| GET | `/session` | `session.list_sessions` |
| POST | `/session` | `session.create_session` |
| GET | `/session/{session_id}` | `session.get_session` |
| DELETE | `/session/{session_id}` | `session.delete_session` |
| POST | `/session/{session_id}/switch` | `session.switch_session` |
| GET | `/session/{session_id}/messages` | `session.messages` |
| POST | `/session/{session_id}/messages` | `session.append_message` |
| POST | `/session/flush` | `session.flush` |

**请求模型**：`SessionCreateRequest {name, character_id}` / `MessageAppendRequest {role, content, source}` / `FlushRequest {session_id: Optional}`。

**响应 DTO**：`SessionInfoData` / `SessionListData` / `MessageItem` / `MessageListData`。

### Save（tag: save，本次修正重复前缀）

| 方法 | 资源路径（修正后） | op | 说明 |
|---|---|---|---|
| GET | `/save/slots` | `save.list_slots` | 存档槽列表 |
| POST | `/save/slots` | `save.create_slot` | 创建存档槽 |
| GET | `/save/slots/{slot_id}` | `save.get_slot` | 存档详情 |
| DELETE | `/save/slots/{slot_id}` | `save.delete_slot` | 删除存档槽 |
| POST | `/save/slots/{slot_id}/toggle` | `save.toggle_slot` | 切换存档 |
| POST | `/save/slots/{slot_id}/save` | `save.save_slot` | 保存存档 |
| POST | `/save/slots/{slot_id}/load` | `save.load_slot` | 加载存档 |

> **本次修复**：`endpoints.json` 原来把这 7 条写成 `/api/save/slots...`，`register_all_routers` 再加 `/api`，实际 URL 变成 `/api/api/save/slots...`，与前端 `src/api/services/save.ts` 不符。现统一为资源相对路径，最终 `/api/save/slots...`。
>
> **待办**：前端 `save.ts` 还有 `restore` / `sync` / `section` 三个方法，后端未注册，需补实现或移除客户端方法。

**请求模型**：`SlotCreateRequest {name, slot_id: Optional}` / `SlotSectionUpdateRequest {data, slot_id}` / `SlotSyncRequest {session_id: Optional}`。

**响应 DTO**：`SlotInfoData {id, name, meta: SlotMeta}` / `SlotListData` / `SlotActionData {id, ok}`。

### Character（tag: character）

| 方法 | 资源路径 | op |
|---|---|---|
| DELETE | `/character/{character_id}` | `character.delete_character` |
| POST | `/character/{character_id}/switch` | `character.switch_character` |
| GET | `/character/{character_id}/state` | `character.get_state` |
| POST | `/character/{character_id}/state` | `character.update_state` |

**请求模型**：`CharacterCreateRequest` / `CharacterUpdateRequest` / `CharacterStateUpdateRequest {mood, affection}`。

**响应 DTO**：`CharacterInfoData {id, name, status, attributes, state}` / `CharacterListData` / `CharacterStateData` / `CharacterAttributesData`。

> 待办：`groups.json` 还声明了 `character.presets` / `character.current` / `character.get` / `character.update` 等 op，当前 `endpoints.json` 未注册，需以端点清单为准。

### Memory（tag: memory）

| 方法 | 资源路径 | op | 说明 |
|---|---|---|---|
| GET | `/ memory/layers` | `memory.layers` | short_term / long_term / detailed |
| GET | `/ memory/short` | `memory.short_term` | 短期记忆摘要 |
| GET | `/ memory/long` | `memory.long_term` | 长期记忆 |
| POST | `/ memory/search` | `memory.search` | 语义/相关记忆搜索 |
| GET | `/ memory/compressed` | `memory.compressed` | 压缩记忆 |
| GET | `/ memory/stats` | `memory.stats` | 容量统计 |
| POST | `/ memory/decay` | `memory.decay` | 手动触发衰减 |
| POST | `/ memory/flush` | `memory.flush` | 等待后台写入 |
| DELETE | `/ memory/{memory_id}` | `memory.delete_memory` | 删除单条记忆 |

**请求模型**：`MemorySearchRequest {query, top_k, session_id}` / `MemoryLayersRequest`。

**响应 DTO**：`MemoryLayersData` / `MemorySearchData` / `MemoryStatsData` / `DetailedMemoryItem` / `CompressedItem`。

所有记忆 API 必须在存储查询**前**按 session 范围过滤；删除语义见 [MemoryDesign.md](MemoryDesign.md)。

---

## 5. 任务与 PPT

### Task（tag: task）

| 方法 | 资源路径 | op |
|---|---|---|
| GET | `/task/{task_id}` | `task.get_task` |
| POST | `/task/{task_id}/cancel` | `task.cancel_task` |

**请求模型**：`TaskCancelRequest {reason: str}`。

**响应 DTO**：`TaskStatusData {task_id, state, result, error, elapsed_ms}`。

### PPT（tag: ppt，本次补齐注册）

| 方法 | 资源路径 | op | 说明 |
|---|---|---|---|
| GET | `/ppt/templates` | `ppt.templates` | 模板列表 |
| POST | `/ppt/outline` | `ppt.outline` | 生成内容大纲（不渲染） |
| POST | `/ppt/render` | `ppt.render` | 提交后台任务，返回 `task_id` |
| POST | `/ppt/render/async` | `ppt.render_async` | 提交后台任务 |
| GET | `/ppt/job/{task_id}` | `ppt.status` | 查询生成任务 |
| GET | `/ppt/download/{file_name}` | `ppt.download` | 取回产出文件（base64 + 路径） |

- 请求 DTO：`PptOutlineRequest {topic, pages, template_id, audience, scenario, style, material}` / `PptRenderRequest {deck, topic, pages, template_id, style, colors, file_name, material}`。
- 响应 DTO：`PptTemplateListData` / `PptOutlineData` / `PptRenderData {ok, task_id, ...}` / `PptJobData` / `PptDownloadData {file_name, file_path, size, content_base64}`。
- **产出目录固定为 `<workspace>/ppt/`**（`security.workspace.service_output_dir("ppt")`）。
- 下载只接受 `basename`，并再次经工作区边界复验；不接受任意绝对路径。

> `groups.json` 里存在 `ppt.*` 声明但 `endpoints.json` 原先无条目，导致 PPT HTTP 接口实际未注册；本次补齐 6 条。

---

## 6. WebSocket 事件契约

路径：`ws://<host>:<port>/`。

### 6.1 帧协议（统一 DTO）

**入站帧**（`requests.py`）：

```python
class WebSocketRequest(_Base):
    type: str
    data: Dict[str, Any] = Field(default_factory=dict)
    client_id: str = ""

class WsChatPayload(_Base):
    text: str = ""
    session_id: str = "default"
    source: str = "text"
    route: Optional[str] = None

class WsAsrPayload(_Base):
    audio: str = ""            # base64
    is_final: bool = True

class WsTtsPayload(_Base):
    text: str = ""

class WsCommandPayload(_Base):
    text: str = ""

class WsSubscribePayload(_Base):
    events: List[str] = Field(default_factory=list)

class WsCancelPayload(_Base):
    request_id: str = ""

class WsDownloadModelPayload(_Base):
    model_name: str = ""        # "ocr:paddle" / "ocr:paddle:ppocr" / 别名
    force: bool = False
```

**出站帧**（`response.py`）：

```python
class WebSocketAPIResponse(Base, Generic[T]):
    type: str
    ok: bool = True
    message: str = "ok"
    data: Optional[T] = None
    from_id: Optional[str] = None
```

**下载事件 DTO**（`dto.py`）：

```python
class WsDownloadStartedData:      # type=STARTED
    model: str = ""
    capability: str = ""
    provider: str = ""
    model_id: str = ""
    task_id: str = ""

class WsDownloadProgressData:     # type=RUNNING
    model: str = ""
    progress: float = 0.0
    file: str = ""
    phase: str = "download"       # download | extract

class WsDownloadCompletedData:    # type=COMPLETED
    model: str = ""
    target_dir: str = ""
    items: List[Dict[str, Any]] = []

class WsDownloadFailedData:       # type=FAILED
    model: str = ""
    error: str = ""
    items: List[Dict[str, Any]] = []

class WsDownloadErrorData:        # type=ERROR
    model: str = ""
    reason: str = ""
```

### 6.2 行为约束

- `type` 必填，`data.client_id` 必须与连接分配的 id 一致，否则回错误但**不切断连接**。
- 心跳：`type=heartbeat` 单独响应，不进入业务派发。
- 单连接在途请求上限 `MAX_INFLIGHT_PER_CLIENT = 8`；超出返回"请求过于频繁"。
- 服务端 → 客户端统一 `WebSocketAPIResponse{type, ok, message, data, from_id}`。
- 事件总线经 `ClientEventBridge` 绑定；Web loop 与调度器 loop 分离，工具事件由事件总线转投，不跨 loop 直接操作 transport。

### 6.3 DOWNLOAD_MODEL 事件（`type=download_model`）

用于本地模型下载：进度走 WS，HTTP 端只负责触发。

入站：

```json
{
  "type": "download_model",
  "data": {
    "model_name": "ocr:paddle" | "ocr:paddle:ppocr" | "image:comfyui-local" | "paddle_ocr",
    "force": false
  }
}
```

- 新格式：`"ocr:paddle"` / `"ocr:paddle:ppocr"` / `"image:comfyui-local"`，按 `:` 分割，第二段是 provider，第三段是 model_id。
- 兼容别名：`paddle_ocr → ocr:paddle`、`umi_ocr → ocr:umi`、`whisper → asr:whisper`、`google_facelandmarker` 保持原路径（暂不在 provider 框架内）。
- 已安装的 provider 会先被 `download_status` 探测；`installed=true` 直接回 `ERROR` "模型已存在" 并不触发下载（`force=true` 可跳过，仅新格式支持）。

出站事件：

| 事件 | DTO | 含义 |
|---|---|---|
| `STARTED` | `WsDownloadStartedData` | 下载已接受 |
| `RUNNING` | `WsDownloadProgressData` | 进度 0–100 |
| `COMPLETED` | `WsDownloadCompletedData` | 全部文件完成 |
| `FAILED` | `WsDownloadFailedData` | 任一文件失败 |
| `ERROR` | `WsDownloadErrorData` | 前置条件不满足 |

单连接在途下载上限 2；超出返回 `ERROR "已有下载任务在进行"` 并不切断连接。

### 6.4 待核对项

多并发 stream 的 `request_id/correlation_id` 区分、订阅生命周期、心跳超时后的清理阈值，需以 `controllers/websocket/manager.py` 与契约测试为准。

---

## 7. 桌面 Bridge 与前端客户端

- `ops.register_all()` 把 `desktop=true` 端点注册为 `ApiGateway` 的 op；`call_sync()` 在无运行中 loop 的线程里复用调度器 loop，不每次新建销毁。
- Web 与 Qt bridge 必须使用同一解包规则、同一成功 code、同一 DTO。
- Vue 前端调用集中在 `src/api/services/*`，由 `scripts/api/generate.py` 生成；须统一契约来源、生成脚本与校验流程。
- Python SDK 目录是否存在以当前源码为准，不按旧文档假定。

---

## 8. shell 服务与命令契约（非 HTTP）

shell 不是独立 HTTP 资源，而是**命令层服务**，通过 `/api/service/shell/tools` 暴露工具声明，由 `core/tools` 链路调用。

- 命令文本：模型直接写原生命令原文（`cd docs`、`ls -la`、`mkdir report`），**不需要** `shell --command` 之类包装。
- 解析规则：不属于 `skill` / `error` / 已注册服务命令，且命中 `shell/commands.py` 命令白名单的行，转成 `service="shell", method="run", params={"command":"<整行>"}`；其它行保留为自然语言。
- 系统映射：Windows `cmd.exe /C`，Linux/macOS `/bin/sh -c`；`dir→ls`、`copy→cp`、`del/erase→rm`、`type→cat`、`move→mv`、`cls→clear`。
- 拒绝项：`rm`、`rmdir`、`del`、`format`、`mkfs`、`dd`、`shutdown`、`sudo`、`chmod`、`chown`、`kill`/`taskkill`、`reg`、`diskpart`，以及 `|` / `;` / `&` / 反引号 / `>` / `>>` 等拼接与重定向。
- 执行边界：cwd 锁定工作区、路径参数经 `realpath` + `is_within` 复验、环境变量净化、超时与输出上限；拒绝返回稳定原因码。

详见 [BackendDesign.md](BackendDesign.md) §6.1、§8。

---

## 9. 源码差异与本次修复清单

| 优先级 | 发现 | 依据 | 状态 |
|---|---|---|---|
| P0 | save 端点 path 自带 `/api`，注册器又加 `/api` | `endpoints.json`、`controllers/__init__.py` | ✅ 本次修复为 `/save/slots...` |
| P0 | 成功 code 分叉：后端 200，desktop bridge 判 0 | `exceptions.py`、`src/api/http.ts` | ⬜ 待办：共用 decoder |
| P0 | `services.service.manager` / `services.keys` / `service.decorator` 等失效导入导致启动期 handler 解析失败 | `ctl.py`、`controllers/*`、`services/*` | ✅ 本次修复 + 兼容层 |
| P0 | 对话 / 语音 / 进度与供应商端点混在 `request.py` / `pipline.py` 旧路由中，op 命名不一致 | `controllers/request.py`、`controllers/providers.py` | ✅ 本次重构：对话迁入 `pipline.py`，供应商归入 `providers.py`，op 前缀统一为 `pipline.*` / `providers.*` |
| P0 | WebSocket 帧未复用 DTO，入站/出站字段散落 | `controllers/websocket/*` | ✅ 本次统一为 `WebSocketRequest` / `WsXxxPayload` / `WebSocketAPIResponse` |
| P1 | PPT / audit HTTP 端点未注册 | `groups.json` vs `endpoints.json` | ✅ 本次补齐 8 条 |
| P1 | WebSocket 注册在 `/`，旧文档写 `/ws` | `controllers/websocket/__init__.py` | ✅ 文档更正 |
| P1 | SSE 旧文档出现 `/api/request/chat/stream` | `controllers/pipline.py` | ✅ 文档更正为 `/api/chat/stream` |
| P1 | `ApiGateway._ok` 形参与调用顺序颠倒 | `gateway.py` | ✅ 本次修复 |
| P1 | `response.py` 未处理异常回显内部详情 | `response.py` | ⬜ 待办 |
| P1 | `raw=true` 可请求敏感配置原值 | `controllers/pipline.py` 及配置 controller | ⬜ 待办 |
| P1 | 前端 `save.ts` 的 `restore`/`sync`/`section` 后端未注册 | `src/api/services/save.ts` | ⬜ 待办 |
| P1 | PPT 渲染器调用不存在的 `RuntimePath.get_output_dir()` | `services/ppt/renderer.py` | ✅ 本次修复并改到工作区 |
| P1 | `handle_download_model` 硬编码 `model_name` 分支，与 provider 体系脱节 | `controllers/websocket/events.py`、`providers/manager.py` | ✅ 本次改为 `provider_manager.download_model` |

---

## 10. 契约变更要求

每次 API 修改需：

1. 更新 `endpoints.json`（权威源）、`groups.json` 与本文。
2. 更新 `requests.py` / `dto.py` 与前端生成源，运行统一生成器。
3. 为正常、业务错误、404、超时、取消与边界参数补契约测试。
4. 给旧路径/字段/事件定义兼容期与移除标准。
5. 在表中注明「现行 / 待办」，避免设计目标被误认为已部署。

任何目标端点都必须先在 `endpoints.json` 注册并通过 `_validate()`，才可从"目标设计"升级为"当前接口"。

### 附：模型归属速查

| 分类 | 请求模型（`requests.py`） | 响应 DTO（`dto.py`） |
|---|---|---|
| 对话 / 语音 | `ChatRequest`、`ChatStreamRequest`、`TTSRequest`、`ASRRequest` | `RequestStatusData`、`ChatResultData`、`TTSResultData`、`ASRResultData`、`AbilityStatus` |
| 供应商 | `ProviderSwitchRequest`、`ProviderDownloadRequest` | `AdapterInfo`、`SwitchResultData`、`ProviderStatusData`、`DownloadStatusData`、`DownloadStartData` |
| WebSocket | `WebSocketRequest`、`WsChatPayload`、`WsAsrPayload`、`WsTtsPayload`、`WsCommandPayload`、`WsSubscribePayload`、`WsCancelPayload`、`WsDownloadModelPayload` | `WebSocketAPIResponse[T]`、`WsDownloadStartedData`、`WsDownloadProgressData`、`WsDownloadCompletedData`、`WsDownloadFailedData`、`WsDownloadErrorData` |
| 会话 / 存档 / 角色 | `SessionCreateRequest`、`MessageAppendRequest`、`FlushRequest`、`SlotCreateRequest`、`SlotSectionUpdateRequest`、`SlotSyncRequest`、`CharacterCreateRequest`、`CharacterUpdateRequest`、`CharacterStateUpdateRequest` | `SessionInfoData`、`SessionListData`、`MessageItem`、`MessageListData`、`SlotInfoData`、`SlotMeta`、`SlotListData`、`SlotActionData`、`CharacterInfoData`、`CharacterListData`、`CharacterStateData`、`CharacterAttributesData` |
| 记忆 | `MemorySearchRequest`、`MemoryLayersRequest` | `MemoryLayersData`、`MemorySearchData`、`MemoryStatsData`、`DetailedMemoryItem`、`CompressedItem` |
| 任务 / PPT | `TaskCancelRequest`、`PptOutlineRequest`、`PptRenderRequest` | `TaskStatusData`、`PptTemplateListData`、`PptOutlineData`、`PptRenderData`、`PptJobData`、`PptDownloadData` |
| 系统 / 日志 / 设备 | `GcRequest`、`LoggerLevelRequest` | `HealthData`、`InfoData`、`StatsData`、`GcData`、`LoggerLevelData`、`LoggerStatsData`、`LogRecordData`、`DeviceInfoData` |

---

## 11. 架构文档索引

- [BackendDesign.md](BackendDesign.md)：模块边界、线程模型、工具链、shell 服务与工作区。
- [SecurityAndAuditDesign.md](SecurityAndAuditDesign.md)：威胁模型、工作区权限、命令准入、审计事件。
- [FrontendBackendContract.md](FrontendBackendContract.md)：REST/SSE/WS/Qt bridge 统一契约。
- [ContextArchitecture.md](ContextArchitecture.md)：session-scoped context 与 prompt 装配。
- [GameSaveArchitecture.md](GameSaveArchitecture.md)：Slot / Snapshot / restore。
- [MemoryDesign.md](MemoryDesign.md)：记忆查询、删改与向量一致性。