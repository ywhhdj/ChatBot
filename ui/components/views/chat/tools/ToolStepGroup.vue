<!-- ToolStepGroup.vue -->
<script setup lang="ts">
const props = defineProps<{
  tools: UI.ToolCallItem[]
}>()
const expanded = ref(props.tools.length < 3)
const names = computed(() =>
  props.tools.length > 3 ? props.tools.map(t => t.label || `${t.service}.${t.method}`).join('、') + '...' : props.tools.map(t => t.label || `${t.service}.${t.method}`).join('、')
);
</script>

<template>
  <div class="step-group">
    <div
      class="step-bar"
      @click="expanded = !expanded"
    >
      <span class="flex items-center gap-1">
        <Icon
          :size="14"
          icon="code"
        /> {{ tools.length }} 步工具调用
      </span>
      <span class="names">{{ names }}</span>
      <span>{{ expanded ? '▸' : '▾' }}</span>
    </div>
    <div
      v-show="expanded"
      class="step-list"
    >
      <ToolCallCard
        v-for="t in tools"
        :key="t.id"
        :tool="t"
      />
    </div>
  </div>
</template>

<style scoped>
.step-bar {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: flex-start;
  cursor: pointer;
  opacity: .85;
  font-size: 13px;
  padding: 4px 0;
}

.names {
  flex: 1;
  opacity: .6;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.step-list {
  padding: 10px 0;
  border-left: 1px solid #242425;
  padding-left: 10px;
}
</style>