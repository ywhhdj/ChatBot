import asyncio
import os
import sys
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src_py'))

async def test_connection():
    """测试QQ机器人连接"""
    from src_py.modules.services.qqbot.client import QQBotClient
    bot = QQBotClient(
        appid="YOUR_APPID",
        secret="YOUR_SECRET"
    )
    print("测试WebSocket连接...")
    try:
        await bot.start()
        print("✅ WebSocket连接成功")
        try:
            info = await bot.get_self_info()
            print(f"✅ 机器人信息: {info}")
        except Exception as e:
            print(f"❌ 获取信息失败: {e}")
        # 等待一段时间观察事件
        print("等待事件中... (5秒)")
        await asyncio.sleep(5)
        
    except Exception as e:
        print(f"❌ 连接失败: {e}")
    finally:
        await bot.close()