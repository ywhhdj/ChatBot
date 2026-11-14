<script setup lang="ts">
/**
 * 长操作状态条 —— FX-05 / FrontendPlan「存档交互状态」
 * 只根据服务端 operation/task 状态更新 UI；partial_failure 必须显式警告，
 * 不能当作普通失败 toast 隐藏。
 */
import { computed } from 'vue';
import type { OperationFetcher } from '@/composables/useOperation';
import { useOperation } from '@/composables/useOperation';
import { errorView } from '@/api/decoder';
import AsyncState from '@/components/common/AsyncState.vue';

const props = withDefaults(
  defineProps<{
    operationId?: string | null;
    label?: string;
    fetcher?: OperationFetcher;
    showCancel?: boolean;
  }>(),
  {
    operationId: null,
    label: '后台操作',
    showCancel: true,
  }
);

const emit = defineEmits<{
  settled: [snapshot: UI.OperationSnapshot];
  error: [err: UI.AsyncErrorView];
}>();

const { snapshot, error, isTerminal, cancel } = useOperation(
  () => props.operationId,
  {
    fetcher: props.fetcher,
    onSettled: (s) => emit('settled', s),
    onError: (err) => {
      const view = errorView(err);
      if (view) emit('error', view);
    },
  }
);

const meta = computed(() => {
  const phase = snapshot.value?.phase || 'idle';
  const table: Record<string, { text: string; cls: string }> = {
    idle: { text: '等待', cls: 'idle' },
    pending: { text: '排队中', cls: 'idle' },
    running: { text: '执行中', cls: 'run' },
    validating: { text: '校验中', cls: 'run' },
    restoring: { text: '恢复中', cls: 'run' },
    succeeded: { text: '已完成', cls: 'ok' },
    failed: { text: '失败', cls: 'err' },
    cancelled: { text: '已取消', cls: 'warn' },
    timeout: { text: '超时', cls: 'warn' },
    rolled_back: { text: '已回滚', cls: 'warn' },
    partial_failure: { text: '部分失败', cls: 'warn' },
  };
  return table[phase] || { text: phase, cls: 'idle' };
});

const isPartial = computed(() => snapshot.value?.phase === 'partial_failure');
const elapsed = computed(() => {
  const s = snapshot.value;
  if (!s) return 0;
  return Math.max(0, Math.round((s.updatedAt - s.startedAt) / 1000));
});

defineExpose({ snapshot, cancel });
</script>

<template>
  <section
    v-if="operationId"
    class="operation"
    :class="meta.cls"
    aria-live="polite"
  >
    <header class="op-head">
      <span class="op-label">{{ label }}</span>
      <span class="op-badge">{{ meta.text }}</span>
      <span class="op-id">{{ operationId }}</span>
      <span class="op-time">{{ elapsed }}s</span>
      <button
        v-if="showCancel && !isTerminal"
        class="op-btn"
        type="button"
        @click="cancel('ui')"
      >取消</button>
    </header>

    <div class="op-bar">
      <div
        class="op-fill"
        :style="{ width: `${snapshot?.percent || 0}%` }"
      />
    </div>

    <div
      v-if="snapshot?.message"
      class="op-message"
    >{{ snapshot.message }}</div>

    <!-- partial_failure 是明确的状态，不是普通 toast -->
    <AsyncState
      v-if="isPartial"
      compact
      state="error"
      :error="{
        title: '恢复未完全成功',
        message: '部分内容已恢复，其余已回滚。请查看下方操作记录，勿当作普通失败忽略。',
        retryable: false,
      }"
    />

    <ul
      v-if="snapshot?.warnings?.length"
      class="op-warnings"
    >
      <li
        v-for="(w, i) in snapshot.warnings"
        :key="i"
      >{{ w }}</li>
    </ul>

    <div
      v-if="error"
      class="op-error"
    >状态查询失败：{{ error.message }}</div>
  </section>
</template>

<style scoped>
.operation {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 14px;
  border-radius: 10px;
  color: var(--text-color);
  background: rgba(0, 14, 39, 0.45);
  border: 1px solid rgba(255, 255, 255, 0.1);
  font-size: 12px;
}

.op-head {
  display: flex;
  align-items: center;
  gap: 10px;
}

.op-label {
  font-weight: 600;
}

.op-badge {
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.1);
}

.run .op-badge {
  background: rgba(96, 165, 250, 0.25);
  color: #bfdbfe;
}

.ok .op-badge {
  background: rgba(74, 222, 128, 0.22);
  color: #bbf7d0;
}

.err .op-badge {
  background: rgba(248, 113, 113, 0.22);
  color: #fecaca;
}

.warn .op-badge {
  background: rgba(251, 191, 36, 0.24);
  color: #fde68a;
}

.op-id {
  opacity: 0.5;
  font-family: ui-monospace, Menlo, monospace;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 220px;
}

.op-time {
  margin-left: auto;
  opacity: 0.6;
  font-variant-numeric: tabular-nums;
}

.op-btn {
  border: 1px solid rgba(255, 255, 255, 0.18);
  border-radius: 6px;
  background: transparent;
  color: inherit;
  padding: 3px 10px;
  cursor: pointer;
}

.op-btn:hover {
  background: rgba(255, 255, 255, 0.1);
}

.op-bar {
  height: 4px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.1);
  overflow: hidden;
}

.op-fill {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, var(--primary-color), #6ee7d7);
  transition: width 0.3s ease;
}

.op-message,
.op-error {
  opacity: 0.75;
  word-break: break-all;
}

.op-error {
  color: #fecaca;
}

.op-warnings {
  margin: 0;
  padding-left: 16px;
  max-height: 120px;
  overflow-y: auto;
  color: #fde68a;
}

:deep(.async-state) {
  height: auto;
}
</style>
