# 硬性约束（本项目执行约定）

- **不下载依赖、不执行构建/测试**：只产出工程源码与构建脚本
- **分层解耦**
- **可维护优先**：单一职责、接口隔离、模块边界清晰，禁止跨层反向依赖
- **记录完成计划到Plan**
- **先设计架构，根据架构执行，并且优化架构**
- **开始执行先读取docs的*Plan,README,*Design，维护api.md,md文件**

# 项目目录结构
```text
📁 src_py/
├── cli/
│   ├── generates/
│   │   ├── config.py
│   │   └── pipline.py
│   └── main.py
├── modules/
│   ├── api/
│   │   ├── controllers/
│   │   │   ├── websocket/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── events.py
│   │   │   │   └── models.py
│   │   │   ├── __init__.py
│   │   │   ├── config.py
│   │   │   ├── logger.py
│   │   │   ├── memory.py
│   │   │   ├── pipline.py
│   │   │   ├── request.py
│   │   │   ├── save.py
│   │   │   ├── service.py
│   │   │   ├── skill.py
│   │   │   ├── system.py
│   │   │   └── task.py
│   │   ├── _common.py
│   │   ├── exceptions.py
│   │   ├── requests.py
│   │   ├── response.py
│   │   └── server.py
│   ├── characters/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── orchestrator.py
│   │   └── presets.py
│   ├── config/
│   │   ├── __init__.py
│   │   ├── builder.py
│   │   ├── manager.py
│   │   └── models.py
│   ├── context/
│   │   ├── audio.py
│   │   └── user.py
│   ├── devices/
│   │   ├── base.py
│   │   ├── config.py
│   │   └── keyboard.py
│   ├── events/
│   │   ├── __init__.py
│   │   ├── bus.py
│   │   ├── data.py
│   │   └── types.py
│   ├── logger/
│   │   ├── __init__.py
│   │   ├── animation.json
│   │   ├── log.py
│   │   └── types.py
│   ├── manager/
│   │   ├── saves/
│   │   │   ├── manager.py
│   │   │   └── models.py
│   │   ├── service/
│   │   │   ├── decorator.py
│   │   │   └── manager.py
│   │   ├── task/
│   │   │   ├── decorator.py
│   │   │   ├── reference.py
│   │   │   └── schedular.py
│   │   ├── websocket/
│   │   │   ├── manager.py
│   │   │   └── models.py
│   │   ├── base.py
│   │   ├── character.py
│   │   ├── dispatcher.py
│   │   ├── pipeline.py
│   │   └── session.py
│   ├── memory/
│   │   ├── docs/
│   │   │   └── design.md
│   │   ├── emdedding/
│   │   │   ├── __init__.py
│   │   │   ├── adapters.py
│   │   │   └── base.py
│   │   ├── rag/
│   │   │   ├── main.py
│   │   │   ├── models.py
│   │   │   ├── retriever.py
│   │   │   └── store.py
│   │   ├── storage/
│   │   │   ├── base.py
│   │   │   ├── database.py
│   │   │   ├── markdown.py
│   │   │   ├── models.py
│   │   │   └── sqlite.py
│   │   ├── compression.py
│   │   ├── config.py
│   │   ├── main.py
│   │   ├── managers.py
│   │   ├── token.py
│   │   └── utils.py
│   ├── pipeline/
│   │   ├── adapters/
│   │   │   ├── asr/
│   │   │   │   └── adapter.py
│   │   │   ├── landmarker/
│   │   │   │   ├── face.py
│   │   │   │   └── models.py
│   │   │   ├── llm/
│   │   │   │   ├── adapter.py
│   │   │   │   ├── client.py
│   │   │   │   └── types.py
│   │   │   ├── ocr/
│   │   │   │   └── adapter.py
│   │   │   └── tts/
│   │   │       ├── adapter.py
│   │   │       ├── client.py
│   │   │       └── models.py
│   │   ├── downloads/
│   │   │   ├── asr.py
│   │   │   ├── landmarker.py
│   │   │   └── ocr.py
│   │   ├── emotion/
│   │   │   └── predictor.py
│   │   ├── chat.py
│   │   ├── enum.py
│   │   └── manager.py
│   ├── routes/
│   │   ├── intent.py
│   │   ├── keywords.json
│   │   ├── models.py
│   │   └── words.py
│   ├── services/
│   │   ├── browser/
│   │   │   ├── scripts/
│   │   │   │   ├── distiller.js
│   │   │   │   └── stealth.js
│   │   │   ├── browser.py
│   │   │   ├── distiller.py
│   │   │   ├── driver.py
│   │   │   └── models.py
│   │   ├── game/
│   │   │   └── minecraft.py
│   │   ├── image/
│   │   ├── knowledge/
│   │   │   └── query/
│   │   │       ├── adapter.py
│   │   │       ├── models.py
│   │   │       └── serach.py
│   │   ├── live2d/
│   │   │   ├── audio.py
│   │   │   ├── canvas.py
│   │   │   ├── components.py
│   │   │   └── views.py
│   │   ├── obs/
│   │   │   ├── client.py
│   │   │   ├── done_table.md
│   │   │   └── models.py
│   │   ├── qqbot/
│   │   │   ├── client.py
│   │   │   └── models.py
│   │   ├── __init__.py
│   │   ├── base.py
│   │   └── config.py
│   ├── tools/
│   │   ├── services/
│   │   │   ├── exceute.py
│   │   │   ├── formatter.py
│   │   │   └── models.py
│   │   ├── skills/
│   │   │   ├── manager.py
│   │   │   ├── models.py
│   │   │   └── sandbox.py
│   │   ├── ctl.py
│   │   └── models.py
│   ├── ui/
│   │   ├── channel.py
│   │   └── views.py
│   ├── utils/
│   │   ├── file/
│   │   │   ├── __init__.py
│   │   │   ├── common.py
│   │   │   ├── env.py
│   │   │   ├── json.py
│   │   │   ├── pickle.py
│   │   │   └── yaml.py
│   │   ├── http/
│   │   │   ├── __init__.py
│   │   │   ├── async_.py
│   │   │   ├── common.py
│   │   │   └── sync.py
│   │   ├── audio.py
│   │   ├── audio_stream.py
│   │   ├── decorators.py
│   │   └── util.py
│   ├── __init__.py
│   ├── app.py
│   ├── models.py
│   └── runtime.py
└── main.py
```

# 线程模型


# 三条铁律
  1. 主线程不跑 asyncio loop。​ `asyncio.run()` 只在「启动前」或「Qt 已退出后的清理阶段」一次性使用。
  2. 主线程 join 任何线程时，必须一边 join 一边泵 Qt 事件（`join_with_pump`）。否则「主线程等线程、线程等主线程派发 Qt 任务」直接死锁。
  3. `emit()` 不得在已有运行中 loop 的线程里调用 `asyncio.run()`。​ 有 loop 就排 task，没 loop 才 `asyncio.run()`。
# 规范
1. 私有属性应用_前缀，如 `_name, _age, _gender` 等。
2. 私有方法应用__前缀，如 `__get_age(), __set_gender()` 等。（__为python真正的私有方法）

# 路由模型

## 三上下文分离
```text
┌─────────────────────────────────────────────────────────────┐
│                     全局共享空间                              │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │  角色上下文    │  │  工具上下文    │  │  用户输入上下文   │   │
│  │              │  │              │  │                  │   │
│  │ • 人设/性格   │  │ • OBS/Browser│  │ • 当前轮输入       │   │
│  │ • 称呼/头衔   │  │ • Live2D/Shell│  │ • 对话记忆(每角色)│   │
│  │ • 心情/好感   │  │ • Skills     │  │ • 任务队列        │   │
│  │ • 随机词汇池  │  │ • 命令文档   │  │                   │   │
│  └──────────────┘  └──────────────┘  └──────────────────┘   │
│         ↓                ↓                    ↓             │
│    CHAT prompt        TASK prompt         USER messages     │
│    (省token)          (纯执行)           (动态注入)           │
└─────────────────────────────────────────────────────────────┘
```

## 双通道输出
```
用户输入
  ↓
IntentRouter 判断意图类型
  ↓
┌────────────┬────────────┐
│ CHAT 通道   │ TASK 通道   │
│            │            │
│ 角色人设    │ 工具文档    │
│ + 10条记忆  │ + 任务描述  │
│ + 随机词汇  │            │
│     ↓      │     ↓      │
│  LLM       │  LLM       │
│  直接回复   │  输出命令   │
│  (省token)  │     ↓      │
│            │  后台执行   │
│            │     ↓      │
│            │  结果回填   │
│            │     ↓      │
│            │  角色化总结  │
└─────┬──────┴─────┬──────┘
      ↓            ↓
   给用户      给用户
```

---
# 输入模型
## 输入流
```text
用户输入
  ↓
router_stream()                              [stream_task_scheduler -> 调度器 loop]
  ├─ ensure_initialized_async()              一次性初始化 + 并发等待（C9）
  ├─ GameSaveManager.get/create(指定 id)      （C5）
  └─ CharacterOrchestrator.process_stream()
       ├─ IntentRouter.route()                规则匹配（同步、零线程池 C32）
       │    └─ 置信度不足 → 轻量 LLM（剥离 markdown 后解析 C14）
       │         └─ 失败回退参数齐全（C13）+ 字段名正确（C57）
       ├─ UserContext.add_user_message()      按 loop 取锁（C1）
       ├─ PromptBuilder.build()               三上下文分离
       │    └─ mood: int → emotion_map → modifiers（C16）
       ├─ [TOOL_CALL/MIXED] _handle_task_stream（C6：不再是死代码）
       │    ├─ ServiceOrchestrator._build_system_prompt
       │    ├─ CommandParser.parse()          三种写法都支持（C58）
       │    ├─ CommandValidator.validate()    tools 形态兼容（C61）
       │    ├─ CommandExecutor.execute()      同步方法不堵 loop（C62）
       │    └─ 结果回填 → 角色化总结（流式）
       └─ [PURE_CHAT] _handle_chat_stream
       ↓
  result 经 result_holder 回填（C8：不读 _last_result）
       ↓
  chat.py emit LLM_FINAL_TEXT / TASK_EXECUTED
       ↓
  GameSaveManager.save_sync()                 （C22：同步落盘）
       ↓
  （用户显式存档）SaveSlotManager.save_slot() ← sync_from_sessions 打通
```

## 技能链路

```text
用户: "用天气技能查一下北京天气"
  ↓
IntentRouter -> TOOL_CALL
  ↓
TASK prompt（含 build_prompt() 输出的技能清单）
  skill --id weather --des "查北京天气"
  ↓
CommandParser.parse    -> {"service":"skill","params":{"id":"weather","des":"..."}}
                          （_parse_builtin 兼容 --id / --name）
  ↓
ServiceOrchestrator._execute_skill_command
  ├─ params.get("id") or params.get("name")        <- A2
  ├─ ExternalSkillManager.execute_skill(skill_id, params)
  │    ├─ skill = self._skills.get(skill_id)
  │    ├─ exec_type == 2 (shell) -> 直接拒绝      <- K14
  │    ├─ exec_type == 1 (python) -> 沙盒执行 skill.code   <- K1/K2
  │    └─ exec_type == 3 (javascript) -> 未实现
  └─ 返回 {"ok":..., "data":...}
  ↓
结果回填 -> 角色化总结（流式）
```

## 记忆链路

```
UserContext.add_message()
  ├─ 按 loop 取锁
  ├─ append + 相邻去重
  └─ maybe_compress_context()
       ├─ 计数器触发
       ├─ persist_context_detail() 
       └─ ContextCompressor.compress_context()
            ├─ prompt 模板缺失时回退内置模板
            ├─ llm_manager.compress(prompt=..., system_prompt=...)  <- M3 参数名
            └─ 失败 -> 规则压缩
  ↓
HybridMemorySystem.get_memory_layers()   -> {short_term, long_term, detailed}
  ↓
UserContext.build_memory_messages() -> SYSTEM 消息注入
  ↓
PromptBuilder.format_memory_context()
```