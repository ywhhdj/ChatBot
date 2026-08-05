<script setup lang="ts">
import { useForceLandscape } from '@/composables/useForceLandscape';
import { websocket } from '@/events/event/websocket';
import { useUserStore } from '@/stores/user';
import type { LogForwarder } from '@/plugins/LogForwarder';
import { WebSocketEvent } from '@/typings/enums';
import notification from '@/utils/notification';
import router from '@/router';
import { useTempStore } from './stores/ui';

const tempStore = useTempStore();

const logger = inject<LogForwarder>('logger')
const forceLandscape = new useForceLandscape();
const useUser = useUserStore();
const showNav = computed(() => {
  return router.currentRoute.value.path !== '/' && router.currentRoute.value.path !== '/settings'
})
function registerWebSocketEvents() {

  websocket.registerEventListener(WebSocketEvent.GET_LOG, (data: any) => {
    const record = {
      log_name: data.log_name,
      timestamp: data.timestamp,
      level: data.level,
      message: data.message,
      source: data.source || 'backend',
      metadata: data.metadata,
    }
    logger?.receiveBackendLog(record)
  });
  websocket.registerEventListener(
    WebSocketEvent.CONNECT,
    (data: WebSocketAPI.WebSocketConnectResponse) => {
    useUser.clientId = data.client_id;
    notification.showSuccess({
      title: '连接成功',
      message: '已连接到服务器'
    });
  });
}

function unregisterWebSocketEvents() {
  websocket.removeEventListener(WebSocketEvent.GET_LOG);
  websocket.removeEventListener(WebSocketEvent.CONNECT);
}

function connectWebSocket() {
  const url = import.meta.env.VITE_WS_URL || "ws://localhost:8000/ws";
  websocket.sendCallback = (data: any) => {
    if (data) {
      return {
        ...data,
        client_id: useUser.clientId || "",
      };
    } else {
      return {
        client_id: useUser.clientId || "",
      };
    }
  };
  registerWebSocketEvents();
  websocket.connect(
    url,
    undefined,
    () => {
      useUser.clientId = "";
      notification.showError({
        title: '连接中断',
        message: '连接已中断，请检查后台服务'
      })
    }
  );
}

onMounted(async () => {
  forceLandscape.init();
  await forceLandscape.tryLock();
  connectWebSocket();
});

const clearStore = () => {
  tempStore.musicList.forEach((item) => {
    if (item.url?.startsWith('blob:')) {
      URL.revokeObjectURL(item.url);
    }
  });
  tempStore.bgList.forEach((item) => {
    if (item.url?.startsWith('blob:')) {
      URL.revokeObjectURL(item.url);
    }
  });
  tempStore.bgList = [];
  tempStore.musicList = [];
};

onUnmounted(() => {
  forceLandscape.unlock();
  forceLandscape.destroy();
  unregisterWebSocketEvents();
  clearStore();
});
</script>

<template>
  <HeaderNav v-show="showNav" />
  <div class="bg-group">
    <Notification />
    <BackgroundGroup />
  </div>
  <RouterView class="main-container" />
</template>

<style scoped>
.main-container {
  width: 98%;
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: center;
  overflow: hidden;
}
</style>
