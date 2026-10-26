# ChatBot API 文档

> 版本：v1　·　Base URL：`http://127.0.0.1:8080`（由 `config.web.host/port` 决定）
> 后端：FastAPI（独立线程 + 独立 asyncio loop，与 Qt 主线程解耦）
> 所有 REST 路径统一挂载在 `/api` 前缀下，WebSocket 挂载在 `/ws`

---

## 0. 通用约定

### 0.1 统一响应信封

**所有** REST 接口返回同一结构：

```jsonc
{
  "ok": true,             // 业务是否成功
  "code": 200,              // 200=成功，非 200 见错误码表
  "message": "ok",        // 可读信息，失败时为错误原因
  "data": { },            // 业务数据，失败时为 null
  "request_id": "9f1c…",  // 每次请求唯一，日志排障用
  "ts": 1757000000.123    // 服务端时间戳（秒）
}
```

失败的 HTTP 状态码仍为语义化状态码（400/404/500…），但 **body 同样是信封**，
前端只需判 `ok` 即可，不必解析两套格式。

### 0.2 错误码

| code | HTTP | 含义 | 处理建议 |
|---|---|---|---|
| 0 | 200 | 成功 | — |
| 1001 | 400 | 参数校验失败 | 检查字段类型/必填 |
| 1002 | 404 | 资源不存在 | id 拼写或已被删除 |
| 1003 | 409 | 状态冲突 | 如重复启动已运行的服务 |
| 2001 | 503 | 依赖未初始化 | 如 LLM/TTS 未配置，先调 `/api/pipeline/.../switch` |
| 2002 | 504 | 处理超时 | 推理/下载超时，可重试 |
| 3001 | 500 | 内部异常 | 携带 `request_id` 查日志 |
| 3002 | 503 | 主线程忙/不可用 | Qt 主线程未就绪，稍后重试 |

### 0.3 请求 ID

每个请求由中间件注入 `X-Request-ID`；客户端也可自带该 header，服务端沿用。
响应中回传 `request_id`。

### 0.4 异步长任务

耗时操作（模型下载、OCR 初始化、技能执行、批量压缩）**不在请求线程内同步执行**，
而是提交给任务调度器，返回 `TaskReference` 语义的 `task` 对象：

```json
{ 
  "ok": true, 
  "data": { 
    "task_id": "t_7f3a",
    "state": "pending" 
  } 
}
```

前端可轮询 `GET /api/task/{task_id}` 或订阅 WebSocket 的 `task.*` 事件。

### 0.5 时间戳

一律为 **Unix 秒（float）**，除非字段明确标注为 ISO 字符串。

---

## 1. 系统 `/api/system`

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/system/health` | 健康检查（Web/调度器/主线程/记忆系统） |
| GET | `/api/system/info` | 应用信息（版本、配置路径、数据目录） |
| GET | `/api/system/stats` | 运行统计（日志、调度器、连接数、记忆） |
| POST | `/api/system/gc` | 触发一次清理（记忆衰减 + 排空日志） |

### GET `/api/system/health`

```jsonc
{
  "ok": true,
  "data": {
    "status": "healthy",          // healthy | degraded | unhealthy
    "web":     { "ready": true,  "host": "127.0.0.1", "port": 8080 },
    "scheduler": { "running": true, "pending": 0, "running_tasks": 2 },
    "main_thread": { "ready": true, "queue": 0 },
    "memory": { "ready": true, "records": 128 },
    "services": { "total": 4, "running": 2 }
  }
}
```

### GET `/api/system/stats`

```jsonc
{ "ok": true, "data": {
  "uptime_sec": 3600.5,
  "log":     { "total": 512, "by_level": { "INFO": 400, "ERROR": 3 }, "dropped": 0 },
  "scheduler": { "submitted": 120, "done": 118, "failed": 1, "streams": 2 },
  "websocket": { "connections": 2 },
  "memory": { "records": 128, "compressed": 6, "tokens_estimate": 3400 }
}}
```

---

## 2. 配置 `/api/config`

配置分 section：`web` `log` `network` `sqlite` `llm` `tts` `asr` `skills`。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/config` | 获取完整配置（`?section=` 取单个） |
| PATCH | `/api/config/{section}` | 局部更新某个 section |
| POST | `/api/config/reload` | 从文件重新加载 |
| POST | `/api/config/save` | 持久化到文件（`{"file_path": "config.json"}`） |
| GET | `/api/config/schema` | 字段说明（给设置页自动生成表单） |

### GET `/api/config`

```jsonc
{ "ok": true, "data": {
  "llm": { "enabled": true, "provider": "DeepSeek", "model": "deepseek-v4-flash",
           "api_key": "sk-***", "base_url": "https://api.deepseek.com" },
  "tts": { "provider": "GPTSoVITS", "base_url": "http://127.0.0.1:9880" },
  "web": { "host": "127.0.0.1", "port": 8080 }
}}
```

> 敏感字段（`api_key`）默认做掩码 `sk-***`；`?raw=true` 返回原值。

### PATCH `/api/config/llm`

请求：`{ "model": "deepseek-v4", "temperature": 0.8 }`（仅传要改的字段）
响应：`{ "ok": true, "data": { "llm": {...更新后...} } }`

### GET `/api/config/schema`

```jsonc
{ "ok": true, "data": {
  "llm": [ { "name": "provider", "description": "LLM 供应商", "value": "DeepSeek" }, ... ]
}}
```

---

## 3. 管道（适配器）`/api/pipeline`

适配器类型：`llm` `tts` `asr` `ocr`。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/pipeline/adapters` | 所有适配器配置与可选 provider |
| GET | `/api/pipeline/adapters/{type}/providers` | 某类型的 provider 列表 |
| GET | `/api/pipeline/adapters/{type}/providers/{name}` | 单个 provider 的完整配置 |
| POST | `/api/pipeline/adapters/{type}/switch` | 切换 provider |
| POST | `/api/pipeline/adapters/{type}/stop` | 关闭当前适配器 |

### POST `/api/pipeline/adapters/llm/switch`

请求：
```jsonc
{ "provider": "DeepSeek", "config": { "api_key": "sk-xxx", "model": "deepseek-v4" } }
```
响应：
```jsonc
{ "ok": true, "data": {
  "type": "llm", "name": "DeepSeek", "success": true, "config": { ... }
}}
```

> 切换会先关闭旧适配器再初始化新的；`config` 留空则使用配置文件中的默认配置。
> OCR 等需要下载模型的 provider，`init_provider_client` 会提交到调度器异步执行，
> 接口立即返回，`/api/system/health` 可观察进度。

---

## 4. 服务 `/api/service`

服务是注册到 `ServiceManager` 的能力单元（OBS、Browser、Live2D、Music…）。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/service` | 服务列表（`?running_only=true` 过滤） |
| GET | `/api/service/{id}` | 单个服务详情 |
| GET | `/api/service/{id}/tools` | 该服务暴露的 LLM 工具定义 |
| GET | `/api/service/tools` | 所有服务的工具定义（OpenAI function 格式） |
| POST | `/api/service/{id}/start` | 启动服务 |
| POST | `/api/service/{id}/stop` | 停止服务 |
| GET | `/api/service/{id}/config` | 读取服务配置 |
| PUT | `/api/service/{id}/config` | 更新服务配置 |
| GET | `/api/service/{id}/ui` | UI 描述（给前端渲染控制面板） |

### GET `/api/service`

```jsonc
{ "ok": true, "data": {
  "services": [
    { "id": "obs", "name": "OBS", "description": "直播推流控制",
      "state": "running", "main_thread": false }
  ],
  "total": 1
}}
```

`state` 取值：`stopped` `starting` `running` `stopping` `error`

### POST `/api/service/obs/start`

响应：`{ "ok": true, "data": { "id": "obs", "state": "running" } }`
已运行时返回 `1003 状态冲突`。

---

## 5. 日志 `/api/logger`

实时日志走 WebSocket（事件 `log.*`），REST 只做查询与级别控制。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/logger/level` | 当前日志级别 |
| PUT | `/api/logger/level` | 设置级别 `{ "level": "DEBUG" }` |
| GET | `/api/logger/levels` | 可选级别列表 |
| GET | `/api/logger/stats` | 统计（各级别条数、丢弃数） |
| GET | `/api/logger/records` | 近期记录（`?limit=100&level=ERROR`） |
| POST | `/api/logger/flush` | 强制落盘 |

### GET `/api/logger/stats`

```jsonc
{ "ok": true, "data": {
  "total": 512, "dropped": 0,
  "by_level": { "DEBUG": 100, "INFO": 380, "WARNING": 29, "ERROR": 3 },
  "queue": 0, "file_enabled": false
}}
```

---

## 6. 通用接口 `/api`

> 路由文件 `controllers/request.py`，变量 `req_router`。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/status` | 各能力就绪状态（LLM/TTS/ASR） |
| GET | `/api/folder?type={type}` | 打开指定目录（images/roles） |
| POST | `/api/chat` | 非流式对话 |
| POST | `/api/chat/stream` | 流式对话（SSE） |
| POST | `/api/tts` | 文本转语音（返回 base64） |
| POST | `/api/asr` | 语音转文本（base64 音频） |
| POST | `/api/command/run` | 直接执行命令文本（skill/service 命令） |

### POST `/api/chat`

请求：
```jsonc
{ "text": "今天天气怎么样", "source": "text", "session_id": "default",
  "route": "pure_chat",           // 可选：pure_chat | tool_call | mixed，留空自动路由
  "stream": false }
```
响应：
```jsonc
{ "ok": true, "data": {
  "text": "今天晴天，26 度～",
  "route": "pure_chat",
  "character_id": "qingmei",
  "mood": 17,
  "commands_executed": [],
  "tokens_estimate": 320,
  "elapsed_ms": 820
}}
```

### POST `/api/request/chat/stream`（SSE）

`Content-Type: text/event-stream`，每个 chunk：
```
data: {"type":"chunk","text":"今天"}
data: {"type":"chunk","text":"晴天"}
data: {"type":"done","route":"pure_chat","character_id":"qingmei","mood":17}
```

> producer 运行在调度器 loop，**不占用 Web 线程**，因此流式期间其它 HTTP 请求不受影响。

### POST `/api/request/tts`

请求：`{ "text": "你好", "format": "mp3" }`
响应：`{ "ok": true, "data": { "audio": "<base64>", "format": "mp3", "duration_hint_ms": 1200 } }`

### POST `/api/request/asr`

请求：`{ "audio": "<base64>", "format": "wav" }`
响应：`{ "ok": true, "data": { "text": "你好" } }`

---

## 7. 会话 `/api/session`

会话 = 一轮轮对话的容器（`GameSaveManager`），与"存档槽"不同（后者是完整快照）。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/session` | 会话列表 |
| POST | `/api/session` | 创建 `{ "name": "和绫的下午", "character_id": "qingmei" }` |
| GET | `/api/session/{id}` | 会话详情 |
| DELETE | `/api/session/{id}` | 删除 |
| POST | `/api/session/{id}/switch` | 切换当前会话 |
| GET | `/api/session/{id}/messages` | 消息列表（`?limit=50`） |
| POST | `/api/session/{id}/messages` | 追加一条 `{ "role": "user", "content": "..." }` |
| POST | `/api/session/flush` | 强制落盘（`{"session_id": "..."}` 可省略=全部） |

### GET `/api/session/{id}/messages`

```jsonc
{ "ok": true, "data": { "messages": [
  { "role": "user", "content": "你好", "timestamp": 1756999999.0, "source": "text" }
], "total": 1 }}
```

---

## 8. 存档槽 `/api/save`

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/save/slots` | 存档槽列表 |
| POST | `/api/save/slots` | 新建 `{ "name": "第一章" }` |
| GET | `/api/save/slots/{id}` | 存档详情 |
| DELETE | `/api/save/slots/{id}` | 删除 |
| POST | `/api/save/slots/{id}/toggle` | 切换当前存档（会加载内容） |
| POST | `/api/save/slots/{id}/save` | 保存 |
| POST | `/api/save/slots/{id}/load` | 加载 |
| PUT | `/api/save/slots/{id}/section` | 更新分区 `{ "section": "characters", "data": {...} }` |
| POST | `/api/save/slots/sync` | 把会话数据同步进当前存档 |

`section` 可选：`characters` `ui` `chat_history` `achievements` `story`

---

## 9. 角色 `/api/character`

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/character` | 角色列表 |
| GET | `/api/character/current` | 当前角色 |
| POST | `/api/character/{id}/switch` | 切换当前角色 |
| POST | `/api/character` | 创建角色 |
| PUT | `/api/character/{id}` | 更新角色属性 |
| DELETE | `/api/character/{id}` | 删除角色 |
| GET | `/api/character/{id}/state` | 运行时状态（心情/好感/消息数） |
| POST | `/api/character/{id}/state` | 更新状态 `{ "mood": 17, "affection": 70 }` |
| GET | `/api/character/presets` | 预设模板列表 |

### GET `/api/character/current`

```jsonc
{ "ok": true, "data": {
  "id": "qingmei", "name": "小青", "title": "青梅竹马",
  "attributes": { "personality": "开朗活泼…", "nickname_for_user": "哥哥",
                  "affection_level": 65, "mood": "高兴", "catchphrases": ["诶嘿~"] },
  "state": { "mood": 17, "affection": 65, "total_messages": 42,
             "last_interaction": 1756999000.0 }
}}
```

---

## 10. 记忆 `/api/memory`

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/memory/layers` | 三层记忆（短期/长期/详细），供 prompt 注入 |
| GET | `/api/memory/short` | 短期摘要 |
| GET | `/api/memory/long` | 长期摘要（`?query=` 语义检索） |
| POST | `/api/memory/search` | 语义检索 `{ "query": "...", "top_k": 8 }` |
| GET | `/api/memory/compressed` | 压缩记忆列表 |
| POST | `/api/memory/decay` | 手动触发衰减 |
| POST | `/api/memory/flush` | 排空后台写入 |
| DELETE | `/api/memory/{id}` | 删除单条记忆 |
| GET | `/api/memory/stats` | 统计与容量 |

### GET `/api/memory/layers?session_id=default&detail_top_k=8`

```jsonc
{ "ok": true, "data": {
  "short_term": "用户说他喜欢吃苹果…",
  "long_term": "用户住在深圳，从事后端开发…",
  "detailed": [ { "id": "12", "content": "明天要去深圳出差", "score": 0.82 } ]
}}
```

> 计算向量会走调度器；`detail_top_k=0` 可跳过详细层以降低延迟。

---

## 11. 技能 `/api/skill`

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/skill` | 技能列表（`?active_only=true`） |
| GET | `/api/skill/{id}` | 技能详情 |
| POST | `/api/skill/reload` | 重新扫描技能目录 |
| POST | `/api/skill/{id}/activate` | 启用 |
| POST | `/api/skill/{id}/deactivate` | 停用 |
| POST | `/api/skill/{id}/execute` | 执行 `{ "params": {...} }` |
| GET | `/api/skill/prompt` | 给 LLM 的技能提示词 |

`exec_type`：`none` `python` `shell` `javascript`
**`shell` 类型暂不支持执行**：会被识别、可见、可启用，但执行时返回 `2001 依赖未初始化`
并附带 `reason: "shell 技能暂不支持执行"`。

命令文本格式：`skill --id weather --city 深圳`
> 只认 `--id`；`--name` 为无效参数（技能名可重复，id 才唯一）。

---

## 12. 任务 `/api/task`

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/task/{task_id}` | 查询任务状态与结果 |
| POST | `/api/task/{task_id}/cancel` | 取消（尽力而为，同步任务无法强杀） |

```jsonc
{ "ok": true, "data": {
  "task_id": "t_7f3a", "state": "done",   // pending|running|done|failed|timeout
  "result": { ... }, "error": null, "elapsed_ms": 1200
}}
```

---

## 13. WebSocket `/ws`

连接：`ws://127.0.0.1:8080/ws?client_id=web-1`

### 13.1 客户端 → 服务端

```jsonc
{ "type": "chat", "data": { "text": "你好", "session_id": "default" } }
```

| type | data | 说明 |
|---|---|---|
| `chat` | `{text, session_id, source, route}` | 发起对话（流式回推） |
| `asr` | `{audio(base64), is_final}` | 语音转文字（流式） |
| `tts` | `{text}` | 文本转语音（流式回推音频块） |
| `command` | `{text}` | 执行命令文本 |
| `subscribe` | `{events: ["log.*", "tts.*"]}` | 订阅事件（支持 `*` 通配） |
| `unsubscribe` | `{events: [...]}` | 取消订阅 |
| `ping` | — | 心跳，服务端回 `pong` |
| `cancel` | `{request_id}` | 取消在途请求 |

### 13.2 服务端 → 客户端

```jsonc
{ "type": "chat.chunk", "data": { "text": "今" }, "request_id": "r_1", "ts": 1757000000.1 }
```

| type | data | 说明 |
|---|---|---|
| `connected` | `{client_id}` | 连接建立 |
| `pong` | `{ts}` | 心跳应答 |
| `chat.chunk` | `{text}` | 流式文本片段 |
| `chat.done` | `{text, route, character_id, mood}` | 对话完成 |
| `chat.error` | `{message, code}` | 对话失败 |
| `tts.chunk` | `{audio(base64)}` | 音频块 |
| `tts.done` | `{}` | 音频结束 |
| `asr.partial` / `asr.done` | `{text}` | 识别中间/最终结果 |
| `log` | `{level, message, source, ts}` | 日志推送（需订阅） |
| `command.result` | `{ok, results, summary}` | 命令执行结果 |
| `task.update` | `{task_id, state}` | 任务状态变化 |
| `error` | `{message, code}` | 通用错误 |

### 13.3 心跳与超时

- 客户端应每 30s 发一次 `ping`
- 服务端 90s 无心跳判定为死连接并清理
- 单客户端在途请求上限 8，超过返回 `chat.error`（code `1003`）

---

## 14. Python SDK（前端调用）

SDK 位于 `modules/api/client/`，同时提供同步与异步两种客户端，
供 PyQt 前端、脚本、测试使用。**前端不要直接用 requests 裸调**——SDK 已封装
信封解包、错误转异常、超时与重试。

### 14.1 同步

```python
from modules.api.client import ApiClient

c = ApiClient("http://127.0.0.1:8080", timeout=10.0)

health = c.system.health()
print(health.data["status"])

cfg = c.config.get("llm").data
c.config.patch("llm", {"model": "deepseek-v4"})

r = c.chat.chat("今天天气怎么样")
print(r.data["text"])

for chunk in c.chat.chat_stream("讲个故事"):
    print(chunk, end="", flush=True)
```

### 14.2 异步

```python
import asyncio
from modules.api.client import AsyncApiClient

async def main():
    async with AsyncApiClient("http://127.0.0.1:8080") as c:
        r = await c.chat.chat("你好")
        async for chunk in c.chat.chat_stream("讲个故事"):
            print(chunk, end="")
asyncio.run(main())
```

### 14.3 WebSocket

```python
from modules.api.client import ApiWebSocket

ws = ApiWebSocket("ws://127.0.0.1:8080/ws")
ws.on("chat.chunk", lambda p: print(p["text"], end=""))
ws.on("log", lambda p: print("[log]", p["message"]))
ws.connect()               # 阻塞接收（内部线程）
ws.send("chat", {"text": "你好"})
ws.subscribe(["log.*"])
```

### 14.4 异常

| 异常 | 触发 |
|---|---|
| `ApiRequestError` | 网络/超时/连接失败 |
| `ApiResponseError` | 服务端返回 `ok=false`（含 `.code` / `.request_id`） |
| `ApiValidationError` | 本地参数校验失败 |

---

## 15. 前端调用约束（重要）

1. **不要在前端主线程同步等待长任务**：聊天/下载走 SSE 或 WebSocket 流式接口。
2. **流式接口在调度器 loop 执行**，Web 线程只做转发；前端可并发发起多个流。
3. **事件回调必须同步**：若前端（PyQt）注册总线回调，回调内只做投递，不 `await`。
4. **双通道输出**：`route=tool_call` 时后端会先执行命令再角色化总结，
   前端通过 `command.result` + `chat.done` 两个事件收到完整链路。
5. **`api_key` 默认掩码**，设置页如需回显请用 `?raw=true`（仅本机可信环境）。

---

## 16. 模块到端点的映射

| 后端模块 | 端点组 |
|---|---|
| `modules/config` | `/api/config` |
| `modules/manager/pipeline.py` | `/api/pipeline` |
| `modules/manager/service/manager.py` | `/api/service` |
| `modules/logger` | `/api/logger` |
| `modules/pipeline/chat.py` | `/api/request` |
| `modules/manager/session.py` | `/api/session` |
| `modules/manager/saves/manager.py` | `/api/save` |
| `modules/characters` + `manager/character.py` | `/api/character` |
| `modules/memory` | `/api/memory` |
| `modules/tools/skills` | `/api/skill` |
| `modules/manager/task` | `/api/task` |
| `modules/api/controllers/websocket.py` | `/ws` |