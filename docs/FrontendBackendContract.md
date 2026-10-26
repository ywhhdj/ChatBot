# 前后端交互契约：REST、SSE、WebSocket 与 Qt Bridge

> 本设计以当前 FastAPI + Vue service + Qt WebChannel bridge 的源码为基线。新增字段和 target endpoint 均为提议，必须经 api.md/DTO/生成流程评审后再实现。

## 1. 目标

REST、SSE、WebSocket 和 Qt bridge 是多种 transport，不应是多套业务 API。它们必须映射到相同的应用服务、DTO、错误语义、授权规则和可观测字段。

原则：
- 一个逻辑操作、一个领域 DTO、一个错误语义；不同 transport 仅负责编码/解码。
- 路由权威来自后端 controller registration，api.md 与前端 service/types 由同一契约校验。
- request_id、session_id、stream_id、task_id 的语义不能混用。
- 持续流和长任务使用明确状态机、deadline、取消与终态，不靠客户端猜测。
- 业务变更的最终状态以服务端为准，前端只保存展示/交互状态。

## 2. 逻辑分层与调用关系

~~~text
Vue View / Composable / Pinia        Python/Qt UI
            |                              |
            +--------------+---------------+
                           |
                  Domain API service
                           |
               Shared Contract / DTO
                           |
           +---------------+----------------+
           |               |                |
          REST             SSE             WS/Qt bridge
           |               |                |
           +---------------+----------------+
                           |
                   API Controller/Gateway
                           |
                  Application service
                           |
                  Domain/Manager/Adapter
                           |
                    Store / Provider
~~~

UI 不直接依赖底层存储格式；controller 不直接成为业务规则所在位置；不同 transport 不可自行定义互相矛盾的成功码。

## 3. 请求标识

| 字段 | 生命周期 | 规则 |
|---|---|---|
| request_id | 一个入站请求 | 用于日志和错误定位；客户端可提供，但长度/字符集须校验 |
| trace_id | 一条完整业务链路 | 串联路由、memory retrieve、LLM、tool、持久化；可跨多个子请求 |
| stream_id | 一次流式传输 | 关联 SSE/WS chunk、done/error/cancel |
| task_id | 一个后台工作 | 持续到 succeeded/failed/cancelled/timeout 等终态 |
| session_id | 一段对话会话 | 每个上下文、检索、写入都必须显式传入 |
| character_id | 当前角色实体 | 作为上下文和角色状态隔离维度 |
| operation_id | 一项长事务型操作 | 存档创建/恢复/索引重建可幂等查询阶段结果 |

request_id 不等于 task_id；一次 POST 可能只负责创建 task，之后用 task_id 查询。session_id 与 character_id 是业务维度，不可仅作为日志标签。

## 4. 标准 REST 结果

现有后端信封字段：\`ok\`、\`code\`、\`message\`、\`data\`、\`request_id\`、\`ts\`。后端成功业务码为 200。

~~~json
{
  "ok": true,
  "code": 200,
  "message": "ok",
  "data": {"id": "resource-id"},
  "request_id": "request-id",
  "ts": 1792992000.0
}
~~~

约定：
- HTTP status 保留语义（2xx/4xx/5xx），业务 code 表示应用错误种类。
- error response 的 data 默认 null 或稳定结构，避免内部 traceback。
- 前端只通过共享 decoder 解包一次；service 不能再次猜测是否包了一层 data。
- 当前源码差异：普通 Axios 分支检查 code===200，而 desktop bridge 分支检查 code===0。目标统一为 200，并建立相同契约用例。
- 若未来变更信封，需有 versioning/compatibility rule，而不是让各 transport 自行兼容。

## 5. 统一错误模型

推荐前端错误对象：
- kind：\`validation | not_found | conflict | not_ready | timeout | cancelled | network | internal\`
- code：稳定业务 code
- status：HTTP status（bridge 可为空）
- request_id：用于用户反馈和诊断
- retryable：按 operation semantics 决定，不仅根据 status 猜测
- message：经过安全处理的可展示文本

重试策略：
- GET 等读操作可对网络抖动/明确 503 进行有限重试。
- 非幂等 POST/PUT/DELETE 默认不自动重试。
- 长任务创建若要重试，必须携带 idempotency key 或 operation_id，以防重复创建。
- timeout 不代表服务端未执行；客户端应查询 task/operation 状态再决定是否重发。
- cancelled 不作为普通错误 notification；用户主动取消需要进入 cancelled 状态。

## 6. SSE 标准事件

当前 controller 提供 \`POST /api/chat/stream\` 概念上的 SSE（最终 URL 应以注册路由为准），旧文档中曾有路径笔误。目标事件 envelope：

~~~text
event: chunk
data: {"stream_id":"s1","request_id":"r1","seq":1,"text":"你好"}

event: tool.status
data: {"stream_id":"s1","request_id":"r1","seq":2,"task_id":"t1","state":"running"}

event: done
data: {"stream_id":"s1","request_id":"r1","seq":3,"result":{"route":"pure_chat"}}

event: error
data: {"stream_id":"s1","request_id":"r1","seq":4,"error":{"code":2002,"kind":"timeout","message":"处理超时"}}
~~~

以上是目标事件 schema，不表示当前代码已经发出全部事件。

要求：
- seq 单调递增，帮助客户端检测缺帧/乱序；若 transport 不支持恢复，不得伪装支持 replay。
- chunk 不包含不必要的敏感 metadata。
- 每个 stream 恰好一个终态事件：done/error/cancelled。
- 断开连接须传播取消策略；服务端应有 max lifetime，不能因客户端离开仍无限生成。
- 需要长时间任务时优先返回 task_id 并用 task stream/轮询观察，而不是占用聊天 SSE。
- 若要求断点续传，先定义 event buffer、cursor 与过期语义再实现。

## 7. WebSocket 消息契约

当前源码中 websocket register function 使用 \`app.websocket("/")\`，现有文档的 \`/ws\` 描述必须与实际 server mount 共同核对；不要在未验证前宣称稳定路径。

建议统一消息形态：

~~~json
{
  "type": "chat",
  "request_id": "r1",
  "data": {
    "session_id": "session-1",
    "character_id": "qingmei",
    "text": "你好",
    "source": "text",
    "route": null
  }
}
~~~

服务端事件形态建议为 \`type + request_id + ts + data\`。同一连接可有多条请求，但每条请求按 request_id 隔离；每连接有最大 in-flight、payload 大小、订阅量和心跳限制。

- ping/pong 只验证连接存活，不作为业务请求成功的证明。
- subscribe/unsubscribe 使用固定 event allowlist，不能无限制订阅任意敏感事件。
- cancel 只取消属于该连接/调用主体且仍可取消的 request/task。
- disconnect 清理 listener、inflight cancellation token 与连接记录。
- WebSocket 的错误模型与 REST 相同；不能以 HTTP 200 作为 WS 业务成功信号。

## 8. Qt WebChannel bridge

当前 src/api/http.ts 根据环境切换 Axios adapter，并通过 \`window.qtwebview.api.call(opName, payload, timeout)\` 调用桌面桥接。目标设计：

1. 领域 service 不知道当前是浏览器还是 Qt。
2. Transport adapter 把路径/参数映射为显式 operation schema，不靠正则猜测 path parameter。
3. bridge operation registry 由 API/handler 生成或集中定义，给每个 op 绑定 method、DTO、timeout、capability。
4. 路径中的 session_id/slot_id/character_id 必须从真实 URL 段解析并放入 payload；禁止保留 \`{session_id}\` 等占位符。
5. bridge 响应通过同一个 ApiResponse decoder，统一 code 200、error kind、request_id 和取消/超时。
6. bridge 初始化带 timeout，并将 bridge-not-ready 与服务端 not-initialized 区分。
7. 高影响操作在后端二次授权；桌面 UI 的确认只是一层用户体验保护，不代替服务端策略。

## 9. API 生成与契约单一来源

当前后端有 controllers/DTO，前端 service 文件注释称由 \`scripts/api/generate.py\` 自动生成，项目也有 \`scripts/gen_api_types.mjs\` 与 openapi-typescript 依赖。目标流程：

1. 从实际 FastAPI app 生成 OpenAPI 与当前注册 route inventory。
2. 对无法被 OpenAPI 完整表达的 SSE/WS/bridge schema，维护补充 event contract 文件。
3. 选定一个正式输入源；明确哪些 TS services/types 是自动生成。
4. CI/静态脚本对比 controller route、OpenAPI、docs/api.md endpoint table 与前端调用 URL/verb。
5. 生成文件标头含生成命令与源文件；不手工编辑生成结果。
6. API 兼容变更必须包含 DTO、api.md、frontend service/types 和 contract tests 的同一 PR 或可依赖 PR。

## 10. 前端数据一致性

- Pinia 保存 view state、当前选择和有限缓存，不建立第二套权威 session/memory database。
- 对写请求使用 response data 更新 store；如果服务端返回异步 task，则先记录 task state，完成后刷新 resource。
- session/character/save 切换是状态边界：取消或结束旧 session 的活动 stream，再加载新 session 数据。
- 错误通知由 UI workflow 处理，底层 HTTP/service 只抛出类型化错误，避免重复 toast。
- 页面卸载要取消 AbortController、关闭/解绑 WS listener 并回收 Blob URL。
- 任何响应都验证 request/session/character 归属，再更新 store；迟到响应不能覆盖用户刚切换的页面状态。

## 11. 性能与可靠性

- REST 请求设置合理 timeout/body limit，非模型健康端点不做昂贵初始化。
- SSE 使用有界缓冲和合理的刷新批次，WS 限制每连接并发。
- provider 与任务队列设置 max concurrency、queue size、deadline 和 overload response。
- 事件丢失不应丢失任务的权威终态；通过 task query 恢复状态。
- 指标按 endpoint/provider/status 聚合，不把 user/session id 或全文 query 作为高基数 label。
- 对同一 logical operation 的多 transport 路径做共享 contract tests。

## 12. 契约验收矩阵

| 场景 | REST | SSE | WebSocket | Qt bridge |
|---|---|---|---|---|
| 正常成功 | 信封 code 200 | done 终态 | 成功事件 | decoder 成功 |
| 参数错误 | 1001/400 | error 事件 | error 事件 | 同类业务错误 |
| 未初始化 | 2001/503 | 可恢复 error | 错误事件 | 同类业务错误 |
| 超时 | 2002/504 或任务状态 | timeout terminal | timeout terminal | timeout 类型化 |
| 用户取消 | 幂等取消接口/状态 | cancelled terminal | cancelled event | cancellation result |
| 断连 | request 状态可查 | server cancel/明确保留策略 | cleanup in-flight | bridge connection failure |
| 重复创建 | 幂等键/409 | 不重复生成 | request id/operation id | 与 REST 相同 |
| 敏感配置 | 默认遮蔽 | 不输出密钥 | 不广播密钥 | 不返回明文默认值 |

## 13. 未解决且需先决策的问题

- API 的当前真实注册路径需导出后校准；save/audit router 已知有可能重复的 /api 前缀。
- WebSocket 的稳定 mount path 是 / 还是 /ws，需要检查 server 周边挂载行为并用客户端测试验证。
- 前端 API generator 的权威输入源需选定，不能同时由多套脚本各自生成。
- Qt bridge 的 operation registry 需要与后端调用入口一一对应，路径参数映射不能靠未实现的占位符注入。
