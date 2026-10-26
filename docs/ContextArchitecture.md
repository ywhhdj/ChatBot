# 上下文架构设计：请求、会话、角色、记忆与工具隔离

> 状态：基于 dev 源码的目标架构。当前 UserContext 是单例，内部使用有界 deque 保存 MessageContext；MessageContext 含 session_id，但 get_current_messages() 返回所有 USER/ASSISTANT 消息且未按 session_id 过滤。除非调用链其他地方另行隔离，这构成跨会话上下文混入风险。本设计将其列为 P0，不把现有实现描述成已完成隔离。

## 1. 目标与原则

上下文不是一个全局字符串，也不应由任何模块随意拼接。ChatBot 应使用显式、带边界、可追踪的 ContextSnapshot，把“本次请求需要模型看到的资料”与“业务系统全部保存的数据”分开。

目标：
- 同一角色可以服务多个会话，但不同 session 的消息/记忆不能串入同一 prompt。
- 当前输入、角色人设、用户/会话事实、工具能力与工具输出分别建模。
- 记忆检索只提供有来源的候选，不获得权限；工具输出不能覆盖 system policy。
- Prompt 由一个纯构建步骤按优先级和 token 预算组合，便于测试、复现和审计。
- 上下文数据带 request_id、session_id、character_id、source 和时间信息，便于重放故障，但默认不记录私人正文日志。

## 2. 五类上下文边界

~~~text
                    RequestContext (每次请求)
       request_id / trace_id / cancellation / deadline
                              |
                              v
+------------------- ConversationContext -------------------+
|                                                           |
|  CharacterContext    User/SessionContext    InputContext   |
|  人设/规则/风格       会话内消息/事实         当前输入/来源   |
|                                                           |
|  ToolContext          RetrievedMemoryContext               |
|  工具能力/Schema      候选记忆/来源/置信度/冲突             |
|                                                           |
+-------------------------+---------------------------------+
                          |
                          v
                  PromptBuilder (纯函数)
     优先级排序 + 安全标记 + token 预算 + 去重 + 截断
                          |
                          v
                     Prompt DTO
                          |
                          v
                   LLM / tool router
~~~

### 各类上下文契约

| 上下文 | 生命周期 | 权威来源 | 是否默认进 prompt | 限制 |
|---|---|---|---|---|
| RequestContext | 单次调用 | API/调度器 | 仅必要的元数据 | 不保存全量聊天正文；拥有 deadline/cancel |
| CharacterContext | 角色版本/单次快照 | CharacterManager/角色配置 | 是，受 token budget 限制 | 只包含当前角色，不混入其他角色状态 |
| User/SessionContext | session 生命周期 | SessionManager + UserContext/持久化记录 | 最近消息经预算裁剪 | 必须严格 session-scoped |
| InputContext | 单次请求 | 当前 API payload | 是 | 原样保留用户文本；只做长度/格式校验，不把它升格为系统规则 |
| ToolContext | 单次任务/授权快照 | ServiceManager、SkillManager、capability registry | 只有当前 route 需要的 schema | 只暴露允许调用的工具；描述文本不是权限 |
| RetrievedMemoryContext | 单次检索 | MemorySystem | 仅高相关、有效且安全的候选 | 每条有 source、score、confidence、validity；低置信/冲突可拒绝注入 |

角色设定、会话历史、记忆候选和工具说明在语义上不同，必须在构建 Prompt DTO 时仍保留 source/type 元数据，而非提前拼成不可区分的大段文本。

## 3. 当前源码映射与风险

- \`src_py/modules/context/user.py\`：UserContext 单例、\`deque(maxlen=max_message*2)\`、消息 ID、session_id、短期消息、记忆片段和压缩流程。
- \`src_py/modules/pipeline/chat.py\`：请求被路由到调度器 loop，再调用 CharacterOrchestrator。
- \`src_py/modules/pipeline/orchestrator.py\`：PURE_CHAT / TOOL_CALL / MIXED 编排、角色化回复、工具执行、近期对话和 UserContext。
- \`src_py/modules/manager/session/\`：会话和 round record 持久化。
- \`src_py/modules/characters/\`、\`manager/character.py\`：角色定义、当前角色与运行时状态。

### P0 风险：全局 deque 与 session 隔离

当前 \`UserContext.get_current_messages()\` 只筛选 USER/ASSISTANT 角色，不按 \`session_id\` 过滤；\`get_memory_snippets()\` 同样汇总所有 SYSTEM 消息。消息本身虽保存 session_id，但 Orchestrator 通过全局 getter 取得消息后用于构造模型输入（当前调用点包含 chat/task prompt 构建）。这意味着多个 session 交错使用时，可能把其他 session 的近期消息/记忆引入 prompt。

目标不是在现有 getter 上临时添加一个可选过滤参数后即结束，而是把上下文存储本身改为按 session 隔离，所有构建入口必须显式传入 session_id，并增加交错并发测试。

其他风险：
- SYSTEM 消息同时存放记忆注入内容，清理/刷新时容易误删或重复注入。
- singleton 全局 memory system 与角色/session 的生命周期不是同一概念。
- \`build_memory_messages()\` 会将摘要追加回共享消息窗口；若多次调用而不替换同一批 memory snippets，可能产生旧摘要残留或重复。
- deque 容量按消息条数限制，不等于 token 预算，长消息仍可能使 prompt 超限。
- 当前工具 schema/工具结果与自然语言历史应显式分离，避免工具输出成为“可信指令”。

## 4. 目标对象模型

以下为领域层概念模型，不代表现有 Python 类型。

~~~python
@dataclass(frozen=True)
class RequestContext:
    request_id: str
    trace_id: str
    session_id: str
    character_id: str
    deadline_monotonic: float
    source: str
    cancellation: CancellationToken

@dataclass(frozen=True)
class ContextMessage:
    id: str
    session_id: str
    role: Literal["system", "user", "assistant", "tool"]
    source: str
    content: str
    created_at: float
    trusted_level: Literal["policy", "configured", "user", "retrieved", "tool"]
    metadata: Mapping[str, object]

@dataclass(frozen=True)
class RetrievedMemory:
    id: str
    session_id: str
    kind: str
    content: str
    score: float
    confidence: float
    source_ids: tuple[str, ...]
    valid_until: float | None
    conflict_group: str | None
~~~

要求：
- RequestContext 是请求作用域对象，不用全局可变变量传递当前 session。
- 任何查询都要带显式 session_id/owner scope。
- ContextSnapshot 在 build 完后不可变；本轮中间结果写入新的状态或事件，不原地修改已交给 LLM 的快照。
- 不把 token、provider key 或不必要的绝对路径塞入上下文。
- source/trust 标签由程序产生，不允许 LLM 对输入内容自行声明信任级别。

## 5. Prompt 构建顺序与安全优先级

建议顺序：

1. 系统安全策略与格式约束（最高优先级，代码/受控配置提供）。
2. 当前角色的人设与行为范围（不能覆盖系统策略）。
3. 工具调用协议与本轮获准工具的 schema（仅 TOOL_CALL/MIXED 需要）。
4. 用户已确认的稳定事实/偏好候选（含来源、置信度、有效期）。
5. 与当前 query 相关的情节/摘要候选（不可信资料，必须以引用/事实片段标记）。
6. 最近会话消息（严格限 session_id，保留 role 顺序）。
7. 当前用户输入（作为本轮输入，不可解释为更高优先级指令）。
8. 生成参数与输出预算（不作为自然语言拼接）。

工具执行结果作为独立 tool-result record；再次请求 LLM 总结时，将其作为不可信观察结果包裹，而不是插入 system prompt。

### PromptBuilder 伪代码

~~~text
build_prompt(request_context, character_snapshot, session_window,
             tool_catalog, memory_candidates, token_budget):
    assert session_window.session_id == request_context.session_id
    assert all(m.session_id == request_context.session_id for m in session_window.messages)
    memory = filter_scope_and_validity(memory_candidates, request_context.session_id)
    memory = resolve_or_mark_conflicts(memory)
    memory = rank_and_deduplicate(memory, current_input)
    sections = [
        system_policy,
        character_snapshot,
        tools_for_allowed_route(tool_catalog),
        trusted_user_facts(memory),
        retrieved_evidence(memory),
        session_window,
        current_input
    ]
    return truncate_by_priority(sections, token_budget)
~~~

预算分配使用可配置区间而非写死比例：system policy 必须保留；工具 schema 只在需要时加入；近期消息和召回记忆按质量/成本分配；为模型输出预留 token。对每个部分记录 included/excluded reason、token estimate 和 source IDs，但默认只记录计数，不记录正文。

## 6. SessionContext 的目标存储

不能在同一条全局 deque 上靠约定隔离多个会话。推荐逻辑接口：

~~~python
class ConversationContextStore(Protocol):
    async def append(self, session_id: str, message: ContextMessage) -> None: ...
    async def get_window(self, session_id: str, limit: int) -> list[ContextMessage]: ...
    async def replace_memory_layer(self, session_id: str, layer: str,
                                   snippets: list[RetrievedMemory]) -> None: ...
    async def clear_session_window(self, session_id: str) -> None: ...
~~~

初期实现可用内存中的 \`dict[session_id, SessionWindow]\`；每个窗口设置消息/ token 双上限，闲置窗口按策略回收。持久化仍由已有 session/memory storage 负责，避免双写两份权威历史。写入长期持久化失败时需有明确状态，而不能让内存上下文“看似成功”且重启后丢失。

锁策略：
- 锁按 session 分片，不使用一把全局锁串行所有会话。
- 同一 session 同一时间只允许一个顺序修改上下文的写入者，或者用 message sequence/round_id 做乐观并发控制。
- 不在持有锁时调用 LLM、检索 embedding、工具执行或磁盘长操作。
- 仅对 append/replace 的短临界区加锁，并在复制快照后释放锁再构建 prompt。

## 7. 上下文更新状态机

~~~text
RECEIVED
  -> VALIDATED
  -> USER_MESSAGE_APPENDED
  -> ROUTED
  -> CONTEXT_SNAPSHOT_BUILT
  -> MODEL_STREAMING
      -> TOOL_REQUESTED -> AUTHORIZED -> TOOL_RUNNING -> TOOL_RESULT_CAPTURED
      -> MODEL_CONTINUED (optional)
  -> ASSISTANT_FINALIZED
  -> PERSISTED
  -> COMPLETED
~~~

对失败/取消：
- 用户消息是否保留由明确策略决定；建议保留 input 与 failed status 作为 round record，不伪造 assistant 成功答案。
- 工具执行完成但最终总结失败时，保留 tool result 与 round state，以便恢复/审计。
- cancelled request 不应由迟到的 chunk 覆盖 completed/cancelled 状态。
- 超时同时传递到 LLM、检索和工具；不允许每个子步骤重新获得完整总 timeout。

## 8. 数据隔离与提示注入防线

- session_id 来自会话服务/请求校验，不应只相信一个任意前端字符串；确认资源属于当前本地用户/会话。
- 检索先过滤 scope，再召回/融合；缓存 key 至少包括 session_id、memory revision、embedding version 与 query fingerprint。
- 记忆按“事实候选/来源”注入，不拼成看似 system 指令的纯文本。
- 工具输出、网页、文件、OCR、ASR 转写等统一标为 untrusted observation，并加长度限制。
- 安全 policy、工具 allowlist、路径白名单和授权判断在代码执行，不让模型自己选择 trust_level。
- session switch 后必须绑定新的 ContextSnapshot，并在发出下一轮模型请求前验证 session_id 与 snapshot/session 一致。

## 9. 兼容迁移

1. 新增显式 session-scoped 的 ContextStore facade，暂时由它包装旧 UserContext。
2. 所有 orchestrator prompt 构建入口改为显式请求 session_id，并验证窗口只包含此 session。
3. 记忆片段单独保存在 session 的 memory slot，不再作为不可区分的 SYSTEM 对话消息永久追加到同一 deque。
4. 保留旧 getter 作为 deprecated adapter，但调用必须传 session_id；无 session_id 调用应先记录兼容使用并最终移除，而不是默认读全局数据。
5. 旧的 UserContext/MessageContext 序列化数据保留读取兼容；迁移期间按 message.session_id 分桶，不能用当前活动 session 一次性接管全部历史。
6. 增加并发交错验收：A 会话写入 Alice 的偏好、B 会话写入 Bob 的秘密，A/B 各自 prompt 不得包含另一方消息或记忆。

## 10. 验收标准

- [ ] 两个 session 交错输入、并发生成、切换角色时没有上下文交叉污染。
- [ ] 所有 PromptBuilder 入口都要求 request_id、session_id、character_id。
- [ ] prompt 符合 token 上限，系统策略不会因普通内容超长被截断。
- [ ] 记忆可追溯来源和置信度，冲突不会被静默合并。
- [ ] tool/web/file 输出以不可信观察数据注入，不可能更改权限。
- [ ] 请求取消/超时后无迟到 token 覆盖终态，也无残留订阅。
- [ ] session window 不重复追加旧 memory snippets，clear 只清目标 session。
