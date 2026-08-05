# ChatBot 架构梳理与职责规划

## 目标与边界
目标是把职责拆分清晰，减少跨层调用与重复实现，让链路更容易扩展：
- 输入链路：`ASR/文本输入 -> LLM -> TTS -> Live2D`
- 视觉链路：`图片/屏幕 -> OCR -> LLM`
- 事件驱动：统一通过 `EventEmitter` 触发服务或模型调用
- UI 与后端通过 API 或事件解耦

## 核心链路
1. 语音输入：ASR 将音频转文本  
2. LLM 输出文本（支持流式）  
3. TTS 将文本转音频（支持流式）  
4. Live2D 根据音素/能量驱动表情  

## 模块职责划分

### Core
负责基础设施、配置、线程与通用工具：
- `src/core/config.py`：统一配置入口
- `src/core/configuration/*`：各模块配置
- `src/core/decorator.py`：单例/重试等
- `src/core/thread.py`：线程封装

### Pipeline（模型侧）
负责模型适配器与推理逻辑，不关心服务与 UI：
- `src/pipeline/base.py`：模型适配器抽象
- `src/pipeline/llm/adapter.py`：LLM 适配器
- `src/pipeline/tts/adapter.py`：TTS 适配器
- `src/pipeline/asr/adapter.py`：ASR 适配器（待补）
- `src/pipeline/ocr/adapter.py`：OCR 适配器（待补）
- `src/pipeline/chat.py`：串联 ASR/LLM/TTS 的流式对话流水线

### Managers（流程编排侧）
负责管理模型与服务的生命周期、调度、任务与线程：
- `src/manager/managers/taskManager.py`：任务调度与执行器
- `src/manager/managers/serviceManager.py`：服务生命周期管理
- `src/manager/managers/pipelineManager.py`：统一调用入口
- `src/manager/manager.py`：系统入口（启动/关闭）

### Services（业务侧）
负责对外部系统、Live2D、OBS、Browser 等的接入和控制：
- `src/services/*`

### Event（事件驱动）
负责事件注册与派发，把 UI/服务/模型解耦：
- `src/event/Emitter.py`

## 角色与职责建议
- `Pipeline`：纯算法/模型调用，不涉及线程或生命周期。
- `Manager`：生命周期与调度，提供对外接口。
- `Service`：外部系统能力封装，接收任务，不处理模型逻辑。
- `Event`：解耦与异步执行通道，统一入口。

## 关键建议与落地
1. **ChatPipeline 唯一化**  
   只保留 `src/pipeline/chat.py` 作为唯一实现，管理侧仅引用。

2. **模型 Provider 工厂化**  
   `src/pipeline/provider.py` 统一创建适配器，配置读取统一入口。

3. **Manager 只负责调度**  
   不处理模型实现细节。`PipelineManager` 只调用已有接口，负责聚合。

4. **TaskManager 稳定性修复**  
   保证任务队列、计数、异步结果获取正确。

5. **ASR/OCR 预留接口**  
   先补全抽象与报错提示，便于后续补模型。

## 现有问题与修复摘要
- `LLMProviderFactory` 缺失导致无法初始化 LLM。  
  已补回并统一在 `LLMManager` 初始化。
- `PipelineManager.predict` 未等待任务完成，且错误引用未定义变量。  
  已修复为等待完成并返回真实结果。
- `TaskManager` 异步结果获取错误（对 `asyncio.Task` 误用 `result()`）。  
  已修复为直接 `await task`。
- `TaskManager` 执行器任务计数未初始化。  
  已修复初始化为 `0`。
- `ASRManager` 未初始化 provider，调用即崩。  
  已补充 `set_provider` 与更明确报错。

## 可扩展结构建议
```
src/
  pipeline/
    adapters/       # ASR/LLM/TTS/OCR 适配器
    flows/          # ChatPipeline 等流程
  managers/
    model_manager.py
    service_manager.py
  services/
    live2d/
    obs/
```

## 下一步建议
- 补齐 `ASR/OCR` 适配器并在配置里声明模型与 API。
- UI 与后端通过 WebSocket 或 EventEmitter 对接，实现实时流式展示。
