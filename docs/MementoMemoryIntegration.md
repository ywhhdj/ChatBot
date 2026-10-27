# 存档（Memento）与记忆曲线的整合设计

> 状态：**提议**。本文是 `GameSaveArchitecture.md` 的增补，不重复其中的 Slot/Checkpoint/Full snapshot 语义、staging 发布和 Preview→Prepare→Commit→Verify 事务，只补充四件事：记忆强度与时钟如何进入快照、时间线与分支、自动存档与保留策略、回档对记忆的影响。
> 与 `MemoryCurveAndForgetting.md` 配套阅读。

## 1. 为什么需要单独处理

引入记忆强度后，"存档"多了两类必须一致的状态：

1. **强度表**（`memory_strength`）：同一条记忆在快照时刻的稳定度与最后强化时间。
2. **时钟**（`memory_clock_state`）：决定"现在过了多少有效天"。

如果恢复存档时只恢复记忆文本、不恢复强度和时钟，角色会"一夜之间忘光"（用现实时间算衰减）或"记得过分清楚"（强度被重置），破坏存档的可预期性。

## 2. 快照 section 增补

在 `GameSaveArchitecture.md` §3 的 section 列表上增加：

| section | 内容 | 说明 |
|---|---|---|
| `memory-strength` | 强度表行（不含记忆正文） | 体积小，全量写入 |
| `memory-clock` | `active_days / game_days / last_wall_ts` | 恢复后以此为时间起点 |
| `forgetting-profile` | 当前角色画像参数与版本 | 避免恢复后用不同参数重算 |
| `memory-manifest` | 记忆数据水位、FAISS checksum、embedding 版本（已有） | 恢复后核对索引一致 |

`consistency_level=full` 的前提：以上 section 都由对应 Originator 的公开接口导出；缺任何一个的域在 manifest 里标记缺失，不得宣称完整（与现有规则一致）。

### 2.1 MemoryOriginator

沿用 `GameSaveArchitecture.md` §2 的接口约定，记忆域的实现要点：

```python
class MemoryOriginator(Protocol):
    def export_snapshot(self, ctx: SnapshotContext) -> list[SnapshotSection]: ...
    def prepare_restore(self, sections: list[SnapshotSection], plan: RestorePlan) -> PreparedRestore: ...
    def commit_restore(self, prepared: PreparedRestore) -> None: ...
    def rollback_restore(self, prepared: PreparedRestore) -> None: ...
```

- `export_snapshot`：通过事务读快照或水位导出 `memory-strength`、`memory-clock`；不读取私有变量，不导出 FAISS 二进制本体，只导出 checksum 和重建所需元数据（SQLite 为权威，FAISS 可重建）。
- `prepare_restore`：把强度表、时钟装入**临时对象**，校验 schema 版本、外键（强度行的 `memory_id` 必须存在于记忆表或属于将被恢复的集合）、`stability_days>0`、`last_reinforced_day ≤ 时钟当前值`。
- `commit_restore`：在恢复锁内原子替换；随后**重放墓碑**。
- `rollback_restore`：用恢复前保护快照（before revision）还原。

## 3. 恢复时的时间语义

| 情形 | 处理 |
|---|---|
| 恢复存档 | `MemoryClock` 回到快照时刻；现实中"存档到恢复之间"的时间**不计入**衰减 |
| 恢复后继续对话 | 从快照时钟继续单调前进；新强化按新时钟记录 |
| 系统时间被改 | 差值为负按 0 处理并记审计；恢复流程不依赖系统时间比较 |
| 跨版本恢复 | 强度 section 带 `schema_version`，未知版本安全拒绝；旧存档无强度 section 时用回填规则（按层默认 S0，`last_reinforced = created`）并在 RestorePlan 中提示 |

## 4. 回档对记忆的影响

快照之后新创建的记忆，在恢复后默认**不存在**（它们属于被放弃的时间线），但有两类例外必须显式处理：

| 类别 | 规则 |
|---|---|
| 用户在快照之后删除的记忆 | **墓碑优先**：恢复后重放墓碑，不得复活（ADR-005/010） |
| 用户在快照之后新增并要求保留的内容 | 默认不保留；RestorePlan 预览必须告知"将丢失 N 条之后创建的记忆、M 次对话"，由用户确认；可选"另存为分支"（§5） |

`preview-restore` 增加 `memory_impact`：

```json
{
  "memory_impact": {
    "will_restore": 1240,
    "will_discard_created_after": 37,
    "tombstones_to_replay": 5,
    "strength_schema": 1,
    "clock": {"from_active_days": 128.4, "to_active_days": 97.1}
  }
}
```

预览只读，无副作用。

## 5. 时间线与分支

现有 manifest 已有 `parent_revision`。把 revision 视作 DAG：

```
rev-1 ─ rev-2 ─ rev-3 ─ rev-4          主线
                  └──── rev-3a ─ rev-3b  回档后的分支
```

- 从旧 revision 恢复并继续游玩，新保存产生的 revision 以被恢复者为 `parent`，自然形成分支；**不覆盖**旧 revision。
- 每个 revision 记录 `branch_id` 和 `label`（可选，用户命名），`current.json` 指向活动 revision。
- UI 以树/时间轴展示；删除分支前检查是否为唯一恢复点或被保护。
- GC 遵循 §8：当前、被标记保护、最近 N 个、最近成功恢复的 revision 默认保留；分支叶子是否保留由策略决定。

提议在 manifest 增加字段（向后兼容，缺省即主线）：

```json
{ "branch_id": "main", "label": "第三章前", "trigger": "manual|quick|auto|pre-restore|pre-migration" }
```

## 6. 存档类型与自动存档

| trigger | 触发 | 保留策略 |
|---|---|---|
| manual | 用户点击保存 | 长期，除非用户删除 |
| quick | 快捷键/快速存档 | 单槽覆盖式，但仍写新 revision，仅保留最近 1–3 个 |
| auto | 固定间隔/关键事件后（如固化完成、章节切换） | 滚动保留最近 N 个（初值 5），不占用户槽位 |
| pre-restore | 恢复前自动保护快照（"before revision"） | 保留到恢复被验证成功后 + 一段缓冲期 |
| pre-migration | 数据迁移（含强度回填）之前 | 迁移验证通过后保留一个版本周期 |

自动存档限制：受磁盘预算约束；写入使用有界队列；恢复事务进行中暂停自动存档；固化任务进行中使用水位而不是长时间冻结。

## 7. 增量与体积

- `memory-strength`、`memory-clock`、`forgetting-profile` 体积小，每次全量写入。
- 会话历史采用 append-only 分段，快照记录截止消息序号，新 revision 只引用已有不可变分段（content-addressed artifact，按 hash 去重、带引用计数，见 `GameSaveArchitecture.md` §8）。
- FAISS 索引不进快照本体：记录 checksum + embedding 版本 + 元数据水位，恢复后核对，不一致则按权威记忆数据后台重建，并在 RestorePlan 标注"需要重建索引"。
- SQLite 使用一致性备份机制或事务读快照，禁止在 WAL 活跃时直接拷贝主文件。

## 8. 与固化/GC 的交互

- 快照创建与固化任务同时进行时，以**水位**为准：快照记录它看到的最后一个记忆版本号；固化新产生的摘要如晚于水位，则不进入该快照，不得出现"摘要在、来源明细不在"的半状态（摘要的 `derived_from` 必须在同一快照内可解析，否则该摘要整体排除）。
- GC（硬删除）执行前检查：待删记忆是否被任何**受保护 revision** 依赖；用户的删除请求高于备份便利，需要彻底删除时按 `GameSaveArchitecture.md` §8 的规则清理 artifact 或销毁数据密钥，并说明备份策略。
- 恢复事务期间禁止启动固化与 GC；恢复完成并 Verify 通过后才恢复调度。

## 9. 验收（增补）

- 快照→推进时间→恢复：同一查询在恢复后的排序与快照时刻一致（容差 ε）。
- 缺少 `memory-strength` 的旧快照可读取，RestorePlan 明确提示回填。
- 强度表与记忆表不一致（孤儿行/缺失行）时，Prepare 阶段拒绝，运行态不变。
- 墓碑在任意 revision 恢复后仍生效，已删记忆不复活。
- 回档预览准确报告将丢弃的记忆条数，且完全只读。
- 摘要与其来源 lineage 在快照内自洽。
- 恢复期间固化/GC/自动存档被暂停，结束后恢复；恢复失败回滚后调度状态也回到恢复前。
- 分支恢复不覆盖原 revision；删除保护中的 revision 被拒绝。
- 故障注入：强度导出失败、校验和错误、commit 中断、时钟 section 缺失，均不发布半成品 revision 或留下无法解释的混合状态。
