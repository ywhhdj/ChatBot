/**
 * Chat UI store —— FrontendDesign §11 / FX-02 / F1-05
 *
 * 只保存「展示与交互状态」，不复制后端 session/memory 的权威数据。
 * 所有写入都要求显式 sessionId；迟到响应由 composable 先做归属校验。
 *
 * 性能：
 * - shallowRef + 不可变替换，避免对大消息数组做深度响应式代理；
 * - 按 message id 增量 patch，不做 deep watch；
 * - 每个会话设置消息上限，长时间对话渲染成本有界（F2-01）。
 */
import { defineStore } from 'pinia';
import { computed, markRaw, ref, shallowRef, type ComputedRef } from 'vue';

const EMPTY: UI.ChatMessage[] = [];
const EMPTY_IDS: string[] = [];
const MAX_MESSAGES_PER_SESSION = 500;
const MEMORY_TTL_MS = 30_000;

export interface MemoryPreview {
  revision: number;
  expiresAt: number;
  items: UI.RetentionItem[];
}

export const useChatStore = defineStore('chat', () => {
  const activeSessionId = ref('');
  const activeCharacterId = ref('');

  const messagesBySession = shallowRef<Record<string, UI.ChatMessage[]>>({});
  const activeStreamBySession = shallowRef<Record<string, UI.StreamSessionState>>({});
  const pendingTasksBySession = shallowRef<Record<string, string[]>>({});
  const memoryPreviewBySession = shallowRef<Record<string, MemoryPreview>>({});

  const messages: ComputedRef<UI.ChatMessage[]> = computed(
    () => messagesBySession.value[activeSessionId.value] || EMPTY
  );

  const streamState: ComputedRef<UI.StreamSessionState | null> = computed(
    () => activeStreamBySession.value[activeSessionId.value] || null
  );

  const pendingTasks: ComputedRef<string[]> = computed(
    () => pendingTasksBySession.value[activeSessionId.value] || EMPTY_IDS
  );

  function ensureSession(sessionId: string): void {
    if (!sessionId) return;
    if (messagesBySession.value[sessionId]) return;
    messagesBySession.value = { ...messagesBySession.value, [sessionId]: [] };
  }

  function getMessages(sessionId: string): UI.ChatMessage[] {
    return messagesBySession.value[sessionId] || EMPTY;
  }

  function setMessages(sessionId: string, list: UI.ChatMessage[]): void {
    ensureSession(sessionId);
    const trimmed = list.length > MAX_MESSAGES_PER_SESSION
      ? list.slice(list.length - MAX_MESSAGES_PER_SESSION)
      : list;
    messagesBySession.value = {
      ...messagesBySession.value,
      [sessionId]: markRaw(trimmed.map((m) => markRaw(m))),
    };
  }

  function appendMessage(sessionId: string, message: UI.ChatMessage): void {
    ensureSession(sessionId);
    const prev = getMessages(sessionId);
    const next = prev.concat(markRaw(message));
    messagesBySession.value = {
      ...messagesBySession.value,
      [sessionId]:
        next.length > MAX_MESSAGES_PER_SESSION
          ? next.slice(next.length - MAX_MESSAGES_PER_SESSION)
          : next,
    };
  }

  /** 只替换命中的那一条，其它消息对象引用保持不变。 */
  function patchMessage(
    sessionId: string,
    id: string,
    updater: (message: UI.ChatMessage) => UI.ChatMessage
  ): void {
    const prev = getMessages(sessionId);
    const index = prev.findIndex((m) => m.id === id);
    if (index === -1) return;
    const next = prev.slice();
    next[index] = markRaw(updater(prev[index] as UI.ChatMessage));
    messagesBySession.value = { ...messagesBySession.value, [sessionId]: next };
  }

  function setStream(sessionId: string, state: UI.StreamSessionState | null): void {
    const next = { ...activeStreamBySession.value };
    if (state) next[sessionId] = state;
    else delete next[sessionId];
    activeStreamBySession.value = next;
  }

  function setPendingTasks(sessionId: string, ids: string[]): void {
    pendingTasksBySession.value = {
      ...pendingTasksBySession.value,
      [sessionId]: ids.slice(0, 20),
    };
  }

  function addPendingTask(sessionId: string, taskId: string): void {
    const prev = pendingTasksBySession.value[sessionId] || [];
    if (prev.includes(taskId)) return;
    setPendingTasks(sessionId, [...prev, taskId]);
  }

  function setMemoryPreview(sessionId: string, items: UI.RetentionItem[]): void {
    memoryPreviewBySession.value = {
      ...memoryPreviewBySession.value,
      [sessionId]: {
        revision: Date.now(),
        expiresAt: Date.now() + MEMORY_TTL_MS,
        items: items.slice(0, 100),
      },
    };
  }

  function memoryPreview(sessionId: string): UI.RetentionItem[] {
    const hit = memoryPreviewBySession.value[sessionId];
    if (!hit || hit.expiresAt < Date.now()) return [];
    return hit.items;
  }

  /** 删除记忆后必须让页面、搜索结果和缓存同时失效（F2-06）。 */
  function invalidateMemory(sessionId: string, memoryId?: string): void {
    if (!memoryId) {
      const next = { ...memoryPreviewBySession.value };
      delete next[sessionId];
      memoryPreviewBySession.value = next;
      return;
    }
    const hit = memoryPreviewBySession.value[sessionId];
    if (!hit) return;
    memoryPreviewBySession.value = {
      ...memoryPreviewBySession.value,
      [sessionId]: {
        ...hit,
        revision: Date.now(),
        items: hit.items.filter((i) => i.id !== memoryId),
      },
    };
  }

  /** 会话/角色切换是状态边界：旧流的迟到事件一律视为 detached（F1-06）。 */
  function setActive(sessionId: string, characterId = activeCharacterId.value): void {
    ensureSession(sessionId);
    const oldId = activeSessionId.value;
    if (oldId && oldId !== sessionId) {
      const old = activeStreamBySession.value[oldId];
      if (old && old.phase !== 'completed' && old.phase !== 'failed' && old.phase !== 'cancelled') {
        activeStreamBySession.value = {
          ...activeStreamBySession.value,
          [oldId]: { ...old, phase: 'detached' },
        };
      }
    }
    activeSessionId.value = sessionId;
    activeCharacterId.value = characterId;
  }

  /** 任何异步结果写回前都要校验归属。 */
  function belongs(sessionId: string, requestId?: string): boolean {
    if (activeSessionId.value !== sessionId) return false;
    if (!requestId) return true;
    return activeStreamBySession.value[sessionId]?.requestId === requestId;
  }

  function clear(): void {
    messagesBySession.value = {};
    activeStreamBySession.value = {};
    pendingTasksBySession.value = {};
    memoryPreviewBySession.value = {};
  }

  return {
    activeSessionId,
    activeCharacterId,
    messages,
    streamState,
    pendingTasks,
    ensureSession,
    getMessages,
    setMessages,
    appendMessage,
    patchMessage,
    setStream,
    setPendingTasks,
    addPendingTask,
    setMemoryPreview,
    memoryPreview,
    invalidateMemory,
    setActive,
    belongs,
    clear,
  };
});
