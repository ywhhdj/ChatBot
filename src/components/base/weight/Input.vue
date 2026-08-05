<script setup lang="ts">
defineProps<{
  value?: string;
  placeholder?: string;
}>()
const emit = defineEmits(['change', 'input']);
const handleChange = (e: Event) => {
  const target = e.target as HTMLInputElement;
  emit('change', target.value)
}
const handleInput = (e: Event) => {
  const target = e.target as HTMLInputElement;
  emit('input', target.value)
}
</script>

<template>
  <input
    :value="value"
    class="text-input"
    type="text"
    @change="handleChange"
    @input="handleInput"
    :placeholder="placeholder"
  >
</template>

<style scoped>
.text-input {
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 8px;
  padding: 6px 12px;
  color: #fff;
  font-size: 14px;
  outline: none;
  transition: border-color 0.2s;
  width: 100%;
}

.text-input:focus {
  border-color: var(--accent-color);
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
}
</style>
