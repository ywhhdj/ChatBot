<script setup lang="ts">
const props = defineProps<{
  type: 'message' | 'reply';
  role: 'user' | 'assistant';
  content: string;
  // emotionTag: string;
  // emotionText: string;
}>();

const emit = defineEmits(['volume']);
const roleName = computed(() => {
  return props.role === 'user' ? '我' : '千灵';
});
</script>

<template>
  <div
    class="message-item"
    v-if="type === 'message'"
  >
    <div></div>
    <span
      class="role"
      style="font-weight: bold;"
    >{{ roleName }}</span>
    <span> : </span>
    <span>{{ content }}</span>
  </div>
  <div
    class="history-character"
    v-if="type === 'reply'"
  >
    <div
      class="message"
      :title="`情感: `"
    >
      <div>
        <span class="name">{{ roleName(role) }}</span>
        <span class="symbol">:&nbsp</span>
        <span class="content">{{ content }}</span>
        <span class="symbol">&nbsp</span>
      </div>
      <span class="icon">
        <Icon
          icon="volume"
          @click="$emit('volume')"
        />
      </span>
    </div>
  </div>
</template>

<style scoped>
.message-item {
  line-height: 1.2;
  word-wrap: break-word;
  margin-bottom: 5px;
  padding: 30px 12px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  font-size: 12px;
  border-left: 10px solid rgba(var(--primary-color), 0.75);
  box-shadow: 2px 2px 4px rgba(0, 0, 0, 0.25);
  word-break: break-all;
  animation: 'fadeIn 0.3s ease';
}

.play-message {
  cursor: pointer;
  display: inline-block;
  /* 让边框包裹内容 */
}

.character-reply {
  cursor: help;
  display: inline-block;
  /* 让边框包裹内容 */
}

/* 为 isFinal 消息的间隔元素添加样式 */
.final-spacer {
  height: 1em;
  /* 高度约等于一个空行 */
}

span {
  vertical-align: middle;
}

.name {
  font-weight: bold;
}

.symbol {
  font-weight: bold;
}

.icon {
  cursor: pointer;
}

.message {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>