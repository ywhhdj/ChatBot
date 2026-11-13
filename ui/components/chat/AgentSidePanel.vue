<!-- AgentSidePanel.vue -->
<script setup lang="ts">

const props = defineProps<{
  visible: boolean;
  messages: UI.ChatMessage[]
}>();
const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
}>();

const measureVersion = ref(0);
const listRef = ref<any>(null);

// 扁平化：user/纯文本 -> markdown块；assistant 多工具 -> 步骤组块 + 文本块
const blocks = computed<UI.PanelBlock[]>(() => {
  const out: UI.PanelBlock[] = []
  for (const m of props.messages) {
    if (m.role === 'user') {
      out.push({
        id: `u_${m.id}`,
        kind: 'markdown',
        messageId: m.id,
        content: m.content
      });
      continue;
    }
    // assistant/system
    if (m.tools && m.tools.length >= 3) {
      out.push({ id: `ts_${m.id}`, kind: 'tool-summary', messageId: m.id, tools: m.tools })
    } else if (m.tools && m.tools.length) {
      for (const t of m.tools) {
        out.push({
          id: `t_${m.id}_${t.id}`,
          kind: 'tool',
          messageId: m.id,
          tool: t
        });
      }
    }
    if (m.content && m.content.trim()) {
      out.push({
        id: `md_${m.id}`,
        kind: 'markdown',
        messageId: m.id,
        content: m.content
      });
    }
  }
  return out;
})

const sizeDeps = (item: UI.PanelBlock) => {
  if (item.kind === 'markdown') return [item.content]
  if (item.kind === 'tool') return [
    item.tool?.status || '',
    JSON.stringify(item.tool?.result ?? null)
  ]
  return [item.tools?.map(
    t => t?.status || '' + (t?.id || '')
  ).join('|')]
}

// 字体/主题加载完再重测，避免首次高度偏差
onMounted(async () => {
  await document.fonts?.ready
  measureVersion.value++
})

// 新消息/流式追加后吸底
watch(
  () => blocks.value.length + ':' + props.messages[props.messages.length - 1]?.content,
  async () => {
    await nextTick()
    listRef.value?.scrollToBottom?.()
  }
)

defineExpose({
  refreshMeasure: () => (measureVersion.value++)
})
</script>

<template>
  <SidePanel
    :visible="visible"
    position="right"
    width="420px"
    @update:visible="emit('update:visible', $event)"
  >
    <template #header>
      <div class="panel-title">后台任务Agent</div>
    </template>

    <VirtualList
      ref="listRef"
      class="agent-scroller"
      :items="blocks"
      :measure="true"
      :item-size="72"
      key-field="id"
      :size-dependencies="sizeDeps"
      :measure-version="measureVersion"
      :sticky="true"
      :sticky-threshold="60"
      height="100%"
    >
      <template #default="{ item }">
        <div
          class="panel-block"
          :class="item.kind"
        >
          <Markdown
            v-if="item.kind === 'markdown'"
            :content="item.content"
          />
          <ToolCallCard
            v-else-if="item.kind === 'tool'"
            :tool="item.tool"
          />
          <ToolStepGroup
            v-else-if="item.kind === 'tool-summary'"
            :tools="item.tools"
          />
        </div>
      </template>
    </VirtualList>
  </SidePanel>
</template>

<style scoped>
.panel-title {
  font-weight: 600;
}

.agent-scroller {
  color: var(--text-color);
  font-size: 16px;
  font-family: var(--font-family);
  height: 100%;
}

.panel-block {
  padding: 10px 12px;
}

.panel-block.markdown {
  /* 让 v-html 文本块有最大宽度，参考阅读区 */
  max-width: 860px;
}
</style>