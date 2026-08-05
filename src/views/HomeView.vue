<script setup lang="ts">
import { defaultUIStore } from '@/stores/ui';
const uiStore = defaultUIStore();
const componentMap: Record<UI.HomeTab, any> = {
  monitor: defineAsyncComponent(() => import('@/components/home/pages/MonitorPage.vue')),
  services: defineAsyncComponent(() => import('@/components/home/pages/ServicesPage.vue')),
  modelprovider: defineAsyncComponent(() => import('@/components/home/pages/ModelProviderPage.vue')),
}

const currentComponent = computed(() => {
  const tab = uiStore.currentHomeTab
  return componentMap[tab] || null
})


</script>

<template>
  <div class="home-view">
    <HomeAside />
    <main class="page">
      <MenuPage width="100%">
        <KeepAlive include="MonitorPage">
          <component :is="currentComponent" />
        </KeepAlive>
      </MenuPage>
    </main>
  </div>
</template>

<style scoped>
.home-view {
  display: flex;
  flex-direction: row;
  height: 100%;
  width: 100%;
}

.aside-nav {
  position: sticky;
  top: 0;
  left: 0;
  width: max-content;
  overflow: hidden;
  height: 100%;
}

.page {
  height: 100%;
  flex: 1;
  overflow-y: auto;
}

@media (max-width: 768px) {
  .aside-nav {
    display: none;
  }

  .page {
    width: 98%;
  }
}
</style>