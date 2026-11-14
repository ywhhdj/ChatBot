/**
 * SSE transport —— FrontendPlan F1-01 / F1-02 / F1-03 / F2-07
 *
 * 对应 POST /api/chat/stream（docs/api.md §4.1）。
 * 与 Axios transport 平行：只负责编码、请求 ID、取消、超时与帧解析，
 * 不写 store、不弹通知、不猜测业务语义。
 *
 * 约束：
 * - 每条流按 request_id / stream_id 归属，seq 单调递增；不伪装支持 replay。
 * - 每条流恰好一个终态（done / finished / error / cancelled / timeout）。
 * - 有界缓冲 + 断连即取消，页面卸载时由调用方 cancel() 释放 reader。
 */
import { CONFIG } from '@/config';
import { ApiClientError, toApiClientError } from './decoder';

/** ChatStreamRequest 之外显式带上隔离维度（F0-06）。 */
export type ChatStreamBody = API.ChatStreamRequest & {
  character_id?: string;
};

export interface StreamHandlers {
  onChunk?: (frame: UI.StreamFrame) => void;
  onProgress?: (frame: UI.StreamFrame) => void;
  onToolStatus?: (frame: UI.StreamFrame) => void;
  onDone?: (frame: UI.StreamFrame) => void;
  onError?: (err: ApiClientError, frame?: UI.StreamFrame) => void;
  onCancelled?: (reason: string) => void;
  onWarning?: (message: string) => void;
}

export interface StreamHandle {
  requestId: string;
  cancel: (reason?: string) => void;
  finished: Promise<void>;
}

export interface StreamOptions {
  requestId?: string;
  /** 客户端 deadline，默认沿用 CONFIG.env.TIMEOUT */
  timeoutMs?: number;
}

const MAX_BUFFER_CHARS = 64 * 1024;
const TERMINALS = new Set(['done', 'finished', 'error', 'cancelled', 'timeout']);

function newRequestId(): string {
  const c = globalThis.crypto;
  if (c && typeof c.randomUUID === 'function') return c.randomUUID();
  return `req_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`;
}

function jsonParse(text: string): Record<string, any> | null {
  try {
    const v = JSON.parse(text);
    return v && typeof v === 'object' ? (v as Record<string, any>) : null;
  } catch {
    return null;
  }
}

/** 解析一个 SSE 帧：兼容带 `event:` 行与旧客户端只有 `data:` 的两种形态。 */
function parseFrame(raw: string): UI.StreamFrame | null {
  const lines = raw.replace(/\r/g, '').split('\n');
  let eventName = '';
  const dataLines: string[] = [];
  for (const line of lines) {
    if (!line || line.startsWith(':')) continue;
    if (line.startsWith('event:')) eventName = line.slice(6).trim();
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart());
  }
  if (!dataLines.length) return null;
  const payload = jsonParse(dataLines.join('\n'));
  if (!payload) return null;
  return { ...payload, event: eventName || String(payload.type || 'chunk') } as UI.StreamFrame;
}

export function openChatStream(
  body: ChatStreamBody,
  handlers: StreamHandlers = {},
  options: StreamOptions = {}
): StreamHandle {
  const requestId = options.requestId || newRequestId();
  const timeoutMs = options.timeoutMs ?? CONFIG.env.TIMEOUT;
  const controller = new AbortController();

  let settled = false;
  let cancelReason = '';
  let timedOut = false;
  let streamId = '';
  let lastSeq = -1;
  let timer: number | null = null;
  let resolveFinished: () => void = () => undefined;
  const finished = new Promise<void>((resolve) => {
    resolveFinished = resolve;
  });

  const warn = (msg: string) => handlers.onWarning?.(msg);

  const finish = () => {
    if (settled) return;
    settled = true;
    if (timer !== null) {
      clearTimeout(timer);
      timer = null;
    }
    resolveFinished();
  };

  const cancel = (reason = 'user') => {
    if (settled) return;
    cancelReason = reason;
    controller.abort();
    finish();
    handlers.onCancelled?.(reason);
  };

  /** 归属校验：迟到/串线的帧一律丢弃，绝不写入当前会话。 */
  const belongs = (frame: UI.StreamFrame): boolean => {
    if (settled) return false;
    if (frame.request_id && frame.request_id !== requestId) {
      warn('收到非本请求的流事件，已丢弃');
      return false;
    }
    if (frame.stream_id) {
      if (!streamId) streamId = frame.stream_id;
      else if (frame.stream_id !== streamId) {
        warn('stream_id 与当前流不一致，已丢弃');
        return false;
      }
    }
    if (typeof frame.seq === 'number') {
      if (frame.seq <= lastSeq) warn(`流帧乱序 seq=${frame.seq}`);
      else if (lastSeq >= 0 && frame.seq > lastSeq + 1) warn(`流帧缺帧 seq=${frame.seq}`);
      lastSeq = Math.max(lastSeq, frame.seq);
    }
    return true;
  };

  const dispatch = (frame: UI.StreamFrame) => {
    const name = frame.event || 'chunk';
    switch (name) {
      case 'chunk':
      case 'pending':
        handlers.onChunk?.(frame);
        break;
      case 'progress':
        handlers.onProgress?.(frame);
        break;
      case 'tool.status':
      case 'tool.result':
      case 'task.update':
        // 工具结果 / 任务更新绝不拼进 assistant 正文（F1-04）
        handlers.onToolStatus?.(frame);
        break;
      case 'done':
      case 'finished':
        handlers.onDone?.(frame);
        finish();
        break;
      case 'cancelled':
        handlers.onCancelled?.('server');
        finish();
        break;
      case 'timeout':
        handlers.onError?.(
          new ApiClientError({
            kind: 'timeout',
            code: 2002,
            status: 504,
            requestId,
            message: '服务端流超时，请查询任务状态',
          }),
          frame
        );
        finish();
        break;
      case 'error': {
        const detail = (frame.error || {}) as { code?: number; kind?: string; message?: string };
        handlers.onError?.(
          new ApiClientError({
            kind: (detail.kind as ApiClientError['kind']) || 'internal',
            code: detail.code ?? frame.code ?? 3001,
            requestId,
            message: detail.message || '流式处理失败',
          }),
          frame
        );
        finish();
        break;
      }
      default:
        if (TERMINALS.has(name)) finish();
        else handlers.onChunk?.(frame);
    }
  };

  const run = async () => {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      'X-Requested-With': 'XMLHttpRequest',
      Accept: 'text/event-stream',
      'X-Request-Id': requestId,
    };
    const token = localStorage.getItem('token');
    if (token) headers.Authorization = `Bearer ${token}`;

    timer = window.setTimeout(() => {
      if (settled) return;
      timedOut = true;
      controller.abort();
      finish();
      handlers.onError?.(
        new ApiClientError({
          kind: 'timeout',
          code: 2002,
          status: 504,
          requestId,
          message: '请求超时，请通过任务状态确认是否已执行',
        })
      );
    }, timeoutMs);

    let reader: ReadableStreamDefaultReader<Uint8Array> | null = null;
    try {
      const response = await fetch(`${CONFIG.env.API_BASE_URL}/api/chat/stream`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ ...body, stream: true }),
        signal: controller.signal,
        credentials: 'include',
      });

      if (!response.ok) {
        finish();
        handlers.onError?.(
          new ApiClientError({
            kind: response.status === 503 ? 'not_ready' : 'internal',
            code: response.status,
            status: response.status,
            requestId,
            message: `流式请求失败（HTTP ${response.status}）`,
          })
        );
        return;
      }
      if (!response.body) {
        finish();
        handlers.onError?.(
          new ApiClientError({
            kind: 'network',
            requestId,
            message: '当前环境不支持流式响应，请使用非流式接口',
          })
        );
        return;
      }

      reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (!settled) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        // 有界缓冲：极端情况下截断，避免内存无上限增长
        if (buffer.length > MAX_BUFFER_CHARS) {
          warn('流缓冲超过上限，已截断尾部内容');
          buffer = buffer.slice(-MAX_BUFFER_CHARS);
        }
        let idx = buffer.indexOf('\n\n');
        while (idx !== -1) {
          const raw = buffer.slice(0, idx);
          buffer = buffer.slice(idx + 2);
          const frame = parseFrame(raw);
          if (frame && belongs(frame)) dispatch(frame);
          idx = buffer.indexOf('\n\n');
        }
      }
      // 处理粘连在结尾的最后一个帧
      const tail = parseFrame(buffer);
      if (tail && belongs(tail)) dispatch(tail);

      if (!settled) {
        finish();
        if (!cancelReason && !timedOut) {
          handlers.onError?.(
            new ApiClientError({
              kind: 'network',
              requestId,
              message: '连接提前关闭，已保留已收到的部分输出',
            })
          );
        }
      }
    } catch (err) {
      if (settled) return;
      finish();
      if (cancelReason) handlers.onCancelled?.(cancelReason);
      else if (timedOut) {
        // 超时错误已在 timer 中发出，避免重复通知
      } else handlers.onError?.(toApiClientError(err, { requestId }));
    } finally {
      if (timer !== null) {
        clearTimeout(timer);
        timer = null;
      }
      try {
        reader?.releaseLock();
      } catch {
        // 连接已关闭时忽略
      }
    }
  };

  void run();
  return { requestId, cancel, finished };
}
