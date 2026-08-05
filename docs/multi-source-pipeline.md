# 多数据源到 LLM 的全流程

## 总览

系统支持三类输入进入统一链路：

1. 用户直接文本输入
2. 语音输入（ASR）
3. OCR 文本输入（图片/屏幕识别后的文本）

统一输出路径：

- LLM 流式文本
- TTS 流式音频
- Live2D 口型驱动（可选）

## 入口

`ChatPipeline` 新增三类入口：

- `handle_text_turn(...)`
- `handle_audio_turn(...)`
- `handle_ocr_turn(...)`

其中：

- 语音输入先走 ASR，再进入统一 `LLM + TTS` 主流程。
- 文本/OCR 输入直接进入统一 `LLM + TTS` 主流程。

## 统一主流程

内部统一函数：`_run_llm_tts_turn(...)`

1. `ContextManager.add_user(...)` 记录输入（带 source 标记）
2. `ContextManager.build_message(...)` 组装 prompt（短期缓存 + 长期检索）
3. LLM 流式返回 delta
4. 按句切分后调用 TTS 生成音频 chunk
5. 通过 hook 推送：
   - `on_text_delta`
   - `on_audio_chunk`
   - `on_final_text`
6. `ContextManager.add_assistant(...)` 写回回答并落库

## Manager 编排

`PipelineManager` 对外提供：

- `handle_audio_turn(...)`
- `handle_text_turn(...)`
- `handle_ocr_turn(...)`

由 `TaskManager` 调度执行，保持接口一致。

## source 标记

`LLMManager.process_message_stream(user_input, source=...)` 中 `source` 已进入记忆写回：

- `asr`
- `text`
- `ocr`
- 也可扩展为 `mcp`、`system_event` 等

## Live2D 与音频联动

`ui/desktop/qr_brige/chat_pipeline_service.py`：

- 接收 TTS chunk
- 解码为 PCM
- 将 PCM 推给 `Live2D.put_audio_chunk(...)`
- 实现口型与音频同步

## 可扩展点

- OCR 适配器：在 `pipeline/adapters` 增加 OCR Adapter 后，直接接 `handle_ocr_turn(...)`。
- 多模态输入：可在 source 层继续增加 `vision`、`document` 等类型。
- 记忆策略：可按 source 设定不同初始 `importance` 与衰减率。
