<script setup lang="ts">
import { marked } from 'marked'

type Block = {
  id: number
  type: 'text' | 'code'
  content?: string
  code?: string
  lang?: string
}

const props = defineProps<{ content: string }>()

const blocks = ref<Block[]>([])
const renderVersion = ref(0)

const parseMarkdownToBlocks = async (md: string): Promise<Block[]> => {
  const tokens = marked.lexer(md)
  const result: Block[] = []
  let textBuffer: string[] = []
  let id = 0

  const flushText = async () => {
    if (!textBuffer.length) return
    const raw = textBuffer.join('')
    let html = marked.parse(raw) as string | Promise<string>
    if (html instanceof Promise) html = await html
    result.push({ id: id++, type: 'text', content: html })
    textBuffer = []
  }

  for (const token of tokens) {
    if (token.type === 'code') {
      await flushText()
      result.push({
        id: id++,
        type: 'code',
        lang: token.lang || 'text',
        code: token.text,
      })
    } else {
      textBuffer.push(token.raw)
    }
  }
  await flushText()
  return result
}

watch(
  () => props.content,
  async (newVal) => {
    blocks.value = await parseMarkdownToBlocks(newVal)
  },
  { immediate: true }
)

// 内容变化 / 字体加载完成 → 强制重新测量所有块
const sizeDeps = (item: Block) =>
  item.type === 'code' ? [item.code] : [item.content]

onMounted(async () => {
  await document.fonts?.ready
  renderVersion.value++
})

const handleCodeChange = (id: number, newCode: string) => {
  const block = blocks.value.find((b) => b.id === id)
  if (block?.type === 'code') block.code = newCode
}
</script>

<template>
  <VirtualList
    class="markdown-scroller"
    :items="blocks"
    :measure="true"
    :item-size="48"
    key-field="id"
    :size-dependencies="sizeDeps"
    :measure-version="renderVersion"
  >
    <template #default="{ item }">
      <div
        v-if="item.type === 'text'"
        class="text-block"
        v-html="item.content"
      />
      <Code
        v-else
        v-model="item.code"
        :language="item.lang || 'text'"
        :editable="false"
        @update:model-value="(val: string) => handleCodeChange(item.id, val)"
      />
    </template>
  </VirtualList>
</template>

<style scoped>
.markdown-scroller {
  height: 100%;
}

/* v-html 出来的元素没有 data-v-xxx，必须用 :deep() */
.text-block :deep(h1) {
  font-size: 2em;
  font-weight: 700;
  margin: 0.67em 0;
}

.text-block :deep(h2) {
  font-size: 1.5em;
  font-weight: 700;
  margin: 0.83em 0;
}

.text-block :deep(h3) {
  font-size: 1.25em;
  font-weight: 600;
  margin: 1em 0;
}

.text-block :deep(h4) {
  font-size: 1em;
  font-weight: 600;
  margin: 1.33em 0;
}

.text-block :deep(h5) {
  font-size: 0.875em;
  font-weight: 600;
  margin: 1.67em 0;
}

.text-block :deep(h6) {
  font-size: 0.85em;
  font-weight: 600;
  margin: 2.33em 0;
}

.text-block :deep(p) {
  margin: 1em 0;
}

.text-block :deep(ul),
.text-block :deep(ol) {
  margin: 1em 0;
  padding-left: 2em;
}

.text-block :deep(li) {
  margin: 0.25em 0;
}

.text-block :deep(blockquote) {
  margin: 1em 0;
  padding-left: 1em;
  border-left: 4px solid #ddd;
  color: #888;
}

.text-block :deep(code) {
  font-family: ui-monospace, Menlo, monospace;
}

.text-block :deep(pre) {
  margin: 1em 0;
}

.text-block :deep(a) {
  color: #4f9cf9;
  text-decoration: underline;
}

.text-block :deep(img) {
  max-width: 100%;
}

.text-block :deep(hr) {
  margin: 1.5em 0;
  border: 0;
  border-top: 1px solid #eee;
}

.text-block :deep(table) {
  border-collapse: collapse;
}

.text-block :deep(th),
.text-block :deep(td) {
  border: 1px solid #ddd;
  padding: 6px 13px;
}
</style>
