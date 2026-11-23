<script setup lang="ts">
const props = withDefaults(
  defineProps<{
    tabs: ReadonlyArray<UI.TabItem>;
    modelValue: string;
    ariaLabel?: string;
  }>(),
  { ariaLabel: '页签' }
);

const emit = defineEmits<{
  'update:modelValue': [id: string];
  change: [id: string];
}>();

function select(id: string, disabled?: boolean) {
  if (disabled || id === props.modelValue) return;
  emit('update:modelValue', id);
  emit('change', id);
}
</script>

<template>
  <div
    class="tab-bar"
    role="tablist"
    :aria-label="ariaLabel"
  >
    <Button
      v-for="tab in tabs"
      :key="tab.id"
      type="nav"
      :class="{ 'is-active': modelValue === tab.id }"
      :disabled="tab.disabled"
      :icon="tab.icon"
      role="tab"
      :aria-selected="modelValue === tab.id"
      @click="select(tab.id, tab.disabled)"
    >{{ tab.label }}</Button>
  </div>
</template>

<style scoped>
.tab-bar {
  display: flex;
  gap: 6px;
  padding-bottom: 8px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.16);
}

.tab-bar :deep(button) {
  flex: 1 1 0;
  justify-content: center;
  min-height: 34px;
  font-family: 'Maoken Assorted Sans', -apple-system, BlinkMacSystemFont, sans-serif;
  font-size: 15px;
}

.tab-bar :deep(.is-active) {
  background: rgba(121, 217, 255, 0.18);
  color: var(--primary-color);
}
</style>
