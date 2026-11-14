<script setup lang="ts">
/**
 * 流状态机展示 —— FrontendPlan F1-01 / F1-02
 * 只显示当前请求的状态；request_id 用于用户反馈与诊断。
 */
import { computed, onUnmounted, ref, watch } from 'vue';

const props = withDefaults(
  defineProps<{
    state: UI.StreamSessionState | null;
    phase?: UI.StreamPhase;
  }>(),
  { phase: 'idle' }
);

const emit = defineEmits<{ cancel: [] }>();

const now = ref(Date.now());
let timer: number | null = null;

const isBusy = computed(
  () => props.phase === 'connecting' || props.phase === 'streaming'
);

// 只在流式中启动 1s 计时器，避免空闲时无谓的定时器与重渲染
watch(
  isBusy,
  (busy) => {
    if (busy && timer === null) {
      timer = window.setInterval(() => (now.value = Date.now()), 1000);
    } else if (!busy && timer !== null) {
      clearInterval(timer);
      timer = null;
    }
  },
  { immediate: true }
);

onUnmounted(() => {
  if (timer !== null) clearInterval(timer);
});

const meta = computed(() => {
  const table: Record<string, { text: string; cls: string; dot: string }> = {
    idle: { text: '空闲', cls: 'idle', dot: '·' },
    connecting: { text: '连接中', cls: 'run', dot: '◌' },
    streaming: { text: '生成中', cls: 'run', dot: '◉' },
    completed: { text: '已完成', cls: 'ok', dot: '✓' },
    failed: { text: '失败', cls: 'err', dot: '✕' },
    cancelled: { text: '已取消', cls: 'warn', dot: '–' },
    detached: { text: '已分离', cls: 'idle', dot: '↗' },
  };
  return table[props.phase] || table.idle!;
});

const elapsed = computed(() => {
  const s = props.state;
  if (!s) return '0.0s';
  const end = s.elapsedMs || (isBusy.value ? now.value - s.startedAt : 0);
  return `${(Math.max(0, end) / 1000).toFixed(1)}s`;
});

const shortRequest = computed(() => (props.state?.requestId || '').slice(0, 8));
</script>

<template>
  <div
    class="stream-status"
    :class="meta.cls"
    role="status"
    aria-live="polite"
  >
    <span class="dot">{{ meta.dot }}</span>
    <span class="text">{{ meta.text }}</span>
    <span
      v-if="state"
      class="metric"
    >seq {{ state.seq }}</span>
    <span
      v-if="state"
      class="metric"
    >{{ state.tokenCount }} 字</span>
    <span
      v-if="state"
      class="metric"
    >{{ elapsed }}</span>
    <span
      v-if="shortRequest"
      class="req"
      :title="state?.requestId"
    >#{{ shortRequest }}</span>
    <button
      v-if="isBusy"
      class="cancel"
      type="button"
      aria-label="取消当前生成"
      @click="emit('cancel')"
    >停止</button>
  </div>
</template>

<style scoped>
.stream-status {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 5px 12px;
  border-radius: 999px;
  font-size: 12px;
  color: var(--text-color);
  background: rgba(0, 14, 39, 0.45);
  border: 1px solid rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(2px);
  white-space: nowrap;
}

.dot {
  font-size: 13px;
  opacity: 0.9;
}

.run .dot {
  color: #60a5fa;
  animation: pulse 1.2s ease-in-out infinite;
}

.ok .dot {
  color: #4ade80;
}

.err .dot {
  color: #f87171;
}

.warn .dot {
  color: #fbbf24;
}

.text {
  font-weight: 600;
  letter-spacing: 0.5px;
}

.metric,
.req {
  opacity: 0.6;
  font-variant-numeric: tabular-nums;
}

.req {
  font-family: ui-monospace, Menlo, monospace;
}

.cancel {
  margin-left: auto;
  border: 1px solid rgba(255, 255, 255, 0.22);
  background: rgba(244, 67, 54, 0.18);
  color: inherit;
  border-radius: 999px;
  padding: 2px 10px;
  cursor: pointer;
  font-size: 11px;
}

.cancel:hover {
  background: rgba(244, 67, 54, 0.35);
}

@keyframes pulse {
  50% {
    opacity: 0.35;
  }
}
</style>
