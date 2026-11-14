/**
 * 统一 stream controller —— FrontendPlan F1-01 / F1-02 / F1-03 / F1-04 / F1-06 / F2-07
 *
 * 状态机：idle → connecting → streaming → completed | failed | cancelled | detached
 * - 每个请求绑定 session_id / character_id / request_id，chunk 按归属过滤；
 * - token 先写缓冲，按帧批量 flush，一帧最多一次 store 写入；
 * - 工具结果 / 任务更新只更新 tools，不污染 assistant 正文；
 * - 切换会话或页面卸载时 cancel + detach，迟到事件不再写 store；
 * - 不自动重发非幂等 POST，重试由用户显式触发。
 */
import { computed, onScopeDispose, ref, shallowRef, type ComputedRef } from 'vue';
import { openChatStream, type ChatStreamBody, type StreamHandle } from '@/api/stream';
import { ApiClientError, errorView } from '@/api/decoder';
import { useChatStore } from '@/stores/chat';

export interface UseChatStreamOptions {
  /** 显式取值，不允许从 store 隐式推导当前会话（F0-06）。 */
  sessionId: () => string;
  characterId: () => string;
  /** 失败通知由页面 workflow 层触发；底层不弹窗。 */
  onError?: (err: ApiClientError) => void;
  onWarning?: (message: string) => void;
  /** token 批量刷新间隔，默认约 20fps */
  flushIntervalMs?: number;
  timeoutMs?: number;
}

const TOOL_STATE_MAP: Record<string, UI.ToolStatus> = {
  pending: 'pending',
  queued: 'pending',
  running: 'running',
  success: 'success',
  done: 'success',
  failed: 'error',
  error: 'error',
  skipped: 'skipped',
  cancelled: 'skipped',
};

function newId(prefix: string): string {
  const c = globalThis.crypto;
  if (c && typeof c.randomUUID === 'function') return `${prefix}_${c.randomUUID()}`;
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

function upsertTool(
  tools: UI.ToolCallItem[] | undefined,
  frame: UI.StreamFrame
): UI.ToolCallItem[] {
  const id = String(frame.task_id || frame.tool_id || frame.id || `tool_${frame.seq ?? Date.now()}`);
  const status = TOOL_STATE_MAP[String(frame.state || frame.status || 'running')] || 'running';
  const next: UI.ToolCallItem = {
    id,
    service: String(frame.service || 'task'),
    method: String(frame.method || frame.event || 'status'),
    raw: String(frame.raw || ''),
    status,
    params: (frame.params as Record<string, any>) || {},
    result: frame.result ?? undefined,
    error: frame.error?.message,
    label: String(frame.label || frame.method || '后台任务'),
  };
  const list = tools ? tools.slice() : [];
  const index = list.findIndex((t) => t.id === id);
  if (index === -1) list.push(next);
  else list[index] = { ...list[index], ...next };
  // 工具列表上限，避免异常流把 UI 拖垮
  return list.length > 40 ? list.slice(list.length - 40) : list;
}

export function useChatStream(options: UseChatStreamOptions) {
  const store = useChatStore();
  const flushIntervalMs = options.flushIntervalMs ?? 48;

  const phase = ref<UI.StreamPhase>('idle');
  const lastError = shallowRef<ApiClientError | null>(null);
  const state = shallowRef<UI.StreamSessionState | null>(null);
  const errorState: ComputedRef<UI.AsyncErrorView | null> = computed(() => errorView(lastError.value));
  const isBusy = computed(() => phase.value === 'connecting' || phase.value === 'streaming');

  let handle: StreamHandle | null = null;
  let requestId = '';
  let assistantId = '';
  let boundSessionId = '';
  let boundCharacterId = '';
  let pendingText = '';
  let rafId: number | null = null;
  let lastFlushAt = 0;
  let settled = false;
  let lastPayload: { text: string; extra: Partial<ChatStreamBody> } | null = null;

  const updateState = (patch: Partial<UI.StreamSessionState>) => {
    if (!state.value) return;
    const next = { ...state.value, ...patch };
    state.value = next;
    if (store.belongs(boundSessionId, requestId)) store.setStream(boundSessionId, next);
  };

  /** 一帧最多一次 store 写入：token 不逐字触发消息列表重渲染。 */
  const flush = (force = false) => {
    if (!pendingText && !force) return;
    const text = pendingText;
    pendingText = '';
    lastFlushAt = performance.now();
    if (!text) return;
    if (!store.belongs(boundSessionId, requestId)) return;
    store.patchMessage(boundSessionId, assistantId, (m) => ({
      ...m,
      content: m.content + text,
      phase: 'answering',
    }));
    updateState({ tokenCount: (state.value?.tokenCount || 0) + text.length });
  };

  const scheduleFlush = () => {
    if (rafId !== null) return;
    rafId = requestAnimationFrame(() => {
      rafId = null;
      const due = performance.now() - lastFlushAt >= flushIntervalMs;
      if (due || settled) flush();
      else if (pendingText) scheduleFlush();
    });
  };

  const releaseRaf = () => {
    if (rafId !== null) {
      cancelAnimationFrame(rafId);
      rafId = null;
    }
  };

  const belongs = (frame: UI.StreamFrame): boolean => {
    if (settled || phase.value === 'detached' || phase.value === 'cancelled') return false;
    if (frame.request_id && frame.request_id !== requestId) return false;
    if (frame.session_id && frame.session_id !== boundSessionId) return false;
    if (frame.character_id && frame.character_id !== boundCharacterId) return false;
    // 用户刚切换会话时，迟到 chunk 不得覆盖新会话
    if (store.activeSessionId !== boundSessionId) return false;
    return true;
  };

  /**
   * 终态回调专用的归属判断：transport 层可能先置 settled 再回调，
   * 因此这里不检查本地 settled，只校验请求/会话归属，避免错误被吞掉。
   */
  const isCurrent = (frame: UI.StreamFrame): boolean => {
    if (phase.value === 'detached') return false;
    if (frame.request_id && frame.request_id !== requestId) return false;
    if (frame.session_id && frame.session_id !== boundSessionId) return false;
    if (frame.character_id && frame.character_id !== boundCharacterId) return false;
    if (store.activeSessionId !== boundSessionId) return false;
    return true;
  };

  const markTerminal = (next: UI.StreamPhase, patch: Partial<UI.StreamSessionState> = {}) => {
    settled = true;
    releaseRaf();
    flush(true);
    phase.value = next;
    updateState({
      phase: next,
      elapsedMs: Date.now() - (state.value?.startedAt || Date.now()),
      ...patch,
    });
    handle = null;
  };

  const send = (text: string, extra: Partial<ChatStreamBody> = {}) => {
    const sessionId = options.sessionId();
    const characterId = options.characterId();
    const content = text.trim();
    if (!sessionId) {
      const err = new ApiClientError({
        kind: 'validation',
        code: 1001,
        message: '缺少 session_id，请先选择或创建会话',
      });
      lastError.value = err;
      options.onError?.(err);
      return;
    }
    if (!content || isBusy.value) return;

    // 防重复点击：已有在途流先取消，再发起新请求
    if (handle && !settled) cancel('superseded');

    boundSessionId = sessionId;
    boundCharacterId = characterId;
    requestId = newId('req');
    assistantId = newId('msg');
    pendingText = '';
    settled = false;
    lastError.value = null;
    lastPayload = { text: content, extra: { ...extra } };
    phase.value = 'connecting';

    store.ensureSession(sessionId);
    store.appendMessage(sessionId, {
      id: newId('msg'),
      role: 'user',
      content,
      createdAt: Date.now(),
    });
    store.appendMessage(sessionId, {
      id: assistantId,
      role: 'assistant',
      content: '',
      phase: 'thinking',
      tools: [],
      createdAt: Date.now(),
    });

    const startedAt = Date.now();
    state.value = {
      streamId: '',
      requestId,
      phase: 'connecting',
      seq: 0,
      tokenCount: 0,
      startedAt,
      elapsedMs: 0,
      error: null,
    };
    store.setStream(sessionId, state.value);

    const body: ChatStreamBody = {
      text: content,
      source: 'text',
      session_id: sessionId,
      character_id: characterId,
      stream: true,
      ...extra,
    };

    handle = openChatStream(
      body,
      {
        onChunk: (frame) => {
          if (!belongs(frame)) return;
          if (phase.value === 'connecting') {
            phase.value = 'streaming';
            updateState({ phase: 'streaming', streamId: frame.stream_id || state.value?.streamId || '' });
          }
          pendingText += String(frame.text ?? '');
          updateState({ seq: frame.seq ?? (state.value?.seq || 0) + 1 });
          scheduleFlush();
        },
        onProgress: (frame) => {
          if (!belongs(frame)) return;
          updateState({ seq: frame.seq ?? state.value?.seq ?? 0 });
        },
        onToolStatus: (frame) => {
          // 工具结果只进 tools，绝不拼进 assistant 正文（F1-04）
          if (!belongs(frame)) return;
          store.patchMessage(boundSessionId, assistantId, (m) => ({
            ...m,
            phase: m.phase === 'thinking' ? 'tooling' : m.phase,
            tools: upsertTool(m.tools, frame),
          }));
          if (frame.task_id) store.addPendingTask(boundSessionId, String(frame.task_id));
        },
        onDone: (frame) => {
          if (!isCurrent(frame)) return;
          markTerminal('completed', {
            seq: frame.seq ?? state.value?.seq ?? 0,
            elapsedMs: frame.elapsed_ms ?? Date.now() - startedAt,
          });
          store.patchMessage(boundSessionId, assistantId, (m) => ({ ...m, phase: 'done' }));
        },
        onError: (err, frame) => {
          if (!isCurrent(frame || { request_id: requestId })) return;
          lastError.value = err;
          markTerminal('failed', { error: errorView(err) });
          store.patchMessage(boundSessionId, assistantId, (m) => ({ ...m, phase: 'error' }));
          options.onError?.(err);
        },
        onCancelled: (reason) => {
          if (phase.value === 'detached') return;
          markTerminal('cancelled');
          store.patchMessage(boundSessionId, assistantId, (m) => ({
            ...m,
            phase: m.content ? 'done' : 'error',
          }));
          if (reason === 'superseded') phase.value = 'idle';
        },
        onWarning: (message) => options.onWarning?.(message),
      },
      { requestId, timeoutMs: options.timeoutMs }
    );
  };

  const cancel = (reason = 'user') => {
    if (!handle || settled) return;
    // transport 会同步回调 onCancelled → markTerminal；下面只作兜底
    handle.cancel(reason);
    if (!settled) markTerminal('cancelled');
  };

  /** 切换 session/character 前调用：取消旧流并把迟到事件全部丢弃。 */
  const detach = () => {
    if (handle && !settled) handle.cancel('detached');
    settled = true;
    phase.value = 'detached';
    releaseRaf();
    pendingText = '';
    handle = null;
  };

  /** 用户显式重试：不自动重发，避免非幂等 POST 重复执行。 */
  const retry = () => {
    if (!lastPayload || isBusy.value) return;
    const sessionId = options.sessionId();
    if (store.getMessages(sessionId).some((m) => m.id === assistantId)) {
      // 移除上一次未完成的占位消息
      const rest = store.getMessages(sessionId).filter((m) => m.id !== assistantId);
      store.setMessages(sessionId, rest);
    }
    send(lastPayload.text, lastPayload.extra);
  };

  const resetError = () => {
    lastError.value = null;
  };

  onScopeDispose(() => {
    if (handle && !settled) handle.cancel('unmounted');
    releaseRaf();
    pendingText = '';
  });

  return {
    phase,
    state,
    lastError,
    errorState,
    isBusy,
    send,
    cancel,
    detach,
    retry,
    resetError,
  };
}
