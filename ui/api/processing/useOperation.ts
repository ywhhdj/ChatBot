/**
 * operation_id / task_id 轮询 —— FX-05 / FrontendPlan「存档交互状态」
 *
 * 只做「查询」，绝不因为超时就自动重发非幂等 POST：
 * 前端只根据服务端 operation 状态更新 UI，终态后停止轮询并释放定时器。
 */
import { computed, onScopeDispose, ref, shallowRef, watch, type ComputedRef } from 'vue';
import { taskService } from '@/api/services/task';
import { ApiClientError, toApiClientError } from '@/api/decoder';

export interface OperationResult {
  state?: string;
  percent?: number;
  message?: string;
  warnings?: string[];
  result?: Record<string, any> | null;
  error?: string | null;
}

export type OperationFetcher = (operationId: string) => Promise<OperationResult>;

export interface UseOperationOptions {
  fetcher?: OperationFetcher;
  pollMinMs?: number;
  pollMaxMs?: number;
  /** 轮询总上限，超时按 terminal 处理，避免定时器永久驻留 */
  maxDurationMs?: number;
  onSettled?: (snapshot: UI.OperationSnapshot) => void;
  onError?: (err: ApiClientError) => void;
}

const TERMINAL = new Set([
  'succeeded', 'done', 'completed', 'restored', 'committed',
  'failed', 'error', 'cancelled', 'timeout', 'rolled_back', 'partial_failure',
]);

const PHASE_MAP: Record<string, UI.OperationPhase> = {
  idle: 'idle',
  pending: 'pending',
  creating: 'pending',
  queued: 'pending',
  running: 'running',
  validating: 'validating',
  restoring: 'restoring',
  preparing: 'restoring',
  succeeded: 'succeeded',
  done: 'succeeded',
  completed: 'succeeded',
  restored: 'succeeded',
  committed: 'succeeded',
  failed: 'failed',
  error: 'failed',
  cancelled: 'cancelled',
  timeout: 'timeout',
  rolled_back: 'rolled_back',
  partial_failure: 'partial_failure',
};

/** 默认走 GET /api/task/{task_id}，与后端 TaskStatusData.state 对齐。 */
const defaultFetcher: OperationFetcher = async (id) => {
  const data = await taskService.getTask(id);
  return {
    state: data.state,
    result: (data.result as Record<string, any>) ?? null,
    error: data.error ?? null,
    message: data.error || '',
  };
};

export function useOperation(
  idSource: () => string | null | undefined,
  options: UseOperationOptions = {}
) {
  const fetcher = options.fetcher || defaultFetcher;
  const pollMinMs = options.pollMinMs ?? 800;
  const pollMaxMs = options.pollMaxMs ?? 5000;
  const maxDurationMs = options.maxDurationMs ?? 600_000;

  const snapshot = shallowRef<UI.OperationSnapshot | null>(null);
  const loading = ref(false);
  const error = shallowRef<ApiClientError | null>(null);
  const isTerminal: ComputedRef<boolean> = computed(
    () => !!snapshot.value && TERMINAL.has(String(snapshot.value.phase))
  );

  let timer: number | null = null;
  let attempt = 0;
  let stopped = false;
  let currentId = '';
  let deadlineAt = 0;

  const stop = () => {
    stopped = true;
    if (timer !== null) {
      clearTimeout(timer);
      timer = null;
    }
  };

  const apply = (id: string, data: OperationResult, startedAt: number) => {
    const phase = PHASE_MAP[String(data.state || 'running')] || 'running';
    const next: UI.OperationSnapshot = {
      operationId: id,
      phase,
      percent: Math.max(0, Math.min(100, Number(data.percent ?? 0))),
      message: data.message || data.error || '',
      warnings: (data.warnings || []).slice(0, 20),
      result: data.result ?? null,
      startedAt,
      updatedAt: Date.now(),
    };
    snapshot.value = next;
    if (TERMINAL.has(phase)) {
      stop();
      options.onSettled?.(next);
    }
  };

  const poll = async (id: string, startedAt: number) => {
    if (stopped || id !== currentId) return;
    if (Date.now() > deadlineAt) {
      apply(id, { state: 'timeout', message: '操作状态查询超时' }, startedAt);
      return;
    }
    loading.value = true;
    try {
      const data = await fetcher(id);
      if (stopped || id !== currentId) return;
      error.value = null;
      attempt = 0;
      apply(id, data, startedAt);
    } catch (err) {
      if (stopped || id !== currentId) return;
      const apiErr = toApiClientError(err);
      error.value = apiErr;
      options.onError?.(apiErr);
      // 查询失败按指数退避继续，不把客户端猜测当成服务端终态
      attempt += 1;
    } finally {
      loading.value = false;
    }
    if (!stopped && !isTerminal.value) {
      const delay = Math.min(pollMaxMs, pollMinMs * 2 ** Math.min(attempt, 3));
      timer = window.setTimeout(() => void poll(id, startedAt), delay);
    }
  };

  const start = (id: string) => {
    stop();
    stopped = false;
    currentId = id;
    attempt = 0;
    deadlineAt = Date.now() + maxDurationMs;
    error.value = null;
    snapshot.value = {
      operationId: id,
      phase: 'pending',
      percent: 0,
      message: '',
      warnings: [],
      startedAt: Date.now(),
      updatedAt: Date.now(),
    };
    void poll(id, snapshot.value.startedAt);
  };

  const cancel = async (reason = 'ui') => {
    if (!currentId) return;
    // 取消是幂等操作，按钮在 UI 层禁用防止连点
    try {
      await taskService.cancelTask(currentId, { reason });
      if (!stopped) void poll(currentId, snapshot.value?.startedAt || Date.now());
    } catch (err) {
      const apiErr = toApiClientError(err);
      error.value = apiErr;
      options.onError?.(apiErr);
    }
  };

  watch(
    () => idSource(),
    (id) => {
      if (id) start(id);
      else {
        stop();
        snapshot.value = null;
        currentId = '';
      }
    },
    { immediate: true }
  );

  onScopeDispose(stop);

  return { snapshot, loading, error, isTerminal, start, stop, cancel };
}
