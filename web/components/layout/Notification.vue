<script setup lang="ts">
import notification from '@/utils/notification';

// 根据类型返回对应的CSS类
const typeClass = computed(() => `notification-${notification.type.value}`)
</script>

<template>
  <div class="notifictiy" v-show="notification.isVisible.value">
    <Transition name="slide-in">
      <div
        class="notification"
        :class="[
          'fixed top-5 left-0 z-[10000] flex items-center gap-4 px-6 py-4 min-w-80 max-w-[480px]',
          typeClass
        ]"
      >
        <!-- 角色头像区域 -->
        <div
          v-if="notification.avatarUrl.value"
          class="shrink-0 w-16 h-16 rounded-full overflow-hidden flex items-center justify-center notification-avatar"
        >
          <img
            :src="notification.avatarUrl.value"
            alt="avatar"
            class="w-full h-full object-cover"
          />
        </div>

        <!-- 文字内容区域 -->
        <div class="flex-1 flex flex-col gap-1.5">
          <div class="text-base font-semibold notification-title">
            {{ notification.title.value || '[通知标题]' }}
          </div>
          <div class="text-sm leading-relaxed notification-message">
            {{ notification.message.value || '[通知内容]' }}
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.notifictiy {
  opacity: 0;
  visibility: hidden;
  position: fixed;
  z-index: 9999;
  left: 0;
  min-width: 400px;
  pointer-events: none;
}

.notification {
  will-change: transform, opacity;
  /* 玻璃态效果 */
  background: linear-gradient(135deg, rgba(30, 30, 40, 0.95) 0%, rgba(20, 20, 30, 0.9) 100%);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);

  border-radius: 0 16px 16px 0;
  box-shadow:
    4px 4px 20px rgba(0, 0, 0, 0.4),
    inset 0 1px 0 rgba(255, 255, 255, 0.1);
}

/* 类型样式 */
.notification-error {
  box-shadow: 0 0 20px rgba(255, 90, 90, 0.55), inset 0 0 12px rgba(255, 60, 60, 0.06);
}

.notification-success {
  box-shadow: 0 0 20px rgba(70, 230, 130, 0.50), inset 0 0 12px rgba(70, 210, 110, 0.06);
}

.notification-info {
  box-shadow: 0 0 22px rgba(70, 170, 250, 0.48), inset 0 0 14px rgba(70, 160, 240, 0.05);
}

.notification-warning {
  box-shadow: 0 0 20px rgba(245, 190, 75, 0.52), inset 0 0 12px rgba(235, 175, 65, 0.06);
}

.notification-avatar {
  background: rgba(255, 255, 255, 0.1);
}

.notification-title {
  color: rgba(255, 255, 255, 0.95);
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
}

.notification-error .notification-title {
  color: rgba(255, 150, 150, 1);
}

.notification-success .notification-title {
  color: rgba(150, 255, 180, 1);
}

.notification-info .notification-title {
  color: rgba(150, 200, 255, 1);
}

.notification-warning .notification-title {
  color: rgba(255, 220, 150, 1);
}

.notification-message {
  color: rgba(255, 255, 255, 0.8);
}

/* 动画 */
.slide-in-enter-active,
.slide-in-leave-active {
  transition: transform 0.38s cubic-bezier(0.34, 1.02, 0.68, 1), opacity 0.32s ease;
}

.slide-in-enter-from {
  transform: translateX(-100%);
  opacity: 0;
}

.slide-in-leave-to {
  transform: translateX(100%);
  opacity: 0;
}

/* 响应式 */
@media (max-width: 520px) {
  .notification {
    max-width: calc(100vw - 20px);
    min-width: 280px;
  }
}
</style>