<script setup lang="ts">
const model = defineModel<string|number>({ default: '' })
defineProps<{
  placeholder?: string
  disabled?: boolean
  type?: 'text' | 'password'
}>()

const emit = defineEmits<{
  (e: 'change', v: string|number): void
  (e: 'enter', v: string|number): void
}>()

function onInput(e: Event) {
  model.value = (e.target as HTMLInputElement).value
}
function onChange(e: Event) {
  emit('change', (e.target as HTMLInputElement).value)
}
function onEnter(e: KeyboardEvent) {
  emit('enter', (e.target as HTMLInputElement).value)
}
</script>

<template>
  <input
    v-model="model"
    class="text-input"
    :type="type || 'text'"
    :placeholder="placeholder"
    :disabled="disabled"
    @input="onInput"
    @change="onChange"
    @keyup.enter="onEnter"
  >
</template>

<style scoped>
.text-input {
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 12px;
  padding: 15px 20px;
  color: var(--text-color);
  font-size: 14px;
  outline: none;
  transition: border-color 0.2s;
  width: 100%;
  font-family: var(--font-mono);
  box-shadow: inset 0 2px 8px rgba(0, 0, 0, 0.2);
}

.text-input:focus {
  border-color: var(--primary-color);
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
}
</style>
