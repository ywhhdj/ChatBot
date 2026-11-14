/**
 * 统一响应解码器 —— FrontendPlan F0-01 / F0-04 / FX-01
 *
 * REST(Axios)、SSE、Qt WebChannel bridge 共用同一份信封判定与错误对象。
 * 后端成功业务码统一为 200；底层只抛出类型化错误，不弹通知、不猜测第二层 data。
 * 通知由 View / composable 层决定何时提示，取消与超时必须单独分类。
 */
export type ApiErrorKind =
  | 'validation'
  | 'not_found'
  | 'conflict'
  | 'not_ready'
  | 'timeout'
  | 'cancelled'
  | 'network'
  | 'internal';

export interface ApiEnvelope<T = unknown> {
  ok?: boolean;
  code?: number;
  message?: string;
  data?: T | null;
  request_id?: string;
  ts?: number;
}

export interface ApiClientErrorInit {
  kind: ApiErrorKind;
  code?: number;
  status?: number;
  requestId?: string;
  message: string;
  retryable?: boolean;
  cause?: unknown;
}

/** 稳定错误对象：不携带堆栈、绝对路径与内部配置。 */
export class ApiClientError extends Error {
  readonly kind: ApiErrorKind;
  readonly code: number;
  readonly status?: number;
  readonly requestId?: string;
  readonly retryable: boolean;

  constructor(init: ApiClientErrorInit) {
    super(safeMessage(init.message));
    this.name = 'ApiClientError';
    this.kind = init.kind;
    this.code = init.code ?? 0;
    this.status = init.status;
    this.requestId = init.requestId;
    this.retryable = init.retryable ?? defaultRetryable(init.kind);
    if (init.cause !== undefined) {
      (this as Error & { cause?: unknown }).cause = init.cause;
    }
  }
}

function defaultRetryable(kind: ApiErrorKind): boolean {
  // 仅网络抖动 / 明确未就绪可考虑有限重试；非幂等 POST 由调用方另行判断。
  return kind === 'network' || kind === 'not_ready';
}

/** 用户可见文本：截断并去掉常见的堆栈、绝对路径痕迹。 */
function safeMessage(message: string): string {
  const text = String(message || '请求失败')
    .replace(/\s+at\s+\S+:\d+:\d+/g, '')
    .replace(/[A-Za-z]:\\[^\s]+|\/(?:home|Users|root|tmp)\/[^\s]+/g, '[path]')
    .trim();
  return text.length > 200 ? `${text.slice(0, 200)}…` : text;
}

function kindFromCode(code: number, status?: number): ApiErrorKind {
  switch (code) {
    case 1001:
      return 'validation';
    case 1002:
      return 'not_found';
    case 1003:
      return 'conflict';
    case 2001:
      return 'not_ready';
    case 2002:
      return 'timeout';
    case 3001:
      return 'internal';
    default:
      break;
  }
  if (status === 404) return 'not_found';
  if (status === 409 || status === 401 || status === 403) return 'conflict';
  if (status === 503) return 'not_ready';
  if (status === 504) return 'timeout';
  if (status && status >= 500) return 'internal';
  if (status && status >= 400) return 'validation';
  return 'internal';
}

export function isEnvelope(value: unknown): value is ApiEnvelope<unknown> {
  return (
    typeof value === 'object' &&
    value !== null &&
    ('ok' in value || ('code' in value && 'data' in value))
  );
}

/**
 * 解包一次。成功条件与 src/api/http.ts 保持一致：ok === true && code === 200。
 * 已解包的裸数据（bridge 适配后的返回值）原样返回，避免二次猜测。
 */
export function decodeEnvelope<T>(
  raw: unknown,
  ctx: { status?: number; requestId?: string } = {}
): T {
  if (!isEnvelope(raw)) return raw as T;

  const env = raw as ApiEnvelope<T>;
  if (env.ok === true && env.code === 200) {
    return (env.data ?? null) as T;
  }

  const code = env.code ?? ctx.status ?? 500;
  throw new ApiClientError({
    kind: kindFromCode(code, ctx.status),
    code,
    status: ctx.status,
    requestId: env.request_id || ctx.requestId,
    message: env.message || '请求失败',
  });
}

/** 把 fetch / axios / bridge 抛出的任意错误收敛成同一个 ApiClientError。 */
export function toApiClientError(
  err: unknown,
  ctx: { status?: number; requestId?: string } = {}
): ApiClientError {
  if (err instanceof ApiClientError) return err;

  const e = err as { name?: string; message?: string; code?: number; status?: number } | null;
  const name = e?.name || '';
  const message = e?.message || '请求失败';

  if (name === 'AbortError' || name === 'CanceledError' || message.includes('user cancelled')) {
    return new ApiClientError({
      kind: 'cancelled',
      status: ctx.status,
      requestId: ctx.requestId,
      message: '已取消',
      retryable: false,
      cause: err,
    });
  }
  if (name === 'TimeoutError' || message.includes('timeout')) {
    return new ApiClientError({
      kind: 'timeout',
      status: 504,
      requestId: ctx.requestId,
      message: '处理超时，请通过任务状态确认是否已执行',
      cause: err,
    });
  }
  if (err instanceof TypeError || name === 'NetworkError' || message.includes('Failed to fetch')) {
    return new ApiClientError({
      kind: 'network',
      status: ctx.status,
      requestId: ctx.requestId,
      message: '网络连接不可用',
      cause: err,
    });
  }
  return new ApiClientError({
    kind: kindFromCode(e?.code ?? 0, e?.status ?? ctx.status),
    code: e?.code ?? 0,
    status: e?.status ?? ctx.status,
    requestId: ctx.requestId,
    message,
    cause: err,
  });
}

/** 供 UI 展示：隐藏内部细节，只保留可诊断的 request_id。 */
export function errorView(err: ApiClientError | null): UI.AsyncErrorView | null {
  if (!err) return null;
  return {
    title: err.kind === 'cancelled' ? '已取消' : '请求失败',
    message: err.message,
    requestId: err.requestId,
    kind: err.kind,
    retryable: err.retryable,
  };
}
