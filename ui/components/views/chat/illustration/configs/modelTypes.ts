/**
 * Live2D / VTS 模型解析结果
 *
 * 诚实边界（见 FrontendPlan Step 10.0）：
 *  - `.moc3` 是编译后的二进制，ArtMesh 的 UV / 顶点 / draw order 都在里面；
 *    纯前端读 JSON **反解不出逐 ArtMesh 网格**，也不引入 Cubism Core（专有授权）。
 *  - 因此可解析的是「模型包的文件索引 + 纹理文件 + 部件显示名」，
 *    部件图的来源如实标注，绝不假装是从 moc3 反解出来的。
 */

export type ModelFormat = 'cubism2' | 'cubism3' | 'vts' | 'loose';

export type PartSource =
  /** Cubism 2.1：一个部件一张独立 PNG 文件 */
  | 'part-file'
  /** 合并图集：按 alpha 连通区域切出的候选部件 */
  | 'connected-component'
  /** 模型包里散落的 PNG，无索引可依 */
  | 'loose-file';

export interface ParsedPart {
  id: string;
  label: string;
  src: string;
  z: number;
  /** 语义分组（用于面板归类，不改写真实部件 ID） */
  group: string;
  /** 来源纹理文件名或图集名 */
  texture: string;
  source: PartSource;
  /** 来源不确定性说明，UI 必须展示 */
  note?: string;
  width?: number;
  height?: number;
}

export interface ParsedModelMeta {
  /** 模型包里存在 moc3（仅标记，不解析二进制） */
  hasMoc3: boolean;
  /** 存在 .vtube.json → VTube Studio 校准配置 */
  hasVtube: boolean;
  /** 存在 .cdi3.json → 可读的部件/参数显示名 */
  hasCdi3: boolean;
  modelJsonName: string;
  textureFiles: string[];
  /** cdi3.json 的 PartIds 显示名（可能为空） */
  partNames: string[];
}

export interface ParsedModel {
  format: ModelFormat;
  name: string;
  parts: ParsedPart[];
  warnings: string[];
  meta: ParsedModelMeta;
}

export const MODEL_LIMITS = {
  /** 单张图集最长边降采样上限（连通域检测用，原图裁切仍保清晰） */
  detectMaxEdge: 1024,
  maxRegions: 24,
  /** 忽略面积小于图集 0.15% 的碎块 */
  minRegionAreaRatio: 0.0015,
  alphaThreshold: 16,
  maxTextureBytes: 24 * 1024 * 1024,
  maxLayerCount: 30,
} as const;

/** 语义分组：只用于面板归类，按真实部件名/ID 关键字匹配，匹配不到归「其他」 */
export const PART_GROUPS: ReadonlyArray<{
  id: string;
  label: string;
  words: string[];
}> = [
  {
    id: 'background',
    label: '背景',
    words: ['back', 'bg', '背景', '後ろ', 'scene']
  },
  {
    id: 'body',
    label: '身体 / 服装',
    words: ['body', 'costume', 'cloth', 'dress', 'shirt', 'skirt', '服', '体', '胴']
  },
  {
    id: 'hair',
    label: '头发',
    words: ['hair', '髪', '发', '前髪', '後髪', 'side']
  },
  {
    id: 'face',
    label: '脸部',
    words: ['face', '顔', '脸', 'skin', 'head', 'neck', '首']
  },
  {
    id: 'eyebrow',
    label: '眉毛',
    words: ['brow', '眉', 'mayu']
  },
  {
    id: 'eyes',
    label: '眼睛',
    words: ['eye', '瞳', '目', 'pupil', 'iris', 'white', 'lash']
  },
  {
    id: 'mouth',
    label: '嘴巴',
    words: ['mouth', '口', 'lip', 'tooth', 'tongue']
  },
  {
    id: 'blush',
    label: '腮红',
    words: ['blush', 'cheek', '頬', '腮']
  },
  {
    id: 'other',
    label: '其他',
    words: []
  },
] as const;

export function guessGroup(label: string, id: string): string {
  const text = `${label} ${id}`.toLowerCase();
  for (const g of PART_GROUPS) {
    if (g.id === 'other') continue;
    if (g.words.some((w) => text.includes(w))) return g.label;
  }
  return '其他';
}
