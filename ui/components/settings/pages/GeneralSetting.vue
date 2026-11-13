<script setup lang="ts">
import { useUserStore } from '@/stores/user';

const userStore = useUserStore()
// const APIBaseURL = ref('http://115.190.213.187:23817/v1');
// const APIKey = ref('sk-202603031555cheshi');
// const modelList = ref(['gpt5.1']);
// const selectedIndex = ref(0);

const textSpeedChange = (value: number) => {
  userStore.config.textSpeed = value;
};
</script>

<template>
  <MenuItem
    icon="speed"
    title="文字显示速度"
  >
  <Silder
    @change="textSpeedChange"
    :min="0"
    :max="100"
    :step="1"
    :value="userStore.config.textSpeed"
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
      :class="['ws-status', userStore.clientId ? 'connected' : 'disconnected']"
    >
      {{ userStore.clientId ? '√ 已连接' : ' X 未连接' }}
    </span>
  </div>
  <div class="netwok-item">
    <span>重试次数</span>
    <input
      type="number"
      value="3"
    />
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
</style>