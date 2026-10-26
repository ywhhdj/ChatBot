<script lang="ts" setup>
import { defaultUIStore } from '@/stores/ui';

const uiStore = defaultUIStore();
const componentMap: Record<UI.MoreTab, Component> = {
  modelprovider: defineAsyncComponent(() => import('@/components/settings/pages/more/pages/ModelProviderSetting.vue')),
  monitor: defineAsyncComponent(() => import('@/components/settings/pages/more/pages/MonitorSetting.vue')),
  // plugins: defineAsyncComponent(() => import('@/components/settings/pages/more/pages/PluginsSetting.vue')),
  services: defineAsyncComponent(() => import('@/components/settings/pages/more/pages/ServicesSetting.vue')),
  // skills: defineAsyncComponent(() => import('@/components/settings/pages/more/Skills.vue')),
}

const currentComponent = computed(() => {
  return componentMap[uiStore.currentTab.more] || null
});

const keepAliveInclude = computed(() => {
  return Object.keys(componentMap).join(',')
});
</script>

<template>
  <div class="flex flex-row h-full w-full ">
    <aside>
      <MoreNav />
    </aside>
    <div class="flex-1">
      <KeepAlive :include="keepAliveInclude">
        <component :is="currentComponent" />
      </KeepAlive>
    </div>
  </div>
</template>