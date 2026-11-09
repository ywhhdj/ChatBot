<script setup lang="ts">
import 'highlight.js/styles/atom-one-dark-reasonable.css'
import hljs from 'highlight.js/lib/core'
import json from 'highlight.js/lib/languages/json'
import javascript from 'highlight.js/lib/languages/javascript'
import typescript from 'highlight.js/lib/languages/typescript'
import plaintext from 'highlight.js/lib/languages/plaintext'

for (const lang of [json, javascript, typescript, plaintext]) {
  hljs.registerLanguage(lang.name, lang)
}
hljs.registerAliases(['js', 'jsx'], { languageName: 'javascript' })
hljs.registerAliases(['ts', 'tsx'], { languageName: 'typescript' })

const props = withDefaults(defineProps<{
  language?: string
  editable?: boolean
  backgroundColor?: string
}>(), {
  language: 'plaintext',
  editable: false,
  backgroundColor: '#282c34',
})

const model = defineModel<string>({ default: '' })

function handleInput(e: Event) {
  model.value = (e.target as HTMLElement).textContent || ''
}

const highlightedCode = computed(() => {
  try {
    const lang = hljs.getLanguage(props.language) ? props.language : 'plaintext'
    return hljs.highlight(model.value, { language: lang }).value
  } catch {
    return model.value
  }
})

async function copyCode() {
  await navigator.clipboard.writeText(model.value)
}
</script>

<template>
  <header class="header">
    <span class="language">{{ language }}</span>
    <span
      class="copy-btn"
      @click="copyCode"
    >复制</span>
  </header>

  <div
    class="hljs"
    :style="{ background: backgroundColor }"
  >
    <div class="code-container">
      <!-- 展示态：高亮渲染 -->
      <code
        v-if="!editable"
        class="code-content"
        v-html="highlightedCode"
      />
      <!-- 编辑态：纯文本 -->
      <code
        v-else
        class="code-content"
        contenteditable
        @input="handleInput"
      >{{ model }}</code>
    </div>
  </div>
</template>

<style scoped>
.hljs {
  margin: 0;
  padding: 0;
  border-radius: 8px;
  width: 100%;
}

.copy-btn {
  background: transparent;
  color: #fff;
  border: none;
  cursor: pointer;
  outline: none;
}

.header {
  border-radius: 10px 10px 0 0;
  padding: 10px 16px 8px 16px;
  border-top: 1px solid #545151;
  border-left: 1px solid #545151;
  border-right: 1px solid #545151;
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  background-color: #303030;
}

.code-container {
  padding: 16px;
  overflow-x: hidden;
  border-left: 1px solid #545151;
  border-right: 1px solid #545151;
  border-bottom: 1px solid #545151;
  overflow-y: auto;
  background-color: #1d1d1d;
  border-radius: 0 0 10px 10px;
}

.hljs,
.code-content {
  white-space: pre-wrap;
  /* 保留缩进，但允许软换行 */
  overflow-wrap: break-word;
  /* 超长单词/URL 才强制断行 */
  word-break: normal;
  /* 不要 break-all，否则标点也乱断 */
}

.language {
  color: #fff;
}

.code-content {
  border: none;
  outline: none;
}
</style>
