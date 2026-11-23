/**
 * 全站唯一资产处理模块
 */
export type AssetKind = 'image' | 'audio' | 'json' | 'model' | 'any';

export interface AssetRule {
  mime: readonly string[];
  ext: readonly string[];
  label: string;
}

/** 唯一一份白名单：任何页面不再自己写 accept 数组 */
export const ASSET_RULES: Readonly<Record<Exclude<AssetKind, 'any'>, AssetRule>> = {
  image: {
    mime: ['image/png', 'image/jpeg', 'image/webp', 'image/gif'],
    ext: ['.png', '.jpg', '.jpeg', '.webp', '.gif'],
    label: 'PNG / JPEG / WebP / GIF 位图',
  },
  audio: {
    mime: ['audio/mpeg', 'audio/wav', 'audio/x-wav', 'audio/ogg', 'audio/mp4', 'audio/aac', 'audio/flac', 'audio/webm'],
    ext: ['.mp3', '.wav', '.ogg', '.m4a', '.aac', '.flac', '.webm'],
    label: 'MP3 / WAV / OGG / M4A / AAC / FLAC / WebM 音频',
  },
  json: {
    mime: ['application/json', 'text/json', 'text/plain', ''],
    ext: ['.json'],
    label: 'JSON 配置',
  },
  model: {
    mime: ['application/json', 'text/plain', 'application/octet-stream', 'image/png', 'image/jpeg', 'image/webp', ''],
    ext: ['.json', '.moc3', '.moc', '.png', '.jpg', '.jpeg', '.webp', '.atlas', '.txt'],
    label: 'Live2D / VTS 模型包',
  },
};

export interface LoadOptions {
  /** 单文件字节上限，默认 8MB（模型图集较大，调用方可放宽） */
  maxBytes?: number;
  /** 本次最多接受几个文件 */
  maxFiles?: number;
  /** 已有指纹集合，用于去重 */
  existing?: ReadonlySet<string>;
  /** 模型包目录模式：跳过 MIME 校验（部分文件如 .moc3 无标准 MIME） */
  looseMime?: boolean;
  /** 是否读取文本内容（json / 模型包） */
  readText?: boolean;
  /** 是否读取位图尺寸 */
  readSize?: boolean;
  /** 只做校验与去重，保留原始 File，不读内容（背景/音乐用 blob URL 时省一次全量解码） */
  rawOnly?: boolean;
}

export interface LoadedAsset {
  id: string;
  label: string;
  /** 位图/音频 → data: URL；文本类 → 文本内容经 text 字段提供，src 留空 */
  src: string;
  width?: number;
  height?: number;
  fingerprint: string;
  text?: string;
  mime: string;
  ext: string;
  /** 原始 File 保留给模型解析器用（不会进序列化） */
  file?: File;
}

export class AssetError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'AssetError';
  }
}

let seq = 0;
export function assetUid(prefix = 'asset'): string {
  seq += 1;
  return `${prefix}_${Date.now().toString(36)}_${seq.toString(36)}`;
}

export function getExtension(name: string): string {
  const i = name.lastIndexOf('.');
  return i < 0 ? '' : name.slice(i).toLowerCase();
}

export function baseName(name: string): string {
  return name.replace(/\.[^.]+$/, '').slice(0, 80) || '未命名';
}

export function fingerprintOf(file: File): string {
  return `${file.name}:${file.size}:${file.lastModified}`;
}

/** 由路径/标签生成轻量去重键（导入的配置没有 File 元信息时使用） */
export function looseFingerprint(label: string, payload: string): string {
  return `${label}:${payload.length}`;
}

/** 一组已有素材 → 轻量指纹集合，供 loadAssets 的 existing 使用 */
export function assetFingerprints(assets: ReadonlyArray<{ label: string; src: string }>): Set<string> {
  return new Set(assets.map((a) => looseFingerprint(a.label, a.src)));
}

export function acceptString(kind: AssetKind): string {
  if (kind === 'any') return '';
  const r = ASSET_RULES[kind];
  return [...r.ext, ...r.mime.filter(Boolean)].join(',');
}

/** src 协议白名单：data: 位图 / 同源 http(s) / 站内相对路径；拒绝 SVG、javascript:、blob: */
export function isSafeImageSrc(src: unknown): src is string {
  if (typeof src !== 'string' || !src) return false;
  if (/^data:image\/(png|jpeg|webp|gif);base64,[A-Za-z0-9+/=]+$/.test(src)) return true;
  if (/^https?:\/\//i.test(src)) return true;
  if (/^\/(?!\/)[\w\-./%]+\.(png|jpe?g|webp|gif)$/i.test(src)) return true;
  return false;
}

/** 允许的配置/模型文本 src 协议（文本不进 <img>，但拒绝 javascript: 等） */
export function isSafeTextSrc(src: unknown): src is string {
  return typeof src === 'string' && src.length > 0 && !/^(javascript|vbscript):/i.test(src);
}

function readAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result;
      if (typeof result === 'string' && isSafeImageSrc(result)) resolve(result);
      else reject(new AssetError('文件内容不是受支持的位图'));
    };
    reader.onerror = () => reject(new AssetError('文件读取失败'));
    reader.onabort = () => reject(new AssetError('文件读取已取消'));
    reader.readAsDataURL(file);
  });
}

function readAsText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ''));
    reader.onerror = () => reject(new AssetError('文本读取失败'));
    reader.readAsText(file, 'utf-8');
  });
}

export function readImageSize(src: string): Promise<{ width: number; height: number }> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => {
      const width = image.naturalWidth;
      const height = image.naturalHeight;
      if (width > 0 && height > 0) resolve({ width, height });
      else reject(new AssetError('无法读取图片尺寸'));
    };
    image.onerror = () => reject(new AssetError('图片解码失败或格式不受支持'));
    image.src = src;
  });
}

function ruleFor(kind: AssetKind): AssetRule {
  if (kind === 'any') {
    return { mime: [], ext: [], label: '任意文件' };
  }
  return ASSET_RULES[kind];
}

/** 单文件校验；失败抛 AssetError，由调用方统一提示 */
export function validateFile(file: File, kind: AssetKind, options: LoadOptions = {}): void {
  const rule = ruleFor(kind);
  const ext = getExtension(file.name);
  const maxBytes = options.maxBytes ?? 8 * 1024 * 1024;
  if (file.size <= 0 || file.size > maxBytes) {
    throw new AssetError(`${file.name}：大小需在 ${Math.round(maxBytes / 1024 / 1024)}MB 以内`);
  }
  if (rule.ext.length && !rule.ext.includes(ext)) {
    throw new AssetError(`${file.name}：仅支持 ${rule.label}`);
  }
  if (!options.looseMime && rule.mime.length && file.type && !rule.mime.includes(file.type.toLowerCase())) {
    throw new AssetError(`${file.name}：MIME 类型 ${file.type} 不受支持`);
  }
}

/**
 * 批量校验并加载。任何一张失败都**不**落库半套；
 * 部分失败时成功项照常返回，原因挂在 warnings 上由页面层展示（不吞异常）。
 */
export async function loadAssets(
  input: FileList | File[],
  kind: AssetKind,
  options: LoadOptions = {}
): Promise<LoadedAsset[]> {
  const list = Array.from(input || []);
  if (!list.length) return [];
  const maxFiles = options.maxFiles ?? 60;
  const accepted: LoadedAsset[] = [];
  const warnings: string[] = [];
  const seen = new Set<string>(options.existing || []);

  for (const file of list) {
    if (accepted.length >= maxFiles) {
      warnings.push(`已达本次数量上限（${maxFiles}），其余文件未添加`);
      break;
    }
    try {
      validateFile(file, kind, options);
      const fp = fingerprintOf(file);
      if (seen.has(fp)) {
        warnings.push(`${file.name}：已添加，跳过重复`);
        continue;
      }
      const ext = getExtension(file.name);
      let src = '';
      let text: string | undefined;
      let width: number | undefined;
      let height: number | undefined;

      if (options.rawOnly) {
        // 只保留 File，由调用方用 useObjectUrls 创建 blob URL
      } else {
        const isTextFile = ext === '.json' || ext === '.atlas' || ext === '.txt';
        if (options.readText && isTextFile) {
          text = await readAsText(file);
        }
        if (kind === 'image' || (kind === 'model' && ['.png', '.jpg', '.jpeg', '.webp'].includes(ext))) {
          src = await readAsDataUrl(file);
          if (options.readSize !== false && kind === 'image') {
            const size = await readImageSize(src);
            width = size.width;
            height = size.height;
          }
        } else if (kind === 'audio') {
          src = await readAsDataUrl(file);
        }
      }

      seen.add(fp);
      accepted.push({
        id: assetUid(),
        label: baseName(file.name),
        src,
        width,
        height,
        fingerprint: fp,
        text,
        mime: file.type,
        ext,
        file,
      });
    } catch (err) {
      warnings.push(`${file.name}：${err instanceof AssetError ? err.message : '读取失败'}`);
    }
  }

  if (!accepted.length) {
    throw new AssetError(warnings[0] || '没有可用的文件');
  }
  if (warnings.length) (accepted as LoadedAsset[] & { warnings?: string[] }).warnings = warnings;
  return accepted;
}

export function assetWarnings(result: LoadedAsset[]): string[] {
  return (result as LoadedAsset[] & { warnings?: string[] }).warnings || [];
}

/** 统一下载：延后 revoke，避免部分浏览器打断下载 */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.rel = 'noopener';
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
