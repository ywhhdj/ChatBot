<script setup lang="ts">
import { useUserStore } from '@/stores/user';

const user = useUserStore();
const history = ref<User.DialogHistory[]>(user.dialogHistory?.["default"] || []);
</script>

<template>
  <MenuItem title="存储路径">
  <div class="save-path">
    <Input
      placeholder="请输入存储路径"
      :value="user.config.historyPath"
      style="height: 50px;"
    />
    <Button>保存</Button>
  </div>
  </MenuItem>
  <MenuItem title="◈ 历史对话">
  <div class="history-container">
    <div
      v-if="history.length === 0"
      class="status-message"
    >
      暂无历史记录，去和ta聊聊天叭(*^▽^*)
    </div>
    <div
      v-else
      class="chat-history-container"
      ref="chatContainer"
    >
      <div
        class="message-item"
        v-for="message in history"
        :key="message.id"
      >
        <HistoryCard
          :type="message.type"
          :role="message.role"
          :content="message.content"
        />
      </div>
    </div>
  </div>
  </MenuItem>
</template>

<style scoped>
.history-container {
  min-height: 400px;
  /* 如果内容过多，可以设置最大高度和滚动条 */
  max-height: 800px;
  overflow-y: auto;
}

.save-path {
  display: flex;
  align-items: center;
  gap: 10px;
}

.chat-history-container {
  padding: 10px;
  display: flex;
  flex-direction: column;
  /* 让消息垂直排列 */
  gap: 12px;
  /* 消息之间的间距 */
  font-size: 18px;
  max-height: 500px;
  /* 如果内容过多，可以设置最大高度和滚动条 */
  overflow-y: auto;
  scroll-behavior: smooth;
}

.status-message {
  display: flex;
  align-items: center;
  justify-content: center;
  color: #f5f5f5;
  padding: 2rem;
  font-size: 24px;
  font-weight: bold;
  height: 100%;
  text-shadow: 0 0 5px rgba(255, 255, 255, 0.5);
}
</style>
