/**
 * 装扮配置的序列化 / 往返 / 导出 / 后端保存
 */
import { saveService } from '@/api/services/save';
import { downloadBlob } from '@/utils/asset';
import {
  LIMITS,
  PART_DEFS,
  clamp,
  isSafeImageSrc,
  type IllustrationSnapshot,
  type PartLayer,
  type PartOption,
  type StickerAsset,
  type StickerInstance,
} from './illustrationTypes';

const SECTION_KEY = 'avatar_appearance';
const PNG_WIDTH = 720;
const PNG_HEIGHT = 960;

export function buildSnapshot(input: {
  layers: PartLayer[];
  stickerAssets: StickerAsset[];
  stickers: StickerInstance[];
  global: IllustrationSnapshot['global'];
  modelMeta?: IllustrationSnapshot['modelMeta'];
}): IllustrationSnapshot {
  // 整体拷贝，避免把 Pinia 的响应式 Proxy 交给下载/请求层
  return JSON.parse(JSON.stringify({
    version: 2,
    layers: input.layers,
    stickerAssets: input.stickerAssets,
    stickers: input.stickers,
    global: input.global,
    modelMeta: input.modelMeta || null,
  }));
}

export function serializedSize(snapshot: IllustrationSnapshot): number {
  try {
    return new Blob([JSON.stringify(snapshot)]).size;
  } catch {
    return Number.POSITIVE_INFINITY;
  }
}

function dateTag(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}`;
}

export function exportJson(snapshot: IllustrationSnapshot): void {
  downloadBlob(
    new Blob([JSON.stringify(snapshot, null, 2)], { type: 'application/json;charset=utf-8' }),
    `立绘配置_${dateTag()}.json`
  );
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error('图片解码失败，无法合成'));
    img.src = src;
  });
}

/** 以 contain 方式把素材画进画布中央的立绘区域 */
function drawContain(
  ctx: CanvasRenderingContext2D,
  img: HTMLImageElement,
  box: { x: number; y: number; w: number; h: number },
  flipX: boolean,
  opacity: number
): void {
  const ratio = Math.min(box.w / img.naturalWidth, box.h / img.naturalHeight);
  const w = img.naturalWidth * ratio;
  const h = img.naturalHeight * ratio;
  const dx = box.x + (box.w - w) / 2;
  const dy = box.y + (box.h - h) / 2;
  ctx.save();
  ctx.globalAlpha = clamp(opacity, 0, 1);
  if (flipX) {
    // 与 DOM 的 scaleX(-1) 等价：以立绘区域水平中心为轴镜像
    ctx.translate(box.x + box.w / 2, 0);
    ctx.scale(-1, 1);
    ctx.translate(-(box.x + box.w / 2), 0);
  }
  ctx.drawImage(img, dx, dy, w, h);
  ctx.restore();
}

/**
 * 导出合成 PNG：按 z 顺序还原层与贴纸。
 * 所有素材都是 data: 位图（或同源 URL），不会污染 canvas；
 * 绘制前再次断言协议，导入的恶意 src 在这里也会被挡住。
 */
export async function exportPng(snapshot: IllustrationSnapshot): Promise<void> {
  const canvas = document.createElement('canvas');
  canvas.width = PNG_WIDTH;
  canvas.height = PNG_HEIGHT;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('当前浏览器不支持画布导出');

  // 立绘区域：底部为对话框预留，避免导出图把人物压到底边
  const stageBox = {
    x: PNG_WIDTH * 0.08,
    y: PNG_HEIGHT * 0.04,
    w: PNG_WIDTH * 0.84,
    h: PNG_HEIGHT * (1 - LIMITS.dialogueReserveRatio) - PNG_HEIGHT * 0.04,
  };

  type DrawItem = { z: number; run: () => void };
  const items: DrawItem[] = [];
  const layerImages = await Promise.all(
    snapshot.layers.map(async (layer) => {
      const option = layer.options.find((o) => o.id === layer.activeId);
      if (!layer.visible || !option || !isSafeImageSrc(option.src)) return null;
      const img = await loadImage(option.src);
      return {
        z: layer.z,
        img,
        flipX: layer.flipX,
        opacity: layer.opacity
      };
    })
  );
  layerImages.forEach((entry: any | null) => {
    if (!entry) return;
    items.push({
      z: entry.z,
      run: () => drawContain(ctx, entry.img, stageBox, entry.flipX, entry.opacity),
    });
  });

  for (const sticker of snapshot.stickers) {
    if (!isSafeImageSrc(sticker.src)) continue;
    const img = await loadImage(sticker.src);
    items.push({
      z: sticker.z,
      run: () => {
        const base = Math.min(stageBox.w, stageBox.h) * 0.32;
        const ratio = img.naturalHeight / Math.max(img.naturalWidth, 1);
        const h = base * ratio;
        const cx = stageBox.x + sticker.x * stageBox.w;
        const cy = stageBox.y + sticker.y * stageBox.h;
        const scale = clamp(sticker.scale, LIMITS.stickerScaleMin, LIMITS.stickerScaleMax);
        ctx.save();
        ctx.globalAlpha = clamp(sticker.opacity, 0, 1);
        ctx.translate(cx, cy);
        // 与 DOM 保持同一公式：scale(s*flip, s) rotate(r)，中心固定
        ctx.rotate((clamp(sticker.rotation, LIMITS.rotationMin, LIMITS.rotationMax) * Math.PI) / 180);
        ctx.scale(sticker.flipX ? -scale : scale, scale);
        ctx.drawImage(img, -base / 2, -h / 2, base, h);
        ctx.restore();
      },
    });
  }

  items.sort((a, b) => a.z - b.z).forEach((item) => item.run());

  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/png'));
  if (!blob) throw new Error('画布导出失败，请改用导出配置');
  downloadBlob(blob, `立绘合成_${dateTag()}.png`);
}

// ---------- 导入：五重校验，失败绝不覆盖现有编辑态 ----------

function isRecord(v: unknown): v is Record<string, any> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

function parseOption(raw: unknown): PartOption | null {
  if (!isRecord(raw) || !isSafeImageSrc(raw.src)) return null;
  return {
    id: String(raw.id || '').slice(0, 80),
    label: String(raw.label || '未命名').slice(0, 40),
    src: raw.src,
    width: Number.isFinite(raw.width) ? clamp(Number(raw.width), 1, 10000) : undefined,
    height: Number.isFinite(raw.height) ? clamp(Number(raw.height), 1, 10000) : undefined,
  };
}

export class ImportError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ImportError';
  }
}

function parseLayer(raw: unknown, fallback?: { key: string; label: string; z: number }): PartLayer {
  const l = isRecord(raw) ? raw : {};
  const options = (Array.isArray(l.options) ? l.options : [])
    .slice(0, LIMITS.maxOptionsPerLayer)
    .map(parseOption)
    .filter((o): o is PartOption => o !== null && Boolean(o.id));
  const activeId = typeof l.activeId === 'string' && options.some((o) => o.id === l.activeId)
    ? l.activeId
    : options[0]?.id || null;
  return {
    key: String(l.key || fallback?.key || '').slice(0, 80),
    label: String(l.label || fallback?.label || '部件').slice(0, 40),
    z: Number.isFinite(l.z) ? clamp(Number(l.z), 0, 1000) : (fallback?.z ?? 0),
    options,
    activeId,
    visible: l.visible !== false,
    flipX: Boolean(l.flipX),
    opacity: Number.isFinite(l.opacity) ? clamp(Number(l.opacity), LIMITS.opacityMin, LIMITS.opacityMax) : 1,
    group: typeof l.group === 'string' ? l.group.slice(0, 40) : undefined,
    source: typeof l.source === 'string' ? l.source.slice(0, 40) : undefined,
    note: typeof l.note === 'string' ? l.note.slice(0, 300) : undefined,
  };
}

/** 模型元信息只接受白名单字段，避免把任意对象带进 store */
function parseModelMeta(raw: unknown): IllustrationSnapshot['modelMeta'] {
  if (!isRecord(raw)) return null;
  return {
    format: String(raw.format || '').slice(0, 40),
    name: String(raw.name || '').slice(0, 60),
    partCount: Number.isFinite(raw.partCount) ? clamp(Number(raw.partCount), 0, 1000) : 0,
    textureFiles: (Array.isArray(raw.textureFiles) ? raw.textureFiles : [])
      .filter((x): x is string => typeof x === 'string').slice(0, 60).map((x) => x.slice(0, 120)),
    warnings: (Array.isArray(raw.warnings) ? raw.warnings : [])
      .filter((x): x is string => typeof x === 'string').slice(0, 20).map((x) => x.slice(0, 300)),
    hasMoc3: Boolean(raw.hasMoc3),
    hasVtube: Boolean(raw.hasVtube),
    hasCdi3: Boolean(raw.hasCdi3),
    importedAt: Number.isFinite(raw.importedAt) ? Number(raw.importedAt) : 0,
  };
}

export function parseSnapshotText(text: string): IllustrationSnapshot {
  let raw: unknown;
  try {
    raw = JSON.parse(text);
  } catch {
    throw new ImportError('不是有效的 JSON 文件');
  }
  if (!isRecord(raw) || (raw.version !== 1 && raw.version !== 2)) {
    throw new ImportError('配置版本不受支持（需要 version: 1 或 2）');
  }
  const version = raw.version as 1 | 2;
  if (!Array.isArray(raw.layers) || !Array.isArray(raw.stickerAssets) || !Array.isArray(raw.stickers)) {
    throw new ImportError('配置结构不完整');
  }
  if (raw.stickers.length > LIMITS.maxStickerInstances || raw.stickerAssets.length > LIMITS.maxStickerAssets) {
    throw new ImportError('配置中的素材或贴纸数量超过上限');
  }

  let layers: PartLayer[];
  if (version === 1) {
    // v1 固定 7 组：按 key 回填，缺失组补空层
    const byKey = new Map<string, unknown>((raw.layers as unknown[]).filter(isRecord).map((l) => [String(l.key), l]));
    layers = PART_DEFS.map((def) => parseLayer(byKey.get(def.key), def));
  } else {
    // v2 动态层：真实模型部件数量与名称都按配置还原
    layers = (raw.layers as unknown[])
      .slice(0, LIMITS.maxLayers)
      .map((l) => parseLayer(l))
      .filter((l) => Boolean(l.key));
    if (!layers.length) layers = PART_DEFS.map((def) => parseLayer(null, def));
  }

  const stickerAssets: StickerAsset[] = (raw.stickerAssets as unknown[])
    .slice(0, LIMITS.maxStickerAssets)
    .map((a) => {
      const parsed = parseOption(a);
      return parsed ? { id: parsed.id, label: parsed.label, src: parsed.src, width: parsed.width, height: parsed.height } : null;
    })
    .filter((a): a is StickerAsset => a !== null && Boolean(a.id));

  const assetIds = new Set(stickerAssets.map((a) => a.id));
  const stickers: StickerInstance[] = (raw.stickers as unknown[])
    .slice(0, LIMITS.maxStickerInstances)
    .map((s) => {
      if (!isRecord(s) || !isSafeImageSrc(s.src)) return null;
      return {
        id: String(s.id || '').slice(0, 80),
        assetId: assetIds.has(String(s.assetId)) ? String(s.assetId) : '',
        src: s.src,
        label: String(s.label || '贴纸').slice(0, 40),
        x: clamp(Number(s.x) || 0, LIMITS.positionMin, LIMITS.positionMax),
        y: clamp(Number(s.y) || 0, LIMITS.positionMin, LIMITS.positionMax),
        scale: clamp(Number(s.scale) || 1, LIMITS.stickerScaleMin, LIMITS.stickerScaleMax),
        rotation: clamp(Number(s.rotation) || 0, LIMITS.rotationMin, LIMITS.rotationMax),
        flipX: Boolean(s.flipX),
        opacity: Number.isFinite(s.opacity) ? clamp(Number(s.opacity), LIMITS.opacityMin, LIMITS.opacityMax) : 1,
        z: Number.isFinite(s.z) ? clamp(Number(s.z), -1, 1000) : 10,
        behind: Boolean(s.behind),
        width: Number.isFinite(s.width) ? Number(s.width) : undefined,
        height: Number.isFinite(s.height) ? Number(s.height) : undefined,
      } as StickerInstance;
    })
    .filter((s): s is StickerInstance => s !== null && Boolean(s.id));

  const g = isRecord(raw.global) ? raw.global : {};
  const global = {
    scale: [1, 1.5, 2].includes(Number(g.scale)) ? Number(g.scale) : 1,
    flipX: Boolean(g.flipX),
    visible: g.visible !== false,
  };

  return {
    version,
    layers,
    stickerAssets,
    stickers,
    global,
    modelMeta: version === 2 ? parseModelMeta(raw.modelMeta) : null,
  };
}

export async function importSnapshotFile(file: File): Promise<IllustrationSnapshot> {
  if (file.size > LIMITS.maxSerializedBytes) {
    throw new ImportError('配置文件过大');
  }
  const text = await file.text();
  return parseSnapshotText(text);
}

// ---------- 后端保存（真实 API） ----------

export interface SaveTarget {
  slotId: string;
  slotName: string;
}

/** 存档槽只从真实 API 取；没有槽就明确报错，不自动创建、不伪造 id */
export async function resolveSaveTarget(): Promise<SaveTarget | null> {
  const data = await saveService.listSlots();
  const slots = data.slots || [];
  const current = data.current || '';
  const picked = slots.find((s) => s.id === current) || slots[0];
  if (!picked?.id) return null;
  return { slotId: picked.id, slotName: picked.name || picked.id };
}

/** 写入后端存档的 `ui` 分区；成功与否以请求结果为准 */
export async function saveToBackend(slotId: string, snapshot: IllustrationSnapshot): Promise<void> {
  if (serializedSize(snapshot) > LIMITS.maxSerializedBytes) {
    throw new Error(`装扮数据超过 ${Math.round(LIMITS.maxSerializedBytes / 1024 / 1024)}MB，请改用「导出配置」保存到本地文件`);
  }
  await saveService.updateSection(slotId, {
    data: { ui: { [SECTION_KEY]: snapshot } },
  });
}
