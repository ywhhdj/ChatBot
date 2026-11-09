<script setup lang="ts">

import { defaultUIStore } from '@/stores/ui';
import { useUserStore } from '@/stores/user';

const uiStore = defaultUIStore();
const userStore = useUserStore();

const statusColor = (status: API.ServiceStatus): string => {
  switch (status) {
    case 'running': return '#22c55e'  // 绿色
    case 'stopped': return '#ef4444'  // 红色
    case 'not_enabled': return '#9ca3af' // 灰色
    default: return '#9ca3af'
  }
}

const statusLabel = (status: API.ServiceStatus): string => {
  switch (status) {
    case 'running': return '运行中'
    case 'stopped': return '已停止'
    case 'not_enabled': return '未启用'
    default: return '未知'
  }
}

const menus = [
  {
    name: "live2d",
    clickAction: () => uiStore.setCurrentServiceTab("live2d")
  },
  {
    name: "qqbot",
    clickAction: () => uiStore.setCurrentServiceTab("qqbot")
  }
]
const activeIndex = ref(0);
const componentMap: Record<UI.ServiceTab, Component> = {
  live2d: defineAsyncComponent(() => import('@/components/settings/pages/more/pages/services/Live2D.vue')),
  qqbot: defineAsyncComponent(() => import('@/components/settings/pages/more/pages/services/QQBot.vue')),
};

const currentComponent = computed(() => {
  return componentMap[uiStore.currentTab.service] || null;
});

const keepAliveInclude = computed(() => {
  return Object.keys(componentMap).join(',')
});
</script>

<template>
  <header class="flex justify-center items-center w-full">
    <Navigator
      v-model="activeIndex"
      :menus="menus"
      :isliquid="userStore.config.animations.liquid"
    />
  </header>
  <MenuPage width="100%">
    <KeepAlive :include="keepAliveInclude">
      <component :is="currentComponent" />
    </KeepAlive>
  </MenuPage>
</template>

<style scoped>
.services-page {
  display: flex;
  flex-wrap: wrap;
  flex-direction: row;
  justify-content: center;
  align-items: center;
  width: 100%;
  height: 100%;
  /* grid-template-columns: repeat(auto-fill, minmax(420px, 1fr)); */
  gap: 2rem;
}
</style>
