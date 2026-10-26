# 安全与审计设计

> 当前 audit controller 主要列出服务和工具能力，不应描述成完整的安全审计日志系统。

## 1. 威胁模型

保护对象包括本机 API/Qt bridge、配置秘密、会话/记忆/存档、外部工具、provider 凭据、日志和生成文件。

风险场景：
- 本机网页或其他进程调用有副作用的 loopback API。
- prompt injection 通过网页、文件、记忆或工具结果影响命令执行。
- 路径穿越、任意脚本、无限运行和资源耗尽。
- api key 经 raw endpoint、异常、日志或浏览器持久化泄露。
- 一个 session 的记忆出现在另一个 session/角色上下文。
- SQLite/FAISS 部分写入、索引损坏、压缩或旧快照恢复导致数据复活。
- request_id、日志和审计事件意外存储隐私正文。
- 多层重试放大 provider 故障和队列积压。

## 2. 当前源码关注点

- modules/api/response.py 实现统一信封、request_id 中间件和异常处理。未处理异常当前会将异常类型/消息用于 response message；目标应回传稳定通用消息，详细信息仅记录在受控日志。
- controllers/pipline.py 有 api_key/token/secret/password 等敏感字段遮蔽，但 raw=true 可返回原值；应移除通用原文回显或限制到显式受控的本地调试。
- src/api/http.ts 从 localStorage 读取 token；不得扩展为存储 provider API key。
- modules/tools/skills 有沙盒相关代码；现有项目文档说明 shell skill 被拒绝，JavaScript skill 尚未实现。隔离未完成前不应启用。
- controllers/audit.py 暴露服务与工具目录；不能替代 audit event log。

## 3. 最小权限

- API 默认监听 127.0.0.1；远程监听必须显式开启认证，并进行来源/网络风险评审。CORS 不是身份验证。
- REST、WebSocket 和 Qt bridge 使用同一套能力模型。
- 配置修改、技能执行、存档加载/删除和记忆清除单独定义 capability。
- 参数使用 allowlist schema，限制字符串/数组大小、枚举、ID、超时和输出长度。
- 对路径先 canonicalize/resolve，再确认仍在允许根目录；避免 traversal 和符号链接逃逸。
- shell/任意脚本默认禁用。允许的脚本需独立进程/沙盒、超时、内存/输出限制、受控网络和临时目录清理。
- LLM 产出意图而非授权；确定性执行层检查身份、权限、参数和业务状态。
- 网页、文件、检索记忆和工具输出均视为不可信数据，并显式标注来源。

## 4. 秘密与配置

- 默认只返回 configured 状态或遮蔽值，不返回明文 provider key。
- raw secret 不应作为通用 query 参数；若开发场景必须支持，需要本地可信环境、显式确认、短时授权和审计。
- 秘密变更只记录 secret name、动作、调用来源和结果，不记录秘密值。
- 对异常 message、任务结果、日志和通知使用 secret scrubber。
- 配置文件权限应尽可能收紧；备份/存档导出识别并排除秘密。
- 前端不得将 provider key 放入 localStorage、Pinia persistence、URL、埋点或 console。

## 5. 审计事件（目标 schema）

~~~json
{
  "event_id": "uuid",
  "ts": 0,
  "request_id": "request-id",
  "actor": {"type": "local_user_or_process", "id": "optional"},
  "action": "memory.delete",
  "resource": {"type": "memory", "id": "opaque-id"},
  "decision": "allow",
  "result": "success",
  "reason_code": "policy_code",
  "source": "api|ui|task|recovery",
  "metadata": {"schema_version": 1}
}
~~~

此 schema 是设计提案，不是当前格式。规则：
- action/reason_code 稳定且低基数，不把用户自由文本作为 event name。
- 敏感读取/导出只记录 resource ID、计数、hash，不记全文。
- 审计事件与普通 debug 日志分离，定义访问控制和保留期限。
- 成功/失败/拒绝均可追踪；影响数据的任务记录 before/after revision。
- 审计日志不是业务事务提交证据的替代品。
- 本地可写日志并不自动具备防篡改/不可抵赖能力；合规级需求需额外设计签名或远端只写存储。

## 6. request_id、日志与错误

- 服务端为缺省 request_id 的请求生成随机 ID；外部提供值时限制长度、字符集并拒绝换行。
- request_id 传播到 async task 和 WebSocket 请求；后台任务保留 parent_request_id。
- 客户端只收稳定错误类别、简短信息和 request_id，详细堆栈仅记录在脱敏的本地日志。
- 结构化日志建议字段：ts、level、logger、request_id、task_id、event、duration_ms、status、provider。
- 默认不记录正文、prompt、音频/图片或私人记忆。诊断采样必须显式 opt-in、有短保留期并脱敏。
- 日志队列和磁盘增长有上限，提供 dropped counter 与明确 flush。

## 7. 记忆与存档隐私

- 查询最开始就按 session/owner 过滤，禁止全局 top-K 后才过滤。
- 删除需覆盖 metadata、FAISS vector/mapping、compressed references、cache 与 snapshots。
- 清理无法立即完成时先写 tombstone 并在检索层立刻排除，再后台物理清理。
- restore 必须重放删除墓碑，防止旧快照复活已删除记忆。
- 导出清楚标明数据范围并排除密钥；归档含 manifest/checksum。
- 删除请求需提供实际完成状态，不能以“已从当前 prompt 移除”代替永久删除。

## 8. 防耗尽与故障安全

- 队列有限，满载时拒绝或返回明确可重试错误。
- provider timeout、最大 response body、音视频大小、工具运行时间和 tool steps 有上限。
- 指数退避加 jitter，并设总重试预算，防止多层重试相乘。
- 限制 WebSocket 消息大小、连接数、单连接在途请求数和订阅数量。
- health check 不触发模型初始化、全量索引 rebuild 或全盘扫描。
- provider 切换、存档加载、GC 和索引 rebuild 需版本检查或互斥，防止并发覆盖。

## 9. 验收清单

- [ ] 无未授权命令执行或任意文件路径访问。
- [ ] 默认不回显密钥，异常/日志不泄漏 secret。
- [ ] 检索不能跨 session 召回。
- [ ] 删除记忆后，查询、压缩、缓存、快照恢复均不能复活。
- [ ] 恶意网页/工具输出不能改变授权或工具白名单。
- [ ] 取消/超时后资源释放，后台异常可追踪。
- [ ] 审计记录动作/资源/决策/结果，但不存隐私正文。
- [ ] 远程绑定、CORS、认证和来源限制经安全审查。
