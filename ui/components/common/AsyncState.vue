<script setup lang="ts">
/**
 * loading / empty / error / confirm 四态容器 —— FrontendPlan F2-04
 * 高影响操作（删除、恢复、重试）必须先看见状态与明确影响说明。
 * 通知不是异常处理的替代：错误在这里展示，底层 service 不弹窗。
 */
import { nextTick, ref, watch, withDefaults } from 'vue';

type ViewState = 'ready' | 'loading' | 'empty' | 'error' | 'confirm';

const props = withDefaults(
  defineProps<{
    state?: ViewState;
    loadingText?: string;
    emptyText?: string;
    error?: UI.AsyncErrorView | null;
    confirm?: UI.ConfirmView | null;
    retryText?: string;
    compact?: boolean;
  }>(),
  {
    state: 'ready',
    loadingText: '加载中…',
    emptyText: '暂无内容',
    error: null,
    confirm: null,
    retryText: '重试',
    compact: false,
  }
);

const emit = defineEmits<{
  retry: [];
  confirm: [];
  cancel: [];
}>();

const confirmRef = ref<HTMLButtonElement | null>(null);

// 确认态把焦点交给「取消」，避免键盘用户误触高影响操作
watch(
  () => props.state,
  async (state) => {
    if (state !== 'confirm') return;
    await nextTick();
    confirmRef.value?.focus();
  },
  { immediate: true }
);
</script>

<template>
  <div
    class="async-state"
    :class="{ compact }"
  >
    <slot v-if="state === 'ready'" />

    <div
      v-else-if="state === 'loading'"
      class="state-card"
      role="status"
      aria-live="polite"
    >
      <span class="spinner" />
      <span class="state-text">{{ loadingText }}</span>
      <slot name="loading" />
    </div>

    <div
      v-else-if="state === 'empty'"
      class="state-card"
      role="status"
    >
      <span class="state-icon">◇</span>
      <span class="state-text">{{ emptyText }}</span>
      <slot name="empty" />
    </div>

    <div
      v-else-if="state === 'error'"
      class="state-card danger"
      role="alert"
    >
      <div class="state-title">{{ error?.title || '请求失败' }}</div>
      <div class="state-text">{{ error?.message || '请稍后重试' }}</div>
      <div
        v-if="error?.requestId"
        class="request-id"
      >request_id: {{ error.requestId }}</div>
      <button
        v-if="error?.retryable !== false"
        class="state-btn"
        type="button"
        @click="emit('retry')"
      >{{ retryText }}</button>
      <slot name="error" />
    </div>

    <div
      v-else
      class="state-card confirm"
      role="alertdialog"
      aria-modal="true"
      :aria-label="confirm?.title || '请确认'"
    >
      <div class="state-title">{{ confirm?.title || '请确认' }}</div>
      <div class="state-text">{{ confirm?.message || '' }}</div>
      <div class="confirm-actions">
        <button
          ref="confirmRef"
          class="state-btn ghost"
          type="button"
          @click="emit('cancel')"
        >{{ confirm?.cancelText || '取消' }}</button>
        <button
          class="state-btn"
          :class="{ danger: confirm?.danger }"
          type="button"
          @click="emit('confirm')"
        >{{ confirm?.confirmText || '确认' }}</button>
      </div>
      <slot name="confirm" />
    </div>
  </div>
</template>

<style scoped>
.async-state {
  width: 100%;
  height: 100%;
  color: var(--text-color);
}

.state-card {
  height: 100%;
  min-height: 96px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 18px;
  text-align: center;
  border-radius: 12px;
  background: rgba(0, 14, 39, 0.35);
  border: 1px solid rgba(255, 255, 255, 0.08);
  backdrop-filter: blur(2px);
}

.compact .state-card {
  min-height: 64px;
  padding: 10px;
}

.state-title {
  font-size: 15px;
  font-weight: 600;
  color: #f0f4ff;
}

.state-text {
  font-size: 13px;
  opacity: 0.82;
  max-width: 520px;
  line-height: 1.6;
}

.state-icon {
  font-size: 26px;
  opacity: 0.55;
}

.spinner {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: 2px solid rgba(255, 255, 255, 0.18);
  border-top-color: var(--primary-color);
  animation: spin 0.8s linear infinite;
}

.request-id {
  font-family: ui-monospace, Menlo, monospace;
  font-size: 11px;
  opacity: 0.5;
  user-select: all;
}

.state-btn {
  border: 1px solid rgba(255, 255, 255, 0.18);
  background: rgba(255, 255, 255, 0.08);
  color: var(--text-color);
  padding: 6px 16px;
  border-radius: 8px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.state-btn:hover {
  background: rgba(255, 255, 255, 0.16);
}

.state-btn:focus-visible {
  outline: 2px solid var(--primary-color);
  outline-offset: 2px;
}

.state-btn.danger {
  background: rgba(244, 67, 54, 0.35);
  border-color: rgba(244, 67, 54, 0.6);
}

.state-btn.ghost {
  background: transparent;
}

.confirm-actions {
  display: flex;
  gap: 10px;
  margin-top: 4px;
}

.danger {
  border-color: rgba(244, 67, 54, 0.3);
}

.confirm {
  border-color: rgba(251, 191, 36, 0.35);
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
