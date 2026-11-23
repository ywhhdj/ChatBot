/** 桌面端注册身份：持久化 uid，重连不换人（docs/api.md §4.5）。 */

const UID_KEY = "chatbot.uid";
const UID_RE = /^[A-Za-z0-9._:-]{1,64}$/;

let memoryUid = "";

function newUid(): string {
  const c = globalThis.crypto;
  if (c && typeof c.randomUUID === "function") return `desktop-${c.randomUUID()}`;
  return `desktop-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

export function getUid(): string {
  try {
    const saved = localStorage.getItem(UID_KEY) || "";
    if (UID_RE.test(saved)) return saved;
    const next = newUid();
    localStorage.setItem(UID_KEY, next);
    return next;
  } catch {
    // 隐私模式 / 非浏览器环境：进程内保底，保证同一次会话 uid 稳定
    if (!memoryUid) memoryUid = newUid();
    return memoryUid;
  }
}

export function getToken(): string {
  try {
    return localStorage.getItem("token") || "";
  } catch {
    return "";
  }
}

export const DESKTOP_DEVICE = "desktop" as const;
