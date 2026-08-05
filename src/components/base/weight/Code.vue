<script setup lang="ts">
import "highlight.js/styles/atom-one-dark-reasonable.css"
import hljs from 'highlight.js/lib/core';
const props = defineProps({
  language: {
    type: String,
    default: "json"
  },
  code: {
    type: String,
    default: ""
  },
  editable: {
    type: Boolean,
    default: false
  },
  backgroundColor: {
    type: String,
    default: "#282c34"
  }
})
const code = ref(props.code);
const emit = defineEmits(['code'])

const handleInput = (e: InputEvent) => {
  code.value = (e.target as HTMLElement).textContent || "";
  if (code.value) {
    emit('code', code.value);
  }
}

const highlightedCode = computed(() => hljs.highlight(props.code, { language: props.language }).value.trim())

const typeClass = computed(() => props.language)

const copyCode = () => {
  navigator.clipboard.writeText(code.value).then(() => {
    console.log('复制成功');
  }).catch(() => {
    console.log('复制失败');
  })
}

</script>

<template>
  <pre
    :class="['hljs', typeClass]"
    :style="{ background: props.backgroundColor }"
  >
    <div class="header">
      <span class="language">{{ typeClass }}</span>
      <button class="copy-btn" @click="copyCode">复制</button>
    </div>
    <div style="overflow: auto;" >
      <code class="code-content" v-html="highlightedCode"
      :contenteditable="editable" @input="handleInput" />
    </div>

  </pre>
</template>

<style scoped>
.hljs {
  border-radius: 8px;
  width: 100%;
  height: min-content;
}

.copy-btn {
  background: transparent;
  color: #fff;
  border: none;
  cursor: pointer;
}

.header {
  padding-bottom: 5px;
  padding-left: 10px;
  padding-right: 10px;
  border-color: #666;
  border-bottom: 1px solid #e5e5e5;
  font-size: 14px;
  display: flex;
  justify-content: space-between;
}

.language {
  font-weight: bold;
  color: #fff;
}

.code-content {
  border: none;
  outline: none;
  white-space: pre;

}
</style>
