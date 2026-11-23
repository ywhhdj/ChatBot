/**
 * Live2D / VTS 模型包解析
 *
 * 支持的真实来源
 *  1. Cubism 2.1 `model.json`：`textures` 常是「一个部件一张独立 PNG」→ 精确按部件分层；
 *  2. Cubism 3/4 与 VTube Studio（`.model3.json` + `.moc3` + 纹理图集 + `.vtube.json`
 *     + `.cdi3.json`）：读 FileReferences / 显示名 / 纹理清单；
 *     - 若纹理是多个独立部件图 → 按文件分层；
 *     - 若是合并图集 → 按 alpha 连通区域切出部件候选（明确标注「不保证与 ArtMesh 一一对应」）；
 *  3. 只有散落 PNG 的目录 → 按文件名分层（兜底，同样标注）。
 */
import { assetUid, isSafeImageSrc } from '@/utils/asset';
import type { LoadedAsset } from '@/utils/asset';
import {
  MODEL_LIMITS,
  guessGroup,
  type ModelFormat,
  type ParsedModel,
  type ParsedPart,
} from './modelTypes';

interface BundleFiles {
  model3?: LoadedAsset;
  model2?: LoadedAsset;
  vtube?: LoadedAsset;
  cdi3?: LoadedAsset;
  moc3?: LoadedAsset;
  textures: LoadedAsset[];
  jsons: LoadedAsset[];
}

function isImage(a: LoadedAsset): boolean {
  return ['.png', '.jpg', '.jpeg', '.webp', '.gif'].includes(a.ext) && isSafeImageSrc(a.src);
}

function safeJson(text: string | undefined): Record<string, any> | null {
  if (!text) return null;
  try {
    const parsed = JSON.parse(text);
    return typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function classify(assets: LoadedAsset[]): BundleFiles {
  const out: BundleFiles = { textures: [], jsons: [] };
  for (const a of assets) {
    const n = `${a.label}${a.ext}`.toLowerCase();
    if (a.ext === '.json') out.jsons.push(a);
    if (isImage(a)) out.textures.push(a);
    if (a.ext === '.moc3' || a.ext === '.moc') out.moc3 = a;
    if (n.includes('.vtube')) out.vtube = a;
    else if (n.includes('.cdi3')) out.cdi3 = a;
    else if (n.includes('.model3')) out.model3 = a;
    else if (n === 'model.json' || n.endsWith('/model.json') || n === 'model') out.model2 = a;
  }
  return out;
}

/** cdi3.json 的 PartIds → 可读名；不同版本字段略有差异，取能取到的 */
function readPartNames(cdi3: Record<string, any> | null): string[] {
  if (!cdi3) return [];
  const raw = Array.isArray(cdi3.PartIds) ? cdi3.PartIds : Array.isArray(cdi3.Parts) ? cdi3.Parts : [];
  const names: string[] = [];
  for (const item of raw) {
    if (typeof item === 'string') names.push(item);
    else if (item && typeof item === 'object') {
      const name = String(item.Name ?? item.name ?? item.DisplayName ?? item.Id ?? item.id ?? '').trim();
      if (name) names.push(name);
    }
  }
  return names.slice(0, MODEL_LIMITS.maxLayerCount);
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error('图集解码失败'));
    img.src = src;
  });
}

interface RegionBox {
  id: number;
  x0: number;
  y0: number;
  x1: number;
  y1: number;
  area: number;
}

/**
 * 合并图集 → 按 alpha 连通区域切出部件候选。
 * 检测在降采样网格上做（避免 4096² 逐像素 BFS 卡死），
 * 裁切仍用原图分辨率 + 放大的区域遮罩，保证清晰度。
 */
async function splitAtlasByAlpha(src: string, partNames: string[]): Promise<ParsedPart[]> {
  const img = await loadImage(src);
  const W = img.naturalWidth;
  const H = img.naturalHeight;
  if (!W || !H) throw new Error('图集尺寸为空');

  const scale = Math.min(1, MODEL_LIMITS.detectMaxEdge / Math.max(W, H));
  const w = Math.max(1, Math.round(W * scale));
  const h = Math.max(1, Math.round(H * scale));
  const probe = document.createElement('canvas');
  probe.width = w;
  probe.height = h;
  const pctx = probe.getContext('2d', { willReadFrequently: true });
  if (!pctx) throw new Error('当前浏览器不支持画布解析');
  pctx.drawImage(img, 0, 0, w, h);
  const pixels = pctx.getImageData(0, 0, w, h).data;

  const labels = new Int32Array(w * h); // 0 = 透明/背景，>0 = 区域 id
  const boxes: RegionBox[] = [];
  const stack: number[] = [];
  let nextId = 0;
  const threshold = MODEL_LIMITS.alphaThreshold;

  for (let start = 0; start < w * h; start += 1) {
    if (labels[start] !== 0 || pixels[start * 4 + 3] < threshold) continue;
    nextId += 1;
    const id = nextId;
    let area = 0;
    let x0 = w;
    let y0 = h;
    let x1 = 0;
    let y1 = 0;
    stack.push(start);
    labels[start] = id;
    while (stack.length) {
      const idx = stack.pop() as number;
      const px = idx % w;
      const py = (idx - px) / w;
      area += 1;
      if (px < x0) x0 = px;
      if (py < y0) y0 = py;
      if (px > x1) x1 = px;
      if (py > y1) y1 = py;
      const neighbours = [idx - 1, idx + 1, idx - w, idx + w];
      for (const nIdx of neighbours) {
        if (nIdx < 0 || nIdx >= w * h) continue;
        // 左右邻居不能跨行
        if ((nIdx === idx - 1 && px === 0) || (nIdx === idx + 1 && px === w - 1)) continue;
        if (labels[nIdx] !== 0 || pixels[nIdx * 4 + 3] < threshold) continue;
        labels[nIdx] = id;
        stack.push(nIdx);
      }
    }
    if (area >= w * h * MODEL_LIMITS.minRegionAreaRatio) {
      boxes.push({ id, x0, y0, x1: x1 + 1, y1: y1 + 1, area });
    }
  }

  // 稳定排序：从上到下、从左到右，贴近视觉层序；再裁掉过碎的尾部
  boxes.sort((a, b) => a.y0 - b.y0 || a.x0 - b.x0);
  const picked = boxes.slice(0, MODEL_LIMITS.maxRegions);
  if (!picked.length) throw new Error('图集中没有可识别的独立部件区域');

  const parts: ParsedPart[] = [];
  for (let i = 0; i < picked.length; i += 1) {
    const box = picked[i];
    const sx = Math.max(0, Math.floor(box.x0 / scale));
    const sy = Math.max(0, Math.floor(box.y0 / scale));
    const sw = Math.min(W - sx, Math.ceil((box.x1 - box.x0) / scale));
    const sh = Math.min(H - sy, Math.ceil((box.y1 - box.y0) / scale));
    if (sw <= 0 || sh <= 0) continue;

    // 区域遮罩：降采样 labels → 原尺寸 bbox（最近邻放大，不平滑以免糊边）
    const mask = document.createElement('canvas');
    mask.width = Math.ceil((box.x1 - box.x0) / scale);
    mask.height = Math.ceil((box.y1 - box.y0) / scale);
    const mctx = mask.getContext('2d');
    if (!mctx) continue;
    mctx.imageSmoothingEnabled = false;
    const small = document.createElement('canvas');
    small.width = box.x1 - box.x0;
    small.height = box.y1 - box.y0;
    const sctx = small.getContext('2d');
    if (!sctx) continue;
    const maskData = sctx.createImageData(small.width, small.height);
    for (let y = 0; y < small.height; y += 1) {
      for (let x = 0; x < small.width; x += 1) {
        if (labels[(box.y0 + y) * w + (box.x0 + x)] === box.id) {
          const o = (y * small.width + x) * 4;
          maskData.data[o] = 255;
          maskData.data[o + 1] = 255;
          maskData.data[o + 2] = 255;
          maskData.data[o + 3] = 255;
        }
      }
    }
    sctx.putImageData(maskData, 0, 0);
    mctx.drawImage(small, 0, 0, mask.width, mask.height);

    const part = document.createElement('canvas');
    part.width = sw;
    part.height = sh;
    const cctx = part.getContext('2d');
    if (!cctx) continue;
    cctx.drawImage(img, sx, sy, sw, sh, 0, 0, sw, sh);
    cctx.globalCompositeOperation = 'destination-in';
    cctx.drawImage(mask, 0, 0, sw, sh);

    const label = partNames[i] || `部件 ${i + 1}`;
    parts.push({
      id: assetUid('modelpart'),
      label,
      src: part.toDataURL('image/png'),
      z: i,
      group: guessGroup(label, ''),
      texture: '合并图集',
      source: 'connected-component',
      note: '按图集 alpha 连通区域切分；一个区域不保证等于一个 ArtMesh，moc3 网格数据未被解析',
      width: sw,
      height: sh,
    });
  }
  return parts;
}

function isTechnicalId(name: string): boolean {
  return /^D_REF|^(PSD|PART|ART)_|^\w+\.\w+/i.test(name);
}

function partFromTexture(a: LoadedAsset, index: number, names: string[], source: ParsedPart['source']): ParsedPart {
  const candidate = names[index] || '';
  // cdi3 / model.json 里的 `D_REF.PT_01` 之类技术 ID 不适合当显示名，回退到文件名
  const label = candidate && !isTechnicalId(candidate) ? candidate : (a.label || candidate || `部件 ${index + 1}`);
  return {
    id: assetUid('modelpart'),
    label,
    src: a.src,
    z: index,
    group: guessGroup(label, a.label),
    texture: `${a.label}${a.ext}`,
    source,
    note: source === 'loose-file' ? '目录内散落图片，按文件名顺序分层' : undefined,
    width: a.width,
    height: a.height,
  };
}

/** 解析入口：只接收真实用户选择的本地文件 */
export async function parseModelBundle(assets: LoadedAsset[]): Promise<ParsedModel> {
  const files = classify(assets);
  const warnings: string[] = [];
  const partNames = readPartNames(safeJson(files.cdi3?.text));
  const hasVtube = Boolean(files.vtube);
  const hasMoc3 = Boolean(files.moc3);
  const isVts = hasVtube || (Boolean(files.model3) && hasMoc3);

  let format: ModelFormat = 'loose';
  let name = '未命名模型';
  let parts: ParsedPart[] = [];
  let textureFiles: string[] = files.textures.map((a) => `${a.label}${a.ext}`);

  const model3 = safeJson(files.model3?.text);
  const model2 = safeJson(files.model2?.text);

  if (model3) {
    format = isVts ? 'vts' : 'cubism3';
    const refs = model3.FileReferences || model3.fileReferences || {};
    const declared: string[] = Array.isArray(refs.Textures) ? refs.Textures : Array.isArray(refs.textures) ? refs.textures : [];
    textureFiles = declared.length ? declared : textureFiles;
    name = String(model3.Name || files.model3?.label || (hasVtube ? 'VTS 模型' : 'Live2D 模型')).slice(0, 60);

    // 按声明路径匹配实际文件（可能带 textures/ 前缀）
    const ordered: LoadedAsset[] = [];
    for (const ref of declared) {
      const tail = String(ref).split('/').pop()?.toLowerCase() || '';
      const hit = files.textures.find((a) => `${a.label}${a.ext}`.toLowerCase() === tail || a.label.toLowerCase() === tail.replace(/\.[^.]+$/, ''));
      if (hit) ordered.push(hit);
    }
    const unique = ordered.length ? ordered : files.textures;

    if (unique.length > 1) {
      parts = unique.slice(0, MODEL_LIMITS.maxLayerCount).map((a, i) =>
        partFromTexture(a, i, partNames, 'part-file')
      );
      warnings.push('按模型声明的纹理文件顺序分层；实际 draw order 在 moc3 内，层序为文件顺序近似');
    } else if (unique.length === 1) {
      try {
        parts = await splitAtlasByAlpha(unique[0].src, partNames);
        warnings.push('检测到合并纹理图集：已按 alpha 连通区域切出部件候选，不保证与 ArtMesh 一一对应');
      } catch (err) {
        warnings.push(err instanceof Error ? err.message : '图集切分失败');
        parts = [partFromTexture(unique[0], 0, partNames, 'part-file')];
        warnings.push('已降级为整张图集单层；可改用「添加素材」手动补部件');
      }
    } else {
      warnings.push('模型声明了纹理但包内未找到对应图片文件');
    }
  } else if (model2) {
    format = 'cubism2';
    const declared: string[] = Array.isArray(model2.textures) ? model2.textures : [];
    textureFiles = declared.length ? declared : textureFiles;
    const partsMeta: Array<{ id?: string }> = Array.isArray(model2.parts) ? model2.parts : [];
    const names = partsMeta.map((p, i) => String(p?.id || partNames[i] || `部件 ${i + 1}`));
    name = String(files.model2?.label || 'Cubism 2.1 模型').slice(0, 60);

    const ordered: LoadedAsset[] = [];
    for (const ref of declared) {
      const tail = String(ref).split('/').pop()?.toLowerCase() || '';
      const hit = files.textures.find((a) => `${a.label}${a.ext}`.toLowerCase() === tail);
      if (hit) ordered.push(hit);
    }
    const unique = ordered.length ? ordered : files.textures;
    parts = unique.slice(0, MODEL_LIMITS.maxLayerCount).map((a, i) =>
      partFromTexture(a, i, names, 'part-file')
    );
    if (!parts.length) warnings.push('model.json 声明的部件纹理未在目录中找到');
  } else {
    parts = files.textures
      .slice()
      .sort((a, b) => a.label.localeCompare(b.label))
      .slice(0, MODEL_LIMITS.maxLayerCount)
      .map((a, i) => partFromTexture(a, i, partNames, 'loose-file'));
    warnings.push('未找到 model.json / .model3.json，已按目录内 PNG 文件名顺序分层（兜底，非模型真实层序）');
  }

  if (!parts.length) {
    warnings.push('没有解析出任何部件图片，请确认模型包内包含 PNG 纹理');
  }
  if (!hasMoc3 && (format === 'vts' || format === 'cubism3')) {
    warnings.push('包内缺少 .moc3；仍可按纹理组装静态立绘，但无法做参数驱动变形');
  }
  if (hasMoc3) {
    warnings.push('.moc3 为编译二进制，本模块只标记存在、不解析 ArtMesh 网格（需官方 Cubism SDK 与授权）');
  }
  if (hasVtube) {
    warnings.push('检测到 .vtube.json（VTS 面捕/位置校准配置）；它不参与静态部件分层，仅作为模型标记');
  }
  if (!partNames.length) {
    warnings.push('未找到 .cdi3.json 的可读部件名，面板显示文件名/序号');
  }
  if (parts.length > MODEL_LIMITS.maxLayerCount) {
    warnings.push(`部件超过 ${MODEL_LIMITS.maxLayerCount} 层，已截断`);
  }

  return {
    format,
    name,
    parts,
    warnings,
    meta: {
      hasMoc3,
      hasVtube,
      hasCdi3: Boolean(files.cdi3),
      modelJsonName: files.model3?.label || files.model2?.label || '',
      textureFiles,
      partNames,
    },
  };
}
