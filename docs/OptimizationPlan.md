# 架构优化总体计划（Plan）

> 状态：**提议**。本计划整合已合并的 `BackendPlan.md`、`FrontendPlan.md`、`ContextArchitecture.md`、`GameSaveArchitecture.md`、ADR-001~011，并新增三个方向：类人记忆曲线与遗忘、前后端分层、存档（Memento）与记忆的整合。
> 未合并的代码、未运行的测试不得标记完成。周期为**粗估**（按 1–2 名开发者），需维护者确认。

## 0. 阅读范围与前提

编写本计划时读取了 dev 分支上已合并的 `BackendDesign.md`、`BackendPlan.md`、`ContextArchitecture.md`、`GameSaveArchitecture.md`、`ArchitectureDecisionRecords.md`（以及 PR #1/#2 的说明）。**以下内容未能读取，计划中涉及它们的部分按已合并文档的摘要推断**，落地前需核对：`MemoryDesign.md`、`FrontendDesign.md`、`FrontendPlan.md`、`FrontendBackendContract.md`、`api.md`、`SecurityAndAuditDesign.md`、`README.md`，以及全部 `src_py/`、前端源码。任务表中标有"核实"的项就是这类依赖。

## 1. 目标与成功标准

| 目标 | 成功标准（可验证） |
|---|---|
| 上下文隔离 | 交错并发的两个 session，prompt、记忆、工具结果零串线（C0 验收） |
| 类人记忆 | 影子评估显示：误注入率下降，Recall@K 不低于基线（容差由 ADR 设定）；记忆库增长趋缓；`pinned` 与身份记忆不被误淡忘 |
| 分层可维护 | 领域层可脱离 FastAPI/Qt/SQLite 测试；违规 import 允许清单清零；前端组件无 transport 级 import |
| 存档可靠 | 任一失败不发布半成品 revision；恢复可回滚；墓碑不复活；旧格式可读 |
| 契约一致 | REST/SSE/WS/Qt bridge 共用契约，路由清单与文档零差异 |
| 可回退 | 每个新行为都有特性开关，关闭后回到上一阶段 |

## 2. 已知基线问题（来自已合并文档，须核实）

| # | 问题 | 来源 | 处理 |
|---|---|---|---|
| 1 | `UserContext` 为单例，`get_current_messages()` 不按 session 过滤 → 跨 session 污染风险 | ContextArchitecture §3 | P0：C0-02 |
| 2 | 后端成功码 200，桌面 bridge 判断 0 | BackendDesign §9 | P0：B0-01、FX-01 |
| 3 | 路由重复 `/api` 前缀，WebSocket 注册路径与文档不符 | PR #1 | P0：B0-02/03 |
| 4 | raw secret 回显、异常信息泄露待审查 | BackendPlan B0-04 | P0 |
| 5 | 存档仅保存路径指针，不是完整快照 | GameSaveArchitecture §1 | P1：S1-* |
| 6 | 记忆注入作为 SYSTEM 消息追加进共享窗口，可能重复/残留 | ContextArchitecture §3 | C0-04 |
| 7 | 记忆只有层级，没有强度/遗忘模型；GC 仅为计划项 | BackendPlan B2-05 | M 系列 |

## 3. 目标架构一页纸

```
前端：View → Composable → Store(per-session) / Service(use-case) → Transport → Contract(单一来源)
                                        │（REST/SSE/WS/Qt bridge，共享 decoder 与错误模型）
后端：L1 Transport → L2 Application Service → L3 Domain(纯逻辑) → L4 Ports → L5 Adapters
记忆：Context(会话窗口) ⇄ PromptBuilder ⇄ Memory(强度模型/固化/保留) ⇄ SQLite+FAISS
存档：Coordinator(Caretaker) ⇄ Originators(Session/Character/Memory[+strength+clock]/Config)
横切：RequestContext · 错误模型 · 审计 · 特性开关 · MemoryClock
```

详细设计：[LayeredArchitecture.md](LayeredArchitecture.md) · [MemoryCurveAndForgetting.md](MemoryCurveAndForgetting.md) · [MementoMemoryIntegration.md](MementoMemoryIntegration.md) · [ContextArchitecture.md](ContextArchitecture.md) · [GameSaveArchitecture.md](GameSaveArchitecture.md)。

## 4. 路线图

| 阶段 | 内容 | 周期（粗估） | 退出条件 |
|---|---|---|---|
| **P0 治理与契约** | 响应码统一、路由清单、安全基线；ADR 批准；架构检查骨架；调研记忆模块实现 | W1 | ADR-012~018 有结论；路由清单与文档对齐；`allowlist` 骨架就绪 |
| **P1 隔离与分层骨架** | RequestContext、session 分桶 ContextStore、PromptBuilder 纯化、ChatApplicationService；前端 decoder/会话分片/流守卫 | W2–W4 | 交错并发测试通过；聊天用例经应用服务；前端 F2/F3/F4 落地 |
| **P2 记忆强度（影子）** | MemoryClock、强度表迁移与回填、StrengthModel、使用事件、影子评分、离线评估 | W4–W6 | 回填完成；影子指标稳定；评估报告给出参数建议 |
| **P3 遗忘生效与固化** | R 排序、状态过滤与唤醒、固化 dry-run→apply、冲突覆盖、pin/revive API、GC dry-run | W7–W10 | 评估指标达标；固化摘要抽查合格；GC 默认关闭 |
| **P4 存档 Memento** | Snapshot schema/manifest、原子发布、恢复事务、记忆 Originator、时间线/分支、自动存档 | W6–W11（可与 P2/P3 重叠） | 故障注入全部通过；旧格式兼容；UI 才可把 S2 标为"完整存档" |
| **P5 前端分层与体验** | services 整理、operation 轮询、存档时间线 UI、保持率 UI、契约生成单一来源 | W8–W12 | ESLint 规则生效；契约矩阵四 transport 全通过 |
| **P6 检索质量与性能** | 混合检索、中文分词、自适应 token 预算、基线与优化 | W10 起持续 | 基线报告；每项优化有数据与降级路径（ADR-008） |

## 5. 任务清单

沿用已合并文档的 ID（`B*`、`C*`、`S*`），新增 `A*`（治理）、`L*`（分层）、`M*`（记忆曲线）、`FX*`（前端）。"来源"列为已有则只引用，不重复定义。

### 5.1 治理与分层（A / L）

| ID | 任务 | 产出 | 验收 | 依赖 |
|---|---|---|---|---|
| A0-01 | 文档状态标注与相对链接检查 | 状态横幅规范、检查脚本 | `docs/` 链接零失效 | — |
| A0-02 | ADR-012~018 评审与结论 | ADR 状态更新、日期、负责人 | 每条为接受/拒绝/修改 | — |
| A0-03 | 特性开关登记机制 | 开关清单、默认值、负责人、清理期限 | §7 清单落地 | — |
| A0-04 | 架构适应度测试骨架（allowlist 模式） | 后端 import 检查、前端 ESLint 规则 | 现有违规被登记，新增违规被拒 | — |
| L1-01 | 组合根整理 | 单一装配入口 | 单例只出现在组合根/适配器 | A0-04 |
| L1-02 | 定义端口：`ContextStore`、`Clock`、`AuditSink` | Protocol/ABC + 内存实现 | 测试可整体注入假实现 | L1-01 |
| L1-03 | `ChatApplicationService` 薄入口 | controller 只调用它 | 行为不变，回归通过 | L1-02、C0-01 |
| L1-04 | 其余应用服务入口（Memory/Save/Pipeline/Task） | 薄函数/对象 | 无空壳目录 | L1-03 |
| L1-05 | allowlist 收紧 | 违规清单减少 | 最终为空 | 持续 |

### 5.2 上下文隔离（引用 `BackendPlan.md` §7）

C0-01 RequestContext、C0-02 ContextStore 分桶、C0-03 PromptBuilder 纯化、C0-04 记忆注入去副作用、C0-05 会话切换/清理生命周期。**C0-02 是 P3 以后 character scope 强化的前置**。

### 5.3 记忆曲线与遗忘（M）

| ID | 任务 | 产出 | 验收 | 依赖 |
|---|---|---|---|---|
| M0-01 | **核实**：memory 模块结构、`short_term/long_term/detailed` 到三层的映射、`compressed_memories` 压缩流程 | 调研记录并回写本文假设 | 假设逐条确认或修订 | — |
| M1-01 | `MemoryClock`（wall/active/game）与 `memory_clock_state` | 时钟端口 + 实现 + 假时钟 | 时钟回拨按 0；单调不减 | L1-02 |
| M1-02 | `memory_strength` / `memory_usage_event` 迁移与回填 | 版本化迁移、分批回填、进度记录 | 回填可中断重入；旧行为不变 | M0-01 |
| M1-03 | `StrengthModel` 纯函数进领域层 | 以 `reference/` 为基准的实现 | 属性测试全过 | M1-01 |
| M1-04 | `MemoryUsageEvent` 管线 | PromptBuilder 输出 + 有界队列 + 异步写入 | 失败/取消轮次不强化；队列满有告警 | C0-03、M1-02 |
| M1-05 | 影子评分与指标 | `strength.shadow` 开关、新旧排序对比日志 | 不改变任何用户可见结果 | M1-03、M1-04 |
| M1-06 | 离线回放评估集与 harness（中/日/英） | 评估集、报告模板 | 输出 Recall@K、MRR/nDCG、误注入率、token 成本 | M1-05 |
| M1-07 | 重要度/显著度估计器 | 规则 + 可选轻量打分器 | 不可用时回退默认值，不阻塞写入 | M1-02 |
| M2-01 | R 参与排序（`strength.rerank`） | 排序公式落地 | 指标达到 ADR 阈值方可启用 | M1-06 |
| M2-02 | 状态过滤与唤醒（`forgetting.state_transition`） | faded/archived 门控 | archived 不进默认检索；唤醒增益减半 | M2-01 |
| M2-03 | 固化流水线 dry-run | 聚合/提升/冲突/归档报告 | 幂等；有界；不持锁调用 LLM | M2-02、C0-02 |
| M2-04 | 固化 apply 与摘要质量抽查 | `consolidation.apply` | 人工抽查合格；失败保留原明细 | M2-03 |
| M2-05 | 冲突覆盖（supersedes） | 冲突组检测、最新者注入 | 冲突不静默合并 | M2-03 |
| M2-06 | `retention/pin/revive` API 与 DTO | 先更新 `api.md` 再生成类型 | 只追加字段，旧客户端无感 | FX-08 |
| M2-07 | GC dry-run 报告（即 B2-05） | 候选清单、字节估算、引用数 | 只读 | M2-03 |
| M2-08 | GC apply | `gc.apply`，走墓碑协议 | 单独审批；默认关闭 | B1-05、M2-07 |

### 5.4 存档（S）

沿用 `BackendPlan.md` §7 的 S1-01~S1-07，新增：

| ID | 任务 | 产出 | 验收 | 依赖 |
|---|---|---|---|---|
| S2-01 | `MemoryOriginator`：strength + clock + profile 三个 section | export/prepare/commit/rollback | 恢复后排序与快照时刻一致（ε） | M1-02、S1-02 |
| S2-02 | manifest 增加 `branch_id/label/trigger`，revision DAG | 向后兼容字段 | 分支恢复不覆盖旧 revision | S1-03 |
| S2-03 | 自动存档与滚动保留 | 触发器、保留策略、有界队列 | 受磁盘预算；恢复期间暂停 | S1-04 |
| S2-04 | `RestorePlan.memory_impact` | 预览输出 | 预览只读，数量准确 | S1-05、S2-01 |
| S2-05 | 恢复期间暂停固化/GC/自动存档 | 调度协调 | 失败回滚后调度状态复原 | S1-05、M2-03 |
| S2-06 | 故障注入套件 | 导出失败、hash 错、commit 中断、时钟缺失 | 无半成品、无混合状态 | S2-01 |

### 5.5 前端（FX）

> 与 `FrontendPlan.md` 的既有 ID 合并时需去重；此处 ID 仅为本计划内部引用。

| ID | 任务 | 验收 | 依赖 |
|---|---|---|---|
| FX-01 | 共享 `decodeEnvelope` 与 `AppError` | Axios/Qt bridge 对 200 与错误信封判断一致 | B0-01 |
| FX-02 | `Map<sessionId, SessionUiState>` 分片 | 会话切换不清空/复用同一对象；交错测试通过 | FX-01 |
| FX-03 | `StreamSession` 守卫与取消 | 晚到 chunk 被丢弃；取消后无写入 | FX-01 |
| FX-04 | services/use-case 整理 + ESLint 限制 import | 组件无 transport 级 import | A0-04 |
| FX-05 | `operation_id` 轮询/订阅组件 | restore/consolidate/重建索引不阻塞 UI | FX-04、S1-05 |
| FX-06 | 存档时间线与回档预览 UI | 显示 revision 树与 `memory_impact` | FX-05、S2-02、S2-04 |
| FX-07 | 记忆保持率 UI（只读提示、pin/revive） | 区分"已淡忘"与"已删除" | M2-06 |
| FX-08 | 契约生成单一来源 + 一致性检查 | 生成后工作区零差异 | B0-03 |
| FX-09 | 四 transport 契约矩阵测试 | 成功/参数错误/未初始化/超时/取消/断连/重复请求一致 | FX-01 |

### 5.6 既有任务（不重复）

B0-01~07、B1-01~08、B2-01~06 见 `BackendPlan.md`。与本计划的关系：B0-01→FX-01；B1-04/05/06 是 M2-08 的前置；B2-04（token 预算）与 M2-01 联动；B2-05 即 M2-07。

## 6. 依赖与关键路径

```
B0-01 → FX-01 → FX-02/03/09
B0-02 → B0-03 → FX-08 → M2-06
C0-01 → C0-03 → M1-04 → M1-05 → M1-06 → M2-01 → M2-02 → M2-03 → M2-04
C0-02 ──────────────────────────────────────────▶ M2-03（character scope）
M0-01 → M1-02 → M1-04；M1-02 → S2-01 → S2-04 → FX-06
B1-04 → B1-05 → M2-08（GC apply）
S1-01 → S1-02 → S1-03 → S1-04 → S1-05 → S2-05
```

**关键路径**：`C0-01/03 → M1-04/05/06 → M2-01~04`。评估集（M1-06）若被推迟，P3 不应开始，因为遗忘的参数没有数据依据。

## 7. 特性开关登记

| 开关 | 默认 | 阶段 | 说明 | 清理期限 |
|---|---|---|---|---|
| `memory.strength.shadow` | false→P2 后 true | P2 | 只计算与记录 | P3 结束后合并为常开 |
| `memory.strength.rerank` | false | P3 | R 参与排序 | 评估通过后常开 |
| `memory.forgetting.state_transition` | false | P3 | faded/archived 门控 | 同上 |
| `memory.consolidation.apply` | false | P3 | 固化实际写入 | 同上 |
| `memory.gc.apply` | false，**永久默认关闭** | P3 | 硬删除，单独审批 | 不清理，保持显式开启 |
| `save.snapshot.v2` | false | P4 | 新快照格式与 API | 验收后默认开启 |
| `ui.memory.retention` | false | P5 | 保持率提示 | UI 稳定后移除 |

每个开关登记负责人与清理日期，禁止长期残留。

## 8. 测试与评估策略

- **永久回归集**：交错并发 session 隔离；四 transport 契约矩阵；墓碑不复活；快照故障注入。
- **属性测试**：强度模型（见 `reference/test_strength_model_reference.py`，stdlib 可运行）。
- **离线回放评估**：M1-06 产出，作为 P3 启用门槛，并在每次改动参数时重跑。
- **影子对比**：线上/本地只记录新旧排序差异，不改行为。
- **迁移测试**：回填可中断重入；旧存档缺 section 的回填路径。
- **性能**：沿用 `BackendDesign.md` §10 的目标值（均为未测量的目标，先建基线）；强化/固化不得进入请求关键路径。

## 9. 度量（KPI）

| 指标 | 目标 |
|---|---|
| 跨 session 污染数 | 0 |
| 误注入率（陈旧/无关记忆被注入） | 相对基线下降（幅度由评估集定义） |
| Recall@K / MRR | 不低于基线（容差在 ADR 中设定） |
| 每轮 prompt 记忆 token | 不上升或下降 |
| 记忆库增长斜率 | 下降 |
| 强化队列丢弃数、固化失败率 | 可监控且低 |
| 恢复成功率 / 回滚成功率 | 故障注入下 100% 无半状态 |
| 契约不一致项 | 0 |
| 架构违规 import 数 | 单调下降至 0 |

## 10. 风险登记

| 风险 | 影响 | 缓解 |
|---|---|---|
| 遗忘参数无数据依据 | 重要信息被淡忘 | 影子 + 回放评估为门槛；置顶、身份下限、protect_tags |
| 分层重构引入回归 | 行为改变 | 绞杀者模式，旧入口保留；回归集；每次只移一块 |
| 强度回填迁移出错 | 数据损坏 | 旁路表、不改 memories；可中断重入；迁移前 pre-migration 快照 |
| 记忆模块源码与文档假设不符 | 设计需返工 | M0-01 首先核实；本文标注假设 |
| 摘要由 LLM 生成产生幻觉 | 错误记忆被固化 | 先 dry-run 人工抽查；失败保留明细；来源 lineage 可追溯 |
| 自动存档占用磁盘 | 用户困扰 | 预算与滚动保留；GC dry-run |
| 范围过大 | 交付延迟 | 分阶段，P2 影子即可独立产生价值；P4 与 P2/P3 可并行 |
| 文档与实现漂移 | 误导 | A0-01 状态标注与链接检查；实现 PR 必须更新对应文档 |

## 11. 完成定义（DoD）

沿用 `BackendPlan.md` §6，并补充：
- 对应设计文档的状态标注已从"提议"更新为"已实现/部分实现"，并写明版本。
- 新增特性开关已登记，默认值与回退路径已验证。
- 涉及强度/时钟/快照的改动，附"恢复一致性"测试结果。
- API 变更先更新 `api.md`，再生成前端类型，附兼容窗口说明。
- 影响用户可见行为的改动附评估数据或影子对比报告。

## 12. 文档维护计划

| 阶段完成时 | 需更新 |
|---|---|
| P0 | ADR 状态、`README.md` 索引、`api.md` 差异表 |
| P1 | `ContextArchitecture.md` 状态、`LayeredArchitecture.md` 已迁移清单、`FrontendDesign.md` |
| P2 | `MemoryCurveAndForgetting.md` 常数与评估结论、`MemoryDesign.md` |
| P3 | 同上 + `api.md`（retention 端点）、`SecurityAndAuditDesign.md`（遗忘/删除语义） |
| P4 | `GameSaveArchitecture.md`、`MementoMemoryIntegration.md`、`api.md`（snapshot 端点） |
| P5 | `FrontendPlan.md`、`FrontendBackendContract.md` |

## 13. 开放问题（需维护者决策）

1. 默认 `MemoryClock` 用 `wall` 还是 `active`？`offline_factor` 初值 0.3 是否符合产品预期？
2. 摘要生成使用本地模型还是云端 provider？涉及隐私，是否需要用户同意？
3. user scope（跨角色用户事实）是否需要？若需要，单独 ADR。
4. 是否向用户暴露"淡忘"状态，还是仅内部使用？
5. 快照是否需要加密（含聊天与记忆）？密钥如何管理？
6. 分支存档是否对普通用户开放，还是先作为内部能力？
7. 自动存档的默认磁盘预算和保留数量。
