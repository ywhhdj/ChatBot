<script setup lang="ts">
import { defaultUIStore } from '@/stores/ui';

const uiStore = defaultUIStore();
const shouldShowOverlay = ref(false);
const overlayOpacity = ref(0);

// 组件映射表
const componentMap: Record<UI.SettingsTab, any> = {
  general: defineAsyncComponent(() => import('@/components/settings/pages/GeneralSetting.vue')),
  history: defineAsyncComponent(() => import('@/components/settings/pages/HistorySetting.vue')),
  character: defineAsyncComponent(() => import('@/components/settings/pages/CharacterSetting.vue')),
  sound: defineAsyncComponent(() => import('@/components/settings/pages/SoundSetting.vue')),
  background: defineAsyncComponent(() => import('@/components/settings/pages/BackgroundSetting.vue')),
}

const currentComponent = computed(() => {
  return componentMap[uiStore.currentSettingsTab] || null
});

const keepAliveInclude = computed(() => {
  return Object.keys(componentMap).join(',')
});



onMounted(() => {
  if (!uiStore.currentSettingsTab) {
    uiStore.setCurrentSettingsTab('general') // 假设 store 中有 setter
  }
  shouldShowOverlay.value = true
  requestAnimationFrame(() => {
    overlayOpacity.value = 1
  })
});

onUnmounted(() => {
  overlayOpacity.value = 0
  setTimeout(() => { shouldShowOverlay.value = false }, 300)
});
</script>

<template>
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
      <MenuPage width="80%">
        <KeepAlive :include="keepAliveInclude">
          <component :is="currentComponent" />
        </KeepAlive>
      </MenuPage>
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
  grid-template-columns: 250px 2fr 50px;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 7vh;
  background: var(--accent-bg);
}

.pages {
  display: flex;
  justify-content: center;
  height: 93vh;
  overflow: auto;
  width: 100%;
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
    grid-template-columns: 10px 2fr 50px;
  }
}
</style>