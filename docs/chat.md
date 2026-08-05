# 角色系统 (Character System)

> 为 AI 桌面助手设计的**多角色管理 + 双通道编排**系统

## 核心理念

### 三上下文分离
```
┌─────────────────────────────────────────────────────────────┐
│                     全局共享空间                              │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │  角色上下文    │  │  工具上下文    │  │  用户输入上下文    │  │
│  │              │  │              │  │                  │  │
│  │ • 人设/性格   │  │ • OBS/Browser│  │ • 当前轮输入     │  │
│  │ • 称呼/头衔   │  │ • Live2D/Shell│  │ • 对话记忆(每角色)│  │
│  │ • 心情/好感   │  │ • Skills     │  │ • 任务队列       │  │
│  │ • 随机词汇池  │  │ • 命令文档   │  │                  │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
│         ↓                ↓                    ↓             │
│    CHAT prompt        TASK prompt         USER messages     │
│    (省token)          (纯执行)           (动态注入)         │
└─────────────────────────────────────────────────────────────┘
```

### 双通道输出
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

## 快速开始

### 1. 初始化

```python
import asyncio
from character_system import CharacterManager, CharacterOrchestrator
from character_system.presets import create_from_preset, list_presets

# 创建角色管理器（全局单例，自动持久化）
char_mgr = CharacterManager(storage_path="./data/characters.json")

# 查看可用预设
for p in list_presets():
    print(f"  [{p['id']}] {p['name']} - {p['desc']}")

# 注册角色
char_mgr.register(create_from_preset("qingmei"))     # 青梅竹马
char_mgr.register(create_from_preset("ku_zixunshi"))  # 心理咨询师
char_mgr.register(create_from_preset("youling_loli")) # 幽灵萝莉

# 切换到小青
char_mgr.switch_to("qingmei")

# 创建自定义角色
from character_system.presets import create_custom
my_char = create_custom(
    name="阿夜",
    title="夜班程序员",
    nickname_for_user="老板",
    personality="沉默寡言但内心细腻",
    catchphrases=["嗯。", "能跑就行。"],
    random_words=["...", "hm", "行吧"],
)
char_mgr.register(my_char)
```

### 2. 创建编排器

```python
# 你的 LLM 调用函数 (async, 接收 messages 列表, 返回文本)
async def my_llm(messages: list[dict]) -> str:
    # 调用 OpenAI / DeepSeek / Ollama 等
    ...

# 你的命令执行函数 (async, 接收命令文本, 返回结果列表)
async def my_executor(cmd_text: str) -> list[dict]:
    # 委托给 ServiceCTLTool 或 ServiceOrchestrator
    ...

# 工具命令文档（从 ServiceCTLTool.get_service_prompt() 获取）
tool_prompt = """
### OBS
obs_switch_scene --name <场景名>
obs_start_recording
### 浏览器
browser_open --url <网址>
"""

# 创建编排器
orch = CharacterOrchestrator(
    character_manager=char_mgr,
    llm_caller=my_llm,
    command_executor=my_executor,
    tool_prompt=tool_prompt,
    intent_router=my_intent_router,  # 可选，你的 IntentRouter
)
```

### 3. 处理用户输入

```python
# 自动判断通道
result = await orch.process("今天好累啊")
print(result.chat_response)       # 情感回复
print(result.channel)             # "chat"
print(result.affection_delta)     # 好感度变化

# 强制走 TASK 通道
result = await orch.process(
    "帮我打开B站直播间", 
    force_channel="task"
)
print(result.commands_executed)   # 执行的命令结果
print(result.chat_response)       # 角色化总结

# 强制走 CHAT 通道
result = await orch.process(
    "陪我聊聊天吧",
    force_channel="chat"
)
```

---

## 与现有项目集成

### 在 `chat.py` 中替换 `router()` 函数

```python
from character_system.integration import CharacterChatRouter

# 创建增强路由器
char_router = CharacterChatRouter(
    llm_manager=llm,              # 你的 manager.LLM 实例
    character_manager=char_mgr,    # CharacterManager 实例
    intent_router=inte,           # 你现有的 IntentRouter
    tts_manager=tts,              # 可选
    events=events,                # 你的事件系统
    service_orchestrator=svc_orch,# 你的 ServiceOrchestrator
    tool_prompt=tool_prompt,      # 工具文档
)

# 替换原有 router
async def router(system_prompt, user_input, source, **kwargs):
    result = await char_router.route(
        user_input=user_input,
        source=source,
        system_prompt_override=system_prompt,
    )
    events.emit(LLM_FINAL_TEXT, (result.chat_response,))
    return result.chat_response

# 流式版本
async def router_stream(system_prompt, user_input, source, **kwargs):
    async for chunk in char_router.route_stream(user_input, source):
        yield chunk
```

### 在 `manager.py` 中注入角色

```python
# LLM 类的 intialize_provider 中追加:
from character_system import CharacterManager

self.char_mgr = CharacterManager(
    storage_path="./data/characters.json"
)
# 注册默认角色
if not self.char_mgr.get_all():
    from character_system.presets import create_from_preset
    self.char_mgr.register(create_from_preset("qingmei"))
    self.char_mgr.switch_to("qingmei")

# 创建角色编排器
from character_system.integration import CharacterChatRouter
self.char_router = CharacterChatRouter(
    llm_manager=self,
    character_manager=self.char_mgr,
    intent_router=None,  # 可以后续注入
    tool_prompt="",
)
```

---

## 角色数据模型

### CharacterAttributes（人设）

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | str | 角色名 |
| `title` | str | 称呼/头衔 |
| `nickname_for_user` | str | 对用户的称呼 |
| `personality` | str | 性格描述 |
| `background` | str | 背景故事 |
| `speech_style` | str | 说话风格 |
| `catchphrases` | list[str] | 口头禅 |
| `rules` | list[str] | 行为规则 |
| `random_words` | list[str] | 随机语气词池 |
| `action_verbs` | list[str] | 动作描写池 |
| `emotion_adjectives` | list[str] | 情感形容词池 |
| `affection_level` | int | 好感度 0-100 |
| `mood_modifiers` | dict | 各心情的自然语言描述 |

### CharacterState（运行时）

| 字段 | 说明 |
|------|------|
| `messages` | 该角色独立的对话历史 |
| `mood` | 当前心情 |
| `affection` | 当前好感度 |
| `pending_tasks` | 后台任务队列 |
| `task_history` | 已执行任务记录 |

---

## 预设角色

| ID | 名称 | 类型 | 特点 |
|----|------|------|------|
| `qingmei` | 小青 | 青梅竹马 | 开朗黏人、爱撒娇、叫你哥哥 |
| `ku_zixunshi` | 沈墨 | 心理咨询师 | 冷静专业、引导式对话 |
| `youling_loli` | 小绫 | 幽灵萝莉 | 古灵精怪、对现代事物好奇 |

---

## Token 优化对比

| 模式 | 注入内容 | 估算 Token |
|------|----------|-----------|
| CHAT | 角色人设 + 10条记忆 + 随机词 + 输出规则 | ~250-400 |
| TASK | 角色轻量身份 + 工具文档 + 任务描述 | ~300-500 |
| MIXED | 角色人设 + 工具文档 + 任务结果 + 混合规则 | ~500-800 |
| 传统全量 | 角色 + 工具 + 全部历史 + 技能 + ... | ~1000-2000+ |

> CHAT 模式比传统方式节省 **60-75%** 的 prompt token

---

## 文件结构

```
character_system/
├── __init__.py        # 入口，对外暴露 API
├── models.py          # 数据模型（Character / State / ChannelType）
├── manager.py         # 角色管理器（单例、持久化、切换）
├── prompt_builder.py  # 动态 Prompt 构建（三通道）
├── orchestrator.py    # 双通道编排路由
├── presets.py         # 预设角色模板
├── integration.py     # 与现有项目集成的适配器
└── README.md          # 本文件
```

---

## 运行 Demo

```bash
python demo_character_system.py
```

包含 9 个演示场景：
1. 注册多角色 + 切换
2. CHAT 通道情感聊天
3. TASK 通道后台执行
4. MIXED 通道自动判断
5. 随机性增强验证
6. Prompt 片段拆解
7. 好感度/心情变化
8. 自定义角色
9. 与现有系统完整集成流程