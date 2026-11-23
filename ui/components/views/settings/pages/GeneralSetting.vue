<script setup lang="ts">
import { CONFIG } from '@/config';
import { useUserStore } from '@/stores/user';

const userStore = useUserStore();

function textSpeedChange(value: number) {
  userStore.config.textSpeed = value;
  userStore.saveConfig();
}
</script>

<template>
  <MenuItem
    icon="speed"
    title="文字显示速度"
  >
    <Silder
      :min="0"
      :max="100"
      :step="1"
      :value="userStore.config.textSpeed"
      @change="textSpeedChange"
    >
      <template #left>慢</template>
      <template #right>快</template>
    </Silder>
  </MenuItem>

  <MenuItem title="📝 显示文字样本">
    <Text :speed="userStore.config.textSpeed">
      你好，我是一个机器人。
    </Text>
  </MenuItem>

  <MenuItem
    icon="communication"
    title="网络状态"
    size="small"
    :disabled="true"
  >
    <div class="netwok-item">
      <span>WebSocket 状态</span>
      <span
        class="ws-status"
        :class="[userStore.clientId ? 'connected' : 'disconnected']"
      >
        {{ userStore.clientId ? '√ 已连接' : ' X 未连接' }}
      </span>
    </div>
    <div class="netwok-item">
      <span>重连上限</span>
      <!-- 真实配置值，只读；不伪造可编辑控件 -->
      <span class="config-value">{{ CONFIG.websocket.maxReconnectAttempts }}</span>
    </div>
  </MenuItem>
</template>

<style scoped>
.netwok-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 2px;
  margin-bottom: 10px;
}

.ws-status {
  text-align: center;
}

.ws-status.connected {
  color: #00ff00;
}

.ws-status.disconnected {
  color: #ff0000;
}

.config-value {
  font-family: ui-monospace, Menlo, monospace;
  opacity: 0.75;
}
</style>
