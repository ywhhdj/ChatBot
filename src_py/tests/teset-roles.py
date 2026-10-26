"""
demo_character_system.py — 角色系统完整演示

展示:
    1. 注册多角色 + 切换
    2. CHAT 通道（纯情感聊天，省 token）
    3. TASK 通道（后台执行命令）
    4. MIXED 通道（任务+聊天混合）
    5. 随机性增强（每次回复不同）
    6. 好感度/心情变化
"""
import asyncio
import sys
import os
from typing import Dict, List
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from modules.characters import (
    CharacterManager,
    CharacterOrchestrator,
    PromptBuilder,
    ChannelType,
    OrchestrationResult,
)
from character_system.presets import (
    create_from_preset,
    create_custom,
    list_presets,
)


# ═════════════════════════════════════════
# Mock LLM
# ═════════════════════════════════════════

class MockLLM:
    """
    模拟 LLM 响应，根据 system prompt 中的角色信息生成回复。
    """
    def __init__(self):
        self._call_count = 0
        self._last_prompt = ""

    async def __call__(self, messages: List[Dict]) -> str:
        self._call_count += 1
        self._last_prompt = messages[0].get("content", "") if messages else ""

        # 检测是否为 TASK 模式（有工具文档）
        is_task = "可用命令" in self._last_prompt or "service" in self._last_prompt.lower()
        # 检测角色
        is_qingmei = "小青" in self._last_prompt and "青梅竹马" in self._last_prompt
        is_shenmo = "沈墨" in self._last_prompt and "咨询师" in self._last_prompt
        is_ling = "小绫" in self._last_prompt and "幽灵" in self._last_prompt

        # 获取用户最后一条输入
        user_msg = ""
        for m in reversed(messages):
            if m.get("role") == Role.USER:
                user_msg = m.get("content", "")
                break

        # ── TASK 模式：输出命令 ──
        if is_task:
            return self._gen_commands(user_msg)

        # ── CHAT 模式：角色化回复 ──
        if is_qingmei:
            return self._qingmei_reply(user_msg)
        elif is_shenmo:
            return self._shenmo_reply(user_msg)
        elif is_ling:
            return self._ling_reply(user_msg)

        return f"收到: {user_msg}"

    def _gen_commands(self, user_msg: str) -> str:
        """模拟 LLM 在 TASK 模式下输出命令"""
        if "直播" in user_msg or "obs" in user_msg.lower():
            return 'obs_switch_scene --name "游戏画面"\nbrowser_open --url https://live.bilibili.com'
        elif "打开" in user_msg and "网页" in user_msg:
            url = "https://www.baidu.com"
            if "b站" in user_msg or "bilibili" in user_msg:
                url = "https://www.bilibili.com"
            return f'browser_open --url {url}'
        elif "截图" in user_msg:
            return 'browser_screenshot'
        elif "表情" in user_msg or "开心" in user_msg:
            return 'live2d_set_expression --name happy'
        return 'error --reason "无法识别为可执行任务"'

    def _qingmei_reply(self, msg: str) -> str:
        """小青风格回复"""
        import random
        greetings = ["诶嘿~", "哥哥~", "哼哼~", "嘻嘻~"]
        g = random.choice(greetings)
        if "累" in msg:
            return f"{g}哥哥辛苦了！要不要先休息一下，我给你倒杯水吧 *关心地歪头*"
        elif "开心" in msg or "好" in msg:
            return f"{g}哥哥开心我就开心！今天也一起加油吧！*握拳*"
        elif "讨厌" in msg:
            return f"呜...哥哥讨厌我了吗？*眼眶微红* 不要嘛不要嘛~"
        else:
            return f"{g}嗯嗯！然后呢然后呢？*好奇地凑近*"

    def _shenmo_reply(self, msg: str) -> str:
        """沈墨风格回复"""
        if "累" in msg:
            return "嗯，我理解。能具体说说，是身体上的疲惫，还是心里觉得累？"
        elif "焦虑" in msg or "担心" in msg:
            return "这种担心是很正常的。我们试着把担心的东西写下来，一件件来看，好吗？"
        elif "开心" in msg:
            return "听起来你今天状态不错。愿意多分享一些吗？"
        else:
            return "嗯，我在听。你愿意多说一些吗？"

    def _ling_reply(self, msg: str) -> str:
        """小绫风格回复"""
        import random
        w = random.choice(["哇啊！", "诶——", "这是什么！", "绫绫不懂~"])
        if "累" in msg:
            return f"{w} 累是什么感觉呀？是像飘了很久没有休息吗？*歪头* 要不要绫绫给你唱歌？"
        elif "手机" in msg or "电脑" in msg:
            return f"{w} 这个发光的小方块好厉害！比我们那时候的八卦镜厉害多了！*眼睛发光*"
        elif "开心" in msg:
            return f"嘿嘿嘿~ 你开心绫绫也开心！要一起飘圈圈吗！*兴奋地转圈*"
        else:
            return f"{w} 绫绫觉得好有趣！再多说一些嘛~"


# ═════════════════════════════════════════
# Mock 命令执行器
# ═════════════════════════════════════════

async def mock_command_executor(command_text: str) -> list[dict]:
    """模拟执行命令"""
    results = []
    for line in command_text.strip().split('\n'):
        line = line.strip()
        if line.startswith('obs_'):
            results.append({"ok": True, "service": "obs", "raw": line, "data": f"OBS: {line} 已执行"})
        elif line.startswith('browser_'):
            results.append({"ok": True, "service": "browser", "raw": line, "data": f"Browser: {line} 已执行"})
        elif line.startswith('live2d_'):
            results.append({"ok": True, "service": "live2d", "raw": line, "data": f"Live2D: {line} 已执行"})
        elif line.startswith('error'):
            results.append({"ok": False, "raw": line, "error": "任务无法完成"})
    return results


# ═════════════════════════════════════════
# 工具命令文档（模拟 ServiceCTLTool 输出）
# ═════════════════════════════════════════

TOOL_PROMPT = """## 可用命令

### OBS
obs_start_recording          # 开始录制
obs_stop_recording           # 停止录制
obs_switch_scene --name <场景名>   # 切换场景

### 浏览器
browser_open --url <网址>     # 打开网页
browser_screenshot            # 截图

### Live2D
live2d_set_expression --name <happy|sad|angry|surprised>
live2d_say --text "<台词>"

## 约束
- 一次最多输出10条命令
- 参数值带空格时用双引号包裹"""


# ═════════════════════════════════════════
# 演示
# ═════════════════════════════════════════

async def demo_basic():
    print("═" * 60)
    print("  Demo 1: 注册多角色 + 切换")
    print("═" * 60)

    char_mgr = CharacterManager(storage_path="./demo_characters.json")

    # 注册 3 个预设角色
    for preset_id in ["qingmei", "ku_zixunshi", "youling_loli"]:
        char = create_from_preset(preset_id)
        char_mgr.register(char)
        print(f"  ✅ 注册角色: {char.name} ({char.attributes.title})")

    # 注册一个自定义角色
    custom = create_custom(
        name="阿夜",
        title="夜班程序员",
        nickname_for_user="老板",
        personality="沉默寡言但内心细腻，偶尔冷幽默",
        background="连续加班三天的后端开发，靠咖啡续命",
        speech_style="简短直接，偶尔蹦出技术梗",
        catchphrases=["嗯。", "能跑就行。", "下班再说。"],
        random_words=["...", "hm", "ok", "行吧", "再说"],
        action_verbs=["揉了揉眼睛", "端起咖啡", "看了一眼屏幕", "叹了口气"],
        emotion_adjectives=["疲惫但满足的", "无奈的", "专注的"],
        affection=30,
        mood="tired",
    )
    char_mgr.register(custom)
    print(f"  ✅ 注册角色: 阿夜 (夜班程序员)")

    print(f"\n  角色列表:")
    for c in char_mgr.get_list():
        marker = " ← 当前" if c["is_current"] else ""
        print(f"    [{c['id']}] {c['name']} - {c['title']}{marker}")

    # 切换到小青
    char_mgr.switch_to("qingmei")
    current = char_mgr.get_current()
    print(f"\n  🔄 切换到: {current.name} (心情: {current.state.mood}, 好感度: {current.state.affection})")


async def demo_chat_channel():
    print("\n" + "═" * 60)
    print("  Demo 2: CHAT 通道 — 纯情感聊天（省 token）")
    print("═" * 60)

    char_mgr = CharacterManager(storage_path="./demo_characters.json")
    if not char_mgr.get_current():
        char_mgr.register(create_from_preset("qingmei"))
        char_mgr.switch_to("qingmei")

    llm = MockLLM()
    orch = CharacterOrchestrator(
        character_manager=char_mgr,
        llm_caller=llm,
        tool_prompt=TOOL_PROMPT,
    )

    # 连续对话（同一角色，状态累积）
    inputs = [
        "今天好累啊",
        "上班好无聊，好想下班",
        "不过今天午饭很好吃！",
    ]

    for msg in inputs:
        print(f"\n  👤 用户: {msg}")
        result = await orch.process(msg, force_channel=ChannelType.CHAT)
        print(f"  💬 {result.chat_response}")
        print(f"     [token估算: {result.used_tokens_estimate}, 通道: {result.channel.value}]")

    # 查看角色状态
    char = char_mgr.get_current()
    print(f"\n  📊 角色状态:")
    print(f"    好感度: {char.state.affection} (变化: {orch._last_result.affection_delta})")
    print(f"    消息数: {char.state.total_messages}")
    print(f"    心情: {char.state.mood}")

    # 切换角色
    print(f"\n  🔄 切换到沈墨...")
    char_mgr.switch_to("ku_zixunshi")
    result = await orch.process("我最近总是焦虑，睡不着", force_channel=ChannelType.CHAT)
    print(f"  👤 用户: 我最近总是焦虑，睡不着")
    print(f"  💬 {result.chat_response}")


async def demo_task_channel():
    print("\n" + "═" * 60)
    print("  Demo 3: TASK 通道 — 后台执行命令")
    print("═" * 60)

    char_mgr = CharacterManager(storage_path="./demo_characters.json")
    char_mgr.register(create_from_preset("qingmei"))
    char_mgr.switch_to("qingmei")

    llm = MockLLM()
    orch = CharacterOrchestrator(
        character_manager=char_mgr,
        llm_caller=llm,
        command_executor=mock_command_executor,
        tool_prompt=TOOL_PROMPT,
    )

    # 用户发出任务
    user_msg = "帮我打开B站直播间，OBS切到游戏场景"
    print(f"  👤 用户: {user_msg}")
    print(f"\n  [TASK 通道启动...]")

    result = await orch.process(user_msg, force_channel=ChannelType.TASK)

    print(f"\n  📋 LLM 生成的命令:")
    for line in result.task_output.strip().split('\n'):
        print(f"    → {line}")

    print(f"\n  ⚡ 执行结果:")
    for r in result.commands_executed:
        icon = "✅" if r.get("ok") else "❌"
        print(f"    {icon} {r.get('raw', '')} → {r.get('data', r.get('error', ''))}")

    print(f"\n  💬 角色化回复:")
    print(f"    {result.chat_response}")

    # 验证：角色状态也更新了
    char = char_mgr.get_current()
    print(f"\n  📊 角色消息历史: {len(char.state.messages)} 条")
    for m in char.state.messages:
        print(f"    [{m['role']}] {m['content'][:50]}")


async def demo_mixed_channel():
    print("\n" + "═" * 60)
    print("  Demo 4: MIXED 通道 — 自动判断（聊天+任务）")
    print("═" * 60)

    char_mgr = CharacterManager(storage_path="./demo_characters.json")
    char_mgr.switch_to("youling_loli")  # 小绫

    llm = MockLLM()
    orch = CharacterOrchestrator(
        character_manager=char_mgr,
        llm_caller=llm,
        command_executor=mock_command_executor,
        tool_prompt=TOOL_PROMPT,
    )

    # 模糊输入：既有聊天又有任务
    user_msg = "绫绫！帮我打开浏览器看看B站有什么好看的，然后陪我聊天！"
    print(f"  👤 用户: {user_msg}")

    result = await orch.process(user_msg)  # 不指定通道，自动判断

    print(f"\n  🔀 自动选择通道: {result.channel.value}")
    print(f"\n  📋 执行的命令:")
    for r in result.commands_executed:
        icon = "✅" if r.get("ok") else "❌"
        print(f"    {icon} {r.get('raw', '')}")

    print(f"\n  💬 最终回复:")
    print(f"    {result.chat_response}")


async def demo_randomness():
    print("\n" + "═" * 60)
    print("  Demo 5: 随机性增强 — 同一输入不同回复")
    print("═" * 60)

    char_mgr = CharacterManager(storage_path="./demo_characters.json")
    char_mgr.switch_to("qingmei")

    from character_system.prompt_builder import PromptBuilder

    char = char_mgr.get_current()

    print(f"\n  角色: {char.name}")
    print(f"  随机词汇池: {char.attributes.random_words}")
    print(f"  动作池: {char.attributes.action_verbs}")
    print(f"  口头禅: {char.attributes.catchphrases}")
    print()

    # 生成 5 次 prompt，观察随机抽取的差异
    for i in range(5):
        built = PromptBuilder.build(
            character=char,
            channel=ChannelType.CHAT,
            user_input="你好",
            inject_randomness=True,
        )
        # 找到 randomness 片段
        rand_seg = next((s for s in built.segments if s["type"] == "randomness"), None)
        print(f"  第{i+1}次随机片段:")
        if rand_seg:
            for line in rand_seg["content"].split('\n')[1:]:
                print(f"    {line}")
        print()


async def demo_prompt_breakdown():
    print("\n" + "═" * 60)
    print("  Demo 6: Prompt 动态构建 — 片段拆解")
    print("═" * 60)

    char_mgr = CharacterManager(storage_path="./demo_characters.json")
    char_mgr.switch_to("qingmei")

    from character_system.prompt_builder import PromptBuilder

    char = char_mgr.get_current()

    # CHAT 模式 prompt
    print("\n  ── CHAT 模式 (情感聊天) ──")
    built = PromptBuilder.build(character=char, channel=ChannelType.CHAT, user_input="你好")
    print(f"  总 token 估算: ~{built.estimated_tokens}")
    print(f"  片段数: {len(built.segments)}")
    for seg in built.segments:
        print(f"    [优先级{seg['priority']:>2}] ({seg['type']:>12}) {seg['content'][:50]}...")

    # TASK 模式 prompt
    print("\n  ── TASK 模式 (任务执行) ──")
    built = PromptBuilder.build(
        character=char, channel=ChannelType.TASK,
        user_input="打开B站", tool_prompt=TOOL_PROMPT
    )
    print(f"  总 token 估算: ~{built.estimated_tokens}")
    print(f"  片段数: {len(built.segments)}")
    for seg in built.segments:
        print(f"    [优先级{seg['priority']:>2}] ({seg['type']:>12}) {seg['content'][:50]}...")

    # MIXED 模式 prompt
    print("\n  ── MIXED 模式 (混合) ──")
    built = PromptBuilder.build(
        character=char, channel=ChannelType.MIXED,
        user_input="帮我截图", tool_prompt=TOOL_PROMPT,
        task_results='[{"ok": true, "data": "截图已保存"}]'
    )
    print(f"  总 token 估算: ~{built.estimated_tokens}")
    print(f"  片段数: {len(built.segments)}")
    for seg in built.segments:
        print(f"    [优先级{seg['priority']:>2}] ({seg['type']:>12}) {seg['content'][:50]}...")


async def demo_affection_mood():
    print("\n" + "═" * 60)
    print("  Demo 7: 好感度 & 心情变化")
    print("═" * 60)

    char_mgr = CharacterManager(storage_path="./demo_characters.json")
    char_mgr.register(create_from_preset("qingmei"))
    char_mgr.switch_to("qingmei")

    llm = MockLLM()
    orch = CharacterOrchestrator(
        character_manager=char_mgr,
        llm_caller=llm,
        command_executor=mock_command_executor,
        tool_prompt=TOOL_PROMPT,
    )

    char = char_mgr.get_current()
    print(f"\n  初始状态: 心情={char.state.mood}, 好感度={char.state.affection}")

    # 正面互动
    for msg in ["谢谢你小青！", "你真好呀", "哈哈好开心！"]:
        await orch.process(msg, force_channel=ChannelType.CHAT)
        print(f"  👤 {msg} → 好感度变化: {orch._last_result.affection_delta:+d}")

    char = char_mgr.get_current()
    print(f"\n  正面互动后: 心情={char.state.mood}, 好感度={char.state.affection}")

    # 负面互动
    for msg in ["讨厌你", "你好烦", "笨死了"]:
        await orch.process(msg, force_channel=ChannelType.CHAT)
        print(f"  👤 {msg} → 好感度变化: {orch._last_result.affection_delta:+d}")

    char = char_mgr.get_current()
    print(f"\n  负面互动后: 心情={char.state.mood}, 好感度={char.state.affection}")

    # 切换心情
    char_mgr.update_mood("qingmei", "sad")
    print(f"\n  手动切换心情 → sad")
    result = await orch.process("怎么了小青？", force_channel=ChannelType.CHAT)
    print(f"  👤 怎么了小青？")
    print(f"  💬 {result.chat_response}")


async def demo_custom_character():
    print("\n" + "═" * 60)
    print("  Demo 8: 自定义角色")
    print("═" * 60)

    char_mgr = CharacterManager(storage_path="./demo_characters.json")

    # 用 create_custom 创建一个猫娘
    catgirl = create_custom(
        name="喵酱",
        title="猫娘管家",
        nickname_for_user="主人",
        personality="傲娇、忠诚、偶尔撒娇，做事认真但嘴上不承认",
        background="被魔法变成猫娘的资深管家，侍奉主人家族三代",
        speech_style="表面恭敬但偶尔漏出傲娇本性，句尾偶尔带喵",
        catchphrases=["才、才不是为了你喵！", "主人请下令~", "哼，随便你喵"],
        rules=[
            "管家职责优先，但可以用猫娘方式表达",
            "傲娇是核心特质，嘴上说不要身体很诚实",
        ],
        random_words=[
            "喵~", "哼", "才没有", "才不要", "主人~",
            "喵呜", "呼呼", "随、随便你啦",
        ],
        action_verbs=[
            "耳朵竖起来", "尾巴摇摆", "轻轻蹭了蹭",
            "脸颊微红", "假装咳嗽", "一本正经地整理裙摆",
        ],
        emotion_adjectives=[
            "傲娇的", "害羞的", "嘴硬的", "温柔但不承认的",
        ],
        mood_modifiers={
            "happy": "尾巴愉快地摇摆，虽然嘴上说'没什么好开心的'",
            "sad": "耳朵耷拉下来，默默靠近",
            "angry": "'主人是大笨蛋！'然后跑开",
            "shy": "脸红到耳朵尖，尾巴炸毛",
        },
        affection=45,
        mood="neutral",
    )

    char_mgr.register(catgirl)
    char_mgr.switch_to("喵酱")

    llm = MockLLM()
    # 为猫娘加一个特殊的回复方法
    async def catgirl_llm(messages):
        user_msg = ""
        for m in reversed(messages):
            if m.get("role") == Role.USER:
                user_msg = m.get("content", "")
                break
        if "累" in user_msg:
            return "哼，主人又熬夜了对吧？*耳朵竖起来* 虽然...虽然我才没有担心你喵！快去休息啦笨蛋主人喵~"
        elif "谢谢" in user_msg:
            return "哼哼~ 不用说谢谢喵，这是管家该做的...才、才不是因为想听到夸奖喵！*脸颊微红*"
        elif "命令" in user_msg or "做" in user_msg:
            return "是，主人请下令~ *一本正经地整理裙摆* 喵酱会完美完成的喵！"
        return "*尾巴愉快地摇摆* 喵~ 主人想说什么呢？"

    orch = CharacterOrchestrator(
        character_manager=char_mgr,
        llm_caller=catgirl_llm,
    )

    for msg in ["喵酱，今天辛苦了", "帮我整理一下明天的日程", "你真好呀"]:
        result = await orch.process(msg, force_channel=ChannelType.CHAT)
        print(f"  👤 {msg}")
        print(f"  💬 {result.chat_response}\n")


async def demo_integration_with_existing():
    print("\n" + "═" * 60)
    print("  Demo 9: 与现有系统集成的完整流程")
    print("═" * 60)

    print("""
┌─────────────────────────────────────────────────────────────────┐
│  集成架构图                                                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   用户输入                                                        │
│      ↓                                                           │
│  ┌────────────┐    路由判断                                      │
│  │IntentRouter │ ──→ PURE_CHAT → CHAT 通道                       │
│  └────────────┘     TOOL_CALL  → TASK 通道                       │
│                   AUTO       → MIXED 通道                        │
│      ↓                                                           │
│  ┌────────────────────────────────────────┐                       │
│  │ CharacterOrchestrator                 │                       │
│  │  ┌──────────────────────────────────┐  │                       │
│  │  │ PromptBuilder (动态组合)          │  │                       │
│  │  │  ├ 角色人设 (CharacterManager)    │  │ ← 全局共享             │
│  │  │  ├ 工具文档 (ServiceCTLTool)     │  │ ← 系统服务             │
│  │  │  ├ 对话记忆 (Character.state)    │  │ ← 每角色独立           │
│  │  │  └ 随机性增强 (随机抽取)         │  │                       │
│  │  └────────────────┬─────────────────┘  │                       │
│  │                   ↓                    │                       │
│  │  ┌──────────────────────────────────┐  │                       │
│  │  │ CHAT: 直接回复 (省token)          │  │                       │
│  │  │ TASK: 输出命令 → 后台执行         │  │                       │
│  │  │       → 结果回填 → 角色化回复     │  │                       │
│  │  └──────────────────────────────────┘  │                       │
│  └────────────────────────┬───────────────┘                       │
│                           ↓                                      │
│                   最终回复给用户                                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
    """)

    # 模拟完整流程
    char_mgr = CharacterManager(storage_path="./demo_characters.json")
    char_mgr.register(create_from_preset("qingmei"))
    char_mgr.switch_to("qingmei")

    # 模拟 IntentRouter 的 decision
    class FakeDecision:
        def __init__(self, rt):
            self.route_type = rt

    class FakeRouter:
        async def route(self, text):
            if any(k in text for k in ["打开", "切换", "截图", "直播"]):
                return FakeDecision("tool_call")
            return FakeDecision("pure_chat")

    llm = MockLLM()
    router = FakeRouter()

    orch = CharacterOrchestrator(
        character_manager=char_mgr,
        llm_caller=llm,
        command_executor=mock_command_executor,
        tool_prompt=TOOL_PROMPT,
        intent_router=router,
    )

    # 场景1: 纯聊天
    print("  ── 场景1: 纯情感聊天 ──")
    r = await orch.process("小青今天天气好好呀")
    print(f"  👤 用户: 小青今天天气好好呀")
    print(f"  🔀 通道: {r.channel.value}")
    print(f"  💬 {r.chat_response}")
    print(f"  📊 token估算: ~{r.used_tokens_estimate}")

    # 场景2: 纯任务
    print("\n  ── 场景2: 纯工具调用 ──")
    r = await orch.process("帮我打开B站直播间")
    print(f"  👤 用户: 帮我打开B站直播间")
    print(f"  🔀 通道: {r.channel.value}")
    print(f"  📋 命令: {r.commands_executed}")
    print(f"  💬 {r.chat_response}")

    # 场景3: 切换角色后再聊
    print("\n  ── 场景3: 切换角色 ──")
    char_mgr.switch_to("youling_loli")
    r = await orch.process("绫绫，给我讲个故事吧")
    print(f"  👤 用户: 绫绫，给我讲个故事吧")
    print(f"  🔀 通道: {r.channel.value}")
    print(f"  💬 {r.chat_response}")

    # 场景4: 再切回小青（状态保留）
    print("\n  ── 场景4: 切回小青（记忆保留）──")
    char_mgr.switch_to("qingmei")
    char = char_mgr.get_current()
    print(f"  📊 小青消息历史: {len(char.state.messages)} 条（之前的对话还在）")
    r = await orch.process("我回来了~")
    print(f"  👤 用户: 我回来了~")
    print(f"  💬 {r.chat_response}")


# ═════════════════════════════════════════
# 主入口
# ═════════════════════════════════════════

async def main():
    print()
    print("╔══════════════════════════════════════════════════╗")
    print("║   角色系统 Character System — Full Demo          ║")
    print("║   双通道编排 · 多角色切换 · 动态Prompt · 随机性  ║")
    print("╚══════════════════════════════════════════════════╝")

    await demo_basic()
    await demo_chat_channel()
    await demo_task_channel()
    await demo_mixed_channel()
    await demo_randomness()
    await demo_prompt_breakdown()
    await demo_affection_mood()
    await demo_custom_character()
    await demo_integration_with_existing()

    # 清理
    import os
    if os.path.exists("./demo_characters.json"):
        os.remove("./demo_characters.json")

    print("\n" + "═" * 60)
    print("  ✅ 所有演示完成")
    print("═" * 60)

    print("""
┌─────────────────────────────────────────────────────────────────┐
│  核心设计总结                                                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. 三上下文分离                                                  │
│     ┌─────────────┐  ┌─────────────┐  ┌──────────────────┐     │
│     │ 角色上下文    │  │ 工具上下文    │  │ 用户输入上下文    │     │
│     │ (人设/心情/  │+│ (命令文档/   │+│ (当前轮输入/    │     │
│     │  好感度)     │  │  服务注册)   │  │  历史消息)       │     │
│     └─────────────┘  └─────────────┘  └──────────────────┘     │
│            ↓                ↓                    ↓               │
│        CHAT prompt       TASK prompt        USER messages       │
│                                                                 │
│  2. 双通道输出                                                   │
│     CHAT → 直接给用户（情感回复，省token）                        │
│     TASK → 后台执行 → 结果回填 → 角色化总结                      │
│                                                                 │
│  3. 全局共享 + 切换恢复                                          │
│     所有角色存于 CharacterManager (单例)                          │
│     切换 = 保存旧状态 + 恢复新状态                                │
│     每个角色独立消息历史                                         │
│                                                                 │
│  4. 随机性增强                                                   │
│     每次构建 prompt 时随机抽取:                                   │
│     - 2-3 个语气词                                               │
│     - 1-2 个动作描写                                             │
│     - 1 个情感形容词                                             │
│     - 1 个口头禅                                                 │
│     → 同一输入每次回复不同                                       │
│                                                                 │
│  5. Token 优化                                                   │
│     CHAT 模式: 仅角色人设 + 10条记忆 + 随机词 ≈ 200-400 tokens  │
│     TASK 模式: 仅工具文档 + 任务描述 ≈ 300-500 tokens           │
│     MIXED 模式: 两者合并 ≈ 500-800 tokens                       │
│     远比全量注入所有上下文节省                                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
    """)


if __name__ == "__main__":
    asyncio.run(main())