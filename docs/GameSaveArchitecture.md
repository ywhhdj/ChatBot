# 游戏存档架构：Memento、版本快照、恢复事务与旧格式兼容

> 基于当前 \`src_py/modules/manager/saves/manager.py\` 与 \`models.py\`。当前 SaveSlotManager 维护 \`index.yaml\` 与每个槽的 \`data.yaml\`；模型文档明确将存档定义为“索引/路径指针 + 部分 UI/服务配置”，角色数据、聊天历史、记忆库仍由各自管理器维护。因此，简单地对 data.yaml 做复制并不能构成完整的游戏状态快照。本设计提出逻辑聚合的 Memento 模式，须分阶段实现。

## 1. 当前存档的真实语义

当前模块：
- \`SaveSlotManager\`：单例管理槽列表、当前槽、index.yaml、data.yaml、section 更新、槽切换和与 session 的同步。
- \`SaveSlot\` / \`Section\`：分为 memory、characters、chat_history、server、ui 等 section。
- 其中 memory、characters、chat_history 常保存路径指针；真实数据由相应管理器/目录单独读写；server section 存储配置数据。
- API 控制器提供 list/create/get/delete/toggle/save/load/section update/sync 等操作。

重要区分：
1. **存档槽（Slot）**：用户命名的逻辑分组，当前实现中也承担路径和少量配置指针。
2. **游戏快照（Snapshot）**：目标方案，是在一个一致性边界内捕获的完整可恢复状态 revision。
3. **会话（Session）**：一轮轮对话的容器，存储生命周期与游戏槽不是同一概念。
4. **持久化数据**：会话、角色、记忆真实内容归各自模块所有，不应在多个地方重复成为权威副本。

新架构应保留 Slot UI 语义，并新增 Snapshot revision 概念；不要继续把“路径指针保存成功”误称为“全游戏状态已经一致冻结”。

## 2. 目标：Memento 三方职责

Memento 是不暴露内部对象、能够捕获和恢复状态的设计模式。对应本项目：

- **Originator**：各领域管理器（Session、Character、Memory、Service/Config 等），负责输出版本化、可序列化的领域快照 DTO，且不把内部 lock、provider object、UI widget、event loop 等放入快照。
- **Memento**：不可变 Snapshot revision；包含 manifest、分区 payload、校验信息和来源版本。
- **Caretaker**：SaveSnapshotCoordinator/SaveSlotManager 的新增职责，管理 revision 创建、排序、保留、预演、应用与回滚，但不能任意修改领域快照内容。

~~~text
User save action
      |
      v
Save API / command
      |
      v
SaveApplicationService
      |
      v
SaveSnapshotCoordinator (Caretaker)
      |  freeze/read barrier + revision capture
      +----------------+----------------+----------------+
      |                |                |                |
      v                v                v                v
Session Originator  Character        Memory         Config/UI
      |                |                |                |
      +----------------+----------------+----------------+
                         |
                         v
                Snapshot DTO set
                         |
                         v
           Staging revision + manifest + hashes
                         |
                   validate & publish
                         |
                         v
              Immutable Snapshot revision
~~~

不要让 SaveSnapshotCoordinator 直接读取每个模块的私有变量或磁盘目录结构；为每个需要参与完整快照的模块提供 \`export_snapshot()\`/\`prepare_restore()\`/\`commit_restore()\`/\`rollback_restore()\` 或一个等价的明确接口。

## 3. 快照范围与一致性等级

提供显式保存级别，避免“看起来完整但实际上只是指针”的误解：

| 级别 | 名称 | 捕获范围 | 使用场景 |
|---|---|---|---|
| S0 | Slot metadata | slot 元数据、路径指针、用户选择 | 当前兼容旧 SaveSlotManager |
| S1 | Checkpoint | 被声明的会话/角色/服务配置 revision 与路径引用 | 快速恢复当前工作状态，但不保证全部历史文件独立复制 |
| S2 | Full snapshot | 所有已注册 originator 的完整必要数据，或以不可变且校验的 artifact 引用保存 | 可靠游戏存档、迁移、用户导出 |
| S3 | Recovery bundle | S2 + schema/migration metadata + required assets manifest + restore verification | 升级前备份、重大状态迁移 |

每份 Snapshot manifest 必须写清 \`consistency_level\` 与包含/排除范围。S2 不能引用会继续原地变化且无法校验的目录；若使用 artifact reference，则对象必须不可变、带版本和 hash。

### 需要纳入评审的 domain section

- \`character_state\`：角色配置版本、心情/好感等需要持久化的状态；不序列化运行时 provider 引用。
- \`sessions\`：会话元数据和消息文件或不可变 artifact；明确是否包含全部历史或最近窗口。
- \`memory\`：记忆数据快照或一致性水位；不得只保存 memory path 后声称 full snapshot。
- \`server_config\`：用户配置的允许字段；剔除 secret、运行态连接和一次性 token。
- \`ui_state\`：用户偏好、布局/背景/音量等；不把 transient popup/组件内部状态纳入存档。
- \`story/game_state\`：如当前业务模块存在，则通过显式 originator adapter 提供；不存在的 section 不得伪造。
- \`asset_refs\`：音频、图片、角色资源和外部文件的引用/拷贝规则。

## 4. 快照文件结构

一种目标布局（文件格式可评审调整）：

~~~text
saves/
  index.yaml                        # 槽列表与 current slot，保持向后兼容
  slots/
    slot_001/
      data.yaml                     # 旧格式兼容/槽配置
      snapshots/
        rev-000001/
          manifest.json
          sections/
            session.json
            character.json
            server_config.json
            ui.json
            memory-manifest.json
          artifacts/
            <content-sha256>        # 可选；按内容 hash 去重的不可变文件
        rev-000002/
          manifest.json
          sections/...
      current.json                  # 当前有效 revision 指针
      staging/
        <operation-id>/             # 未发布临时数据，启动时可清理
~~~

### Manifest（概念 schema）

~~~json
{
  "format": "chatbot-snapshot",
  "schema_version": 1,
  "slot_id": "slot_001",
  "revision": "rev-000002",
  "parent_revision": "rev-000001",
  "created_at": "2026-10-26T00:00:00Z",
  "app_version": "0.1.0",
  "consistency_level": "full",
  "operation_id": "op-uuid",
  "sections": {
    "session": {"schema_version": 1, "sha256": "...", "bytes": 1234},
    "character": {"schema_version": 1, "sha256": "...", "bytes": 250},
    "memory-manifest": {"schema_version": 1, "sha256": "...", "bytes": 98}
  },
  "artifacts": [
    {"id": "sha256:...", "bytes": 1000, "kind": "session-history"}
  ],
  "redactions": ["provider_secrets"],
  "status": "prepared"
}
~~~

这是设计示例，非当前 schema。Manifest 中 status 的最后发布值为 \`committed\`；只有完整验证并被 current 指针引用的 revision 才能作为默认加载目标。不能通过修改已发布 manifest 原地改变快照内容；需要新 revision。

## 5. 创建快照的事务阶段

1. **请求校验**：验证 slot、权限/确认、当前任务状态、磁盘空间与保留策略；分配 operation_id/request_id。
2. **冻结边界**：由 Coordinator 获取轻量读屏障或各 originator 的 revision token。避免持有全局锁调用 LLM/磁盘长操作。
3. **导出快照 DTO**：各模块使用公开接口导出版本化 JSON/二进制 artifacts；记录每个 section 的 revision/watermark。
4. **暂存写入**：写入唯一 staging 目录；限制最大文件数、总字节、嵌套深度和路径字符。
5. **完整性校验**：重读临时文件、验证 schema/hash、检查 artifact 引用都在 bundle 内或指向不可变内容。
6. **发布快照**：先把 staging 原子 rename 到 snapshots/rev-N（若文件系统支持），再将 current 指针原子替换。平台不支持目录原子替换时，使用可恢复的双文件/提交标记协议。
7. **持久化确认**：返回 revision、consistency_level、captured sections、excluded sections 和 warning，而不仅返回 ok=true。
8. **事件/审计**：记录槽、revision、动作、时长、字节数、失败阶段；不记录聊天正文或密钥。

若进程在步骤 4 崩溃，staging 不得变成有效快照；在步骤 6 前崩溃，旧 current 保持不变；发布后但响应丢失时，可根据 operation_id 查询结果而不重复生成同一逻辑 revision。

## 6. 恢复事务：Preview → Prepare → Commit → Verify

恢复是比保存更危险的写操作，应单独建模：

### Preview
- 用户指定 slot + revision；如果 revision 不指定，则解析 current。
- 校验 manifest、文件 hash、大小、schema version、required assets 与路径边界。
- 生成 RestorePlan：将覆盖哪些 domain、需迁移哪些 section、是否有缺失资源、目标一致性等级。
- 预览阶段不改运行态、不创建/删除角色、不清理记忆。

### Prepare
- 创建保护快照（before revision）。
- 每个 originator 把数据加载到临时对象/隔离目录，执行 schema migration 和业务不变量检查。
- 所有准备步骤可失败但不能暴露部分恢复状态。
- 若有不可逆副作用，需先定义补偿操作；不能加入无法回滚的副作用到 commit 前半段。

### Commit
- 在统一的应用层恢复锁内验证当前 revision 未发生并发变化（乐观版本检查）。
- 按依赖顺序应用 staged domain state；禁止 UI、EventBus listener 或模型调用在关键事务内部执行。
- 更新活动 slot/revision pointer；只发出“restore committed”事件后才让 UI 显示成功。
- 记忆的删除墓碑/tombstone 高于快照旧数据，commit 后重放墓碑和隐私清除记录。

### Verify / Rollback
- 重新读取关键状态进行校验：active session/character、section checksum、记忆索引与源数据版本。
- 验证失败时用保护快照和 originator rollback 恢复应用状态。
- 无法完全 rollback 的失败必须报告 \`partial_failure\` 与恢复指引，不能回报普通成功。
- 保留 before/target/after revision、各阶段结果和错误类型，供排障。

## 7. 快照与领域数据的一致性

当前部分 section 只是路径指针。Full snapshot 必须明确处理底层真实数据：

- 对支持 revision 的存储，引用一个只读 revision。
- 对不支持 revision 的文件，复制到 content-addressed artifact 并校验 hash。
- 对 SQLite 数据库，使用一致性备份机制或事务读快照；不得随意在 WAL 活跃时只拷贝主 DB 文件。
- 对 FAISS，记录 index checksum、embedding version、metadata watermark；快照恢复后核对 FAISS 与记忆表的一致性，必要时从权威记忆数据重建。
- 对正在写入的 session/history，使用 message sequence watermark 或短暂写入屏障，确保快照记录截至哪条消息。
- 对外部服务（OBS、浏览器、QQ bot 等）不应假装可以快照远端世界；只保存可恢复配置和可重建状态，并在 manifest 记为 external/non-snapshotable。
- 对 secret/config，仅保存可恢复的非秘密配置；密钥应由独立安全配置库管理，恢复时重新校验是否已配置。

## 8. 存档生命周期与清理策略

revision 状态：
\`staging → prepared → committed → superseded → eligible_for_gc → deleted\`

- committed revision 不得原地编辑。
- current revision 永远不能被 GC。
- 最近 N 个 revision、用户标记保护的 revision 和最近成功恢复的 revision 默认保留。
- GC 先 dry-run 输出将删除 revision、估算字节和引用计数，再执行。
- 内容去重 artifacts 需引用计数；只有没有任何 retained revision 引用时才能回收。
- 删除槽时先验证不是唯一恢复点，并支持明确确认；逻辑删除/回收应有审计和恢复窗口。
- 用户的数据删除请求高于备份恢复便利；若要求彻底删除，应同时清除快照 artifact 或对密钥化存储销毁对应数据密钥，并说明备份策略。

## 9. 迁移兼容

第一阶段保持原有 \`index.yaml\`、\`data.yaml\` 的读取与 UI；不在同一次变更中迁移所有底层数据。

1. 将当前槽标记为 S0；现有 save/load 行为保持兼容。
2. 新增 snapshots 目录和新 API/命令，不让旧客户端意外触发 full snapshot。
3. 提供 \`consistency_level\` 明确说明现有路径指针槽仅捕获了哪些 section。
4. 分模块提供 export/restore adapter；缺少 adapter 的域在 Full snapshot 中报缺失，不能默认为完整。
5. 完成 round-trip、故障注入和跨版本迁移后，才允许 UI 把 S2 标为“完整游戏存档”。
6. 若修改 API，先更新 api.md，再生成前端服务/types，并提供兼容窗口。

## 10. 建议的新增 API（待 ADR/契约评审）

这些端点是目标设计，不是当前已实现接口：

| 方法 | 目标路径 | 职责 |
|---|---|---|
| POST | /api/save/slots/{slot_id}/snapshots | 创建快照，返回 operation_id/revision |
| GET | /api/save/slots/{slot_id}/snapshots | 列出不可变 revisions |
| GET | /api/save/slots/{slot_id}/snapshots/{revision} | 获取 manifest 与详情 |
| POST | /api/save/slots/{slot_id}/snapshots/{revision}/preview-restore | 仅生成 RestorePlan |
| POST | /api/save/slots/{slot_id}/snapshots/{revision}/restore | 执行 prepare/commit/verify |
| POST | /api/save/operations/{operation_id}/cancel | 取消可取消的长操作 |
| GET | /api/save/operations/{operation_id} | 查询分阶段进度与结果 |

不要把所有操作塞进原有 \`/save/slots/{id}/load\`；旧 load 是 slot 切换语义，新 restore 是事务性领域状态恢复。

## 11. 验收清单

- [ ] 快照 manifest 能说明完整捕获范围、excluded domains 与 consistency level。
- [ ] 任意一个 originator 失败时不发布半成品 revision。
- [ ] current revision 只在快照校验成功后更新。
- [ ] restore preview 完全只读。
- [ ] restore prepare 阶段失败不改变运行态。
- [ ] commit 中断可恢复至 before revision，或明确报告部分失败。
- [ ] 恢复后 session、character、memory、FAISS 与源文件 revision 一致。
- [ ] 旧格式可继续读取，未知 schema 默认安全拒绝。
- [ ] 路径穿越、超大文件、损坏 hash、缺失 artifact 和并发 restore 均有测试。
- [ ] 记忆删除墓碑在 restore 之后仍生效，不从旧 snapshot 复活。
- [ ] API/UI 明确区分 Slot、Checkpoint 和 Full snapshot。

## 12. 与记忆强度、时钟的整合

记忆强度表、`MemoryClock` 状态和遗忘画像作为快照 section 的方式、恢复时的时间语义、回档对记忆的影响（含 `RestorePlan.memory_impact`）、revision 时间线/分支和自动存档策略见 [MementoMemoryIntegration.md](MementoMemoryIntegration.md)。本文的事务阶段与验收清单仍然适用，新增验收项见该文第 9 节。