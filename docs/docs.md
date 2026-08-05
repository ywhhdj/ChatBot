## 系统总体架构
- **线程**
  - **主线程**
    - 负责启动 FastAPI / WebSocket 服务器
    - UI 刷新,渲染
    - Live2D 模型推理
    - 与 TaskManager 交互，提交任务（如启动/停止服务、模型推理）
  - **后台线程**
    - TaskManager 事件循环，处理同步和同步任务
    - LLM 模型推理任务
    - TTS 任务
    - 音频处理任务
    - OCR 识别任务
    - MediaPipe 人脸检测任务
    - 音频处理任务

## 启动流程

1. 启动 Python 主进程：`python main.py`
2. `main.py`：
  - 调用 `system_manager.start_background_logic()` 启动 TaskManager 事件循环
  - 注册并启动后台服务：
    - `service_manager.register_service(ServiceName.Live2D, Live2DService(...))`
    - `service_manager.register_service(ServiceName.OBS, OBSService(...))`
    - `service_manager.start()`
  - 启动桌面 UI：`DesktopApp.run()`
3. FastAPI / WebSocket 由 `webapp` 模块启动（可通过 `uvicorn`）

## 事件流与交互流程

### 1. Web UI <-> 后端 WebSocket

- Web UI 建立连接：
  - 前端：`new WebSockets(VITE_WS_URL, ...)`
  - 发送 JSON：
    ```json
    {
      "event": "connect",
      "payload": { "client_type": "web_ui" }
    }
    ```


---

### 三、结合流程，如何改造以实现 Live2D + OBS + UI 交互 & 美化 UI

下面是我建议的实际改造方向（可以按这几个子任务一步步落地）：

#### 1. 规范 WebSocket 协议 & 前后端对接

- **后端改造建议**
  - 在 `src/neroSystem/api/websocket.py` 中：
    - 扩展 `WebSocketEvent`，增加：
      - `live2d_set_model`, `live2d_set_opacity`, `live2d_set_scale` ...
      - `obs_connect`, `obs_set_scene`, `obs_toggle_stream` 等。
    - `websocket_endpoint` 使用 `await websocket.send_json(response.to_json())`，并约定所有消息都是 JSON。
    - `handle_event` 中：
      - 解析 `event["event"]` 和 `event.get("payload", {})`。
      - 根据事件分发到不同 handler，例如：
        - `if event["event"] == "live2d.set_model":` -> 调用 `service_manager.get_service("Live2D").set_model_path(...)`
        - `if event["event"] == "obs.set_scene":` -> 调用 `obs_service.set_scene(...)`。
  - 在应用启动（比如 `main.py` 或 FastAPI 启动入口）中，**初始化并注册服务**：
    - 实例化 `Live2DService`（封装当前 `Live2D` 类）
    - 实例化 `OBSService`（封装当前 `OBSClient`）
    - 调用 `service_manager.register_service(ServiceName.Live2D, live2d_service)` 等。

- **前端改造建议**
  - 封装统一的 WebSocket 消息体：
  ```typescript
    type WSRequest = {
      event: string;
      payload?: any;
    };

    function sendWS(event: string, payload?: any) {
      webSocket.send(JSON.stringify({ event, payload }));
    }
  ```
    