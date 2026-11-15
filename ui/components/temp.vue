<script setup lang="ts">
import notification from '@/utils/notification';

const ServiceConsole = defineAsyncComponent(
  () => import('@/components/views/components/services/ServiceConsole.vue')
);

const router = useRouter();

function onError(view: UI.AsyncErrorView) {
  notification.showError({
    title: view.title || '服务请求失败',
    message: view.message,
  });
}

function goHome() {
  void router.push('/');
}

onBeforeUnmount(() => notification.hideNotification());
</script>

<template>
  <div class="services-page">
    <header class="page-head">
      <AppIcon
        :size="56"
        label="ChatBot 服务管理"
      />
      <div class="page-title">
        <h2>服务管理</h2>
        <span>管理 Live2D · QQBot · OBS 等已注册服务</span>
      </div>
      <Button
        type="nav"
        icon="home"
        @click="goHome"
      >返回主菜单</Button>
    </header>

    <main class="page-body">
      <ServiceConsole @error="onError" />
    </main>

    <div class="page-foot"></div>
  </div>
</template>

<style scoped>
.services-page {
  position: relative;
  flex: 1 1 auto;
  width: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 10px 1% 0;
  color: var(--text-color);
}

.page-head {
  display: flex;
  align-items: center;
  gap: 14px;
  flex: 0 0 auto;
  padding: 8px 14px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  background: rgba(0, 14, 39, 0.42);
  backdrop-filter: blur(3px);
  text-shadow: 0 2px 4px rgba(0, 0, 0, 0.5);
}

.page-title {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.page-title h2 {
  margin: 0;
  font-family: 'Maoken Assorted Sans', -apple-system, BlinkMacSystemFont, sans-serif;
  font-size: 24px;
  font-weight: 600;
  color: #fff;
}

.page-title span {
  font-size: 12px;
  opacity: 0.7;
}

.page-head :deep(button) {
  margin-left: auto;
}

.page-body {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  padding: 10px 12px 16px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: linear-gradient(
    to top,
    rgba(0, 14, 39, 0.62) 0%,
    rgba(0, 14, 39, 0.18) 100%
  );
  backdrop-filter: blur(1px);
}

/* 底部对话框渐变上沿，延续 galgame 对话框视觉 */
.page-foot {
  flex: 0 0 auto;
  height: 28px;
  background: linear-gradient(
    to bottom,
    transparent 0%,
    rgba(0, 14, 39, 0.3) 50%,
    var(--dialog-bg-color) 100%
  );
  pointer-events: none;
}

@media (max-width: 768px) {
  .page-title h2 {
    font-size: 20px;
  }

  .page-title span {
    display: none;
  }
}
</style>
