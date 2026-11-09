<script setup lang="ts">
const props = defineProps<{
  tool: UI.ToolCallItem;
  compact?: boolean;
}>()
const expanded = ref(false)

const statusMeta = computed(() => {
  switch (props.tool.status) {
    case 'running':
      return {
        text: '执行中',
        cls: 'run',
        icon: '◌'
      }
    case 'success':
      return {
        text: '成功',
        cls: 'ok',
        icon: '✓'
      }
    case 'error':
      return {
        text: '失败',
        cls: 'err',
        icon: '✕'
      }
    case 'skipped':
      return {
        text: '已跳过',
        cls: 'skip',
        icon: '–'
      }
    default:
      return {
        text: '等待',
        cls: 'wait',
        icon: '•'
      }
  }
})

const previewResult = computed(() => {
  const r = props.tool.result
  if (r == null) return ''
  try {
    const s = typeof r === 'string' ? r : JSON.stringify(r)
    return s.length > 120 ? s.slice(0, 120) + '…' : s
  } catch {
    return String(r)
  }
})
</script>

<template>
  <div
    class="tool-card"
    :class="statusMeta.cls"
  >
    <div
      class="tool-head"
      @click="expanded = !expanded"
    >
      <span class="tool-icon">{{ statusMeta.icon }}</span>
      <span class="tool-label">{{ tool.label || `${tool.service}.${tool.method}` }}</span>
      <span class="tool-status">{{ statusMeta.text }}</span>
      <span
        v-if="tool.elapsedMs != null"
        class="tool-ms"
      >{{ tool.elapsedMs }}ms</span>
      <span class="tool-toggle">{{ expanded ? '▸' : '▾' }}</span>
    </div>

    <div
      v-show="expanded"
      class="tool-detail flex flex-col gap-1"
    >
      <div class="row">
        <Code
          language="bash"
          :model-value="tool.raw"
        />
      </div>
      <!-- <div
        class="row"
        v-if="tool.result != null"
      >
        <h6>返回</h6>
        <Code
          language="json"
          :model-value="typeof tool.result === 'string' ? tool.result : JSON.stringify(tool.result, null, 2)"
        />
      </div> -->
      <div
        class="row err"
        v-if="tool.error"
      >
        <code>{{ tool.error }}</code>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tool-card {
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 5px;
  background: rgba(255, 255, 255, 0.03);
  padding: 8px 10px;
  margin: 6px 0;
  font-size: 13px;
}

.tool-head {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.tool-label {
  flex: 1;
}

.tool-status {
  opacity: 0.8;
}

.tool-ms {
  opacity: 0.5;
  font-variant-numeric: tabular-nums;
}

.tool-toggle {
  opacity: 0.6;
  font-size: 12px;
}

.tool-preview {
  margin-top: 6px;
  opacity: 0.7;
  white-space: pre-wrap;
  word-break: break-all;
}

.tool-detail .row {
  margin-top: 6px;
}

.tool-detail pre {
  margin: 4px 0 0;
  max-height: 240px;
  overflow: auto;
  background: rgba(0, 0, 0, 0.25);
  padding: 8px;
  border-radius: 8px;
  font-family: ui-monospace, Menlo, monospace;
}

.ok .tool-icon {
  color: #4ade80;
}

.err .tool-icon {
  color: #f87171;
}

.run .tool-icon {
  color: #60a5fa;
}

.skip .tool-icon {
  color: #fbbf24;
}
</style>