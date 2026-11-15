<script setup lang="ts">
/**
 * 输入与发送 —— FrontendPlan F2-04
 * 发送中禁用重复提交、显式取消、有界输入、IME 组合键不误触发送。
 */
import { nextTick, ref, watch } from 'vue';

const props = withDefaults(
  defineProps<{
    modelValue?: string;
    streaming?: boolean;
    disabled?: boolean;
    maxLength?: number;
    placeholder?: string;
  }>(),
  {
    modelValue: '',
    streaming: false,
    disabled: false,
    maxLength: 4000,
    placeholder: '输入内容，Enter 发送，Shift+Enter 换行',
  }
);

const emit = defineEmits<{
  send: [text: string];
  cancel: [];
  'update:modelValue': [value: string];
}>();

const draft = ref(props.modelValue || '');
const textareaRef = ref<HTMLTextAreaElement | null>(null);
const locked = ref(false);

watch(
  () => props.modelValue,
  (v) => {
    if (v !== draft.value) draft.value = v || '';
  }
);

watch(draft, (v) => {
  emit('update:modelValue', v);
  autoResize();
});

function autoResize() {
  nextTick(() => {
    const el = textareaRef.value;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  });
}

function onKeydown(e: KeyboardEvent) {
  // 中文/日文输入法组合期间不把 Enter 当作发送
  if (e.isComposing || (e as KeyboardEvent & { keyCode?: number }).keyCode === 229) return;
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    submit();
  }
}

function submit() {
  const text = draft.value.trim();
  if (!text || locked.value || props.disabled || props.streaming) return;
  locked.value = true;
  emit('send', text);
  draft.value = '';
  autoResize();
  // 极短的防连点窗口：父组件流状态接管后由 streaming 禁用
  window.setTimeout(() => (locked.value = false), 180);
}

function onCancel() {
  emit('cancel');
}

function clear() {
  draft.value = '';
  textareaRef.value?.focus();
}

defineExpose({ focus: () => textareaRef.value?.focus(), clear });
</script>

<template>
  <div class="composer">
    <div class="composer-top">
      <slot name="leading" />
    </div>

    <div class="composer-main">
      <textarea
        ref="textareaRef"
        v-model="draft"
        class="composer-input"
        rows="1"
        :maxlength="maxLength"
        :placeholder="placeholder"
        :disabled="disabled"
        :aria-busy="streaming"
        aria-label="消息输入框"
        @keydown="onKeydown"
      />
      <div class="composer-actions">
        <span class="counter">{{ draft.length }}/{{ maxLength }}</span>
        <button
          v-if="draft.length"
          class="icon-btn ghost"
          type="button"
          aria-label="清空输入"
          @click="clear"
        >清空</button>
        <button
          v-if="streaming"
          class="icon-btn danger"
          type="button"
          @click="onCancel"
        >停止</button>
        <button
          v-else
          class="icon-btn primary"
          type="button"
          :disabled="!draft.trim() || disabled || locked"
          @click="submit"
        >发送 ▼</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.composer {
  width: 100%;
  padding: 12px 16px 14px;
  background: var(--dialog-bg-color);
  border-top: 1px solid rgba(255, 255, 255, 0.18);
  backdrop-filter: blur(1px);
  color: var(--text-color);
}

.composer::before {
  content: '';
  position: absolute;
  top: -40px;
  left: 0;
  right: 0;
  height: 40px;
  background: linear-gradient(to bottom, transparent 0%, rgba(0, 14, 39, 0.3) 50%, rgba(0, 14, 39, 0.6) 100%);
  pointer-events: none;
}

.composer-top {
  display: flex;
  gap: 8px;
  margin-bottom: 6px;
}

.composer-main {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: min(100%, 860px);
  margin: 0 auto;
}

.composer-input {
  width: 100%;
  min-height: 40px;
  max-height: 160px;
  resize: none;
  border: none;
  outline: none;
  background: transparent;
  color: #fff;
  font-size: 16px;
  line-height: 1.6;
  font-family: inherit;
  overflow-y: auto;
}

.composer-input::placeholder {
  color: rgba(255, 255, 255, 0.5);
}

.composer-input:disabled {
  opacity: 0.5;
}

.composer-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}

.counter {
  margin-right: auto;
  font-size: 11px;
  opacity: 0.45;
  font-variant-numeric: tabular-nums;
}

.icon-btn {
  border: 1px solid rgba(255, 255, 255, 0.18);
  border-radius: 8px;
  padding: 5px 14px;
  font-size: 13px;
  color: inherit;
  background: rgba(255, 255, 255, 0.07);
  cursor: pointer;
  transition: all 0.2s ease;
}

.icon-btn:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.16);
}

.icon-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.icon-btn.primary {
  color: rgb(4, 188, 255);
  border-color: rgba(4, 188, 255, 0.4);
}

.icon-btn.danger {
  color: #fca5a5;
  border-color: rgba(248, 113, 113, 0.45);
  background: rgba(244, 67, 54, 0.16);
}

.icon-btn.ghost {
  background: transparent;
  opacity: 0.7;
}

@media (max-width: 768px) {
  .composer {
    padding: 10px;
  }

  .composer-input {
    font-size: 15px;
  }
}
</style>
