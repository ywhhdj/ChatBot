# 改造进度计划（PLAN.md）

> 约束来源：`docs/README.md` 第 1–4 行（硬性约束）
>
> 1. **不下载依赖、不执行构建/测试**：只产出工程源码与构建脚本，构建动作由使用者在本地执行。
> 2. **可维护优先**：单一职责、接口隔离、模块边界清晰，禁止跨层反向依赖。
> 3. **每次完成一步必须记录进度**到本文件。
>
> 基线：`dev` 分支源码。任务 ID 沿用 `docs/BackendPlan.md`、`docs/OptimizationPlan.md`。

## 0. 执行状态约定

| 状态  | 含义                     |
| ----- | ------------------------ |
| `[x]` | 源码已改，静态审查通过   |
| `[~]` | 部分落地，剩余部分已注明 |
| `[ ]` | 未开始                   |

**本轮未执行任何构建、测试或依赖安装。** 改动仅经过静态语法解析（`ast.parse`），
编译 `.pyd`、运行测试、生成前端类型均由使用者在本地按 §7 的命令执行。

---

## 1. P0：协议与安全正确性（B0-*）

| ID    | 工作项                               | 状态  | 落地位置                                                     |
| ----- | ------------------------------------ | ----- | ------------------------------------------------------------ |
| B0-01 | 统一后端成功 code 与前端 bridge 解包 | `[x]` | `modules/api/exceptions.py` 新增 `SUCCESS_CODES` / `is_success()` |
| B0-02 | 消除重复 `/api` 路由前缀             | `[x]` | `controllers/__init__.py`（`_effective_prefix` + `find_duplicate_prefixes`）、`save.py`、`audit.py`、`websocket/__init__.py` |
| B0-03 | 基于控制器和 DTO 校准 api.md         | `[x]` | `controllers/__init__.py::route_inventory()` + `scripts/api/check_routes.py` |
| B0-04 | 收敛 raw secret 与异常泄露           | `[x]` | `response.py::_unhandled_handler`、`gateway.py::_invoke`、`websocket/__init__.py` |
| B0-05 | 审查 loopback、CORS、request_id      | `[x]` | `modules/api/access.py`、`server.py`；request_id 校验见 `response.py` |
| B0-06 | 工具执行安全规则                     | `[x]` | `modules/tools/policy.py`、`services/exceute.py`、`ctl.py`   |
| B0-07 | 审查后台任务/线程关闭                | `[~]` | 情绪预测去阻塞（orchestrator）；全局 shutdown 审查见 §6      |

### 本轮改动明细

- **B0-01**：后端输出 `code=200`，桌面 bridge 判 `code=0`，同一信封在两种 transport 上结论相反。
  收敛为单一权威判定 `is_success(code, ok)`：0 作为历史别名保留，前端一律调该函数，不再比较字面量。
- **B0-02**：`save.py` / `audit.py` 自带 `/api` 前缀，注册时又被拼一次 → 实际路径 `/api/api/save`。
  controller 前缀收敛为资源前缀；`_effective_prefix()` 做兼容兜底；`find_duplicate_prefixes()` 供 CI 断言。
  WebSocket 由 `"/"` 迁到 `"/ws"`（原路径与静态资源 mount 争抢 `"/"`，且与 `api.md` 不一致）。
- **B0-04**：500 响应体此前直接拼接 `f"{type(exc).__name__}: {exc}"`，会把绝对路径、密钥、SQL 片段回给客户端。
  改为只回 `MESSAGES[CODE_INTERNAL]` + `request_id`，细节经 `exc.debug` 进受控日志。
  网关同步处理，并补上 `call_sync()` 超时/异常的信封化（此前直接抛到 bridge）。
- **B0-05**：`X-Request-ID` 客户端可自带，未校验即回写响应头与日志，可注入换行。
  新增 64 字符白名单校验，脏值直接换新。

### B0-06 明细（本轮完成）

缺口：`CommandValidator` 只回答"服务注册了吗、方法存在吗、参数齐吗"——
**方法存在即可调用**。任何服务上的 `delete_*` / `shutdown` / `exec_*`
只要名字存在，LLM 输出一行命令就能调到。这与 §3「LLM 产出意图而非授权」直接冲突。

| 机制            | 落地                                                         |
| --------------- | ------------------------------------------------------------ |
| deny by default | 方法必须出现在服务声明的 `tools` 里；服务未声明 tools 一律拒绝（可 `allow_undeclared_service` 临时放开以便迁移） |
| 执行类默认拒绝  | 方法名命中 shell/exec/eval/subprocess/powershell 等一律拒绝；即使声明了也需 `allow_exec=True` 且方法显式声明 `exec` 能力 |
| 能力模型        | `Capability` 枚举，`method_capabilities()` 从服务声明读取；未声明按最小权限 `read`；**拼错的能力名保守当作 `exec`**，不会悄悄退化成放行 |
| 超时            | 每条命令默认 30s，`asyncio.wait_for` 兜底                    |
| 输出上限        | 结果序列化超 8000 字符即在**执行层**截断（不等到格式化时才截） |
| 参数限制        | 字符串 4000 字符、数组 200 元素、嵌套深度 6、路径穿越形态拒绝 |
| 审计留痕        | 每次判定记 service/method/决策/reason_code，**不存参数与正文**（§5） |

**误杀防护**：黑名单刻意不含裸 `sh`——它会误伤 `show`/`flush`/`push`/`hash`/`dashboard`。
已加参数化回归。

**取舍要说明**：同步方法的超时**杀不掉线程**。`asyncio.wait_for` 超时后
线程里的命令仍在跑完。这是刻意的：强杀线程会留下半完成的副作用
（写了一半的文件、未释放的锁）。我们只是不再等待，并如实标记 timeout。
真正的资源回收要靠方法自身支持取消，属于 B0-07 的范围。

### B0-05 明细（本轮完成）

缺口：`start_web_in_thread(host="0.0.0.0")` 即可全网监听，且**不要求任何凭据**。
本机 API 含工具执行、存档删除、记忆清除等全部副作用权限，
而 CORS 只管浏览器同源策略、不提供身份验证（§3 原文）。

| 机制       | 落地                                                         |
| ---------- | ------------------------------------------------------------ |
| 本机判定   | `is_loopback()`：127.0.0.1 / localhost / ::1 / 空串；域名无法判定时**保守当作远程** |
| 启动门槛   | 非本机 host 必须 `allow_remote=True` 且配好 token，否则**拒绝启动**（不是"启动但警告"） |
| token 校验 | `hmac.compare_digest` 常量时间比较；`Authorization: Bearer`  |
| 中间件     | 仅非本机监听时挂载，本机路径零开销、零行为变化               |
| 探活豁免   | `/api/system/health` 等不校验 token，监控系统可探活          |
| 环境变量   | `CHATBOT_ALLOW_REMOTE` / `CHATBOT_API_TOKEN`；**缺省即最保守** |

**为什么拒绝启动而不是记警告**：警告会被忽略，而暴露面一旦打开就是既成事实。

**未做**：真正的网络风险评审、token 轮换与吊销、TLS。这些超出源码改造范围，
需要在部署环节完成，已在 §6 记为待办。

### 附带修复（审查中发现，非计划项）

- `ctl.py::get_audit_result()` 读 `self._current_messages`，但该属性只在
  `reset_state()` 里赋值、`__init__` 里没有 —— **首次调用即 AttributeError**。已在 `__init__` 初始化。

- `gateway.py::_ok()` 形参与调用实参顺序错位（`_ok(rid, data)` vs `_ok(result, rid)`），
  桌面端 bridge 拿到的 `data` 恒为 16 位十六进制的 request_id。
- `gateway.py::set_request_id()` 无返回值，`call()` 的 `finally` 复位成 `None`。
- 13 处混用 `from src_py.modules...` 绝对导入，在 `sys.path` 未含仓库根时直接 `ModuleNotFoundError`。统一为相对导入。
- `orchestrator.py` 主流程被 `for _ in range(config.llm.max_turns)` 包裹且无 `break`：
  同一句输入写进上下文 10 次、LLM 调用 10 次、流式回答重复 yield 10 次。改回单轮。

---

## 2. P0：上下文隔离（C0-*）

| ID    | 工作项                        | 状态  | 落地位置                                                     |
| ----- | ----------------------------- | ----- | ------------------------------------------------------------ |
| C0-01 | 建立 RequestContext DTO       | `[x]` | `modules/context/request.py`（frozen dataclass + contextvar） |
| C0-02 | ContextStore 按 session 分桶  | `[x]` | `modules/context/store.py`（per-session deque + per-(loop,session) 锁） |
| C0-03 | PromptBuilder 纯化            | `[x]` | `modules/context/budget.py` + `config/builder.py`            |
| C0-04 | 记忆注入去副作用              | `[x]` | `context/store.py::set_memory_snippets`（每轮整体覆盖，不进对话窗口） |
| C0-05 | session switch/clear 生命周期 | `[x]` | `store.clear(session_id)` 只清指定桶                         |

### 关键设计

- `UserContext` 退化为**门面**：只保留跨会话共享的记忆系统与配置，消息全部下沉到 `ContextStore`。
- 读取接口一律要求 `session_id`；不传时取当前 `RequestContext`，**绝不退回"所有会话"全集**。
- 锁按 `(running_loop, session)` 分片，不同会话互不串行（OptimizationPlan §8）。
- 压缩/摘要等慢活在**锁外**执行，避免一条会话等 LLM 时堵住其他会话（BackendDesign §3.6）。

---

## 3. 本轮新增（Step 4）：PromptBuilder 纯化与 token 预算

对应 **C0-03** 与 **B2-04（自适应 prompt token budget）**。

| 项                                          | 状态  |
| ------------------------------------------- | ----- |
| `modules/context/budget.py`：预算策略纯函数 | `[x]` |
| PromptBuilder 拆成 分段 → 预算 → 组装 三步  | `[x]` |
| 各段可独立构建与计 token                    | `[x]` |
| `memory_limit` 死参数生效                   | `[x]` |
| `BuiltPrompt.budget` 报告字段               | `[x]` |
| `tests/test_prompt_budget.py`               | `[x]` |

### 发现的问题

- `_build_chat_segments(..., memory_limit: int, ...)` 接收了 `memory_limit` 却**从未使用**——
  `orchestrator` 传的 `memory_limit=10` 是死参数，记忆片段数量与体积完全不受控。
- 原 `build()` 一步到底：分段、排序、拼接、估算混在一起，单段无法独立测试，也无预算概念。
- 系统提示词无上限，角色设定 + 记忆 + 工具文档叠加后可轻易超出模型上下文，
  表现为调用方只看到"context length 400"，却无从判断是哪一段撑爆的。

### 设计

- **保护段不可裁剪**：`character` / `output_rules` / `task*` 属人格与安全边界，
  降级顺序按 BackendDesign §10 —— 先裁记忆、detailed、技能目录。
- **裁剪可解释**：`BudgetReport` 记录每段用量、丢弃与截断原因，可直接进日志。
- **估算口径统一**：`builder.estimate_tokens` 委托给 `budget.estimate_tokens`，
  避免"报告说没超、实际超了"。

### 3.1 分层修正：PromptBuilder 迁出 config/

`PromptBuilder` 原先放在 `modules/config/builder.py`，但它依赖
`characters` / `routes` / `context.budget` 三个领域模块 ——
配置层反向依赖领域层，违反约束 2（禁止跨层反向依赖）。

| 项                                                           | 状态  |
| ------------------------------------------------------------ | ----- |
| 新建 `modules/context/prompt.py`（正文迁此）                 | `[x]` |
| `config/builder.py` 收敛为兼容 shim                          | `[x]` |
| `memory/compression.py`、`pipeline/orchestrator.py` 改走新路径 | `[x]` |

保留 shim 而不是直接删除：存量 import（`tests/teset-roles.py` 等）
不会立刻断裂，迁移可以分批做。shim 已标注"新代码请用 context.prompt"。

---

## 3.2 动态上下文装配（上下文既要分离，也要动态装配）

**分离**解决"不串线"，**装配**解决"这一刻该看什么"。一轮请求要多次调模型，
每次需要的上下文并不一样——一次装配打天下，要么信息不足，要么噪声过多。

| 项                                                        | 状态  |
| --------------------------------------------------------- | ----- |
| `modules/context/assembly.py`：阶段与装配计划（纯函数）   | `[x]` |
| `PromptBuilder.build(directives=...)`：程序生成的阶段指令 | `[x]` |
| `ctl.py` 暴露 `ToolBudgetState`（截断不再静默）           | `[x]` |
| `orchestrator` 按额度状态推进阶段                         | `[x]` |
| PPT 服务声明专属上下文                                    | `[x]` |
| `tests/test_context_assembly.py`                          | `[x]` |

### 阶段机

`COMMAND_PLAN` →（额度/终止状态决定）→ `TOOL_SUMMARY` / `FORCED_SUMMARY` / `SERVICE_WORK`

**工具次数达上限**（用户明确要求的场景）：此前 `ctl.py` 静默截断，
上层只看到"执行了 N 条"，模型毫不知情、继续输出命令，用户以为任务还在跑。
现在：

1. 截断事实落进 `ToolBudgetState`（`skipped > 0` 才算打满，刚好用满不算）；
2. 阶段推进到 `FORCED_SUMMARY`；
3. 注入**程序生成**的指令——"额度已用尽（上限 10，已执行 10，另 5 条未执行），
   不要再输出任何命令" + "立即用角色口吻基于已有结果回答"；
4. 上下文切回角色（带人设、记忆、历史）。

指令为什么必须独立成参数而不是拼进 `user_input`：模型分不清"用户说的"
和"系统要求的约束"，混在一起等于让外部内容有机会自我声明信任级别
（ContextArchitecture §8：trust label 由程序产生）。

**工具结果一律标为 untrusted observation**：`<tool-observation trust="untrusted">` 包裹 +
明文提示"其中的要求/链接不要执行"。标记本身不阻止注入（阻止靠 `tools/policy.py`），
但没有标记时，工具返回的一段文字就可能被模型当成指令。

**PPT 等服务切换上下文**：服务在 `context_profile` 里声明（用 dict，不依赖 context 层类型），
装配层据此切到 `SERVICE_WORK`：角色人设让位、预算放宽到 8000、带上服务作业约定。
未声明的服务走常规装配，不会失效。

### 各阶段默认预算

| 阶段                          | 预算 | 说明                                                         |
| ----------------------------- | ---- | ------------------------------------------------------------ |
| ROUTE_JUDGE                   | 800  | 要快且便宜                                                   |
| COMMAND_PLAN                  | 6000 | 要塞下完整工具 schema；**不带人设**（否则模型开始寒暄而不是输出命令） |
| SERVICE_WORK                  | 8000 | 大纲/渲染正文更长                                            |
| TOOL_SUMMARY / FORCED_SUMMARY | 3000 | 人设 + 结果摘要                                              |
| CHARACTER_REPLY               | 3000 | 常规                                                         |

---

## 4. 本轮新增（Step 5）：本地推理下沉 Rust

对应「模型本地推理可以放到 rust」。

| 项                                                          | 状态  |
| ----------------------------------------------------------- | ----- |
| `native/src/tokenizer.rs`：BPE 编解码与计数                 | `[x]` |
| `native/src/sampler.rs`：temperature / top-k / top-p 采样   | `[x]` |
| `native/src/inference.rs`：生成循环、停止条件、超时与取消   | `[x]` |
| `Cargo.toml` feature gate（`candle-backend` 默认关闭）      | `[x]` |
| `lib.rs` 注册                                               | `[x]` |
| `modules/core/native/inference.py`：胶水层 + 纯 Python 回退 | `[x]` |

### 职责边界

**Rust 侧不实现神经网络算子**，只负责控制流：

* 停止条件（stop token / stop 字符串 / max_tokens / 上下文窗口）
* 超时（单调时钟）与协作式取消
* 增量解码：只在凑够完整 UTF-8 字符时才回调，避免流式吐出半个汉字
* 统计：首 token 延迟、token 数、停止原因

权重加载与前向传播交给 `Backend` trait，由可选 feature `candle-backend` 接入。
这样"只想用并发内核"的用户不必拉起几 GB 的 ML 依赖。

### 关键点

- **取消是协作式**：`cancel()` 只置标志，循环在下一个检查点退出并返回
  `StopReason::Cancelled` —— 不谎报成功（BackendDesign §3.7）。
- **内核缺失只能降级性能，不能降级功能**：Python 胶水层每条路径都有纯 Python 回退，
  `generate()` 在内核不可用时返回 `degraded=True` 而非抛异常。
- **health 不加载模型**：`capabilities()` 只报告编译期能力（BackendDesign §3.8）。
- **Null 后端是诊断状态**：未编译后端时 `forward()` 返回明确错误，不是静默成功。

---

## 5. 回归集（源码，未执行）

| 文件                              | 覆盖                                                         |
| --------------------------------- | ------------------------------------------------------------ |
| `tests/test_context_isolation.py` | 交错并发 session 零串线、per-session 锁不串行、记忆瞬态、清理只影响目标会话 |
| `tests/test_api_contract.py`      | 成功码唯一判定、request_id 校验、异常脱敏、404 信封化、无重复 `/api` |
| `tests/test_prompt_budget.py`     | 保护段不可裁剪、裁剪可解释、历史裁剪保留最近轮、估算口径     |

运行方式见 §7。**本轮未运行**，交付前需由使用者执行。

Rust 侧单测写在各模块 `#[cfg(test)]` 内（`tokenizer.rs` / `sampler.rs` / `inference.rs`），
同样未执行，需 `cargo test` 跑。

---

## 5.1 改动文件清单

**新增**

| 文件                                                     | 说明                                                     |
| -------------------------------------------------------- | -------------------------------------------------------- |
| `PLAN.md`                                                | 本文件（硬性约束 3）                                     |
| `src_py/modules/context/store.py`                        | session 分桶上下文存储 + per-session 锁                  |
| `src_py/modules/context/request.py`                      | RequestContext（frozen）                                 |
| `src_py/modules/context/budget.py`                       | token 预算策略（纯函数）                                 |
| `src_py/modules/core/native/inference.py`                | Rust 推理胶水层 + 纯 Python 回退                         |
| `src_py/native/src/tokenizer.rs`                         | BPE 分词与计数                                           |
| `src_py/native/src/sampler.rs`                           | 采样（temperature/top-k/top-p，可复现）                  |
| `src_py/native/src/inference.rs`                         | 生成循环、停止条件、超时与取消                           |
| `src_py/tests/test_context_isolation.py`                 | 会话隔离回归集                                           |
| `src_py/tests/test_api_contract.py`                      | API 契约回归集                                           |
| `src_py/tests/test_prompt_budget.py`                     | 预算与裁剪回归集                                         |
| `src_py/tests/test_tool_policy.py`                       | 工具执行安全策略回归集                                   |
| `src_py/tests/test_remote_access.py`                     | 远程访问与认证回归集                                     |
| `src_py/tests/test_context_assembly.py`                  | 动态上下文装配回归集                                     |
| `src_py/modules/utils/file/atomic.py`                    | 原子写 + 路径安全原语                                    |
| `src_py/modules/manager/saves/memento.py`                | 快照 manifest / revision 发布 / 恢复预演                 |
| `src_py/tests/test_save_memento.py`                      | 存档快照回归集（含故障注入）                             |
| `src_py/modules/memory/integrity.py`                     | 墓碑 / 索引对齐诊断 / embedding 指纹（纯函数）           |
| `src_py/tests/test_memory_integrity.py`                  | 记忆索引完整性回归集                                     |
| `src_py/modules/core/task_state.py`                      | 任务状态机（纯函数）                                     |
| `src_py/modules/logger/audit.py`                         | 结构化审计事件（脱敏 + sink 抽象）                       |
| `src_py/tests/test_task_and_audit.py`                    | 状态机与审计回归集                                       |
| `config/api/endpoints.json` / `groups.json`              | 84 条端点的 json 权威清单                                |
| `src_py/modules/api/registry.py`                         | 端点声明模型与 handler 解析                              |
| `src_py/modules/api/loader.py`                           | json 加载 → gateway op + FastAPI router                  |
| `src_py/modules/api/ops.py`                              | 改为 json 优先、内置映射兼容回退                         |
| `src_py/modules/api/controllers/__init__.py`             | json 路由注册 + 去重 + 路由清单                          |
| `src_py/modules/api/gateway.py` / `response.py`          | `reset_request_id()` 修复 contextvar 复位                |
| `src_py/modules/manager/saves/binary.py`                 | `.save` 二进制容器（双校验和 + 原子写）                  |
| `src_py/modules/manager/saves/manager.py`                | 当前状态改二进制存储，旧 yaml 只读兼容                   |
| `src_py/modules/security/workspace.py`                   | 三档权限 + 路径边界 + 敏感脱敏                           |
| `src_py/modules/logger/trail.py`                         | 追加写轨迹 + 链式 hash + WebSocket 推送 + 删除硬保护     |
| `src_py/modules/tools/policy.py` / `ctl.py`              | 轨迹删除硬拦截 + 工具调用轨迹记录                        |
| `src_py/modules/events/types.py`                         | `WebSocketEventType.TRAIL_EVENT`                         |
| `src_py/tests/test_save_binary.py`                       | 二进制存档（含篡改/截断故障注入）                        |
| `src_py/tests/test_workspace_trail.py`                   | 权限/脱敏/轨迹链/不可删回归集                            |
| `src_py/tests/test_endpoint_config.py`                   | 端点配置静态校验                                         |
| `src_py/native/src/memory.rs`                            | Rust 记忆重计算内核（向量/RRF/遗忘曲线/embedding trait） |
| `src_py/native/src/lib.rs` / `Cargo.toml`                | 注册 `core.MemoryKernel` + `embedding-backend` feature   |
| `src_py/modules/memory/domain/layers.py`                 | 五层逻辑记忆、层策略、旧字段映射、常数表                 |
| `src_py/modules/memory/domain/strength.py`               | §6 全套遗忘公式、状态机、门控、GC 条件                   |
| `src_py/modules/memory/domain/scoring.py`                | RRF、CJK 友好词法打分、归一化                            |
| `src_py/modules/memory/ports/protocols.py` / `clock.py`  | 端口定义 + 三种时钟与假时钟                              |
| `src_py/modules/memory/compute/kernel.py`                | Rust 优先 / Python 回退 / 常数一致性校验                 |
| `src_py/modules/memory/vector/`                          | Milvus、按 session 分片的 FAISS、内存降级、组合根        |
| `src_py/modules/memory/application/`                     | 检索编排、使用事件队列、固化 dry-run                     |
| `src_py/modules/memory/features.py`                      | 特性开关（默认全关，gc 永久默认关）                      |
| `src_py/modules/memory/migrations.py`                    | schema v2 版本化迁移与可重入回填                         |
| `src_py/modules/memory/config.py` / `config/memory.json` | 记忆配置改为 json 驱动                                   |
| `src_py/modules/memory/managers.py`                      | 接入 Rust embedding 前向；修非 ndarray 静默归零(C113)    |
| `src_py/modules/memory/main.py`                          | 组合根装配（构造期不连 Milvus）                          |
| `resources/defaults/memory.sql`                          | v2 列 + 强度/事件/时钟/迁移进度表                        |
| `src_py/tests/test_memory_layers.py`                     | 分层/公式/内核/迁移/向量/影子模式回归集                  |
| `src_py/modules/context/assembly.py`                     | 动态装配：阶段机 + 装配计划（纯函数）                    |
| `src_py/modules/context/prompt.py`                       | PromptBuilder 迁移后的正文（见 §3.1）                    |
| `src_py/modules/tools/policy.py`                         | 工具执行安全策略（纯函数）                               |
| `src_py/modules/api/access.py`                           | 远程访问与认证（纯函数）                                 |
| `scripts/api/check_routes.py`                            | 路由清单导出与契约断言                                   |
| `src_py/pytest.ini`                                      | 测试配置（`asyncio_mode=auto`）                          |

**修改**

| 文件                                                   | 说明                                                         |
| ------------------------------------------------------ | ------------------------------------------------------------ |
| `src_py/modules/context/user.py`                       | 重写为门面，消息下沉到 ContextStore                          |
| `src_py/modules/api/exceptions.py`                     | 成功码唯一判定、脱敏辅助、debug 字段                         |
| `src_py/modules/api/response.py`                       | 异常不外泄、request_id 校验、set 返回 token                  |
| `src_py/modules/api/gateway.py`                        | `_ok` 参数错位、call_sync 信封化、异常脱敏                   |
| `src_py/modules/api/controllers/__init__.py`           | 前缀收敛、路由清单、重复前缀自检                             |
| `src_py/modules/api/controllers/save.py`、`audit.py`   | 去掉自带 `/api`                                              |
| `src_py/modules/api/controllers/websocket/__init__.py` | `/` → `/ws`，异常脱敏                                        |
| `src_py/modules/pipeline/orchestrator.py`              | 移除 10 次死循环、session 传递、情绪异步化、动态装配         |
| `src_py/modules/config/builder.py`                     | 收敛为兼容 shim（正文迁 `context/prompt.py`，见 §3.1）       |
| `src_py/modules/context/prompt.py`                     | 三步纯化、预算生效、memory_limit 生效、directives            |
| `src_py/modules/pipeline/models.py`                    | `OrchestrationResult.stage`                                  |
| `src_py/modules/services/ppt/service.py`               | 声明 `context_profile`，切换专属上下文                       |
| `src_py/modules/app.py`                                | 关闭幂等改用终态标志 `_closed`                               |
| `src_py/modules/manager/saves/manager.py`              | index/data 改原子写；新增 create/list/preview 快照方法       |
| `src_py/modules/memory/storage/database.py`            | 墓碑读写、指纹读写、对齐取样、`index_ids()`                  |
| `src_py/modules/memory/storage/sqlite.py`              | 隐私删除立碑、检索/压缩复活闸门、指纹核对、`health_report()` |
| `resources/defaults/memory.sql`                        | 新增 `memory_tombstones`、`embedding_meta` 表与索引          |
| `src_py/modules/pipeline/orchestrator.py`              | 任务状态记录、流式守卫、终态审计、额度感知摘要               |
| `src_py/modules/pipeline/models.py`                    | `OrchestrationResult.stop_reason`                            |
| `src_py/modules/characters/models.py`                  | `BuiltPrompt.budget` 字段                                    |
| `src_py/native/src/lib.rs`                             | 注册推理模块                                                 |
| `src_py/native/src/error.rs`                           | 新增 `CoreError::Model`                                      |
| `src_py/native/Cargo.toml`                             | `candle-backend` feature（默认关闭）                         |
| `scripts/builds/config.py`、`steps/rust.py`            | 支持 `--rust-features`                                       |
| 13 处 `from src_py.modules...`                         | 统一改为相对导入                                             |

---

## 3.3 P1：存档 Memento（B1-01 / B1-02 / B1-03）

| ID    | 工作项                                | 状态  | 落地位置                                                     |
| ----- | ------------------------------------- | ----- | ------------------------------------------------------------ |
| B1-01 | 定义 snapshot schema/version/manifest | `[x]` | `modules/manager/saves/memento.py`                           |
| B1-02 | 原子发布存档 revision                 | `[x]` | `utils/file/atomic.py` + `memento.publish_revision()` + `manager` 改原子写 |
| B1-03 | 恢复预演和回滚                        | `[~]` | `memento.preview_restore()` + `RestorePlan`；**Prepare/Commit/Rollback 未做**，见 §6 |
| B1-04 | SQLite/FAISS 对齐诊断                 | `[x]` | `memory/integrity.py::analyze_alignment` + `storage.health_report()` |
| B1-05 | 记忆删除完整传播                      | `[x]` | `memory/integrity.py` 墓碑/压缩引用 + `database.py` + `storage/sqlite.py` |
| B1-06 | embedding 版本化                      | `[x]` | `memory/integrity.py::EmbeddingFingerprint` + `embedding_meta` 表 |
| B1-07 | 统一任务状态机                        | `[x]` | `core/task_state.py`；接线 `orchestrator.process_stream`     |
| B1-08 | 结构化日志和审计                      | `[x]` | `logger/audit.py`；接线 tools 拒绝、记忆删除、任务终态       |

### B1-01：manifest

旧 `index.yaml` / `data.yaml` 不受影响照旧可读；新增 snapshot 层。
未知 `schema_version` 一律**安全拒绝**并返回稳定 reason code，
不做"尽力解析"——猜错字段语义比拒绝更危险。

**一致性等级必须诚实**：`consistency_level` 声明 S2(full) 但含
引用型 section（memory/characters/chat_history 在 data.yaml 里只是路径指针）
时，`effective_level()` 会降级回 checkpoint 并记入 warning。
声明与实际不符是虚假承诺——"data.yaml 写成功"不等于"状态已冻结"。

### B1-02：原子发布

原 `_write_index` / `_write_data` 直接 `open("w")`：
写到一半崩溃会留下截断的 YAML，`safe_load` 失败后**整个存档列表打不开**，
而旧内容已被 truncate 覆盖，两个版本同时丢失。

| 机制     | 落地                                                         |
| -------- | ------------------------------------------------------------ |
| 原子写   | 同目录临时文件 → fsync → `os.replace`（跨目录 rename 不原子，必须同目录） |
| 失败语义 | 写失败清理临时文件，原文件**原封不动**                       |
| 发布流程 | staging → 翻 committed → 校验 hash → rename → 原子写 current 指针 |
| 不可覆盖 | 目标 revision 已存在时拒绝（committed revision 不得原地编辑） |
| 崩溃点   | 第 3 步前崩溃 → staging 不是有效 revision，旧 current 不变；第 3 步后、第 4 步前 → 可按 operation_id 补指，不重复生成 |

顺带修：临时文件必须清理，否则 staging 会堆满 `.part`。

### B1-03：恢复预演（Preview）

`preview_restore()` **只读**，生成 `RestorePlan`：
会覆盖哪些域、缺哪些 section、要哪些迁移、有哪些告警。

阻断条件（都给稳定 code）：manifest 非法 / 未 committed / section 缺失或
hash 不符 / section schema 高于当前（**不能降级**）/ 路径越界。

**未做**：Prepare（保护快照）、Commit（乐观版本检查 + 按序应用 + 墓碑重放）、
Verify/Rollback。这三步要动运行态，且需要各 originator 提供
`prepare_restore()` / `commit_restore()` / `rollback_restore()` 接口——
属于跨模块的契约改动，单独一轮做（见 §6）。

---

## 3.4 P1：记忆索引完整性（B1-04 / B1-05 / B1-06）

### B1-05：删除完整传播

原 `delete_memories()` 只删 `memories` 行 + `faiss_id_map` 行，挡住了当前查询，
但挡不住**旧快照恢复**——恢复一个删除前的快照，那行记忆原样回来。

| 机制       | 落地                                                         |
| ---------- | ------------------------------------------------------------ |
| 墓碑       | `memory_tombstones` 表：`memory_id` + `session_id` + **内容摘要** + 时间 + 原因。**不存正文**（§5） |
| 写入时机   | 先读正文算摘要、再删行。反了就拿不到内容，墓碑退化成弱匹配   |
| 复活闸门   | `retrieve_memory()` 与 `get_compressed()` 在注入前调 `filter_resurrected()` |
| 压缩引用   | 引用了已删记忆的摘要**整条排除**（默认）——摘要无法只切掉其中一段 |
| 裁剪不立碑 | `__prune_if_needed` 的容量删除**不写墓碑**，否则墓碑随每次裁剪无限增长 |

**id 复用陷阱**（本次最重要的一个正确性决定）：墓碑按 id 匹配会误杀。
快照恢复重建表后，新行完全可能拿到和已删记忆相同的 id——
按 id 一查就命中墓碑，结果删掉一条**全新的记忆**。
所以匹配条件是 `id + 内容摘要`；摘要为空时才退化为弱匹配（宁可多挡）。

### B1-04：对齐诊断

`analyze_alignment()` 输入 id 集合（纯函数），输出四类问题：

| 问题                                | 后果                            |
| ----------------------------------- | ------------------------------- |
| `orphan_metadata` 有记忆无向量      | 永远检索不到                    |
| `lost_mapping` 映射指向不存在的记忆 | 悬空记录                        |
| `orphan_vector` 索引里有无主向量    | 白占 `top_k` 名额，召回率被稀释 |
| `dim_mismatch` 维度不符             | 需整体重建                      |

报告里的样例 id 限 5 条——诊断进日志，不能把整库 id 灌进去。

### B1-06：embedding 版本化

`EmbeddingFingerprint{provider, model, dim, version}` + `embedding_meta` 单行表。

**同维度不同模型也判定为不兼容**：384 维的两个模型产出的向量不在同一空间，
混用表现为"明明记得这件事，检索永远召不回"——这类问题极难排查。

启动时核对指纹，**不一致只告警不重建**：重建可能耗时很久，
自动执行会在启动时卡死进程。结论经 `embedding_status()` 暴露给 UI。

**未验证项**：`FAISSMemory.index_ids()` 依赖反射 faiss 的 `id_map` 数组，
未在真机跑过。取不到时返回空列表 → 跳过"无主向量"检测，
属于**少报**（只漏优化项，不会误删数据）。

---

## 3.5 P1：任务状态机与结构化审计（B1-07 / B1-08）

### B1-07：统一任务状态机

任务状态此前是**字符串 + 口头约定**：Rust 侧返回 `"pending"/"running"/...`，
Python 各处自行比较字面量。三类真实故障：

1. 终态被覆盖 —— 迟到的事件把 completed 改回 running；
2. 取消/超时不可解释 —— 只知道"不是 done"，说不清是哪种结束；
3. 状态名漂移 —— `cancelled` / `canceled` 两种拼写，漏一种就静默走进 UNKNOWN 分支。

| 机制       | 落地                                                         |
| ---------- | ------------------------------------------------------------ |
| 状态归一   | `normalize_state()` 收录两种 cancel 拼写与常见别名；未知返回 `UNKNOWN` 而非抛异常 |
| 终态不可逆 | `TERMINAL_STATES` 一律拒绝转移，保留原状态并累加 `rejected_count`（这是迟到事件的明确信号） |
| 可解释原因 | `StopReason` 枚举 + `finish()` 作为终止语义的**唯一入口**（映射只此一处定义） |
| 不可变记录 | `TaskRecord` frozen，`advance()` 返回新记录——并发下"读到一半状态变了"最难查 |
| 重试判定   | `StopReason.retryable`：取消**不该**重试（用户主动取消后再跑一遍是他不想要的）；超时也不盲重试（同样输入很可能再超时，只会放大拥塞） |

**流式守卫**（接线到 `process_stream`）：取消/超时后不再向下游投递 chunk。
此前取消只作用于 LLM 客户端层，已生成但未发出的 chunk 仍会继续 yield——
前端看到"已取消"之后又冒出一段文字（ContextArchitecture §7）。

### B1-08：结构化审计

与 debug 日志分流：日志回答"系统在干什么"，审计回答"谁对什么做了什么、结果如何"。
混在一起的后果是审计事件被海量 debug 淹没。

| 机制         | 落地                                                         |
| ------------ | ------------------------------------------------------------ |
| 不存正文     | 正文类字段只留**长度 + hash**：够做"是不是同一条"的比对，无法还原 |
| 不存秘密     | 键名命中 `api_key/token/password/...` 一律 `[scrubbed]`      |
| 拒绝日志注入 | 含换行/控制字符的值整体替换——换行意味着可以伪造整条日志行    |
| 不阻断业务   | sink 抛异常只计数降级；审计为可追溯服务，不能反过来成为可用性风险 |
| 有界缓冲     | `MAX_BUFFERED=500`，溢出计数 `dropped`                       |
| 父子串联     | `parent_request_id` + `task_id`（§6 后台任务保留父请求）     |
| 稳定动作名   | `Action.*` 常量，拒绝自由文本事件名（§5）                    |

**默认 sink 只走 logger**：真正的落盘、访问控制与保留期限属部署环节，
接入时 `register_sink()` 替换即可。已记为待办。

接线点：`tools/ctl.py` 策略拒绝、记忆删除、任务终态（流式与非流式共用同一摘要与审计，
两条路不会给出不同说法）。

| B1-09 | API 端点改为 json 驱动（op + HTTP 同一份配置） | `[x]` | `config/api/*.json`、`api/registry.py`、`api/loader.py`、`ops.py`、`controllers/__init__.py` |
| B1-10 | 存档改二进制 `.save` 容器 | `[x]` | `manager/saves/binary.py`、`manager.py` |
| B1-11 | 目标工作区三档权限 + 敏感脱敏 | `[x]` | `modules/security/workspace.py` |
| B1-12 | AI 行为轨迹日志（不可删 + WebSocket 实时推送） | `[x]` | `modules/logger/trail.py`、`tools/policy.py`、`tools/ctl.py` |

---

## 3.6 P1：json 驱动 API、二进制存档、沙盒与轨迹

### B1-09：API 端点 json 驱动

用户已把 API 与 providers 改为 json 控制。本轮把**端点注册**也收敛成
一份配置：`config/api/endpoints.json` 同时驱动桌面 Bridge 的 gateway op
与 Web 的 FastAPI 路由，不再有 `ops.py` 硬编码表 + controllers 各自
router 两份清单（新增接口极易漏一边，表现为"桌面能调、Web 404"）。

| 机制         | 落地                                                         |
| ------------ | ------------------------------------------------------------ |
| 契约层       | `api/registry.py`：`EndpointSpec` 启动即校验 op 格式、dispatch 白名单、path 不得自带 `/api`、timeout 上界 |
| 加载层       | `api/loader.py`：`register_gateway()` / `build_router()` / `catalog()` / `reload()` |
| 桌面 handler | `desktop_handler` 字段：HTTP 薄壳常带 `Query(...)` 占位默认值，直接给网关会把占位对象传进业务判断。loader 会清洗这类默认值 |
| 兼容         | 配置不存在时 `ops.py` / `controllers/__init__.py` 回退内置注册表；json 已声明的 op 不被覆盖 |

**修掉上传版实现的三个真 bug**（仓库内版本已是修后状态，勿用旧文件覆盖）：

1. `app.include_router(APIRouter().add_api_route(...))` —— `add_api_route()` 返回 **None**，`include_router(None)` 必崩。现改为复用 loader 产出的真实 route 对象，元数据（deprecated/name）不丢。
2. 上传版 `gateway.py` 的 `_ok(rid, data)` 形参顺序与调用处 `_ok(result, rid)` 错位，桌面端拿到的 `data` 恒为 16 位 request_id 串；且 `_invoke` 把异常原文回给客户端（B0-04 回归）、`call_sync` 留了 `if False else` 死代码。
3. `set_request_id(token)` 被当成复位用 —— 它把 `contextvars.Token` 当**值**写进 contextvar，后续请求 ID 全部串味。新增 `reset_request_id()`，`gateway.call` 的 finally 改用它。

配置由控制器源码静态提取生成：84 条路由、84 个 op，无重复 op / 无重复
(method, path) / 无 `/api` 前缀 / 无重复斜杠。`tests/test_endpoint_config.py`
做静态校验，不需要 import handler。

### B1-10：二进制存档 `saves/<slot_id>.save`

一个槽 = 一个文件。文本 YAML 没有完整性校验：被截断、被改几个字节、
或拷到一半，`safe_load` 可能仍解析出"看起来正常"的槽，只是悄悄少字段。

格式（小端）：magic `CBSAVE\x00\x01` → header_len → canonical JSON header
→ 各 section 二进制块 → 尾部 sha256。header 记每段 offset/length/sha256/kind/
reference_only。读档按「magic → 长度 → 全局 hash → header → 每段 hash」逐层
校验，任一失败返回稳定 reason code，**绝不"尽力解析"**；未知版本安全拒绝。

| 机制     | 落地                                                         |
| -------- | ------------------------------------------------------------ |
| 原子写   | 复用 `utils/file/atomic.py`，写失败旧 `.save` 原封不动       |
| 双重校验 | 整档 sha256 + 每段 sha256，能报出"是哪一段坏了"              |
| 体积上限 | 整档 256MB / 单段 64MB / 64 段 / header 16MB，防坏长度字段导致巨量分配 |
| 秘密     | `server` 段落档前脱敏，header 记 `redactions`                |
| 兼容     | `_read_data` 优先 `.save`，缺失时读旧 `data.yaml`（只迁移读，不再写） |

`.save` 是**槽的当前状态**，`snapshots/rev-*` 是历史 revision，互不替代：
当前状态频繁覆盖写，已发布 revision 不得原地修改。

### B1-11：目标工作区三档权限

| 档位           | read | write | delete | exec |
| -------------- | ---- | ----- | ------ | ---- |
| `READ_ONLY`    | ✓    | ✗     | ✗      | ✗    |
| `WRITABLE`     | ✓    | ✓     | ✗      | ✗    |
| `UNRESTRICTED` | ✓    | ✓     | ✓      | ✓    |

`check()` 是纯函数；路径用 `realpath` 归一化，区分"本来就在外面"与
"软链指到外面"（后者单列 `SYMLINK_ESCAPE`）。

**只读可读任意，但密钥不让步**：文件名命中 `.env`/`id_rsa`/`*.pem`/
`api_key`/`signature`/`credentials` 等 → 整文件不给 AI；内容里的
PEM 私钥块、`sk-*`、JWT、长十六进制签名、`key: value` 赋值行 → 逐段替换。
只有 `confirm_sensitive_exposure()`（必须由 UI 的显式确认动作调用）才给原文，
且该次确认**仍然进轨迹**——确认不是无痕。`read_for_ai()` 把
路径边界 → 权限判定 → 脱敏三步合成唯一入口，调用方不可能漏一步。

### B1-12：AI 行为轨迹日志

用户硬规则：**绝对不许可 AI 删除，只能人为，哪怕工作区完全放开也不许可**。

三层防护：

1. **物理隔离**：轨迹在 `user_data/trail/`，不在工作区里，AI 的文件操作路径解析不到。
2. **策略硬拦截**：`tools/policy.evaluate()` 第 0 步先判轨迹路径 + 破坏性方法，
   不读配置、无开关；`ctl.py` 再兜一层（策略层被改也不会漏）；
   `workspace.check()` 对轨迹路径的 delete/write 一律拒绝。
3. **链式校验**：JSONL 追加写，每条带 `prev_hash` + `hash`。
   删行 / 改字段 / 重排 / 截断都能被 `verify_chain()` 检出。

记录字段对齐用户的"做什么 / 从哪 / 这次执行哪个工具"：
`action` / `source` / `tool(service.method)` / `target`，叠加 decision、
result、reason_code、request_id。metadata 复用审计脱敏，不记正文。

WebSocket 实时推送：写入后广播 `trail.event`，写轨迹常发生在调度器/Qt 线程，
一律经 `submit_to_loop` 投递到 Web loop，**绝不跨 loop 直接 await**。
推送失败只降级，不影响写盘（轨迹比通知重要）。轮转只开新文件，
**旧文件绝不删除** —— 清理只能由人做。

局限（SecurityAndAuditDesign §5 已写明）：本地可写日志做不到密码学级
不可抵赖；能检出"改一行"，挡不住"整体换成另一条自洽的假链"。
合规级需求需签名或远端只写存储。

### 基线语法清理（全量扫描附带）

本轮对 `src_py/` 全量 214 个 `.py` 做静态语法扫描，发现 5 个**既有**问题
（非本轮改造引入），已顺手修复，现在全量 0 失败：

| 文件                                                         | 问题                                                         |
| ------------------------------------------------------------ | ------------------------------------------------------------ |
| `api/controllers/logger.py`、`ui/views.py`、`utils/decorators.py` | UTF-8 BOM，`ast.parse` 报 U+FEFF                             |
| `pipeline/adapters/asr/models.py`                            | `class SamplerParams(BaseModel):` 无类体，import 必崩；补最小占位定义，不臆造字段 |
| `tests/native.py`                                            | 旧手动脚本 `main()` 函数体全是注释导致语法错误；补提示语句，不恢复已废弃断言 |

---

## 3.7 架构判断：embedding / 供应商模型 / WebView 是否下沉 Rust

结论：**分层处理，不整体下沉**。

| 层                                          | 建议       | 理由                                                         |
| ------------------------------------------- | ---------- | ------------------------------------------------------------ |
| embedding 的**推理循环**                    | 可下沉     | 采样、停止条件、超时、协作取消、增量解码是 CPU 控制流，Rust 已有 `native/inference` 边界；权重交给 Backend trait |
| embedding 的**版本/指纹、检索策略、缓存键** | 留 Python  | 刚做完 B1-06 指纹与 `cache_key(session, revision, embedding, query)`，属于策略与数据层，下沉只会让配置热更新变困难 |
| 各类供应商模型（LLM/TTS/ASR/OCR）           | **不下沉** | 用户刚改成 json 驱动（Registry → shim → transport），价值就在配置热更新与各家 HTTP SSE / 认证差异适配；Rust 重写要重做整套解析，收益低、回归面大 |
| `transport=local` 的**本地推理执行**        | 可下沉     | 已有 `RUNTIME_REGISTRY` 接口，把 local runtime 换成 Rust 实现即可，provider 声明不动 |
| WebView（wry 替换 qtwebview2）              | **不建议** | gateway 的进程内 Bridge 已把桌面端降到零网络；wry 的收益主要是包体积/内存，却要推翻现有 Qt + Bridge + WebSocket + 前端资产全链路。除非目标是彻底去 Qt，否则保持现状 |

一句话：**把"算得快"下沉，把"配得动"留在 Python，把"界面"保持现状**。

---

## 3.8 记忆系统：未完成计划核对、Rust 下沉、Milvus、分层重构

### 3.8.1 先回答"还有哪些计划没做"

以 `docs/MemoryDesign.md` §11（M0–M5）、`docs/MemoryCurveAndForgetting.md`
§14–§18、`docs/OptimizationPlan.md` §5.3（M0-01~M2-08）与
`docs/BackendPlan.md` §7（B2-01~B2-06）为准，本轮开始前状态：

| 组            | 已做（前几轮）                                               | **本轮开始前未做**                                           |
| ------------- | ------------------------------------------------------------ | ------------------------------------------------------------ |
| M0 正确性     | 会话隔离(C0-02)、删除传播(B1-05)、维度/指纹(B1-06)、对齐诊断(B1-04) | **M0-01 核实**：旧字段到五层的映射从未确认                   |
| 五层逻辑记忆  | 只有 `short_term/long_term/detailed/compressed` 四个物理字段 | **M2 全部**：`layer/kind/confidence/validity/source_ids/supersedes` schema、层策略、生命周期 |
| 遗忘曲线 M1   | 无                                                           | **全部**：MemoryClock、strength/usage 表与回填、StrengthModel、使用事件管线、影子评分、评估集、重要度估计器 |
| 遗忘曲线 M2   | 无                                                           | **全部**：R 参与排序、faded/archived 门控与唤醒、固化 dry-run/apply、冲突 supersedes、retention/pin/revive API、GC dry-run/apply |
| 存档与记忆 S2 | Memento 快照(B1-01~03)                                       | MemoryOriginator（strength+clock+profile）、revision DAG、RestorePlan.memory_impact、恢复期暂停调度、故障注入 |
| 检索 B2       | 无                                                           | **全部**：多路召回、RRF 离线对照、中文分词、自适应预算、GC dry-run、本地性能基线 |
| 性能 M5       | 无                                                           | 批量 embedding、后台 rebuild、可选 reranker、缓存            |

本轮把**可纯源码实现且不依赖离线评估数据**的部分一次落地，其余仍列为待办（见 §6）。
M1-06 评估集是硬门槛：`OptimizationPlan` §6 明确"评估集推迟则 P3 不应开始"，
所以 `rerank / state_transition / consolidation.apply / gc.apply` 四个开关
**保持默认关闭**，代码就绪但不启用 —— 这不是没做完，是纪律。

### 3.8.2 分层：五层是逻辑分区，不是五个数据库

`memory/domain/layers.py` 定义 L1 WORKING / L2 EPISODIC / L3 SEMANTIC /
L4 SUMMARY / L5 ARCHIVE 与每层 `BASE_S / S_MAX / rank_floor / retention /
inject_by_default / max_inject_tokens`。共用同一存储，靠查询期
`scope + layer` 过滤隔离；强行拆五库只会带来五份一致性问题。

M0-01 核实结论（写入 `normalize_layer()`）：

| 旧字段                | → 新层                                |
| --------------------- | ------------------------------------- |
| `short_term`          | `WORKING`（有界 deque，会话结束落盘） |
| `long_term`           | `SEMANTIC`（高置信稳定事实/偏好）     |
| `detailed`            | `EPISODIC`（带时间与来源的事件明细）  |
| `compressed_memories` | `SUMMARY`（有 source range、可重建）  |
| 归档/导出原文         | `ARCHIVE`（默认不进检索）             |

`ARCHIVE` 只在 `explicit_recall=True`（"你还记得…吗"）才进候选，
且仍要过高置信门控 —— 放进候选不等于注入。

### 3.8.3 按公式实现的强度模型（`memory/domain/strength.py`）

`MemoryCurveAndForgetting.md` §6 的公式全部落成**纯函数**（所有时间由
调用方传入，模块不持有任何时钟，属性测试可复现）：

```
R(Δ,S) = 1/(1+Δ/(9S))                     pinned 恒为 1，Δ<0 按 0
S0 = BASE_S·(1+3·imp)·(1+1.5·sal)         受 S_MAX 限制
spacing = 0.1+0.9·(1−R_now)               间隔效应
massed  = 0.2 若距上次强化 <10 分钟       突击惩罚
gain    = 1.2·w_usage·spacing·massed·(1+0.5·imp)
S'      = min(S_MAX, S·(1+gain))
lapse   : S'=max(0.25, S·0.5)，不重置时间轴
final   = relevance·(floor + (1−floor)·R_eff)   §8.1
```

参考值已进回归集：闲聊 S0=1.30、普通事件 2.86、重要事件 7.48、
摘要 15.4、用户偏好 120.9；`R(S,S)=0.9`。

状态机 `active(R≥0.5) → faded(0.2~0.5) → archived(<0.2)` 由 R **派生**，
`state` 列只是缓存。GC 候选六条件缺一不可，语义层 importance≥0.7
有"身份下限"，最低降到 archived 不进 GC。

抖动用 **FNV-1a 64** 而非 sha256：Rust 标准库没有 SHA 实现，
引 crate 会拉依赖；FNV-1a 两边各几行整数运算、可静态比对，
且"同一天同一条记忆固定"这个用途不需要密码学强度。

### 3.8.4 重计算下沉 Rust（`native/src/memory.rs`）

新增 `PyMemoryKernel`，注册为 `core.MemoryKernel`，在 `py.allow_threads`
下跑完整个批量再返回：

| 下沉的计算                                  | 原本的开销                       |
| ------------------------------------------- | -------------------------------- |
| 批量 L2 归一化 / 批量内积打分               | numpy 多次分配 + GIL             |
| RRF 多路融合                                | Python dict 累加，10k 候选时明显 |
| TF 余弦词法打分（CJK 单字+bigram）          | 中文 bigram 逐条 Python 循环     |
| `R(Δ,S)` / `S0` / gain / `final_score` 批量 | 每轮检索逐条算                   |
| FNV-1a 抖动                                 | 同上                             |
| `EmbeddingBackend` trait + `encode_batch`   | 模型前向的接入点                 |

**没搬的东西及理由**：hash 兜底 embedding 只有几行、不是重计算，
搬过去反而会让 Python 与 Rust 两套 MD5 产生 fingerprint 漂移，
迫使已有索引重建。NFKC 归一化也留在 Python（Rust 不引 unicode crate），
`compute/kernel.lexical_scores()` 调用前统一预处理，保证 token 集合一致。

**常数一致性护栏**（本轮新增）：业务常数在 Python `domain/layers.py`
与 Rust `memory.rs` 各存一份，`kernel.check_constants()` 启动时逐项
比对 32 个键；不一致就**强制纯 Python** 并告警。绝不允许多数请求走
Rust、少数走 Python —— 那会让排序结果随路径变化，离线回放无法复现。

**本地 embedding 前向**：`embedding-backend` feature 默认关闭，
后端由 Rust 侧 `attach_backend()` 注册（刻意不接受 Python 回调对象：
跨语言逐 batch 回调会把 GIL 拖回关键路径，且 Python 侧悄悄换模型时
fingerprint 不会变，旧新向量混进同一索引）。未启用时
`encode_batch()` **抛明确异常，不静默降级成 hash 向量** ——
静默降级正是 B1-06 里"明明记得这件事，检索永远召不回"的成因。

Python 侧 `compute/kernel.py` 是薄门面：Rust 优先、纯 Python 回退、
`status()` 给出 `backend / constants_ok / fallback_reason`，降级可见。

### 3.8.5 向量库改 Milvus（`memory/vector/`）

定义 `VectorStore` 端口，三个实现共协议：

| 实现                  | 角色                                                         |
| --------------------- | ------------------------------------------------------------ |
| `MilvusVectorStore`   | 主选。`session_id` 为 **partition key**，filter 里同时限定 `session_id / fingerprint / layer / tombstone`，**服务端先过滤再 ANN** |
| `FaissVectorStore`    | 降级。**按 session 分索引**（`memory.faiss.<sid-hash>.faiss`），查询只在该会话索引里做，等价于 partition key；绝不复用旧全局索引（全局自增 faiss_id 与分片 id 空间不同，混用会静默错配） |
| `InMemoryVectorStore` | 最后降级，也按 `(session_id, layer)` 分桶                    |

`create_vector_store()` 组合根返回 `(store, status)`，
`status.fallback_chain` 记录每一级降级原因，**永不抛异常**、不静默。
**构造期不连 Milvus**（`HybridMemorySystem.ensure_vector_backend()` 显式触发），
否则一个不可达地址会在启动时卡死进程。

Milvus filter 表达式的所有字面量过 `safe_literal()` 白名单，
拒绝转义而不是"转义引号" —— 转义规则随版本变化，漏一种就是注入。
指纹不符**只告警不自动重建**（B1-06）；`as_dict()` 不导出 uri/token。

### 3.8.6 应用编排与 json 配置

* `application/ranker.py`：`exact / lexical / dense / recency / confidence`
  五路 → RRF → 强度排序 → 门控，输出**带来源与理由的候选清单**，
  不拼"长期记忆全文"、不做授权判断（MemoryDesign §12）。
  影子模式并行算新旧排序、写 `shadow_diff`，但**返回旧排序**，
  用户可见结果零变化。单路失败自然退化（B2-01）。
* `application/usage.py`：COMPLETED 才发布、有界队列、
  队满丢最旧 `injected`（保住 `confirmed`）、写失败放回、不在请求线程写库。
* `application/consolidation.py`：dry-run 报告，幂等 `operation_id`、
  有界、不持锁调 LLM、拒绝跨 scope 提升、GC 只列候选不删除。
* `migrations.py`：schema v2 版本化迁移，分批回填 + 游标持久化，
  **可中断重入**；不静默改用户数据库，须组合根显式调用。
* `config/memory.json` + `load_memory_config()`：与 api / providers 一样
  改为 json 驱动，配置不存在或解析失败回退默认值并告警。
* `resources/defaults/memory.sql`：新库直接带 v2 列与
  `memory_strength / memory_usage_event / memory_clock_state / memory_schema_meta`。

### 3.8.7 顺带修掉的一个真实缺陷

`EmbeddingManager.embed()`：非 ndarray 的 adapter 结果会被
`embedding = zeros(...)` 先重置，再 `list(embedding)` 填充 ——
填进去的全是 0，任何 list/tuple 形式的向量都被**静默丢弃成零向量**。
已改为先取原始值再建目标数组（C113）。

### 3.8.8 本轮未做（保持纪律，不是遗漏）

| 项                                                           | 为什么没做                                                   |
| ------------------------------------------------------------ | ------------------------------------------------------------ |
| `rerank / state_transition / consolidation.apply / gc.apply` 开默认 | 依赖 M1-06 离线评估集（中/日/英 Recall@K、MRR/nDCG、误注入率、token 成本）达标；`OptimizationPlan` §6 明确"评估集推迟则 P3 不应开始" |
| 真实 ONNX/candle embedding 后端实现                          | 需引入模型依赖并下载权重，违反硬性约束；已留 `EmbeddingBackend` trait 与 feature 接入点 |
| M2-06 `retention/pin/revive` API 与 DTO                      | 需先更新 `docs/api.md` 再生成前端类型（FX-08 依赖），属契约变更，单独一轮 |
| S2-01~S2-06 MemoryOriginator / 恢复期调度 / 故障注入         | 需 B1-03 的 Prepare/Commit/Rollback 接口先定                 |
| B2-02 离线对照报告、B2-06 性能基线                           | 需要真实评估数据与压测环境，本环境不执行构建/测试            |

---

## 6. 未完成项（按优先级排队）

| 优先级 | 项                                                           | 说明                                                         |
| ------ | ------------------------------------------------------------ | ------------------------------------------------------------ |
| P0     | B0-05 剩余                                                   | token 轮换与吊销、TLS、远程模式的网络风险评审属部署环节，源码改造已到位 |
| P1     | C0-03 剩余                                                   | ~~PromptBuilder 迁出 `config/` 到 `context/` 层~~ 已完成，见 §3.1 |
| P1     | B1-03 剩余                                                   | Prepare / Commit / Verify-Rollback 未做，需各 originator 提供 restore 接口（见 §3.3） |
| P1     | B1-04~B1-06 剩余                                             | 墓碑保留期策略未定（现由调用方传 cutoff）；`index_ids()` 依赖 faiss 反射，未真机验证 |
| P1     | B1-08 剩余                                                   | 审计落盘 sink、访问控制与保留期限属部署环节；当前默认 sink 只走 logger |
| P1     | B1-12 剩余                                                   | 轨迹保留期限与人为清理入口（UI）未做；当前只轮转不删除，需人工清理 |
| P1     | B1-09 剩余                                                   | `endpoints.json` 由源码静态提取，新增 controller 后需重跑生成；热更新 `reload()` 已提供但未接 API |
| P1     | provider json 层                                             | 上传的 Registry/shim/transport 设计未并入本仓库（本轮只按 json 驱动约定改 API 层，未改 provider 层） |
| P1     | M0-01 / M1-01~M1-05 / M1-07 / M2-01~M2-05 / M2-07 / B2-01 / B2-03 / B2-04 / B2-05 | `[x]` 源码已落地，见 §3.8；**开关默认关闭**，等 M1-06 评估集 |
| P1     | M1-06 离线回放评估集（中/日/英 harness）                     | **关键路径**：未做，P3 不得开始；需真实评估数据，本环境不产出 |
| P1     | M2-06 retention/pin/revive API + DTO                         | 需先更新 `docs/api.md` 再生成前端类型（FX-08）               |
| P1     | M2-08 GC apply                                               | 代码留了 `gc.apply` 开关但**永久默认关闭**，硬删除需单独审批 + 墓碑协议 |
| P1     | S2-01~S2-06 MemoryOriginator / revision DAG / 恢复期调度 / 故障注入 | 依赖 B1-03 的 Prepare/Commit/Rollback 接口                   |
| P1     | B2-02 RRF 离线对照、B2-06 本地性能基线                       | 需评估数据与压测环境，本环境不执行构建/测试                  |
| P1     | 真实 ONNX/candle embedding 后端                              | 需引入模型依赖与权重下载；trait + feature 接入点已就绪       |

---

## 7. 本地执行入口（使用者执行，本轮未执行）

~~~bash
# 路由清单与契约自检（不依赖运行中的服务）
python scripts/api/check_routes.py --fail-on-diff
python scripts/api/check_routes.py --markdown   # 用于校准 docs/api.md

# Python 回归集
cd src_py && python -m pytest tests/ -q

# Rust 单测（分词 / 采样 / 生成循环）
cd src_py/native && cargo test
~~~

### 构建内核（使用者执行）

`scripts/builds/steps/rust.py` 是既有构建步骤入口；命令行等价形式：

~~~bash
cd src_py/native
cargo build --release                              # 并发内核 + 推理控制流 + 记忆计算内核
cargo build --release --features candle-backend    # 接入本地推理后端
cargo build --release --features embedding-backend # 接入本地 embedding 前向（需 Rust 侧注册后端）
cd .. && python -m pytest tests/test_memory_layers.py -q
~~~

`builds/steps/rust.py` 已支持 `--rust-features`，等价于：

~~~bash
python scripts/builds/steps/rust.py --rust-features embedding-backend
~~~

未编译 `embedding-backend` 时，`MemoryKernel.encode_batch()` 抛明确异常，
`EmbeddingManager` 保持原有 adapter 路径 —— 功能完整，不会静默换向量空间。

产物为 `core.pyd`（Windows）/ `core.so`（Linux），落位参见既有构建脚本。
未构建时 Python 侧全部走回退路径，功能不缺失（见 §4「关键点」）。

---

## 7. 本轮进度：dev 基线对齐 + services/安全沙盒改造

本轮按「第一步先更新 docs，第二步改代码」推进，事实基线是 `dev` 分支
`src_py/` 源码与 `resources/config/api/endpoints.json`。完整变更清单见
仓库根 `CHANGELOG_更新说明.md`。

### 7.1 第一步：docs 更新（已完成）

| 文档                             | 处置                                                         |
| -------------------------------- | ------------------------------------------------------------ |
| `docs/BackendDesign.md`          | 重写：真实模块地图（`core/pipeline`、`core/tools`、`core/context`）、进程/线程模型、`endpoints.json` 驱动的三入口、工具链、服务模型、shell 服务、工作区输出规范 |
| `docs/api.md`                    | 重写：以 `endpoints.json` 的 89 个端点为权威清单，统一 `/api` 前缀、错误码、SSE/WS 路径、shell 命令契约、差异与修复表 |
| `docs/SecurityAndAuditDesign.md` | 更新：三档权限、命令准入双层检查、产出目录规范、验收清单     |
| `docs/README.md`                 | 更新：模块地图勘误、文档导航、风险状态、实施顺序             |

关键勘误：旧索引把 `modules/pipeline`、`modules/tools`、`modules/context`
写成顶层，实际都在 `modules/core/` 下；旧 api 文档描述"controller 自带
router 统一加 /api"，实际路由由 `endpoints.json` 驱动生成。

### 7.2 第二步：代码改造（已完成）

1. **服务层修复**：`services/manager.py` 自引用导入、`stop()` 未定义变量、
   `BaseServiceConfig.__getattr__` 无限递归、`ApiGateway._ok` 参数顺序、
   `controllers/service.py` 启停逻辑反转、`controllers/audit.py` 与
   `controllers/skill.py` 的 KeyError/AttributeError、`generate()` 返回类型，
   共 10 类运行期缺陷。新增 `services/service/*` 与 `services/keys.py`
   兼容层修复历史失效导入。
2. **打通 `security/workspace`**：原本未被任何业务模块引用。新增默认工作区、
   `service_output_dir()` / `output_path()` / `make_output_writer()`，
   以及命令准入的权威数据与纯函数。
3. **新增 shell 服务**：平台命令映射（`cmd.exe /C` ↔ `/bin/sh -c`、
   `dir↔ls` / `type↔cat` / `copy↔cp` / `move↔mv` / `cls↔clear`）、
   命令白名单、危险命令硬拦截、cwd 锁定、路径参数 `realpath` 复验、
   环境净化、超时与输出上限。
4. **命令兜底**：`CommandParser` 把非服务命令且命中已知动词的行转成
   `shell.run`，模型不需要 `shell --command` 包装；`PromptBuilder` 同步
   输出对应说明。
5. **策略层修复**：服务用 `get_tools()` 声明工具，旧 policy 只读 `tools`
   属性导致所有服务被判 `SERVICE_UNDECLARED`（工具链整体不可用）；
   新增 `COMMAND_FORBIDDEN` 粗筛。
6. **产出目录**：PPT 固定 `<workspace>/ppt/`，技能输出固定
   `<workspace>/skill/<skill_id>/`，其它服务 `<workspace>/<service_id>/`。
7. **端点修正**：save 的 7 条 path 去掉自带 `/api`（原实际为
   `/api/api/save/...`）；补齐 ppt 6 条、audit 2 条、workspace 4 条。

### 7.3 验收状态

- `endpoints.json`：89 个启用端点，无重复 `METHOD+PATH`，无残留 `/api` 前缀。
- 语法编译：本次 26 个改动/新增文件全部通过；全量 263 个 `.py` 仅 3 处
  原有告警（2 个 UTF-8 BOM 属检查假阳性，`adapters/asr/models.py` 是
  无引用的空壳文件，见 7.4）。
- 逻辑自测：命令粗筛、平台映射、解析兜底、策略判定、工作区目录与边界
  全部按预期（未安装依赖、未运行项目、未执行构建/测试，遵守硬性约束）。

### 7.4 本轮未做（不是遗漏）

| 项                                                    | 原因                                                      |
| ----------------------------------------------------- | --------------------------------------------------------- |
| 前端 `src/api/http.ts` 的 `code===0` 与后端 200 分叉  | 属前端契约改动，需同步生成器与契约测试，单独一轮          |
| `response.py` 未处理异常回显详情、`raw=true` 原文回显 | 属安全收紧，需配合前端兼容窗口                            |
| `save` 的 `restore` / `sync` / `section` 后端补实现   | 契约变更，需先定 DTO 与语义                               |
| `adapters/asr/models.py` 空壳语法错误                 | 无任何模块引用，且不在本轮 services/沙盒范围              |
| `groups.json` 的 op 命名与 `endpoints.json` 不一致    | 能力目录，非路由权威源；统一命名需单独一轮                |
| 运行项目 / 安装依赖 / 构建 Rust / push 到远端         | 硬性约束禁止；且远端 git 访问返回 403，改动以本地文件交付 |

---

## 8. 本轮进度：providers 供应商接入 + pipeline 编排

事实基线仍是 `dev` 分支源码。**未安装依赖、未运行项目、未执行构建/测试**；只做全量语法编译、静态契约核对与纯函数级逻辑自测。详细变更说明见仓库根 `CHANGELOG_更新说明.md` 第二轮章节，架构说明见 `BackendDesign.md` §9.1。

### 8.1 架构收敛

| 层   | 落地项                                                       |
| ---- | ------------------------------------------------------------ |
| 配置 | `Registry` 单一权威源；`${ENV}` 缺失保留占位 + `missing_env` 告警；文件签名加入"被引用环境变量是否已设置"，避免凭据已配好却仍报不可用；`flat()` / `describe()` 默认脱敏 |
| 构造 | `factory.create_adapter()` 唯一入口，拆分 secrets / endpoint / params；旧 `core/pipeline/adapters/factory.py` 收敛为薄委托层，消除双轨实现 |
| 传输 | `HttpTransport.sync()` 让二次配置覆盖真正生效；client 按 `(base_url, timeout, loop)` 池化，LRU 淘汰的 client 登记 aclose 任务，停机统一 await；只对连接失败重试 1 次，生成请求不重放 |
| 管理 | `ProviderManager` 按 capability 串行切换；用量取门面快照，切换前折进旧实例计数；`switch` 覆盖白名单不含任何端点字段 |
| 编排 | `chat.ensure_initialized_async()` 改 `concurrent.Future` + `wrap_future`（跨 loop 安全）；意图判断缓存键与 `IntentRouter` 同构、结果先规范化再入有界 LRU；情绪分类默认纯规则、LLM 兜底需显式注入且有超时 |
| 留痕 | 新增 `logger/audit.py`（§5 事件契约）与 `logger/trail.py`（低基数轨迹 + `is_trail_path()`），补齐 dev 分支 6 处失效 import |

### 8.2 修复清单（本轮）

| 文件                                 | 问题 → 处置                                                  |
| ------------------------------------ | ------------------------------------------------------------ |
| `logger/audit.py`、`logger/trail.py` | 模块根本不存在，编排器顶层 import 必崩、审计调用全被 except 吞掉 → 补齐零依赖实现 |
| `core/pipeline/chat.py`              | `asyncio.Event` 绑定单一 loop，Web / 调度器 / to_thread 多 loop 下跨 loop await 抛错；同步入口与异步入口并发会重复建实例 → 共享 `concurrent.Future`，失败后可重试 |
| `providers/entity.py`                | 切换 provider 时旧 shim 的累计 token 用量丢失 → `_replace()` 成功构建后先 `_accumulate_usage()` |
| `transports/http.py`                 | `_order` 独立列表导致 LRU 错乱、同 key 重复入队；被淘汰 client 从不 aclose → `OrderedDict` + 可等待的关闭任务 |
| `api/loader.py`                      | `dispatch=main` 引用不存在的 `ui.dispatcher.run_in_main_thread` → 改用 `get_main_thread_dispatcher().run_async_on_main_thread()` |
| `controllers/system.py`              | `manager.websocket.manager` 路径不存在，连接数恒为 0 → 改 `controllers/websocket/manager.py` 并优先用 `connection_count()` |
| `core/pipeline/orchestrator.py`      | 轻量判断缓存用原文 `strip()`，同句多标点即重复付费；截断/带代码块响应被整段缓存后反复解析失败 → 规范化键 + 规范化结果；情绪回落的异常分支二次 import 可能盖掉真实回复 → 模块级常量 |
| `providers/manager.py`               | switch 白名单含 `base_url` / `auth` / `headers`，前端可把带密钥请求引到任意地址；模型级 params 被误判为不可覆盖 → 收紧白名单并按选中模型取 spec |
| `providers/adapters/registry.py`     | 环境变量从无到有不触发重载，`missing_env` 永久过期 → 纳入签名（只记是否设置，不记值） |
| `controllers/pipline.py`             | `get_provider` 的 `raw=true` 开关从未生效却暗示可回显密钥 → 移除 |
| `shim/base.py`                       | `initialize_client()` 二次覆盖只改 shim 自身，传输层仍打旧地址 → `HttpTransport.sync()` |

### 8.3 成本与性能

- 生成请求只在"连接未建立"时重试 1 次；429 / 5xx / ReadTimeout 上抛，不重复计费。
- HTTP 连接池复用 + 淘汰/停机真正 aclose，省重复 TCP/TLS 握手且不泄漏连接。
- 情绪分类默认 0 次额外模型调用；轻量路由判断缓存键规范化、结果规范化，避免同一句话反复付费。
- 无可执行工具结果时短路本地回复，不发起第二次完整推理；用量快照使 `usage` 统计不再因切换而少记。

### 8.4 验证结果（不运行项目）

| 检查                                               | 结果                                                         |
| -------------------------------------------------- | ------------------------------------------------------------ |
| 全量 268 个 `.py` 语法编译                         | 0 失败                                                       |
| `endpoints.json`                                   | 89 个端点，`METHOD+PATH` 无重复、无 `/api` 前缀残留          |
| 89 个 handler 模块 + 顶层符号静态解析              | 全部可解析（不 import，避免依赖缺失干扰）                    |
| 66 个改动 `.py` 的相对导入 / 符号解析              | 0 可疑项（含 PEP 420 namespace package）                     |
| 纯函数级自测                                       | 审计脱敏/不可变/缓冲/sink 降级/轨迹低基数、Registry 缓存与热更新签名、factory 拆分、轻量判断规范化、连接池 LRU 与停机关闭 —— 全部通过 |
| 依赖 `pydantic` / `fastapi` 的 controller 与编排器 | 仅语法编译 + 代码审查，未做运行时导入验证（环境缺依赖，遵守硬性约束） |

### 8.5 本轮未做（不是遗漏）

| 项                                                           | 原因                                           |
| ------------------------------------------------------------ | ---------------------------------------------- |
| `controllers/config.py` 的 `raw=true` 原文回显               | 需配合前端兼容窗口；pipeline 端点已先行移除    |
| 审计落盘 sink、访问控制与保留期限                            | 属部署环节；事件本体与脱敏已落地               |
| `response.py::_unhandled_handler` 回显异常详情、前端成功码分叉 | 契约改动，单独一轮                             |
| `providers` 运行时全链路导入验证                             | 需本地安装 `pydantic` / `fastapi` 后跑契约测试 |
| push 到远端                                                  | 远端 403，改动以本地覆盖包交付                 |


---

## 9. 本轮进度：聚焦 services/ 性能优化、缺陷修复与不兼容旧调用

事实基线仍是 `dev` 分支源码。**未安装依赖、未运行项目、未执行构建/测试**；本轮首次用「注入最小依赖替身」做服务层运行时自测（不是启动项目）。详细变更见仓库根 `CHANGELOG_更新说明.md` 第三轮章节，架构见 `BackendDesign.md` §7.1 / §7.2。

### 9.1 硬性约束：不兼容旧调用

删除前两轮新增的兼容层，调用方统一到唯一正式入口：

| 删除                                                         | 唯一正式入口                                                 |
| ------------------------------------------------------------ | ------------------------------------------------------------ |
| `services/keys.py`、`services/service/{__init__,decorator,manager}.py` | `modules.keys` / `modules.services.manager`                  |
| `from src_py.modules.* import ...`（controllers / tests / cli 共 8 处） | 相对导入或 `from modules.* import ...`                       |
| `PptRenderService(output_dir=...)`、`load_defaluts()`、`OBSClient(obs_password=...)`、`QQBotClient(appid=...)` | `PptRenderService()` / `load_defaults()` / `password=` / `app_id=` |

扫描结果：旧路径代码残留 0，绝对导入残留 0，兼容目录/文件均不存在。

### 9.2 运行时架构（§7.1）

- async 服务（`Browser`/`OBS`/`QQBot`）各自一个 `run_forever()` 持久 loop；`start_original` 投递并等待完成（60s 上限），失败即时反馈并关掉本次 loop。
- `CommandExecutor._invoke()` 通过 `ServiceManager.get_service_loop(id)` 把协程回投服务自己的 loop（`wrap_future(run_coroutine_threadsafe(...))`）；property 类型工具直接取值。
- 同步服务共用 `services/_async.py` 共享持久 loop；`ServiceManager.stop()` 调 `shutdown_service_loop()`，先在该 loop 上 `await shutdown_clients()` 再关闭，释放 httpx 连接。
- `get_tools()` 按注册表变更缓存；策略层支持字符串形态工具声明。

### 9.3 本轮修复（摘要）

配置：`BaseServiceConfig` 物化字段默认值（深拷贝）、`to_dict()` 回显当前值、路径默认值惰性求值、`ServiceConfig` 实例属性隔离；`set_service_config()` 注入对象并触发 `on_config_change`。

控制器：`_construct()` 按构造签名过滤 payload；`/start` 不再把配置当启动参数；`/config/apply` 回显 `to_dict()`；Live2D 画布尺寸字符串转 tuple。

PPT：大纲改走 `providers.LLM.process_message()`（旧事件链从未可用）；模板 YAML 缺失 → 内置 5 套预设回落；渲染器原子落盘、类级版式表、图表数值容错；任务表有界 + 终态落定；构造不再占位 RUNNING。

浏览器：截图落 `<workspace>/browser/`、滚动参数整数化夹取、`set_viewport_size` 正确传 dict、DOM 相似度 `quick_ratio()` 上界剪枝。

其它：OBS / QQBot 的 `await self.stop()` 必崩路径、QQBot 配置字段与断线误停、Live2D 工具声明与单例标记覆盖、Shell 构造状态 —— 全部修复。

### 9.4 性能

工具目录缓存、DOM 相似度剪枝（1500 组随机样本判定等价）、PPT 版式类级分派、共享 loop 复用 HTTP 连接池、任务表有界、启动等待避免"假成功"。

### 9.5 验证结果（本轮收尾，不运行项目）

| 检查                                 | 结果                                                         |
| ------------------------------------ | ------------------------------------------------------------ |
| 全量 265 个 `.py` 语法编译           | 0 失败                                                       |
| `endpoints.json`                     | 89 个端点，无重复 `METHOD+PATH`、无 `/api` 前缀，handler 全部可解析 |
| 81 个改动 `.py` 相对导入 / 符号解析  | 0 可疑项                                                     |
| 旧调用 / `src_py.*` 绝对导入代码残留 | 0                                                            |
| 关键静态断言 22 项                   | 21 项直接通过；另 1 项为核对脚本把注释误判为代码，修正口径后复核通过 |
| 注入替身的运行时自测 **34 项**       | 配置对象、管理器启停/缓存/持久 loop、跨 loop 执行与 property、PPT 大纲与任务终态、shell 判定、DOM 剪枝等价性 —— 全部通过 |
| 真实依赖环境导入验证                 | 未做（`pydantic`/`fastapi`/`PyQt6`/`playwright` 未安装，遵守硬性约束） |

### 9.6 本轮未做（不是遗漏）

| 项                                               | 原因                                           |
| ------------------------------------------------ | ---------------------------------------------- |
| 真实依赖下的端到端契约测试                       | 需使用者本地安装依赖后执行                     |
| `Live2D` / `knowledge` / `game` 骨架接入管理器   | 属独立功能开发，不在本轮 services 缺陷修复范围 |
| 前端成功码分叉、`config.raw=true`、审计落盘 sink | 沿用前两轮遗留，需配合前端兼容窗口 / 部署侧    |
| push 到远端                                      | 远端 403，改动以本地完整增量包交付             |


---

## 10. 本轮进度：存档 / session 会话系统 + 快捷键映射与热键修改

事实基线仍是 `dev` 分支源码。**未安装依赖、未运行项目、未执行构建/测试**；注入最小依赖替身做运行时自测（78 项），回归第三轮服务层自测（34 项），合计 112 项通过。详细变更见 `CHANGELOG_更新说明.md` 第四轮章节；前端对接契约见 `docs/HotkeyFrontendContract.md`。

### 10.1 检查出的 P0（dev 基线既有）

| 模块                         | 缺陷                                                         |
| ---------------------------- | ------------------------------------------------------------ |
| `manager/session/manager.py` | 8 个被 controller / chat.py 直接调用的方法不存在，会话 API 与每轮对话收尾必 AttributeError |
| `controllers/save.py`        | `_slot_info()` 未定义，create/get 槽必 NameError             |
| `utils/file/atomic.py`       | `atomic_write_yaml()` 签名与 import 双错且异常被吞 → index.yaml 永远写不成功；`file_size` / `read_json` 未转出 → `SaveSlotManager` 连 import 都做不到 |
| `manager/saves/manager.py`   | `_legacy_data_path()` 缺失、`create_slot` 签名少一个参数、`ensure_default_slot` 条件写反、`_write_index` 对自定义 id 抛 ValueError |
| `core/context/user.py`       | `clear_messages()` 清的桶与读取的桶不一致，且无锁改 deque    |

### 10.2 会话与存档

- 会话目录隔离到 `<user_data>/sessions/`（旧 `saves/` 里的会话文件一次性迁移，存档文件不动）；id 白名单 + `safe_join` 防路径穿越。
- yaml 只存元信息、pkl 存消息，双临时文件都成功后「先 pkl 后 yaml」原子提交；`append_message` 标脏 + 1.5s/8 条合并写，强制落盘点覆盖 flush/switch/delete/save_sync/atexit。
- 轮次记录按 session 分桶；单例加锁、文件锁表有界、LRU 缓存、current 指针持久化。
- 存档补齐前端 `save.ts` 早已调用的三条端点：`PUT /save/slots/{id}/section`、`POST /save/slots/sync`、`POST /save/slots/restore`；`sync_from_sessions` 真正写会话快照，`restore_to_sessions` 反向恢复；`delete_slot` 连主存档文件一起删。
- 端点 **89 → 94**；controller handler 同时接受 pydantic 模型与桌面网关 dict。
- 上下文存储：桶级线程锁、LRU 护栏修正（无 idle 也淘汰）、`clear_messages_sync()`。

### 10.3 快捷键映射与热键修改（新增）

- `devices/hotkeys.py`：11 个动作、`hold`/`press` 模式、组合键规范化与别名、系统/编辑器保留组合、跨动作冲突、`revision` 乐观并发、失败回滚、原子持久化、变更通知。
- `controllers/hotkeys.py` + 5 条端点：列表、录制实时校验、单个修改、批量修改、恢复默认；错误用稳定 `data.code` 返回。
- `devices/keyboard.py` 重写：修掉「用配置键名查按键表导致映射全 None」、默认缺 `record_key`、无效 `is_interrupting`、`listener.join()` 阻塞、组合键不支持、录音结果丢失；现支持组合键、可启停监听、配置变更自动 reload、动作 handler 分发。
- 前端负责录制交互与设置页 UI；`docs/HotkeyFrontendContract.md` 给出键位规范、录制伪代码、端点示例、错误码与 TypeScript 类型片段。

### 10.4 验证结果（本轮）

| 检查                       | 结果                                                         |
| -------------------------- | ------------------------------------------------------------ |
| 全量 267 个 `.py` 语法编译 | 0 失败                                                       |
| `endpoints.json`           | 94 个端点，无重复 `METHOD+PATH`、无 `/api` 前缀，handler 全部可解析 |
| 运行时自测 78 项           | 原子写/路径安全 4、热键注册表 30、会话管理器 21、存档管理器 11、上下文存储 6、键盘设备 6 —— 全过 |
| 回归第三轮服务层自测 34 项 | 全过                                                         |
| 真实依赖环境导入验证       | 未做（遵守硬性约束）                                         |

### 10.5 本轮未做（不是遗漏）

| 项                                                      | 原因                                                         |
| ------------------------------------------------------- | ------------------------------------------------------------ |
| 热键设置页 UI 与录制交互                                | 明确交给前端；本轮只交付后端能力与对接契约                   |
| 重新生成 `src/types/api.d.ts` / `src/api/services/*.ts` | 生成产物需按 `scripts/api/generate.py` 接入；契约片段已在文档中给出 |
| 真实依赖下的端到端契约测试                              | 需使用者本地安装依赖后执行                                   |
| 前端成功码分叉、`config.raw=true`、审计落盘 sink        | 沿用前几轮遗留                                               |
| push 到远端                                             | 远端 403，改动以本地完整增量包交付                           |


---

## 11. 本轮进度：日志系统缺陷修复与成本/性能优化

事实基线仍是 `dev` 分支源码。**未安装依赖、未运行项目、未执行构建/测试**；注入最小依赖替身做运行时自测（56 项），回归第四轮（78 项）与第三轮（34 项），合计 168 项通过。详细变更见 `CHANGELOG_更新说明.md` 第五轮章节。

### 11.1 检查出的 P0（dev 基线既有）

| 模块                                      | 缺陷                                                         |
| ----------------------------------------- | ------------------------------------------------------------ |
| `logger/log.py` + `controllers/logger.py` | `PUT /logger/level` 把级别 upper() 后交给只认小写的映射表，任何设置都静默回落 INFO |
| `controllers/logger.py::stats`            | 读的字段名与 handler 产出的完全对不上，`/logger/stats` 永远返回全 0 |
| `logger/models.py` → `log.py`             | `exc_info` 提取的 `stack_trace` 在控制台、落盘、前端三路全被丢掉 |
| `logger/log.py::__print_log_color`        | 事件总线 emit 排在 print 之前；启动期总线未就绪，emit 抛异常导致整段启动日志不打印 |

### 11.2 P1 修复

- `Logger.init()` 不再清空外部 handler（修复 `/logger/records` 拿到孤儿 handler 恒为空）；`__get_logger()` 不再重建未启动的 handler；`reconfigure()` 让单例配置生效。
- 落盘每批 `flush()`、句柄 LRU 上限 8、可选 `retention_days`（默认 0 不删文件）。
- 队列设 `maxsize`、原子丢弃最旧、`_FlushBarrier` 保证 `flush()` 不漏队列里未处理的日志；停止哨兵不再被内层批量循环吞掉；`stop()` 从消费者线程自身调用也会排空 + 落盘 + 关文件。
- 消费者逐批隔离异常 + 每 256 条守护检查自动拉起，避免一次意外就永久失明。
- `UvicornLoggerHandler` 去掉双打印、不再改写 `LogRecord`；`gc` 的 `flush_log` 改走门面方法。
- 显式导出 `audit` / `trail`，避免打包/热重载时隐式子模块导入拿到 `None`。

### 11.3 自测中又暴露的 3 处

`queue.Queue()` 未设 `maxsize`（有界丢弃形同虚设）、`flush()` 只刷已处理批次（漏队列残留）、`Authorization: Bearer xxx` 被前一条规则截断导致 token 残留（脱敏漏洞）——均已修复。

### 11.4 优化

采集侧统一脱敏（`api_key=` / `Bearer` / `sk-`）与限长（正文 8000 / 堆栈 12000）；控制台每批一次 write + flush；事件总线 import 缓存 + 失败 5s 冷却；新增 `by_level` / `event_push_failures` / `handler_errors` / `running` / `open_files` 运行态指标。DTO 新增字段均为向后兼容的增量。

### 11.5 验证结果（本轮）

| 检查                            | 结果                                                         |
| ------------------------------- | ------------------------------------------------------------ |
| 全量 267 个 `.py` 语法编译      | 0 失败                                                       |
| `endpoints.json`                | 94 个端点（本轮不新增），无重复 `METHOD+PATH`、无 `/api` 前缀，handler 静态可解析 |
| 累计 105 个差异文件的相对导入   | 0 可疑                                                       |
| 日志系统运行时自测 56 项        | 全过（级别 7 / 模型 8 / handler 14 / 事件隔离 4 / 停止队列 4 / 门面与 REST 12 / uvicorn 与 audit-trail 7） |
| 回归第四轮 78 项 + 第三轮 34 项 | 全过                                                         |

### 11.6 本轮未做（不是遗漏）

| 项                                                      | 原因                                                         |
| ------------------------------------------------------- | ------------------------------------------------------------ |
| 热键设置页 UI 与录制交互                                | 明确交给前端                                                 |
| 重新生成 `src/types/api.d.ts` / `src/api/services/*.ts` | 生成产物需按 `scripts/api/generate.py` 接入；`LoggerStatsData` 新字段与 `stack_trace` 是增量字段，旧前端忽略即可 |
| 审计落盘 sink / 访问控制 / retention                    | 沿用前几轮遗留，属部署侧                                     |
| 自动删除旧日志                                          | `retention_days` 默认 0，避免擅自删用户文件                  |
| 真实依赖下的端到端契约测试                              | 需使用者本地安装依赖后执行                                   |
| push 到远端                                             | 远端 403，改动以本地完整增量包交付                           |

---

## 12. 本轮进度：app 组装与 UI（缺陷修复 + 装配优化）

事实基线仍是 `dev` 分支源码。**未安装依赖、未运行项目、未执行构建/测试**；注入最小依赖替身做运行时自测 63 项，回归前几轮 168 项，累计 231 项通过。详细设计见 `docs/AppAssemblyAndUI.md`，变更清单见 `CHANGELOG_更新说明.md` 第六轮章节。

### 12.1 检查出的 P0（dev 基线既有）

| 模块                                               | 缺陷                                                         |
| -------------------------------------------------- | ------------------------------------------------------------ |
| `api/controllers/__init__.py`                      | `app.include_router(APIRouter().add_api_route(...))` —— `add_api_route()` 返回 `None`，注册第一条路由即 `AttributeError`，94 个 HTTP 端点一个都挂不上 |
| `runtime.py` + `api/_common.py` + `api/gateway.py` | 13 处读 `runtime.manager.task_manager`（从未定义），`is_runing` 拼写错误且把 `is_running()` 方法当属性用；`events.emit()` 启动期拿到 `runtime.manager=None` |
| `ui/setup.py`                                      | `_running` 从未置 True → `stop()` / `exit()` 直接 return，托盘「退出」与 SIGINT 都退不出 Qt 循环；`_hide_system_tray()` 读未初始化属性；托盘 `QMenu`/`QAction` 局部变量被 GC |
| `api/server.py`                                    | `StaticFiles(directory=<static>/index.html)` 传文件而非目录，启动即 RuntimeError；`run_web()` 硬编码 8080 与配置/前端 8000 不一致 |
| `src_py/main.py`                                   | `debug` 写死 `True`，使 `auto` 模式永远落到 web，桌面 WebView 模式从未启用 |
| `ui/bridge.py`                                     | `is_runing` 判定恒 False，同步 handler 全部退化到 UI 线程内联执行（LLM/文件 IO 冻窗） |

### 12.2 P1 修复

- `Application.run()` 保证 `init()`；配置加载后 `logger.reconfigure()`；运行时先于日志消费者；`_shutdown()` 幂等且每步隔离；`self.ui` 可为 None。
- `RuntimeManager` 单例守卫 + `task_manager` 别名 + `NoopScheduler` 兜底 + `event_bus` 停机不置 None；`RuntimePath` 文件路径不再被当目录创建。
- `UIApp` 运行态/退出路径/托盘引用/资源探测/自动降级；Web 启动失败不再静默吞掉；`web_stop()` 不再空等。
- `Web.init()` 幂等、静态目录挂载、配置化端口、`server.started` 就绪判定；`register_all_routers` 按带前缀完整路径去重。
- `BrowserViewManager` 禁止派发失败时跨线程碰 Qt；`DesktopBrowserWindow` 关闭后不再对已销毁控件 load；`available_backends()` 缓存。
- Bridge 判定/调用约定/网关回退/JS 转义；前端 `async install()`、暗色 watch、WS 默认事件幂等、LogForwarder 回环与 teardown。
- 新增 `POST /api/logger/append`（端点 94 → **95**），补齐 `groups.json` 与生成物 `logger.ts`。

### 12.3 验证结果（本轮）

| 检查                                 | 结果                                                         |
| ------------------------------------ | ------------------------------------------------------------ |
| 全量 267 个 `.py` 语法编译           | 0 失败                                                       |
| `endpoints.json`                     | 95 个端点，无重复 `METHOD+PATH`、无 `/api` 前缀，handler 静态可解析 |
| 累计 119 个差异文件的相对导入        | 0 可疑；旧调用 / 兼容层残留 0                                |
| app 组装 + UI 运行时自测 63 项       | 全过（Application 13 / RuntimeManager 7 / events 1 / 路由 3 / Web 8 / UIApp 12 / Bridge 窗口 8 / append 5 / 前端断言 6） |
| 回归日志 56 + 会话/热键 78 + 服务 34 | 168 项全过                                                   |

### 12.4 本轮未做（不是遗漏）

| 项                                            | 原因                                                         |
| --------------------------------------------- | ------------------------------------------------------------ |
| 真实依赖下的端到端启动 / `tsc` / `vite build` | 环境无 `pydantic` / `fastapi` / `PyQt6` / `qtwebview2` 与 `node_modules`；遵守硬性约束不安装依赖、不运行项目 |
| 重新生成 `src/types/api.d.ts`                 | 生成产物需按 `scripts/api/generate.py` 接入；`logger.ts` 已手工同步 `appendLog` |
| 热键录制 UI 与设置页交互                      | 明确属前端范围，后端能力与契约已交付                         |
| push 到远端                                   | 远端 403，改动以本地完整增量包交付                           |