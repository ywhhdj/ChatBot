# ChatBot API 契约与源码差异

> 源码基线：dev，提交 c5e6343ec4b3913caaa04e5f6af2c34327213314。本文在不运行项目的情况下，根据控制器、统一响应、前端 service 和现有 API 文档交叉整理。
>
> 重要：本文件同时记录“资源逻辑契约”和“当前源码中需要确认的注册差异”。实际发布路径必须以 FastAPI app.routes/OpenAPI 导出结果为准。此文档变更不修改业务源码。

## 0. 通用约定

### 0.1 REST 响应信封

后端 ApiResponse 定义的标准字段如下：

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

- 后端成功业务 code 当前为 200（见 modules/api/exceptions.py）。
- 失败返回语义化 HTTP status，同时使用同构响应信封。
- request_id 使用 X-Request-ID 传入/返回，并应用于日志关联。
- 时间戳 ts 当前为 Unix 秒（float）。
- 前端普通 Axios 分支使用 code === 200；src/api/http.ts 的桌面 bridge 分支使用 code === 0，与后端不一致，为 P0 差异。

### 0.2 错误码（以源码为准）

| code | HTTP | 含义 | 客户端建议 |
|---:|---:|---|---|
| 200 | 200 | 成功 | 读取 data |
| 1001 | 400 | 参数校验失败 | 修正输入 |
| 1002 | 404 | 资源不存在 | 刷新资源或确认 ID |
| 1003 | 409 | 状态冲突 | 查询当前状态后决定是否重试 |
| 2001 | 503 | 依赖未初始化 | 配置/初始化依赖 |
| 2002 | 504 | 处理超时 | 先查询任务状态；仅幂等操作可重试 |
| 3001 | 500 | 内部异常 | 使用 request_id 排障 |
| 3002 | 503 | 主线程忙或不可用 | 稍后重试 |

不要把业务 code 和 HTTP status 混为一谈。所有调用端应使用相同成功 code 和 decoder。

### 0.3 长任务

模型下载、初始化、PPT 生成或其他长操作应优先使用任务接口/异步提交端点，返回 task_id；通过 task 查询状态。任务取消对同步任务不保证强制终止。

## 1. 系统与配置

### System — 逻辑资源前缀 /api/system

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/system/health | Web、调度器、主线程、记忆和服务健康状态 |
| GET | /api/system/info | 版本、配置路径和数据目录信息 |
| GET | /api/system/stats | uptime、日志、任务、连接和记忆统计 |
| POST | /api/system/gc | 触发记忆衰减/清理及日志排空 |
| GET | /api/system/ping | 轻量探测；具体注册需以 OpenAPI 为准 |

健康检查不得触发模型加载、全量索引重建或全盘扫描。

### Config — 逻辑资源前缀 /api/config

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/config | 读取配置；可按 section 查询 |
| PATCH | /api/config/{section} | 局部更新配置 |
| POST | /api/config/reload | 从配置文件重新加载 |
| POST | /api/config/save | 持久化配置 |
| GET | /api/config/schema | 获取配置字段描述 |

配置涉及密钥时默认遮蔽。当前相关接口可能支持 raw 参数，应按 SecurityAndAuditDesign.md 收紧；不要在 URL、日志或前端持久化明文凭据。

## 2. 管道、服务与技能

### Pipeline — 逻辑资源前缀 /api/pipeline

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/pipeline/adapters | 列出 adapter 类型与 provider |
| GET | /api/pipeline/adapters/{adapter}/providers | 列出某 adapter 的 provider |
| GET | /api/pipeline/adapters/{adapter}/providers/{provider} | 读取 provider 配置 |
| POST | /api/pipeline/adapters/{adapter}/switch | 切换 provider |
| POST | /api/pipeline/adapters/{adapter}/stop | 停止当前 provider |
| GET | /api/pipeline/configs | 读取各管道配置 |

provider 切换建议先初始化新实例并健康检查，成功后切换流量；不要让新 provider 初始化失败导致旧 provider 已不可用。

### Service — 逻辑资源前缀 /api/service

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/service | 服务列表 |
| GET | /api/service/tools | 所有服务可用工具定义 |
| GET | /api/service/{service_id} | 服务详情 |
| GET | /api/service/{service_id}/tools | 单个服务工具定义 |
| GET | /api/service/{service_id}/ui | 服务 UI 描述 |
| POST | /api/service/{service_id}/start | 启动服务 |
| POST | /api/service/{service_id}/stop | 停止服务 |
| GET | /api/service/{service_id}/config | 读取服务配置 |
| PUT | /api/service/{service_id}/config | 更新服务配置 |
| PUT | /api/service/{service_id}/config/apply | 应用配置（具体字段以 DTO 为准） |

服务状态包括 stopped/starting/running/stopping/error 一类状态；实际枚举以 DTO/manager 定义为准。

### Skill — 逻辑资源前缀 /api/skill

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/skill | 技能列表 |
| GET | /api/skill/prompt | 给模型使用的技能提示内容 |
| GET | /api/skill/{skill_id} | 技能详情 |
| POST | /api/skill/reload | 重新扫描技能目录 |
| POST | /api/skill/{skill_id}/activate | 启用技能 |
| POST | /api/skill/{skill_id}/deactivate | 停用技能 |
| POST | /api/skill/{skill_id}/execute | 执行技能 |

执行技能必须通过后端权限、参数、资源限制和沙盒策略。项目既有说明指出 shell 类型当前不支持执行、JavaScript 类型未完整实现；未经过安全评审不得宣称为可安全执行能力。

## 3. 对话、SSE 与语音

### Request — 逻辑资源前缀 /api

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/status | LLM/TTS/ASR 就绪状态 |
| GET | /api/folder/{type} | 打开受支持的本地目录；必须限制目录类型 |
| POST | /api/chat | 非流式对话 |
| POST | /api/chat/stream | SSE 流式对话 |
| POST | /api/tts | 文本转语音 |
| POST | /api/asr | base64 音频转文字 |
| POST | /api/progress-stream/{task_id} | 任务进度流；具体事件字段以实现为准 |

非流式对话的常用请求字段：text、source、session_id、route、stream。route 的逻辑枚举包含 pure_chat、tool_call、mixed；真实 DTO 为准。

SSE 的概念事件：
- chunk：一段增量文本。
- done：最终状态与必要的 route/character metadata。
- error：稳定错误码与 message。

旧文档出现过 /api/request/chat/stream 的示例，但 request controller 的路径是 /chat/stream 且由 /api 前缀统一挂载。应将此作为路径笔误修正。实际 SSE 的终态/错误事件需由控制器实现核对，不可只靠示例推断。

TTS/ASR 使用 base64 时必须限制请求体、音频时长、格式和解码资源；不在普通日志记录音频内容。

## 4. 会话与存档

### Session — 逻辑资源前缀 /api/session

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/session | 会话列表 |
| POST | /api/session | 新建会话 |
| GET | /api/session/{session_id} | 会话详情 |
| DELETE | /api/session/{session_id} | 删除会话/消息文件 |
| POST | /api/session/{session_id}/switch | 切换当前会话 |
| GET | /api/session/{session_id}/messages | 查询消息 |
| POST | /api/session/{session_id}/messages | 追加消息，不触发模型推理 |
| POST | /api/session/flush | 强制持久化会话 |

### Save — 目标逻辑资源前缀 /api/save

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/save/slots | 存档槽列表 |
| POST | /api/save/slots | 创建存档槽 |
| GET | /api/save/slots/{slot_id} | 存档详情 |
| DELETE | /api/save/slots/{slot_id} | 删除存档槽 |
| POST | /api/save/slots/{slot_id}/toggle | 切换存档 |
| POST | /api/save/slots/{slot_id}/save | 保存存档 |
| POST | /api/save/slots/{slot_id}/load | 加载存档 |
| PUT | /api/save/slots/{slot_id}/section | 更新某 section |
| POST | /api/save/slots/sync | 会话数据同步入当前存档 |
| POST | /api/save/slots/restore | 从存档恢复到会话（前端 service 已有调用；需核实当前控制器是否注册） |

存档 section 以实际 DTO 为准；现有文档提到 characters、ui、chat_history、achievements、story。加载/删除为高影响操作，建议加入 manifest/hash 校验和恢复预演。

## 5. 角色与记忆

### Character — 逻辑资源前缀 /api/character

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/character | 角色列表 |
| GET | /api/character/presets | 角色预设 |
| GET | /api/character/current | 当前角色 |
| GET | /api/character/{character_id} | 角色详情 |
| POST | /api/character | 创建角色 |
| PUT | /api/character/{character_id} | 更新角色 |
| DELETE | /api/character/{character_id} | 删除角色 |
| POST | /api/character/{character_id}/switch | 切换角色 |
| GET | /api/character/{character_id}/state | 查询角色运行时状态 |
| POST | /api/character/{character_id}/state | 更新角色运行时状态 |

### Memory — 逻辑资源前缀 /api/memory

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/memory/layers | 读取 short_term/long_term/detailed |
| GET | /api/memory/short | 查询短期记忆摘要 |
| GET | /api/memory/long | 查询长期记忆 |
| POST | /api/memory/search | 语义/相关记忆搜索 |
| GET | /api/memory/compressed | 查询压缩记忆 |
| GET | /api/memory/stats | 统计记忆容量 |
| POST | /api/memory/decay | 手动触发衰减 |
| POST | /api/memory/flush | 等待后台记忆写入 |
| DELETE | /api/memory/{memory_id} | 删除单条记忆 |

layers query 包括 session_id 与 detail_top_k；search request 需以 MemorySearchRequest DTO 核对 query、top_k 等字段。所有记忆 API 必须在存储查询前按 session 范围过滤。删除的向量、映射、压缩引用、缓存和快照恢复语义见 MemoryDesign.md。

## 6. 任务、日志、审计与 PPT

### Task — 逻辑资源前缀 /api/task

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/task/{task_id} | 查询任务状态与结果 |
| POST | /api/task/{task_id}/cancel | 请求取消任务 |

任务状态以 Task DTO 为准；旧文档的 pending/running/done/failed/timeout 应检查是否还包含 cancelled 或其他终态。

### Logger — 逻辑资源前缀 /api/logger

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/logger/level | 当前日志级别 |
| PUT | /api/logger/level | 修改日志级别 |
| GET | /api/logger/levels | 允许的日志级别 |
| GET | /api/logger/stats | 日志统计 |
| GET | /api/logger/records | 近期日志查询 |
| POST | /api/logger/flush | 强制落盘 |

### Audit — 目标逻辑资源前缀 /api/audit

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/audit/tree | 服务/工具能力树 |
| GET | /api/audit/tools | 扁平工具清单 |

当前 audit controller 主要呈现可调用服务/工具能力，不代表具备完整的安全操作审计事件流。

### PPT — 逻辑资源前缀 /api/ppt

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/ppt/templates | 模板列表 |
| POST | /api/ppt/outline | 生成内容大纲 |
| POST | /api/ppt/render | 同步渲染 PPT |
| POST | /api/ppt/render/async | 提交后台生成任务 |
| GET | /api/ppt/job/{task_id} | 查询生成任务 |
| GET | /api/ppt/download/{file_name} | 下载已生成文件 |

文件下载需验证 basename、路径边界和文件存在性，不应接受可任意访问的绝对路径。

### Device

控制器集合会注册 device router，但设备接口的准确路径/方法需从实际 device 子目录控制器导出后再加入正式端点清单。

## 7. WebSocket 事件契约

旧文档描述了 /ws、chat/asr/tts/command/subscribe/unsubscribe/ping/cancel 等消息。然而当前 websocket 路由注册函数使用 app.websocket("/")，不是在函数内部声明 /ws；因此实际 WebSocket URL 与旧文档有不一致风险。

待核对项：
- server 初始化是否在其他位置重写/挂载 WebSocket 根路径。
- 消息模型的 type/data 与 controller 实际接收的字段。
- server → client 的 type 命名、终态和错误字段。
- 每连接在途请求上限、心跳超时、事件订阅是否在实现中持续生效。
- request_id/correlation_id 是否能区分多个同时进行的 stream。

在确认实际注册结果前，不应承诺 /ws、/ws/ 或根路径中的任意一个是最终稳定路径。目标是把路径和事件 schema 明确化，并由测试覆盖。

## 8. Python SDK 与前端客户端

- Python SDK 位于 modules/api/client（以当前目录存在状态为准）；推荐使用 SDK 统一超时、信封和错误处理，避免各处裸调请求。
- Vue 前端调用集中在 src/api/services。
- 前端 service/types 有自动生成痕迹；须统一契约来源、生成脚本和校验流程。
- Web 与 Qt bridge 必须使用同一响应解包规则、同一错误码和同一 DTO。

## 9. 安全和性能约束

- 默认只绑定 loopback。远程访问必须显式启用认证和严格来源限制。
- 秘密字段默认遮蔽；不要常态化开放 raw=true。
- 对 chat、audio、文件、PPT 和工具请求限制 body size、超时、并发和输出大小。
- 长任务返回 task_id 并具有状态、失败、超时与取消语义。
- 不对非幂等 POST 默认重试；provider 重试应遵守总预算。
- 日志避免保存 key、完整 prompt、音频和私人记忆正文。

## 10. 路由注册规则

期望规则：Controller router 只声明资源路径（例如 /save、/audit），统一由 register_all_routers 添加一次 /api。当前 controllers/__init__.py 确实为所有 router 添加 prefix=/api；但 save.py router prefix 当前是 /api/save，audit.py 当前是 /api/audit，可能产生重复 /api/api 路径。这是源码差异，不可仅用文档掩盖。应导出 FastAPI 的实际 registered paths、修正 controller prefix，并同步客户端。

同理，WebSocket 当前在 app.websocket("/") 注册，而旧文档写 /ws；需统一为明确且被测试的路径。

## 11. 契约变更要求

每次 API 修改需：
1. 更新本文件与请求/响应 DTO。
2. 更新前端 service/types 的权威生成源并运行统一生成器。
3. 为正常、业务错误、404、超时、取消和边界参数添加契约测试。
4. 给旧路径/字段/事件定义兼容期与移除标准。
5. 在 API 表中注明 current/target，避免设计目标被误认为已部署。

## 12. 源码差异与需核对项

| 优先级 | 发现 | 文件依据 | 建议 |
|---|---|---|---|
| P0 | 成功 code 分叉：后端 200，desktop bridge 判断 0 | modules/api/exceptions.py、src/api/http.ts | 共用 decoder，以 200 为统一成功 code |
| P0 | save/audit router 自带 /api，注册器又加 /api | controllers/__init__.py、controllers/save.py、controllers/audit.py | controller prefix 改为资源名，再从 app.routes 导出验证 |
| P1 | WebSocket route 当前声明在 /，旧文档写 /ws | controllers/websocket/__init__.py、server.py | 明确稳定路径并对客户端兼容 |
| P1 | SSE 文档曾出现 /api/request/chat/stream | controllers/request.py | 按注册器统一路径 /api/chat/stream 校对 |
| P1 | PPT/审计/device 等路由未完全出现在旧文档 | controllers/ppt.py、audit.py、controllers/__init__.py | 统一生成/检查 endpoint inventory |
| P1 | 前端 save service 有 /save/slots/restore 方法，当前 save controller 清单需核对是否实现 | src/api/services/save.ts、controllers/save.py | 决定补实现或移除未支持客户端方法 |
| P1 | response.py 的 unhandled exception message 可能暴露内部异常详情 | modules/api/response.py | 对外通用错误 + request_id，内部日志脱敏 |
| P1 | raw=true 可请求敏感配置原值 | controllers/pipline.py 及配置 controller | 移除通用原文输出，或加本地受控权限 |

本轮文档提交不修复这些实现风险，也未运行应用导出真实路由；路线和方法清单中已标注应以 FastAPI 实际注册结果为最终依据。


## 14. 架构设计文档索引

本文件定义外部接口和 transport 契约；以下文档定义实现该契约的模块边界与状态生命周期：

- [FrontendBackendContract.md](FrontendBackendContract.md)：REST/SSE/WebSocket/Qt bridge 共用请求 ID、事件信封、错误与取消语义。
- [ContextArchitecture.md](ContextArchitecture.md)：session-scoped context/prompt 构建。API 的 session_id 是业务隔离字段，不是可选装饰字段。
- [GameSaveArchitecture.md](GameSaveArchitecture.md)：Slot、Checkpoint、Full Snapshot 与 restore operation 的目标 API/流程；其中新增 snapshot endpoint 仅为目标设计，未经实现不得当作当前可用 API。
- [MemoryDesign.md](MemoryDesign.md)：记忆查询、来源、置信度、删改和向量一致性。

任何目标 endpoint 都必须先在源码实现并导出 OpenAPI 后，才可从“目标设计”升级为“当前接口”。当前 session/save API 的兼容性要求维持旧路径和字段，新增 Memento 能力应使用明确的新操作，而不是改变旧 load 的意义。
