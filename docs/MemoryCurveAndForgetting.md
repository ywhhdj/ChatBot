# 类人记忆曲线与遗忘机制设计

> 状态：**提议（Proposed）**，尚未实现。本文建立在 `MemoryDesign.md`（五层逻辑记忆）、`ContextArchitecture.md`（session 隔离、PromptBuilder）和 `GameSaveArchitecture.md`（Memento 快照）之上，不替换它们。
> 对现有源码内部结构的描述来自已合并文档（dev 分支，PR #1/#2），**落地前必须对照源码逐项核实**。参考实现与测试见 [reference/](reference/)。所有常数都是初始值，须经 §16 的离线回放评估后再定。

## 1. 要解决的问题

现有文档描述的记忆系统有 short_term / long_term / detailed 三个 API 层级，SQLite + FAISS 存储，`compressed_memories` 做压缩。就设计层面看，缺的是**"一条记忆现在有多可靠、该不该出现在这一轮 prompt 里"**这个连续量：

| 现状（来自已合并文档） | 后果 |
|---|---|
| 记忆只有层级，没有随时间变化的强度 | 三个月前的闲聊和昨天的约定在排序里权重相同 |
| 衰减/GC 只是计划项（B2-05），没有模型 | 记忆库只增不减，检索噪声和 token 成本随时间上升 |
| 被召回的记忆不会因"被用到"而更牢固 | 反复被提到的偏好与一次性噪音无区别 |
| 删除只有"删"这一种语义 | 无法表达"淡忘但可想起"，也无法和隐私删除区分 |

目标是让角色的记忆行为**可解释、可复现、可回滚**地接近人类：新事物先清晰后模糊，反复用到的更牢固，重要和有情绪色彩的更持久，淡忘的东西遇到强线索还能想起来，而用户要求删除的东西必须真正消失。

## 2. 设计原则

1. **派生而非改写**：强度是原始记忆的派生状态，存放在独立表中；关掉功能开关即恢复旧行为，原始记忆内容永不因衰减被改写。
2. **惰性计算**：不跑周期任务逐条更新强度；读取时由 `(now, last_reinforced, stability)` 计算 R。写入只发生在"被强化/被纠正/被固化"时。
3. **遗忘 ≠ 删除**：软遗忘（状态降级、停止默认注入、可被线索唤醒）与硬删除（墓碑协议，不可逆）是两套语义，UI 与 API 分开表达。
4. **强化要有证据**：只有记忆被真正注入 prompt 并产生作用才强化，"被检索到"不等于"被使用"，避免富者愈富。
5. **时间可注入**：所有计算通过 `MemoryClock`，可用墙钟、活跃时间或游戏内时间；测试和存档恢复不依赖系统时间。
6. **隔离优先**：强化、固化、提升都在 scope（session/character/user）内进行，不能因为"记忆强"而跨 session 泄漏（见 `ContextArchitecture.md` P0 风险）。
7. **先影子后生效**：新模型先只计算和记录、不影响检索结果，用数据证明收益后再按层逐步开启。

## 3. 认知现象与工程映射

| 心理学现象 | 本项目机制 | 不做什么 |
|---|---|---|
| 遗忘曲线（Ebbinghaus）：保持率随时间快速下降后趋缓 | 幂律保持率 `R(Δ,S)`，S 为稳定度 | 不声称复现具体神经机制，只借用曲线形态 |
| 间隔效应：间隔越长的成功回忆，巩固越多 | 强化增益随"回忆时 R 越低越大" | 不做"每天定时复习"，角色没有主动复习行为 |
| 提取练习（testing effect）：被成功取用的记忆更牢 | 被注入且产生作用的记忆强化 S | 仅被检索未使用 → 弱强化或不强化 |
| 加工深度 / 重要性 | `importance` 提高初始稳定度和增益 | 重要度不由 LLM 单独决定，见 §6.4 |
| 情绪增强 | `salience` 提高初始稳定度 | 不做情绪诊断，只用轻量显著度评分 |
| 干扰与更新 | 新事实 `supersedes` 旧事实，冲突组 | 不静默合并冲突，保留来源链 |
| 睡眠固化 | 空闲期的有界固化任务：摘要、提升、归档 | 不在请求路径里做 |
| 再巩固（reconsolidation） | 淡忘记忆被强线索唤醒后重新进入 active，但增益较小 | 不让被唤醒的记忆立刻回到高稳定度 |
| 线索依赖性遗忘（可用但不可达） | `faded` 状态：默认不注入，高相关时仍可检索 | 不把 faded 当作已删除 |

## 4. 数据模型

强度状态与记忆本体分表，1:1 关联，不修改 FAISS。

```python
@dataclass(frozen=True)
class MemoryStrength:
    memory_id: str
    scope: Literal["session", "character", "user"]
    scope_id: str
    layer: Literal["episodic", "summary", "semantic"]   # 工作记忆在 ContextStore，不在此衰减
    importance: float            # 0..1，写入时估计，可被后续证据修正
    salience: float              # 0..1，情绪/新奇度
    stability_days: float        # S：保持率降到 0.9 所需的有效天数
    last_reinforced_day: float   # 以 MemoryClock 有效天数计
    created_day: float
    reinforce_count: int
    lapse_count: int
    pinned: bool                 # 用户"记住这个"或系统保护，免疫衰减与 GC
    state: Literal["active", "faded", "archived"]   # 缓存，权威值由 R 派生
    supersedes: str | None       # 被它取代的旧记忆 id
    derived_from: tuple[str, ...]  # 摘要/语义记忆的来源 id（lineage）
    schema_version: int
```

```sql
-- 提议的迁移（schema-versioned，不改 memories 表）
CREATE TABLE memory_strength (
  memory_id TEXT PRIMARY KEY,
  scope TEXT NOT NULL, scope_id TEXT NOT NULL,
  layer TEXT NOT NULL,
  importance REAL NOT NULL, salience REAL NOT NULL DEFAULT 0,
  stability_days REAL NOT NULL,
  created_day REAL NOT NULL, last_reinforced_day REAL NOT NULL,
  reinforce_count INTEGER NOT NULL DEFAULT 0,
  lapse_count INTEGER NOT NULL DEFAULT 0,
  pinned INTEGER NOT NULL DEFAULT 0,
  state TEXT NOT NULL DEFAULT 'active',
  supersedes TEXT, derived_from TEXT,
  schema_version INTEGER NOT NULL
);
CREATE INDEX idx_strength_scope ON memory_strength(scope, scope_id, state);
CREATE TABLE memory_usage_event (          -- 强化证据，按天滚动清理
  event_id TEXT PRIMARY KEY, memory_id TEXT NOT NULL, request_id TEXT NOT NULL,
  session_id TEXT NOT NULL, usage TEXT NOT NULL, at_day REAL NOT NULL
);
CREATE TABLE memory_clock_state (          -- 参与存档快照
  id INTEGER PRIMARY KEY CHECK (id = 1),
  active_days REAL NOT NULL, last_wall_ts REAL NOT NULL, game_days REAL
);
```

**迁移回填**：对已有记忆按层赋 `S0`（§6.2），`last_reinforced_day = created_day`，`importance` 取默认 0.3；分批执行、可重入、带进度记录；回填完成前功能开关保持关闭。`short_term / long_term / detailed` 与三层的映射需对照源码确认，初始假设为 short_term→episodic、long_term→semantic+summary、detailed→episodic 明细。

## 5. 时间模型：MemoryClock

游戏/角色扮演应用里"过了多久"不等于墙钟时间：用户关机三天，角色不该像过了三天一样忘事；存档回档后也不该用当前系统时间计算衰减。

```python
class MemoryClock(Protocol):
    def now_day(self) -> float: ...       # 单调不减的"有效天数"
```

| 模式 | 有效天数来源 | 适用 |
|---|---|---|
| `wall` | 墙钟差 | 默认，最简单 |
| `active` | 应用运行/会话活跃时长 + `offline_factor × 离线时长` | 推荐；`offline_factor` 初值 0.3，可按角色配置 |
| `game` | 游戏/剧情推进的虚拟日期 | 有明确剧情时间线时 |

规则：
- `Δ<0`（系统时间回拨）一律按 0 处理，并记审计事件，避免被利用来"复活"或"加速遗忘"。
- 时钟状态 `memory_clock_state` 属于快照 section：恢复存档后时钟回到存档时刻，不把"现实中过去的时间"算进去（详见 `MementoMemoryIntegration.md`）。
- 同一进程内所有记忆读写使用同一个注入的时钟实例，测试用假时钟。

## 6. 数学模型

### 6.1 保持率

```
R(Δ, S) = 1 / (1 + Δ / (9·S))        Δ = now_day − last_reinforced_day，S > 0
```

幂律形态比纯指数更贴近人类遗忘（早期快、长尾慢），且 `R(S, S)=0.9`，所以 S 有直观含义："多少天后还能记得 90%"。该形态借鉴间隔重复研究（如 FSRS）中的做法，**参数仍须用本项目回放数据校准**。`pinned` 记忆 R 恒为 1。

### 6.2 初始稳定度

```
S0 = BASE_S[layer] × (1 + 3·importance) × (1 + 1.5·salience)，并受 S_MAX[layer] 限制
```

| layer | BASE_S（天） | S_MAX（天） | 排序时 R 的下限权重 |
|---|---|---|---|
| episodic（情节） | 1 | 30 | 0.2 |
| summary（摘要） | 7 | 120 | 0.4 |
| semantic（语义事实/偏好） | 30 | 720 | 0.6 |

参考实现算出的保持率（`reference/strength_model_reference.py`，未复习）：

| 记忆类型 | S0 | 1天 | 7天 | 30天 | 90天 | 365天 |
|---|---|---|---|---|---|---|
| 闲聊 (episodic, imp 0.1) | 1.30 | 0.92 | 0.63 | 0.28 | 0.12 | 0.03 |
| 普通事件 (imp 0.4, sal 0.2) | 2.86 | 0.96 | 0.79 | 0.46 | 0.22 | 0.07 |
| 重要事件 (imp 0.8, sal 0.8) | 7.48 | 0.99 | 0.91 | 0.69 | 0.43 | 0.16 |
| 摘要 (summary, imp 0.4) | 15.4 | 0.99 | 0.95 | 0.82 | 0.61 | 0.28 |
| 用户偏好 (semantic, imp 0.7) | 120.9 | 1.00 | 0.99 | 0.97 | 0.92 | 0.75 |

### 6.3 强化与失误

被使用时，按当时的保持率计算增益（间隔效应：越接近遗忘时被成功使用，收益越大）：

```
spacing = 0.1 + 0.9·(1 − R_now)
massed  = 0.2 若距上次强化 < 10 分钟，否则 1        # 突击记忆惩罚
gain    = 1.2 × usage_weight × spacing × massed × (1 + 0.5·importance)
S'      = min(S_MAX, S·(1 + gain))；last_reinforced_day = now
```

`usage_weight`：`injected`（进了 prompt）0.3，`referenced`（回复明显引用）0.7，`confirmed`（用户确认或主动提起）1.0。
失误（取出后被拒绝，或用户纠正"不对"）：`S' = max(0.25, S × 0.5)`，`lapse_count += 1`，**不重置时间轴**。

参考实现的间隔效应对比（普通事件，`referenced`）：

| 复习方式 | 稳定度 S | 30 天后 R | 90 天后 R |
|---|---|---|---|
| 无复习 | 2.86 | 0.46 | 0.22 |
| 突击（3 分钟内 3 次） | 3.04 | 0.48 | 0.23 |
| 间隔（第 2、6、14 天） | 5.09 | 0.74 | 0.38 |

使用类型对比（第 3、9、21 天各用一次，60 天后）：injected R=0.48，referenced R=0.56，confirmed R=0.62。

### 6.4 重要度与情绪显著度的估计

- 显式信号最高优先：用户说"记住/别忘了" → `pinned` 或 `importance≥0.9`；用户纠正过去的说法 → 新记忆 `supersedes` 旧记忆。
- 规则特征：身份/关系/承诺/日期/偏好类句式、被用户重复提及次数、对话轮长度。
- 轻量打分器（可选）：低成本模型或规则给 `importance`/`salience`，**输出只作先验**，会被后续强化/失误修正；打分器不可用时用默认值，不阻塞写入。
- 情绪显著度只用于提高持久度，不用于情绪诊断，也不写入可见日志正文。

### 6.5 确定性抖动

为避免曲线过于整齐，可对 R 加 ±5% 抖动，`jitter = f(hash(memory_id, day))`，同一天同一条记忆结果固定，保证测试和回放可复现。默认关闭，按角色 `ForgettingProfile` 开启。

## 7. 状态机

```
            R ≥ 0.5                0.2 ≤ R < 0.5             R < 0.2
          ┌─────────┐   衰减    ┌────────────┐   衰减    ┌──────────────┐
          │ active  │ ────────▶ │   faded    │ ────────▶ │  archived    │
          │ 默认注入 │ ◀──────── │ 高相关才注入 │ ◀──────── │ 仅摘要/显式查询 │
          └─────────┘  被强化/唤醒 └────────────┘  强线索唤醒 └──────┬───────┘
                                                                   │ GC 候选（dry-run，需批准）
                                                                   ▼
                                                         墓碑协议 / 硬删除（B1-05）
```

- 状态由 R 派生，`state` 列只是缓存，用于索引过滤；以 R 为准。
- `archived`：向量保留或迁入冷档案，默认不进检索；若已有 `summary` 记忆通过 `derived_from` 覆盖它，则明细可成为 GC 候选。
- **GC 候选必须同时满足**：未置顶、`R<0.05`、年龄>90 天、已有覆盖它的摘要、`importance<0.5`、层级为 episodic。条件缺一不可，且只输出 dry-run 报告，真正删除走墓碑协议并需批准。
- 语义层且 `importance≥0.7` 的记忆设"身份下限"：最低降到 `archived`，不进入 GC 候选。

## 8. 与检索和 PromptBuilder 的集成

### 8.1 排序

```
final = relevance × (floor[layer] + (1 − floor[layer]) × R_eff)
```

`relevance` 来自现有或后续混合检索（精确 → 词法 → 稠密 → RRF，见 ADR-004），先过 scope 与有效期过滤。排序公式只改变**权重**，不改变召回集合，影子模式下可并行计算两种排序比较差异。

### 8.2 门控与唤醒

| 状态 | 注入条件 |
|---|---|
| active | `relevance ≥ θ_rel`（沿用现有阈值） |
| faded | `relevance ≥ θ_rel_faded`（初值 0.75，更严格） |
| archived | 仅显式查询（"你还记得…吗"）或高置信线索 `relevance ≥ 0.9`，命中后按"再巩固"处理 |

唤醒：faded/archived 记忆被成功使用，则 `R` 视为不低于 0.5 起算，且强化增益乘 0.5，避免一次命中就回到高稳定度。

### 8.3 使用事件管线

`PromptBuilder` 已要求记录每段 included/excluded 原因（`ContextArchitecture.md` §5）。在此基础上输出 `MemoryUsageEvent(memory_id, request_id, session_id, usage)`：

1. 请求完成且状态为 `COMPLETED` 后才发布；失败、取消、超时的轮次**不强化**。
2. 经有界队列异步写入 `memory_usage_event` 并更新 `memory_strength`，写入失败不影响本次回复；队列满时丢弃最旧的 `injected` 事件并计数告警。
3. 事件必须带 `session_id`，强化只作用于与该 session 的 scope 匹配的记忆。
4. 强化路径不持有会话锁，不在请求线程中执行。

## 9. 固化（Consolidation）流水线

在空闲时间（无活跃请求超过 N 分钟、应用退出前、或用户手动触发）运行，**有界、可恢复、幂等**，每次有 `operation_id`：

1. **选批**：按 scope 取最近未处理的 episodic，限制条数和耗时预算。
2. **聚合**：按 session/话题时间窗聚类，生成 `summary` 记忆，`derived_from` 记录来源；摘要由 LLM 生成时先落草稿，校验长度与来源后再发布，失败则保留原明细。
3. **提升**：同一事实在 ≥2 个不同日期被强化 ≥3 次 → 提升为 `semantic` 候选。**提升不得跨 scope**，默认停留在原 session/character 范围，跨 scope 提升需显式策略与测试通过。
4. **冲突处理**：同 `conflict_group` 的事实，新者 `supersedes` 旧者；旧者降为 `faded` 并保留来源，不静默合并。
5. **归档**：R<0.2 的明细转 `archived`；
6. **GC 报告**：只生成 dry-run 清单（预计释放字节、引用数、被摘要覆盖情况），不删除。
7. 全程不持锁调用 LLM/embedding；单批失败不影响其他批；产生的事件和指标见 §16。

## 10. 冲突、覆盖与干扰

- 写入新事实时按 `(scope, subject, predicate)` 或语义近邻检查冲突组；命中则新记忆写入 `supersedes=旧id`，旧记忆标记 `faded` 并降低 S，而非删除。
- 检索时同冲突组只注入最新有效者；若存在无法裁决的冲突（来源置信度相近），PromptBuilder 以"不确定"标注两条或拒绝注入，遵循 `ContextArchitecture.md` 对冲突的要求。
- 用户明确纠正（"不是 A，是 B"）视为 `confirmed` 级别证据，对旧事实触发 `lapse`。

## 11. 作用域与隔离

| scope | 含义 | 强化/固化范围 |
|---|---|---|
| session | 仅当前会话可见 | 仅该 session 内的使用事件 |
| character | 某角色对用户的长期认知 | 同 character 下的 session，需 P0 隔离修复完成后启用 |
| user | 与角色无关的用户事实 | 默认关闭，开启需单独 ADR 与测试 |

在 `ContextArchitecture.md` 的 P0 隔离修复（C0-02）完成之前，本机制**只启用 session scope**。

## 12. 角色遗忘画像（ForgettingProfile）

不同角色可有不同"记性"，但只通过缩放参数实现，不改模型结构：

```yaml
forgetting_profile:
  name: default
  base_s_scale: {episodic: 1.0, summary: 1.0, semantic: 1.0}
  offline_factor: 0.3
  r_active: 0.5
  r_archive: 0.2
  jitter_amplitude: 0.0         # 0 = 关闭
  protect_tags: ["promise", "birthday", "name"]   # 命中则初始 pinned 或 importance≥0.9
```

画像随角色版本化，参与存档快照；切换角色不改变已有记忆的 S，只改变此后的计算参数。

## 13. 硬删除与隐私

- 软遗忘不满足"删除"义务。用户要求删除（或隐私清除）必须走墓碑协议（B1-05）：同时清理向量、映射、压缩引用、使用事件、缓存，并在存档恢复后重放墓碑。
- UI 文案区分："已淡忘（角色可能想起来）" 与 "已删除（不可恢复）"。
- 使用事件和强度表不含明文记忆内容，只含 id 和数值；日志默认只记计数。
- 备份/快照中的强度数据随快照 GC 一并处理（见 `GameSaveArchitecture.md` §8）。

## 14. 提议的 API / DTO（未实现，需契约评审）

| 方法 | 路径 | 职责 |
|---|---|---|
| GET | `/api/memory/{id}/retention` | 返回 `state / retrievability / stability_days / pinned`（调试与 UI 提示） |
| POST | `/api/memory/{id}/pin` · `/unpin` | 置顶/取消置顶 |
| POST | `/api/memory/{id}/revive` | 用户手动"让她想起来" |
| POST | `/api/memory/consolidate` | 触发固化，返回 `operation_id`（长操作，不阻塞） |
| GET | `/api/memory/retention/dry-run` | 返回 GC 候选清单，只读 |

现有 memory DTO 仅**追加**可选字段 `retention`，不破坏旧客户端。所有端点先更新 `api.md` 再生成前端类型（ADR-002）。

## 15. 配置与特性开关

```yaml
memory:
  strength:
    shadow: true             # 只计算与记录，不影响检索
    rerank: false            # 用 R 调整排序
  forgetting:
    state_transition: false  # 允许 faded/archived 过滤注入
  consolidation:
    apply: false             # false = 只出 dry-run
  gc:
    apply: false             # 永远默认 false；开启需维护者批准
```

开关按层、按角色可单独设置。关闭任一开关后，行为回到上一阶段，因为强度表是旁路数据。

## 16. 可观测性与评估

**指标**（不含正文）：`active/faded/archived` 计数、R 分布直方图、每轮注入记忆数与 token、强化队列深度与丢弃数、固化耗时与失败率、GC 候选数、影子模式下新旧排序的 top-K 重合度。

**离线回放评估**（Phase 2 必做）：
1. 用真实或合成对话构建带标注的评估集（中/日/英）：哪些记忆应在第 N 天被想起，哪些应已淡忘。
2. 比较 `baseline`、`+R 排序`、`+状态过滤`：Recall@K、MRR/nDCG、**误注入率**（陈旧/无关记忆被注入）、每轮 token 成本、记忆库增长曲线。
3. 以回放结果校准 BASE_S、阈值和 `usage_weight`，结论写入 ADR，常数不凭直觉定。

## 17. 测试

- **属性测试**（参考实现已覆盖）：R 单调不增且在 (0,1]；S 有上界；置顶免疫衰减/强化/失误；间隔复习优于突击；usage 权重有序；同输入同输出；时钟回拨按 0 处理。
- **集成测试**：A/B 两个 session 交错使用，A 的使用事件不强化 B 的记忆；失败/取消的轮次不产生强化；固化重复执行结果不变（幂等）；archived 不进默认检索；GC 条件缺一不可。
- **恢复测试**：快照 → 推进时间 → 恢复，R 排序与快照时刻一致（误差 ε）；墓碑后恢复不复活已删记忆。
- **故障注入**：强化队列满、固化中途崩溃、迁移回填中断后重启、摘要生成失败。

## 18. 推出策略与回滚

1. 迁移回填 + `shadow=true`：只记录，不改变任何用户可见行为。
2. 评估通过后，对 episodic 层先开 `rerank`，再开 `state_transition`；semantic 层最后开。
3. 固化先 dry-run 数周，人工抽查摘要质量，再允许 `apply`。
4. `gc.apply` 单独审批，首次只在测试数据上执行。
5. 任一阶段出现误注入率上升或用户可见异常，关闭对应开关即可回退，无需回滚数据。

## 19. 风险与开放问题

| 风险/问题 | 缓解 |
|---|---|
| 重要度打分不准导致重要信息被淡忘 | 显式信号优先；`protect_tags`；身份下限；用户可置顶 |
| 强化信号噪声（注入≠使用） | 低权重 `injected`；`referenced` 需有引用证据；评估集度量 |
| 常数缺乏数据支撑 | 影子模式 + 回放评估后再调整；常数集中配置 |
| 与现有 `compressed_memories` 压缩流程职责重叠 | 固化流水线复用其输出，不并行维护两套摘要；需对照源码确认 |
| 离线/回档时间语义复杂 | MemoryClock + 存档快照包含时钟状态（见 `MementoMemoryIntegration.md`） |
| "想起来"体验与产品期望不一致 | 先在 UI 暴露只读的保持率提示，收集反馈再决定是否可见 |
| 开放问题：user scope 是否需要？ | 暂不启用，待 C0-02 完成后单独 ADR |
