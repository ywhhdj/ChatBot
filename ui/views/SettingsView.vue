<script setup lang="ts">
import { defaultUIStore } from '@/stores/ui';

const uiStore = defaultUIStore();
const shouldShowOverlay = ref(false);
const overlayOpacity = ref(0);

// 组件映射表
const componentMap: Record<UI.SettingsTab, Component> = {
  general: defineAsyncComponent(() => import('@/components/settings/pages/GeneralSetting.vue')),
  history: defineAsyncComponent(() => import('@/components/settings/pages/HistorySetting.vue')),
  character: defineAsyncComponent(() => import('@/components/settings/pages/CharacterSetting.vue')),
  background: defineAsyncComponent(() => import('@/components/settings/pages/BackgroundSetting.vue')),
  sound: defineAsyncComponent(() => import('@/components/settings/pages/SoundSetting.vue')),
  save: defineAsyncComponent(() => import('@/components/settings/pages/SaveSetting.vue')),
  more: defineAsyncComponent(() => import('@/components/settings/pages/MoreSetting.vue')),
}

const currentComponent = computed(() => {
  return componentMap[uiStore.currentTab.settings] || null
});

const keepAliveInclude = computed(() => {
  return Object.keys(componentMap).join(',')
});

let hideTimer: number | null = null


onMounted(() => {
  shouldShowOverlay.value = true
  requestAnimationFrame(() => {
    overlayOpacity.value = 1
  });
  hideTimer = setTimeout(() => {
    shouldShowOverlay.value = false;
    hideTimer = null;
  }, 300)
});

onUnmounted(() => {
  if (hideTimer) clearTimeout(hideTimer)
  overlayOpacity.value = 0;
});
</script>

<template>
  <div v-bind="$attrs">
    <div
      class="blur-overlay"
      v-show="shouldShowOverlay"
      :style="{ opacity: overlayOpacity }"
    ></div>
    <div class="settings-panel">
      <div class="nav">
        <SettingsNav />
      </div>
      <div class="pages">
        <MenuPage width="90%">
          <KeepAlive :include="keepAliveInclude">
            <component :is="currentComponent" />
          </KeepAlive>
        </MenuPage>
      </div>
    </div>
  </div>
</template>

<style scoped>
.header {
  display: flex;
  align-items: center;
  padding: 10px 15px;
  position: relative;
  justify-content: space-between;
}

.settings-panel {
  position: fixed;
  top: 0;
  right: 0;
  width: 100%;
  height: 100%;
  opacity: 1;
  padding: 0;
  box-sizing: border-box;
  z-index: 3;
  color: #333;
  /* background-color: rgba(0, 0, 0, 0.15);
  background-color: transparent; */
}

.nav {
  display: grid;
  grid-template-columns: 50px 1fr 32px;
  grid-gap: 10px;
  align-items: center;
  width: 100%;
  padding: 0 15px 0 15px;
  background: var(--accent-bg);
  box-shadow: 0 0 10px rgba(0, 0, 0, 0.5);
  position: sticky;
  top: 0;
}

.pages {
  display: flex;
  justify-content: center;
  overflow: auto;
  width: 100%;
  height: 100%;
}

.blur-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  z-index: 2;

  /* 初始状态 */
  opacity: 0;
  backdrop-filter: blur(2px);
  /* background-color: rgba(0, 0, 0, 0.2); */

  /* 过渡效果 */
  transition: opacity 0.3s ease;

  /* 确保覆盖层可以点击穿透 */
  pointer-events: none;
}

@media screen and (max-width: 768px) {
  .nav {
    grid-template-columns: 1fr 32px;
  }
}
</style>