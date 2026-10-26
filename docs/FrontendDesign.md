# 前端架构设计

> 当前栈：Vue 3、TypeScript、Pinia、Vue Router、Axios；桌面模式通过 Qt WebChannel bridge 连接后端。本文描述职责边界和目标设计，不代表尚未存在的抽象已经落地。

## 1. 分层架构

~~~text
Views / Components
       |
       v
Composable / UI workflows
       |
       v
Pinia stores (view state / session state)
       |
       v
Domain API services (src/api/services)
       |
       v
Shared transport adapter (Axios / Qt bridge)
       |
       v
FastAPI contract (docs/api.md)
~~~

- View/Component 只负责展示、交互和可访问性；不拼 API 根地址、不实现信封解包。
- Composable 封装可重用的流式会话、音频、任务取消与订阅生命周期。
- Pinia 管理跨页面共享状态；避免组件、store、service 三处重复缓存同一业务实体。
- API services 按领域拆分 chat、session、memory、save、pipeline、service、task 等，负责类型化调用，不负责弹通知。
- Transport adapter 统一 timeout、request_id、错误对象、信封解包、取消和 desktop bridge 兼容。
- 自动生成的 types/services 视为只读；修改契约源并运行统一生成流程，不手改生成产物。

## 2. 当前前端入口

- src/main.ts 初始化 Vue app、Pinia、Router 与 composable/plugin。
- src/router/index.ts 使用 HTML5 history 并懒加载主菜单、聊天、设置、Markdown、测试和兜底页面。
- src/api/http.ts 基于 Axios，并按桌面环境替换 adapter 调用 window.qtwebview.api.call。
- src/api/services/*.ts 提供领域 API service；部分文件注释表示由生成流程创建。
- src/App.vue 加载 UI 配置，负责应用外壳与卸载清理。

## 3. 统一响应解包

普通 HTTP 和 desktop bridge 必须共用同一个 decoder：

1. 输入原始 ApiResponse：ok、code、message、data、request_id、ts。
2. 以当前后端成功 code 200 为标准；错误统一转换为 ApiClientError，保留稳定业务 code、HTTP status、request_id 和安全 message。
3. notification 只由页面 workflow 层触发；底层 service 不重复弹窗。
4. 取消、超时、网络错误和业务拒绝区分开；POST 操作请求默认不自动重试。
5. bridge 与 REST 返回相同 DTO 与错误语义，不允许分别使用 0 和 200 代表成功。

源码审阅发现 src/api/http.ts 的普通 Axios 分支判断 code === 200，而 desktop adapter 判断 result.code === 0；此处为 P0 修复项。另见 api.md 的差异表。

## 4. 流式聊天状态

建议建立有明确生命周期的 stream composable/controller：

- 请求绑定 session_id、request_id、route、source；每个 stream 独立维护状态。
- 状态机：idle → connecting → streaming → completed | failed | cancelled。
- SSE/WebSocket chunk、command.result、task.update 和 chat.done 按请求 ID 归属；工具结果不能误拼到 assistant 正文。
- 页面卸载时取消请求/订阅、移除 listener、停止播放、释放 Blob URL。
- 网络断开后默认标记部分输出并停止；仅协议显式支持 resume 时才自动续接。
- 对 token chunk 批量刷新响应状态，避免每个 token 都触发完整消息列表重渲染。
- 并发请求需要独立 cancel handle，不能用一个全局布尔值取消所有聊天。

## 5. Store 职责

| Store / 状态域 | 负责 | 不负责 |
|---|---|---|
| 用户/UI 配置 | 主题、布局、偏好 | provider secret、服务端运行真相 |
| Chat/Session | 当前会话、消息、stream state、取消 | 复制整套后端持久化逻辑 |
| Character | 当前角色、角色状态显示 | 在组件里直接修改领域对象 |
| Pipeline/Service | provider/服务状态、任务状态 | 取代后端状态机 |
| Settings | 表单草稿、字段校验 | 将密钥存进 localStorage 或 URL |
| Memory/Save | 查询、用户确认的删除/保存/恢复 | 自动加载存档或将低置信记忆当事实 |

后端是业务状态的权威。成功操作后用响应数据更新或重新获取；不能仅因按钮点击就显示成功。

## 6. Desktop bridge 与 Web 共用契约

- 两种 transport 使用同样的 service method 和 ApiResponse decoder。
- bridge operation name 应来自显式映射或生成 metadata；不依赖脆弱的字符串猜测。
- bridge 初始化设置 timeout/取消和可诊断错误，不能无限等待。
- path params 应从最终 URL 正确解析并编码。当前 injectPathParams 主要扫描 URL pattern，没有显式从 URL 实值取出参数，实际参数是否由 bridge 层处理需复核。
- 对 REST 和 bridge 共享测试向量：成功、业务失败、404、超时、取消、空 data 和流式事件。
- 本地 loopback API 仍需考虑恶意网页对高权限 localhost endpoint 的滥用；CORS 不能单独作为授权防线。

## 7. 性能与资源管理

- 维持 route-level lazy loading。
- 大型消息历史优先虚拟滚动；按 message id 增量更新，避免深度 watch 大数组。
- markdown 高亮、大音频处理与大响应解析应避免重复阻塞 UI thread。
- 尽量使用 Blob/ArrayBuffer 避免多次 Base64 复制。
- 对流式缓冲、日志 UI、通知数量和任务历史设置上限。
- 前端缓存提供清晰的失效与刷新策略，避免和后端副本争抢权威。

## 8. 安全与可访问性

- provider API key 不进入 localStorage、Pinia persistence、URL、埋点、console 或错误通知。
- markdown/HTML 输出按上下文安全渲染；不默认执行原始 HTML 与外部脚本。
- 前端确认不是后端授权的替代；服务端必须重复验证能力和参数。
- 关键操作有 loading、disabled、success/failure、cancelled 状态；删除/恢复有明确影响说明。
- 对用户可见错误隐藏堆栈、绝对路径和内部配置。
