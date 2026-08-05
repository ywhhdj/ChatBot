<script setup lang="ts">
defineProps<{
  value: string;
  options: any[];
}>()
const emit = defineEmits<{
  (e: 'change', value: string): void
}>()
function handleChange(event: Event) {
  const target = event.target as HTMLSelectElement
  emit('change', target.value)
}
</script>

<template>
  <select
    :value="value"
    @change="handleChange"
    name="select"
    id="select"
    class="w-full px-3 py-2 rounded-lg border border-white/12 bg-white/8 text-white text-sm outline-none focus:border-[var(--accent-color)] backdrop-blur-md"
  >
    <slot></slot>
    <option
      class=" bg-[#424141] backdrop-blur-md"
      v-for="(item, index) in options"
      :key="index"
      :value="item"
    >{{ item }}
    </option>
  </select>
</template>
