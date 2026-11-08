# 安全与审计设计（dev 分支现行基线）

> 事实基线：`src_py/modules/security/workspace.py`、`core/tools/policy.py`、`services/shell/`、`core/tools/skills/sandbox.py`、`api/response.py`。
>
> 本次更新把「shell 默认全部拒绝」细化为「**仅放行受工作区与命令白名单约束的 shell 服务**」，并补齐服务产出目录规范。标注为「目标」的条目仍是提案。

---

## 1. 威胁模型

保护对象：本机 API / Qt bridge、配置秘密、会话/记忆/存档、外部工具、provider 凭据、日志、生成文件、用户工作区文件与轨迹日志。

风险场景：

- 本机网页或其他进程调用有副作用的 loopback API。
- prompt injection 通过网页、文件、记忆或工具结果诱导命令执行、路径穿越或任意脚本。
- **模型直接输出 `rm -rf`、`del /S`、绝对路径、符号链接、`>` 重定向或 `;` 命令拼接**。
- 路径穿越、任意脚本、无限运行与资源耗尽。
- 服务产出（PPT、技能输出）写到工作区之外，或被下载接口用绝对路径越权读取。
- api key 经 raw endpoint、异常、日志或浏览器持久化泄露。
- 一个 session 的记忆出现在另一个 session/角色上下文。
- SQLite/FAISS 部分写入、索引损坏、压缩或旧快照恢复导致数据复活。
- request_id、日志和审计事件意外存储隐私正文。
- 多层重试放大 provider 故障与队列积压。

---

## 2. 当前源码关注点（本次核对）

- `api/response.py` 实现统一信封、request_id 中间件与异常处理。**未处理异常当前仍会把 `type(exc).__name__: exc` 用作 response message**；目标为稳定通用消息 + request_id，详情仅写受控日志（待办）。
- `controllers/pipline.py` 有 api_key/token/secret/password 遮蔽，但 `raw=true` 可返回原值；应移除通用原文回显或限制到显式受控本地调试（待办）。
- `src/api/http.ts` 从 localStorage 读取 token；不得扩展为存储 provider API key；其成功码判定与后端不一致（待办）。
- `security/workspace.py` 原本已实现三档权限、路径边界与脱敏，但**没有任何业务模块引用**；本次已接入 PPT 产出、技能执行输出与 shell 命令执行。
- `core/tools/skills/sandbox.py` 是 AST 白名单受限 Python 沙盒；`shell` / `javascript` 类型**技能**仍不支持执行。注意与新增的 **shell 服务**区分：后者是受控命令通道，不是任意脚本执行。
- `controllers/audit.py` 暴露服务与工具能力目录，不能替代 audit event log。

---

## 3. 最小权限

- API 默认监听 `127.0.0.1`；远程监听必须显式开启认证并进行来源/网络风险评审。CORS 不是身份验证。
- REST、WebSocket 和 Qt bridge 使用同一套能力模型。
- 配置修改、技能执行、存档加载/删除、记忆清除、工作区切换单独定义 capability。
- 参数使用 allowlist schema，限制字符串/数组大小、枚举、ID、超时和输出长度。
- 对路径先 `realpath` / canonicalize，再确认仍在允许根目录内；避免 traversal 与符号链接逃逸。
- **任意脚本/通用 exec 默认禁用**。`Capability.EXEC` 与 `ToolPolicy.allow_exec` 默认关闭；唯一例外是 `shell` 服务：它在 `security/workspace` 边界内、按平台命令白名单执行，且由确定性代码二次校验命令文本。
- LLM 产出意图而非授权；确定性执行层检查身份、权限、参数、命令与业务状态。
- 网页、文件、检索记忆和工具输出均视为不可信数据，并显式标注来源。

---

## 4. 秘密与配置

- 默认只返回 configured 状态或遮蔽值，不返回明文 provider key。
- raw secret 不应作为通用 query 参数；若开发场景必须支持，需要本地可信环境、显式确认、短时授权和审计。
- 秘密变更只记录 secret name、动作、调用来源和结果，不记录秘密值。
- 对异常 message、任务结果、日志和通知使用 secret scrubber（`scrub_text`）。
- 配置文件权限应尽可能收紧；备份/存档导出识别并排除秘密。
- 前端不得将 provider key 放入 localStorage、Pinia persistence、URL、埋点或 console。
- shell 子进程的环境变量必须净化：剔除凭据类变量，`PATH` 置为受控值，不继承任意用户环境。

---

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

- action / reason_code 稳定且低基数，不把用户自由文本作为 event name。
- 敏感读取/导出只记录 resource ID、计数、hash，不记全文。
- 审计事件与普通 debug 日志分离，定义访问控制和保留期限。
- 成功/失败/拒绝均可追踪；影响数据的任务记录 before/after revision。
- 审计日志不是业务事务提交证据的替代品。
- 本地可写日志并不自动具备防篡改/不可抵赖能力；合规级需求需额外设计签名或远端只写存储。

现行可用的低基数原因码：`ToolPolicy.ReasonCode`（`service_not_registered`、`method_not_declared`、`service_undeclared`、`exec_forbidden`、`capability_not_granted`、`param_too_large`、`param_unsafe`、`command_forbidden`）与 `workspace.DenyReason`（`no_workspace`、`outside_root`、`symlink_escape`、`mode_denied`、`trail_protected`、`invalid_path`、`not_a_file`、`command_denied`）。

---

## 6. request_id、日志与错误

- 服务端为缺省 request_id 的请求生成随机 ID；外部提供值时限制长度、字符集并拒绝换行。
- request_id 传播到 async task 和 WebSocket 请求；后台任务保留 parent_request_id。
- 客户端只收稳定错误类别、简短信息和 request_id，详细堆栈仅记录在脱敏的本地日志。
- 结构化日志建议字段：ts、level、logger、request_id、task_id、event、duration_ms、status、provider。
- 默认不记录正文、prompt、音频/图片或私人记忆。诊断采样必须显式 opt-in、有短保留期并脱敏。
- 路径标签用「目录名 + 短 hash」（`workspace._root_label`），不把含用户名/盘符的完整绝对路径写进日志。
- 日志队列和磁盘增长有上限，提供 dropped counter 与明确 flush。

---

## 7. 记忆与存档隐私

- 查询最开始就按 session/owner 过滤，禁止全局 top-K 后才过滤。
- 删除需覆盖 metadata、FAISS vector/mapping、compressed references、cache 与 snapshots。
- 清理无法立即完成时先写 tombstone 并在检索层立刻排除，再后台物理清理。
- restore 必须重放删除墓碑，防止旧快照复活已删除记忆。
- 导出清楚标明数据范围并排除密钥；归档含 manifest/checksum。
- 删除请求需提供实际完成状态，不能以"已从当前 prompt 移除"代替永久删除。

---

## 8. 防耗尽与故障安全

- 队列有限，满载时拒绝或返回明确可重试错误。
- provider timeout、最大 response body、音视频大小、工具运行时间和 tool steps 有上限。
- 单轮命令默认 10 条（`CLTTool.max_tool_calls`），超出部分标记 `skipped` 并留痕。
- `CommandExecutor` 每条命令有超时与结果字符上限（默认 8000）；同步方法跑 `CmdExec` 专用池，技能跑 `SkillSandbox` 专用池，避免占满 `asyncio.to_thread` 默认池。
- shell 命令额外限制：超时、stdout/stderr 字节上限、禁止后台化与管道拼接。
- 指数退避加 jitter，并设总重试预算，防止多层重试相乘。
- 限制 WebSocket 消息大小、连接数、单连接在途请求数（8）和订阅数量。
- health check 不触发模型初始化、全量索引 rebuild 或全盘扫描。

---

## 9. 验收清单

- [x] 服务方法必须声明才可调用；`EXEC` 默认关闭，仅 shell 服务在受控条件下放行进程执行。
- [x] 所有服务产出路径经 `realpath` + `is_within` 校验，符号链接逃逸返回 `SYMLINK_ESCAPE`。
- [x] `rm`/`del`/`format`/`sudo` 等危险命令、重定向与命令拼接被拒绝，且拒绝带稳定原因码。
- [x] PPT / 技能 / shell 产出均落在 `<workspace>/<service_id>/...`，下载接口只接受 basename 并复验边界。
- [x] 工具命令有最大条数、超时、输出上限与取消传播。
- [ ] 默认不回显密钥，异常/日志不泄漏 secret（未处理异常 message 仍待修）。
- [ ] 检索不能跨 session 召回（ContextArchitecture P0 待办）。
- [ ] 删除记忆后，查询、压缩、缓存、快照恢复均不能复活。
- [ ] 恶意网页/工具输出不能改变授权或工具白名单。
- [ ] 取消/超时后资源释放，后台异常可追踪。
- [ ] 审计记录动作/资源/决策/结果，但不存隐私正文（audit event log 尚未落地）。
- [ ] 远程绑定、CORS、认证和来源限制经安全审查。

---

## 10. 上下文和恢复带来的安全边界

- ContextStore 以 session_id 做数据隔离，检索 API 先过滤再排名；不能依赖 prompt 指令来防止跨会话泄露。
- PromptSnapshot 区分 configured policy、用户输入、retrieved memory、tool result 和文件/网页内容的 trust label；label 由程序生成，不能由模型或外部内容自我声明。
- 切换 session/character 时检查活动请求和任务的归属，避免迟到的 stream/工具结果写入错误的会话。
- RestorePlan 先校验 slot/revision 权限、schema、hash、文件大小和路径。不能直接把外部导入的 YAML/JSON 对象当作可信内部对象。
- 恢复阶段禁止路径逃逸、任意 import、执行脚本或自动打开外部 URI；所有 artifact 都在受控根目录内经过验证。
- Snapshot manifest 可记录哈希以发现意外损坏，但本地可写 hash 不能防恶意修改；若要防篡改，需要 HMAC/签名密钥与安全存储策略。
- 删除墓碑必须优先于旧快照恢复。恢复动作不能重置隐私删除状态。
- 存档导出默认剔除 provider key、token、登录凭证和短期 session secret；重新加载后需要明确提示缺失秘密需重新配置。

---

## 11. 工作区与命令执行边界（本次新增）

### 11.1 三档权限

| 档位 | 读 | 写 | 删 | 执行 |
|---|---|---|---|---|
| `READ_ONLY` | ✓ | ✗ | ✗ | ✗ |
| `WRITABLE` | ✓ | ✓ | ✗ | ✗ |
| `UNRESTRICTED` | ✓ | ✓ | ✓ | ✓ |

- 判定函数是纯函数，不读请求内容、不受 LLM 输出改写。
- 轨迹日志物理存放在应用数据目录（不在工作区内），且 `TRAIL_PROTECTED` 在任何档位都禁止删除/截断/清空 —— 防止"嫌疑人烧掉监控录像"。
- 敏感文件名（api_key/secret/.env/*.pem…）与内容片段（sk-、AKIA、JWT、PEM 私钥、赋值式密钥）由 `scrub_text` 处理；`allow_sensitive` 必须由 UI 显式确认翻开，且确认本身进轨迹（确认不是无痕）。
- 未手动选择时，系统惰性创建默认工作区 `<用户数据目录>/workspace`，`mode=WRITABLE`。

### 11.2 服务产出目录规范

| 产出方 | 目录 |
|---|---|
| PPT | `<workspace>/ppt/` |
| 技能（tools/skills） | `<workspace>/skill/<skill_id>/` |
| 其它服务 | `<workspace>/<service_id>/` |
| shell cwd | `<workspace>/`（或 `<workspace>/<service_id>/`） |

统一入口 `service_output_dir()` / `output_path()` / `make_output_writer()`：检查工作区已选、档位允许写、最终路径仍在 root 内，并自动建目录。技能沙盒禁用 `open` / `os` / `pathlib` / `subprocess`，落盘只能通过注入的受限 `write_output(name, text)`。

### 11.3 命令准入（双层确定性检查）

```
LLM 命令文本
  │
  ├─ 第一层：ToolPolicy.inspect_command()（纯函数）
  │    拒绝危险动词、重定向、拼接、超长参数 → COMMAND_FORBIDDEN
  ▼
  ├─ 第二层：ShellService（执行前）
  │    平台映射 → 命令白名单 → 危险动词 → 路径参数 realpath/is_within
  │    → cwd 锁定 → 环境变量净化 → 超时/输出上限
  ▼
  └─ 子进程执行
```

- Windows 用 `cmd.exe /C`，Linux/macOS 用 `/bin/sh -c`；`dir→ls`、`copy→cp`、`del→rm`、`type→cat`、`move→mv`、`cls→clear` 等按系统映射。
- 拒绝：`rm`、`rmdir`、`del`、`erase`、`format`、`mkfs`、`dd`、`shutdown`、`reboot`、`sudo`、`chmod`、`chown`、`kill`、`taskkill`、`reg`、`diskpart`，以及 `|`、`;`、`&`、反引号、`>`、`>>`、`<`、换行等拼接/重定向形态。
- `cd` 只在单次调用内有效，且目标必须是工作区内的真实目录；`..` 逃逸、绝对路径越界、符号链接指向外部一律拒绝。
- 任何一层拒绝都返回稳定低基数原因码，不执行、不回显命令原文到日志（只记命令动词与原因码）。

### 11.4 明确不做的事

- 不提供任意脚本执行能力；`.sh` / `.js` 技能仍不支持执行。
- 不因为 `UNRESTRICTED` 档位就放行危险命令 —— 命令白名单是独立于权限档位的硬约束。
- 不把 shell 当作通用 `EXEC` 能力开放给其它服务；`ToolPolicy.allow_exec` 保持默认 `False`。
- 不信任模型自称"这条命令是安全的"；所有判定由代码完成。
