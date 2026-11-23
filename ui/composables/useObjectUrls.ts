/**
 * Object URL 生命周期
 */
import { onScopeDispose } from 'vue';

export function useObjectUrls(autoRevoke = true) {
  const owned = new Set<string>();

  const create = (file: Blob): string => {
    const url = URL.createObjectURL(file);
    owned.add(url);
    return url;
  };

  const revoke = (url: string): void => {
    if (!url || !url.startsWith('blob:')) return;
    if (owned.has(url)) owned.delete(url);
    URL.revokeObjectURL(url);
  };

  const revokeAll = (): void => {
    for (const url of owned) URL.revokeObjectURL(url);
    owned.clear();
  };

  /** 只释放「已不被任何存活集合引用」的 URL；仍在 store 里的资源保留 */
  const prune = (keep: Iterable<string>): void => {
    const alive = new Set(keep);
    for (const url of Array.from(owned)) {
      if (!alive.has(url)) revoke(url);
    }
  };

  const owns = (url: string): boolean => owned.has(url);

  // 全局 store（背景/音乐列表）里的 blob 可能仍被其它页面使用，
  // 这类调用方传 autoRevoke=false，并在卸载时自行 prune。
  onScopeDispose(() => {
    if (autoRevoke) revokeAll();
  });

  return { create, revoke, revokeAll, prune, owns, size: () => owned.size };
}
