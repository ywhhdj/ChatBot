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
