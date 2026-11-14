import { markRaw } from "vue";

/**
 * 展示层预设。
 * 模型清单、参数与状态的权威来源是 provider API（controllers/providers.py），
 * 这里的离线描述仅按 resources/configs/providers/models/*.json 提炼，
 * 用于接口未就绪时的骨架展示，绝不参与切换/下载请求。
 */

export const CAPABILITY_PRESETS: Record<Model.Capability, Model.CapabilityPreset> = markRaw({
  llm: {
    capability: "llm",
    title: "大模型 · 心智",
    subtitle: "对话与推理",
    icon: "chip",
    intro: "选择寄宿于这台终端的心智。温度与上限，会改变她说话的方式……",
    tags: ["对话", "推理", "工具意图"],
  },
  tts: {
    capability: "tts",
    title: "语音合成 · 声线",
    subtitle: "Text to Speech",
    icon: "volume",
    intro: "为她挑一副嗓音吧。音色、语速与格式，都在这里定下。",
    tags: ["声线", "语速", "音频格式"],
  },
  asr: {
    capability: "asr",
    title: "语音识别 · 倾听",
    subtitle: "Speech to Text",
    icon: "microphone",
    intro: "让她听清你说的话。本地模型需要先唤醒，才能开始聆听。",
    tags: ["本地模型", "语言", "束搜索"],
  },
  ocr: {
    capability: "ocr",
    title: "文字识别 · 凝视",
    subtitle: "Optical Character Recognition",
    icon: "text",
    intro: "把画面里的文字读出来。识别语言与模型文件，由这里决定。",
    tags: ["本地模型", "视觉", "语言"],
  },
  embedding: {
    capability: "embedding",
    title: "向量模型 · 记忆",
    subtitle: "Embedding",
    icon: "box",
    intro: "记忆要变成可被找回的形状。归一化与批处理，交给这里。",
    tags: ["向量", "归一化", "批处理"],
  },
  image: {
    capability: "image",
    title: "图像模型 · 描绘",
    subtitle: "Image Generation",
    icon: "background",
    intro: "让她把想象画成画面。尺寸、格式与提示词，在此落笔。",
    tags: ["图像", "尺寸", "工作流"],
  },
});

/** 参数 key → 中文标签。模型描述自带 label 时优先用描述里的。 */
export const FIELD_LABELS: Record<string, string> = markRaw({
  api_key: "API Key",
  access_token: "访问令牌",
  organization: "组织 ID",
  temperature: "温度",
  top_p: "Top P",
  max_tokens: "最大 token",
  num_ctx: "上下文窗口",
  presence_penalty: "存在惩罚",
  frequency_penalty: "频率惩罚",
  voice: "音色",
  voice_id: "音色 ID",
  voice_name: "音色名称",
  speaker_id: "说话人 ID",
  model_uuid: "模型 UUID",
  speaker_uuid: "说话人 UUID",
  response_format: "响应格式",
  output_format: "输出格式",
  audio_format: "音频格式",
  audio_encoding: "音频编码",
  encoding: "编码",
  speed: "语速",
  speed_factor: "语速系数",
  length: "时长系数",
  language: "识别语言",
  language_code: "语言代码",
  lang: "语言",
  languages: "语言列表",
  prompt_language: "参考文本语言",
  text_language: "合成文本语言",
  ref_audio_path: "参考音频路径",
  beam_size: "束搜索宽度",
  model_size: "模型规格",
  model_path: "模型目录",
  device: "计算设备",
  thread_pool_size: "线程池大小",
  normalize: "L2 归一化",
  batch_size: "批处理大小",
  prompt: "提示词",
  negative_prompt: "反向提示词",
  n: "生成数量",
  size: "画面尺寸",
  aspect_ratio: "宽高比",
  workflow_json: "工作流 JSON",
  client_id: "客户端 ID",
  model: "请求模型",
  model_id: "请求模型 ID",
  text: "合成文本",
});

export const TAG_LABELS: Record<string, string> = markRaw({
  cloud: "云端",
  local: "本地",
  paid: "付费",
  free: "免费",
  llm: "大模型",
  text: "文本",
  audio: "音频",
  tts: "语音合成",
  asr: "语音识别",
  ocr: "文字识别",
  vision: "视觉",
  embedding: "向量",
  image: "图像",
  workflow: "工作流",
  multilingual: "多语言",
});

export const SCOPE_LABELS: Record<Model.Scope, string> = markRaw({
  init: "初始化",
  request: "每次请求",
  unknown: "通用",
});

/** 端点/连接字段：后端 switch 白名单不接受，前端只读展示、绝不提交。 */
export const READONLY_ENDPOINT_KEYS: readonly string[] = markRaw([
  "base_url",
  "chat_path",
  "speech_path",
  "image_path",
  "prompt_path",
  "auth",
  "headers",
  "transport",
  "protocol",
  "runtime",
  "model_dir",
  "timeout",
  "max_retries",
  "download",
]);

/** 凭据字段识别：不回显、不缓存、不写 localStorage、不进通知与日志。 */
const SECRET_PATTERN = /(api[_-]?key|access[_-]?token|secret|password|authorization|credential|token|user[_-]?id)/i;
const MASK_PATTERN = /^\*+$|^\*+[^*]+\*+$/;

export function isSecretKey(key: string): boolean {
  return SECRET_PATTERN.test(key);
}

export function isMaskedValue(value: unknown): boolean {
  return typeof value === "string" && value.length > 0 && MASK_PATTERN.test(value);
}

export function tagLabel(tag: string): string {
  return TAG_LABELS[tag] || tag;
}

export function fieldLabel(key: string): string {
  return FIELD_LABELS[key] || key;
}

/** provider 图标：只使用 Icon.vue 内置图标，避免伪造资源路径 */
export function providerIcon(name: string): UI.IconType {
  if (name.includes("deepseek")) return "deepseek";
  if (name.includes("openai") || name.includes("chatgpt")) return "chatgpt";
  if (name.includes("sound") || name.includes("tts") || name.includes("voice")) return "volume";
  if (name.includes("asr") || name.includes("whisper")) return "microphone";
  if (name.includes("ocr") || name.includes("paddle")) return "text";
  if (name.includes("image") || name.includes("comfy")) return "background";
  if (name.includes("box") || name.includes("embedding") || name.includes("sentence")) return "box";
  return "chip";
}

/**
 * 离线模型描述骨架。
 * 来源：resources/configs/providers/models/{llm,tts,asr,ocr,embedding,images}.json
 * 只保留展示需要的 name / label / tags / deployment / models / params keys。
 */
export const OFFLINE_DESCRIPTIONS: Record<Model.Capability, Model.OfflineDescription> = markRaw({
  llm: {
    providers: [
      { name: "openai", label: "OpenAI", tags: ["cloud", "paid", "text"], deployment: "cloud", models: [{ id: "gpt-5.4", label: "GPT-5.4" }, { id: "gpt-5.4-mini", label: "GPT-5.4 Mini" }], params: ["temperature", "max_tokens"] },
      { name: "deepseek", label: "DeepSeek", tags: ["cloud", "paid", "text"], deployment: "cloud", models: [{ id: "deepseek-chat", label: "DeepSeek Chat" }, { id: "deepseek-reasoner", label: "DeepSeek Reasoner" }], params: ["temperature", "max_tokens"] },
      { name: "qwen", label: "Qwen (百炼)", tags: ["cloud", "paid", "text"], deployment: "cloud", models: [{ id: "qwen-max", label: "Qwen Max" }, { id: "qwen-plus", label: "Qwen Plus" }, { id: "qwen-turbo", label: "Qwen Turbo" }], params: ["temperature", "max_tokens"] },
      { name: "kimi", label: "Moonshot Kimi", tags: ["cloud", "paid", "text"], deployment: "cloud", models: [{ id: "kimi-k2.5", label: "Kimi K2.5" }, { id: "moonshot-v1-128k", label: "Moonshot 128K" }], params: ["temperature", "max_tokens"] },
      { name: "anthropic", label: "Anthropic Claude", tags: ["cloud", "paid", "text"], deployment: "cloud", models: [{ id: "claude-sonnet-4-5-20250929", label: "Claude Sonnet 4.5" }, { id: "claude-haiku-4-5-20251001", label: "Claude Haiku 4.5" }], params: ["max_tokens", "temperature"] },
      { name: "gemini", label: "Google Gemini", tags: ["cloud", "paid", "text"], deployment: "cloud", models: [{ id: "gemini-3.1-pro", label: "Gemini 3.1 Pro" }, { id: "gemini-3.1-flash", label: "Gemini 3.1 Flash" }], params: ["temperature", "max_tokens"] },
      { name: "ollama", label: "Ollama (本地)", tags: ["local", "free", "text"], deployment: "local", models: [], params: ["temperature", "num_ctx"] },
    ],
  },
  tts: {
    providers: [
      { name: "openai-tts", label: "OpenAI TTS", tags: ["cloud", "paid", "audio"], deployment: "cloud", models: [{ id: "gpt-4o-mini-tts", label: "GPT-4o Mini TTS" }, { id: "tts-1", label: "TTS-1" }, { id: "tts-1-hd", label: "TTS-1 HD" }], params: ["voice", "response_format", "speed"] },
      { name: "elevenlabs", label: "ElevenLabs", tags: ["cloud", "paid", "audio"], deployment: "cloud", models: [{ id: "eleven_multilingual_v2", label: "Multilingual v2" }, { id: "eleven_turbo_v2_5", label: "Turbo v2.5" }], params: ["voice_id", "output_format", "model_id"] },
      { name: "azure-tts", label: "Azure TTS", tags: ["cloud", "paid", "audio"], deployment: "cloud", models: [{ id: "azure-neural", label: "Azure Neural TTS" }], params: ["voice_name", "language", "output_format"] },
      { name: "google-tts", label: "Google Cloud TTS", tags: ["cloud", "paid", "audio"], deployment: "cloud", models: [{ id: "google-neural2", label: "Neural2" }, { id: "google-chirp3-hd", label: "Chirp 3 HD" }], params: ["voice_name", "language_code", "audio_encoding"] },
      { name: "bv2", label: "BV2 (本地)", tags: ["local", "free", "audio"], deployment: "local", models: [{ id: "bv2", label: "BV2" }], params: ["speaker_id", "audio_format", "lang", "length"] },
      { name: "gptsovits", label: "GPT-SoVITS (本地)", tags: ["local", "free", "audio"], deployment: "local", models: [{ id: "gptsovits", label: "GPT-SoVITS" }], params: ["prompt_language", "text_language", "speed_factor"] },
      { name: "vits", label: "VITS (本地)", tags: ["local", "free", "audio"], deployment: "local", models: [{ id: "vits", label: "VITS" }], params: ["ref_audio_path", "prompt_language", "text_language"] },
    ],
  },
  asr: {
    providers: [
      { name: "whisper", label: "Whisper (本地)", tags: ["local", "free", "audio"], deployment: "local", models: [{ id: "base", label: "Whisper Base" }, { id: "small", label: "Whisper Small" }, { id: "medium", label: "Whisper Medium" }], params: ["language", "beam_size", "model_size"] },
    ],
  },
  ocr: {
    providers: [
      { name: "paddle", label: "PaddleOCR (本地)", tags: ["local", "free", "vision"], deployment: "local", models: [{ id: "ppocr", label: "PP-OCR" }], params: [] },
      { name: "tesseract", label: "Tesseract (本地)", tags: ["local", "free", "vision"], deployment: "local", models: [{ id: "tesseract", label: "Tesseract" }], params: ["lang"] },
      { name: "easy", label: "EasyOCR (本地)", tags: ["local", "free", "vision"], deployment: "local", models: [{ id: "easy", label: "EasyOCR" }], params: ["languages"] },
      { name: "umi", label: "UmiOCR (本地)", tags: ["local", "free", "vision"], deployment: "local", models: [{ id: "umi", label: "UmiOCR" }], params: [] },
    ],
  },
  embedding: {
    providers: [
      { name: "sentence", label: "Sentence ONNX", tags: ["local", "free", "text"], deployment: "local", models: [{ id: "all-MiniLM-L6-v2", label: "All-MiniLM-L6-v2" }, { id: "bge-small-zh-v1.5", label: "BGE Small ZH v1.5" }], params: ["model_path", "device", "thread_pool_size", "normalize", "batch_size"] },
      { name: "openai", label: "OpenAI", tags: ["cloud", "paid", "text"], deployment: "cloud", models: [{ id: "text-embedding-3-small", label: "text-embedding-3-small" }, { id: "text-embedding-3-large", label: "text-embedding-3-large" }, { id: "text-embedding-ada-002", label: "text-embedding-ada-002" }], params: ["organization", "normalize", "batch_size"] },
      { name: "ollama", label: "Ollama", tags: ["local", "free", "text"], deployment: "local", models: [{ id: "nomic-embed-text", label: "Nomic Embed Text" }, { id: "mxbai-embed-large", label: "MXBai Embed Large" }, { id: "bge-m3", label: "BGE-M3" }], params: ["normalize", "batch_size"] },
    ],
  },
  image: {
    providers: [
      { name: "openai-image", label: "OpenAI 图像", tags: ["cloud", "paid", "vision"], deployment: "cloud", models: [{ id: "gpt-image-2", label: "GPT Image 2" }, { id: "gpt-image-1", label: "GPT Image 1" }], params: ["prompt", "n", "size", "response_format"] },
      { name: "qwen-image", label: "Qwen 图像 (通义万相)", tags: ["cloud", "paid", "vision"], deployment: "cloud", models: [{ id: "qwen-image-3.0-pro", label: "Qwen Image 3.0 Pro" }, { id: "qwen-image-2.1", label: "Qwen Image 2.1" }], params: ["prompt", "n", "size", "response_format"] },
      { name: "stability", label: "Stability AI", tags: ["cloud", "paid", "vision"], deployment: "cloud", models: [{ id: "sd3.5-large", label: "SD 3.5 Large" }, { id: "stable-image-ultra", label: "Stable Image Ultra" }], params: ["prompt", "aspect_ratio", "output_format", "negative_prompt"] },
      { name: "comfyui-local", label: "ComfyUI (本地)", tags: ["local", "free", "workflow"], deployment: "local", models: [{ id: "comfyui-workflow", label: "ComfyUI 工作流" }], params: [] },
    ],
  },
});
