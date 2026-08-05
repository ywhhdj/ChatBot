# import threading
# from src.neroSystem.core.mediapipeLandmarker import run_face_debug_window

import sys
import os
import time



# Add the project root to Python path to allow imports
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# if __name__ == "__main__":
    # try:
    #     from src.services.live2d.components import EnhancedDialogueComponent
    #     from src.utils import util
    #     from src import const
    #     model_path=util.normpath(const.RESOURCES_DIRECTORY, "models", "live2d/肥牛/hiyori_pro_mic.model3.json")
    #     face_model_full_path = util.normpath(
    #         const.RESOURCES_DIRECTORY, "models", "mediapipe/face_landmarker.task"
    #     )
    #     # from src.services.live2d.views import Live2DView
    #     from PyQt5.QtWidgets import QApplication
    #     import sys
    #     app = QApplication(sys.argv)
    #     # live2d = Live2DView(
    #     #     model_path=model_path,
    #     #     window_size=(800, 600),
    #     #     is_face_detected=False,
    #     #     mediaPipeFace_model_path=face_model_full_path,
    #     # )
    #     # live2d.init()
    #     # live2d.start()
    #     dialogue = EnhancedDialogueComponent(
    #         text_speed=30,
    #         max_width=1000
    #     )

    #     # 设置对话组件位置
    #     dialogue.move(500, 1200)
    #     dialogue.show()

    #     # 流式显示AI回复
    #     # def ai_response_generator():
    #     #     """模拟AI流式回复"""
    #     #     response = "这是一个AI的流式回复示例，文字会逐个显示出来..."
    #     #     for i in range(0, len(response), 2):
    #     #         yield response[i:i+2]
    #     #         time.sleep(0.05)  # 模拟网络延迟

    #     # 方法1：使用生成器流式显示
    #     dialogue.display_text("这是一个AI的流式回复示例，文字会逐个显示出来...")


    #     # # 方法3：立即显示文本
    #     # dialogue.display_text("立即显示的内容", instant=True)

    #     # 自定义样式
    #     # dialogue.set_text_color("#6DBADE")
    #     # dialogue.set_background_color("rgba(30, 30, 30)", opacity=0.9)
    #     sys.exit(app.exec_())
    # except KeyboardInterrupt:
    #     sys.exit(0)
import webview
class BackendAPI:
    """这个类的所有非私有方法都将被暴露给前端 JavaScript 调用。"""

    def process_data(self, user_input):
        """一个可以被前端调用的方法，对输入数据进行处理并返回。"""
        if not user_input:
            return {"status": "error", "message": "输入不能为空！"}
        
        # 这里是你的业务逻辑，可以是任何 Python 代码
        processed = f"Python 后端已处理: '{user_input}'，长度是 {len(user_input)}。"
        return {"status": "success", "message": processed}
    
    def perform_calculation(self, a, b):
        """另一个示例方法，演示如何处理数字计算。"""
        try:
            result = float(a) + float(b)
            return {"status": "success", "result": result}
        except ValueError:
            return {"status": "error", "message": "请输入有效的数字。"}

# --- 前端：UI 和交互逻辑，直接嵌入在 Python 字符串中 ---
FRONTEND_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>PyWebview 交互示例</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; }
        .card { background-color: #f8f9fa; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        button { background-color: #007bff; color: white; border: none; padding: 10px 15px; border-radius: 5px; cursor: pointer; }
        button:hover { background-color: #0056b3; }
        input, .calc-input { padding: 8px; margin-right: 10px; border: 1px solid #ced4da; border-radius: 4px; }
        .result-area { margin-top: 15px; padding: 10px; background-color: #e9ecef; border-radius: 4px; }
        .error { color: #dc3545; }
        .success { color: #28a745; }
    </style>
</head>
<body>

    <div class="card">
        <h3>📝 文本处理器</h3>
        <input type="text" id="userInput" placeholder="输入一些文本...">
        <button id="processBtn">提交处理</button>
        <div id="processResult" class="result-area">等待处理...</div>
    </div>

    <div class="card">
        <h3>🧮 加法计算器</h3>
        <input type="number" id="numA" class="calc-input" placeholder="数字 A">
        <input type="number" id="numB" class="calc-input" placeholder="数字 B">
        <button id="calcBtn">计算</button>
        <div id="calcResult" class="result-area">等待计算...</div>
    </div>

    <div class="card">
        <h3>🔔 调用前端</h3>
        <button id="callPythonBtn">调用 Python 并更新前端</button>
        <div id="callResult" class="result-area"></div>
    </div>

    <script>
        // 确保 pywebview API 完全加载后再调用
        window.addEventListener('pywebviewready', function() {
            console.log('pywebview is ready!');

            // 1. 调用 process_data 方法
            document.getElementById('processBtn').addEventListener('click', function() {
                const inputVal = document.getElementById('userInput').value;
                const resultDiv = document.getElementById('processResult');
                resultDiv.innerHTML = '<i>处理中...</i>';
                
                // 调用 Python 方法，它会返回一个 Promise
                window.pywebview.api.process_data(inputVal).then(response => {
                    if (response.status === 'success') {
                        resultDiv.innerHTML = `<span class="success">✅ ${response.message}</span>`;
                    } else {
                        resultDiv.innerHTML = `<span class="error">❌ ${response.message}</span>`;
                    }
                }).catch(err => {
                    resultDiv.innerHTML = `<span class="error">发生错误: ${err.message}</span>`;
                });
            });

            // 2. 调用 perform_calculation 方法
            document.getElementById('calcBtn').addEventListener('click', function() {
                const a = document.getElementById('numA').value;
                const b = document.getElementById('numB').value;
                const resultDiv = document.getElementById('calcResult');
                resultDiv.innerHTML = '<i>计算中...</i>';
                
                window.pywebview.api.perform_calculation(a, b).then(response => {
                    if (response.status === 'success') {
                        resultDiv.innerHTML = `<span class="success">✅ 计算结果: ${response.result}</span>`;
                    } else {
                        resultDiv.innerHTML = `<span class="error">❌ ${response.message}</span>`;
                    }
                }).catch(err => {
                    resultDiv.innerHTML = `<span class="error">发生错误: ${err.message}</span>`;
                });
            });

            // 3. 演示 Python 主动调用前端（在请求中完成）
            document.getElementById('callPythonBtn').addEventListener('click', function() {
                const resultDiv = document.getElementById('callResult');
                resultDiv.innerHTML = '<i>收到请求，正在调用后端...</i>';
                
                // 调用 Python 方法
                window.pywebview.api.perform_calculation(10, 20).then(response => {
                    if (response.status === 'success') {
                        resultDiv.innerHTML = `<span class="success">✨ 后端计算结果为 ${response.result}，现在由前端更新这条消息。</span>`;
                    } else {
                        resultDiv.innerHTML = `<span class="error">后端返回错误: ${response.message}</span>`;
                    }
                });
            });
        });
    </script>
</body>
</html>
"""

if __name__ == '__main__':
    # 创建 API 实例
    api = BackendAPI()
    # 创建窗口，将 API 实例传递给 js_api 参数
    webview.create_window('PyWebview 双向通信示例', html=FRONTEND_HTML, js_api=api)
    # 启动应用
    webview.start()

