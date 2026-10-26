<script setup lang="ts">
type Option = {
  id: string | number
  label: string
} | string | number

const model = defineModel<string | number>({ default: '' })
const props = defineProps<{
  options?: Option[]
  disabled?: boolean
}>()

const emit = defineEmits<{
  (e: 'change', v: string): void
}>()

function onChange(e: Event) {
  const v = (e.target as HTMLSelectElement).value
  // 若原 options 是数字，按类型还原
  const isNum = props.options?.every(o => typeof o === 'number')
  const val: string | number = isNum ? Number(v) : v
  model.value = val
  emit('change', v)
}

const key = (item: Option) => {
  //判断是否是对象，是则返回id，否则返回item
  if (typeof item === 'object' && item !== null) {
    return String(item.id)
  }
  return String(item)
}

const label = (item: Option) => {
  if (typeof item === 'object' && item !== null) {
    return item.label
  }
  return item
}

</script>

<template>
  <select
    v-model="model"
    :disabled="disabled"
    class="w-full px-3 py-2 rounded-lg border border-white/12 bg-white/8 text-white text-sm outline-none focus:border-[var(--primary-color)] backdrop-blur-md"
    @change="onChange"
  >
    <slot />
    <option
      v-for="item in options"
      :key="key(item)"
      :value="key(item)"
      class="bg-[#424141] backdrop-blur-md"
    >{{ label(item) }}</option>
  </select>
</template>
