<script lang="ts" setup>
const props = defineProps<{
  checked?: boolean
}>()
const id = ref(`toggle-${Date.now().toString()}`);
const internalChecked = ref(props.checked);

const emit = defineEmits<{
  (e: 'click', value: boolean): void
}>()

watch(() => props.checked, (newVal) => {
  internalChecked.value = newVal;
})

function handleClick(event: Event) {
  const target = event.target as HTMLInputElement;
  internalChecked.value = target.checked;
  emit("click", target.checked);
}
const toggleClass = computed(() => {
  return internalChecked.value
    ? 'border-(--accent-color) bg-[rgba(121,217,255,0.3)] shadow-[0_0_10px_rgba(121,217,255,0.3)]'
    : 'border-white/30 bg-white/20';
});

const colorClass = computed(() => {
  return internalChecked.value
    ? 'left-5.5 bg-linear-to-br from-(--accent-color) to-[#64b5f6] shadow-[0_3px_8px_rgba(121,217,255,0.4),0_1px_3px_rgba(0,0,0,0.2)]'
    : 'left-1 bg-linear-to-br from-white to-[#f0f0f0] shadow-[0_2px_6px_rgba(0,0,0,0.3),0_1px_2px_rgba(0,0,0,0.1)]';
});

</script>

<template>
  <div class="flex items-center cursor-pointer select-none">
    <input
      type="checkbox"
      :id="id"
      :checked="internalChecked"
      @change="handleClick"
      class="hidden"
    />
    <label
      :for="id"
      class="relative cursor-pointer text-white text-[14px] select-none inline-flex items-center"
      style="text-shadow: 0 2px 4px rgba(0, 0, 0, 0.3)"
    >
      <span
        class="relative inline-block w-12.5 h-6.5 rounded-[13px] transition-all duration-300 ease-in-out mr-2"
        :class="toggleClass"
      >
        <span
          class="absolute top-1/2 -translate-y-1/2 w-5 h-5 rounded-full transition-all duration-300 ease-in-out"
          :class="colorClass"
        ></span>
      </span>
      <slot></slot>
    </label>
  </div>
</template>
