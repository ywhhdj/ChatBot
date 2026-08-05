
import asyncio
import os
import sys



project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

if __name__ == "__main__":
    # 创建增强版路由器
    from modules.routes.intent import IntentRouter
    router = IntentRouter()
    
    # 测试用例
    test_inputs = [
        "帮我打开百度搜索",
        "今天心情不太好",
        "播放一首歌",
        "明天天气怎么样",
        "翻译这个句子",
        "我好想你啊",
        "计算一下123 * 456",
        "随便聊聊吧"
    ]
    
    for test_input in test_inputs:
        decision = asyncio.run(router.route(test_input))
        print(f"\n输入: {test_input}")
        print(f"决策: {decision.route_type.value}")
        print(f"置信度: {decision.confidence:.2f}")
        print(f"理由: {decision.reason}")
        if decision.suggested_services:
            print(f"建议服务: {decision.suggested_services}")
    
    # 打印统计信息
    print("\n=== 统计信息 ===")
    stats = router.get_stats()
    for key, value in stats.items():
        print(f"{key}: {value}")
