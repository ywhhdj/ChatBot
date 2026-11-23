/**
 * 分层拼接立绘 —— 数据模型与数值刻度
 */
import type { ParsedModel, ParsedPart } from './modelTypes';

export { isSafeImageSrc, type ParsedModel } from '@/utils/asset';

/** 动态层 ID：默认分组用固定 key，模型解析出的层用真实 ID（uid） */
export type PartKey = string;

export interface PartOption {
  id: string;
  label: string;
  src: string;
  width?: number;
  height?: number;
}

/** 一个部件层：z 决定叠放顺序；group 只用于面板归类 */
export interface PartLayer {
  key: PartKey;
  label: string;
  z: number;
  options: PartOption[];
  activeId: string | null;
  visible: boolean;
  flipX: boolean;
  opacity: number;
  group?: string;
  source?: string;
  note?: string;
}

export interface StickerAsset {
  id: string;
  label: string;
  src: string;
  width?: number;
  height?: number;
}

/** x / y 为归一化坐标（0..1），整体缩放档与 resize 都不会让贴纸漂移 */
export interface StickerInstance {
  id: string;
  assetId: string;
  src: string;
  label: string;
  x: number;
  y: number;
  scale: number;
  rotation: number;
  flipX: boolean;
  opacity: number;
  z: number;
  behind: boolean;
  width?: number;
  height?: number;
}

export interface IllustrationGlobalState {
  scale: number;
  flipX: boolean;
  visible: boolean;
}

/** 模型来源元信息（只记录可解析的事实，不含 moc3 二进制内容） */
export interface ModelMetaLite {
  format: string;
  name: string;
  partCount: number;
  textureFiles: string[];
  warnings: string[];
  hasMoc3: boolean;
  hasVtube: boolean;
  hasCdi3: boolean;
  importedAt: number;
}

export interface IllustrationSnapshot {
  /** v2 支持动态层与模型元信息；parseSnapshotText 仍兼容 v1 */
  version: 1 | 2;
  layers: PartLayer[];
  stickerAssets: StickerAsset[];
  stickers: StickerInstance[];
  global: IllustrationGlobalState;
  modelMeta?: ModelMetaLite | null;
}

/** 空白画布的默认 7 组（参考图 UI），模型导入后会被真实层替换 */
export const PART_DEFS: ReadonlyArray<{ key: PartKey; label: string; z: number }> = [
  { key: 'background', label: '背景', z: 0 },
  { key: 'costume', label: '服装', z: 1 },
  { key: 'eyebrow', label: '眉毛', z: 2 },
  { key: 'eyes', label: '眼睛', z: 3 },
  { key: 'mouth', label: '嘴巴', z: 4 },
  { key: 'blush', label: '腮红', z: 5 },
  { key: 'other', label: '其他', z: 6 },
];

export const SCALE_STEPS: ReadonlyArray<number> = [1, 1.5, 2];

export const LIMITS = {
  stickerScaleMin: 0.2,
  stickerScaleMax: 4,
  rotationMin: -180,
  rotationMax: 180,
  opacityMin: 0.2,
  opacityMax: 1,
  positionMin: -0.1,
  positionMax: 1.1,
  maxStickerInstances: 24,
  maxStickerAssets: 60,
  maxOptionsPerLayer: 12,
  maxLayers: 30,
  maxFileBytes: 2 * 1024 * 1024,
  maxSerializedBytes: 8 * 1024 * 1024,
  stickerGridSize: 8,
  stickerBasePx: 96,
  dialogueReserveRatio: 0.26,
} as const;

export function clamp(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) return min;
  return Math.min(Math.max(value, min), max);
}

export function createEmptyLayers(): PartLayer[] {
  // 只创建结构，不预置任何候选素材（不伪造数据）
  return PART_DEFS.map((d) => ({
    key: d.key,
    label: d.label,
    z: d.z,
    options: [],
    activeId: null,
    visible: true,
    flipX: false,
    opacity: 1,
    group: '默认分组',
    source: 'blank',
  }));
}

/** 真实模型 → 动态层。每层一个真实部件，label / group / note 都来自解析结果 */
export function createLayersFromModel(model: ParsedModel): PartLayer[] {
  return model.parts.slice(0, LIMITS.maxLayers).map((part: ParsedPart) => ({
    key: part.id,
    label: part.label,
    z: part.z,
    options: [{ id: `${part.id}__0`, label: part.label, src: part.src, width: part.width, height: part.height }],
    activeId: `${part.id}__0`,
    visible: true,
    flipX: false,
    opacity: 1,
    group: part.group,
    source: part.source,
    note: part.note,
  }));
}

export function createDefaultGlobal(): AvatarGlobalState {
  return { scale: 1, flipX: false, visible: true };
}

let seq = 0;
export function uid(prefix: string): string {
  seq += 1;
  return `${prefix}_${Date.now().toString(36)}_${seq.toString(36)}`;
}

/** 按 z 稳定排序，供舞台与面板共用 */
export function sortedLayers(layers: ReadonlyArray<PartLayer>): PartLayer[] {
  return layers.slice().sort((a, b) => a.z - b.z || a.label.localeCompare(b.label));
}
