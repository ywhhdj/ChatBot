class AppEventType:

    class TaskSchedularEventType:
        START = "task_schedular.start"
        STOP = "task_schedular.stop"
    
    class ManagerEventType:
        WEB_SOCKET_START = "websocket.start"
        WEB_SOCKET_STOP = "websocket.stop"
        SERVICE_STOP = "service.stop"
        PIPELINE_STOP = "pipeline.stop"
        MEMORY_STOP = "memory.stop"
        PIPELINE_START = "pipeline.start"
        CHARACTER_STOP = "character.stop"
    
    class MainThreadDispatcherEventType:
        RUN_ON_MAIN_THREAD = "main_thread_dispatcher.run_on_main_thread"
        RUN_ASYNC_ON_MAIN_THREAD = "main_thread_dispatcher.run_async_on_main_thread"
        STOP = "main_thread_dispatcher.stop"

    class KeyboardEventType:
        KEYBOARD_START = "keyboard.press"
        KEYBOARD_STOP = "keyboard.stop"

class PptEventType:
    PPT_STOP = "ppt.stop"

class Live2DEventType: #用事件名: 方法名定义
    LIVE2D_START = "live2d.start"
    LIVE2D_DRAW = "live2d.draw"
    LIVE2D_AUDIO_PLAY = "live2d.put_audio"
    LIVE2D_STOP = "live2d.stop"
    LIVE2D_CLOSE = "live2d.close"
    LIVE2D_SET_MODEL="live2d.set_model_path"

class Live2DFaceEventType:
    LIVE2D_FACE_SET_FACE_ENABLED = "live2d.set_face_face_enabled"
    LIVE2D_FACE_SET_FACE_SOURCE = "live2d.set_face_source"
    LIVE2D_FACE_SET_FACE_FPS = "live2d.set_face_fps"

class LiveStreamEventType:
    LIVE_STREAM_ALIVE_START = "live_stream.alive_start"
    LIVE_STREAM_ALIVE_END = "live_stream.alive_end"
    LIVE_STREAM_FRAME = "live_stream.frame"

class ObsEventType:
    OBS_CONNECT = "obs.connect"             # 连接 OBS
    OBS_DISCONNECT = "obs.disconnect"       # 断开连接
    OBS_START_RECORD = "obs.start_rec"      # 开始录制
    OBS_STOP_RECORD = "obs.stop_rec"        # 停止录制
    OBS_SWITCH_SCENE = "obs.switch_scene"   # 切换场景
    OBS_TOGGLE_SOURCE = "obs.toggle_source" # 控制源显示/隐藏

class QQBotEventType:
    QQ_BOT_START = "qq_bot.start"
    QQ_BOT_STOP = "qq_bot.stop"
    QQ_BOT_C2C_MSG_CREATE = "qq_bot.c2c_msg_create"
    QQ_BOT_ON_FRIEND_ADDED = "qq_bot.on_friend_added"
    QQ_BOT_ON_GROUP_ADDED = "qq_bot.on_group_added"
    QQ_BOT_INFO = "qq_bot.info"

class PipelineEventType:
    LLM_TEXT_DELTA = "pipeline.text_delta"
    LLM_FINAL_TEXT = "pipeline.final_text"
    TTS_AUDIO_CHUNK = "pipeline.audio_chunk"
    TTS_FINAL_AUDIO = "pipeline.final_audio"
    LLM_TOOL_INTERRUPT = "pipeline.tool_interrupt"
    ERROR = "pipeline.error"
    OCR_TEXT = "pipeline.ocr_text"
    ASR_TEXT = "pipeline.asr_text"
    TASK_EXECUTED = "pipeline.task_executed"

class BrowserEventType:
    BROWSER_START = "browser.start"
    BROWSER_STOP = "browser.stop"
    BROWSER_OPEN_PAGE = "browser.open_page"

class ChatStreamEventType:
    """TD6：聊天流式事件（前端工具卡片 / phase 展示）。

    命名与 `PipelineEventType.*` 区分开：
    后者是管道内部事件（text_delta / audio_chunk 这类**数据**流），
    这里是**元信息**流（消息开始、phase 变化、工具开始/结束）。
    前端两类都订阅，但用途不同。
    """

    MESSAGE_START = "chat.message.start"
    PHASE = "chat.phase"
    TOOL_START = "chat.tool.start"
    TOOL_END = "chat.tool.end"
    MESSAGE_END = "chat.message.end"

class WebSocketEventType:
    CONNECT = "connect"
    PRIVATE = "private"
    HEARTBEAT = "heartbeat"
    RESULT = "result"
    CHAT = "chat"
    DOWNLOAD_MODEL = "download_model"
    GET_LOG = "get_log"
    RECORD_START = "record.start"
    RECORD_STOP = "record.stop"
    RECORD_CHUNK = "record.audio_chunk"
    GET_AUDIT_LOGS = "get_audit_logs"

class ToolEventType:
    TOOL_CALL_START   = "tool.call.start"      # 开始调用某个工具
    TOOL_CALL_RUNNING = "tool.call.running"     # 工具执行中（可携带进度）
    TOOL_CALL_SUCCESS = "tool.call.success"     # 工具执行成功
    TOOL_CALL_ERROR   = "tool.call.error"       # 工具执行失败
    TOOL_CALL_SKIPPED = "tool.call.skipped"     # 工具被跳过
    TOOL_CALL_FINISH  = "tool.call.finish"      # 一组工具全部结束（附带摘要）

class DownloadEventType:
    STARTED = "download_started"
    RUNNING = "download_running"
    COMPLETED = "download_completed"
    FAILED = "download_failed"
    ERROR = "download_error"

class CharacterEventType:
    MOOD_CHANGED = "character.mood_changed"