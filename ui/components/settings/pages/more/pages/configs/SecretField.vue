<script setup lang="ts">
/**
 * 秘密字段规则 —— FrontendPlan F2-02 / FrontendDesign §8
 * provider key 不回显、不持久化、不进入 console / URL / 错误通知。
 * 值只存在于组件内存，提交后立即清空，卸载时兜底清空。
 */
import { onBeforeUnmount, ref } from 'vue';

const props = withDefaults(
  defineProps<{
    label: string;
    placeholder?: string;
    hint?: string;
    disabled?: boolean;
  }>(),
  {
    placeholder: '粘贴密钥（不会回显）',
    hint: '仅本次会话生效；不回显、不持久化、不写入日志与 URL',
    disabled: false,
  }
);

const emit = defineEmits<{
  commit: [value: string];
  'update:modelValue': [value: string];
}>();

// 即便父组件传入了旧值，也绝不回填到输入框
const value = ref('');
const revealed = ref(false);

function clear() {
  value.value = '';
  emit('update:modelValue', '');
}

function commit() {
  const v = value.value;
  if (!v) return;
  emit('update:modelValue', v);
  emit('commit', v);
  // 内存即焚：组件不保留任何密钥副本
  value.value = '';
}

onBeforeUnmount(() => {
  value.value = '';
});
</script>

<template>
  <label class="secret-field">
    <span class="label">{{ label }}</span>
    <div class="row">
      <input
        v-model="value"
        class="input"
        :type="revealed ? 'text' : 'password'"
        :placeholder="placeholder"
        :disabled="disabled"
        autocomplete="new-password"
        spellcheck="false"
        aria-label="敏感配置输入"
        @keyup.enter="commit"
      />
      <button
        class="mini"
        type="button"
        :aria-label="revealed ? '隐藏' : '显示'"
        @click="revealed = !revealed"
      >{{ revealed ? '隐藏' : '显示' }}</button>
      <button
        class="mini"
        type="button"
        @click="clear"
      >清空</button>
      <button
        class="mini primary"
        type="button"
        :disabled="!value || disabled"
        @click="commit"
      >应用</button>
    </div>
    <span class="hint">{{ hint }}</span>
  </label>
</template>

<style scoped>
.secret-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 12px;
  color: var(--text-color);
}

.label {
  font-weight: 600;
}

.row {
  display: flex;
  gap: 6px;
  align-items: center;
}

.input {
  flex: 1;
  min-width: 0;
  border: 1px solid rgba(255, 255, 255, 0.16);
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.25);
  color: inherit;
  padding: 6px 10px;
  font-family: ui-monospace, Menlo, monospace;
  outline: none;
}

.input:focus {
  border-color: rgba(59, 130, 246, 0.6);
}

.mini {
  border: 1px solid rgba(255, 255, 255, 0.16);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.06);
  color: inherit;
  cursor: pointer;
  padding: 5px 10px;
  font-size: 11px;
}

.mini:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.mini.primary {
  background: rgba(59, 130, 246, 0.22);
  border-color: rgba(59, 130, 246, 0.4);
}

.hint {
  opacity: 0.55;
  font-size: 11px;
}
</style>
