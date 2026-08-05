<script setup lang="ts">
import { getServiceConfigInfo } from '@/api/services';
import { defaultUIStore } from '@/stores/ui';
import { useUserStore } from '@/stores/user';

const uiStore = defaultUIStore();
const userStore = useUserStore();
const updateServiceConfig = () => {
  getServiceConfigInfo().then((res) => {
    Object.keys(res).forEach((id) => {
      const item = res[id as API.ServiceId];
      if (!userStore.serviceConfig) {
        userStore.serviceConfig = {} as User.State['serviceConfig'];
      }
      userStore.serviceConfig![id] = {
        name: item.name,
        description: item.description,
        status: item.config.some((config) => config.name === 'enabled' && config.value === true) ? 'running' : 'not_enabled',
        config: item.config.map((config) => {
          return {
            type: typeof config.value === 'boolean' ? 'boolean' : typeof config.value === 'string' ? 'string' : 'select',
            name: config.name,
            description: config.description,
            value: config.value,
            options: config.options || undefined
          }
        })
      }
    });
    console.log(userStore.serviceConfig)
  });
};

onMounted(() => {
  updateServiceConfig();
});

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
const componentMap: Record<UI.ServiceTab, any> = {
  live2d: defineAsyncComponent(() => import('@/components/home/pages/services/Live2D.vue')),
  qqbot: defineAsyncComponent(() => import('@/components/home/pages/services/QQBot.vue')),
};

const currentComponent = computed(() => {
  return componentMap[uiStore.currentServiceTab] || null;
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
