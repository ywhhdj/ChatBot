<script setup lang="ts">
import { useRoute, type LocationQuery } from 'vue-router';
import { defaultUIStore } from '@/stores/ui';
import {
  SETTINGS_PAGE_MAP,
  SETTINGS_PAGE_NAMES,
  SETTINGS_TABS,
  MORE_TABS,
} from '@/components/views/settings/settingsPages';

const route = useRoute();
const uiStore = defaultUIStore();
const shouldShowOverlay = ref(false);
const overlayOpacity = ref(0);

const currentComponent = computed(() => SETTINGS_PAGE_MAP[uiStore.currentTab.settings] || null);

/** 与组件名一致；配合模块级映射，KeepAlive 才真正复用实例 */
const keepAliveInclude = SETTINGS_PAGE_NAMES;

function applyRouteTab(query: LocationQuery) {
  const tab = String(query.tab ?? '');
  const sub = String(query.sub ?? '');
  if (SETTINGS_TABS.includes(tab as UI.SettingsTab)) {
    uiStore.setCurrentSettingsTab(tab as UI.SettingsTab);
  }
  if (tab === 'more' && MORE_TABS.includes(sub as UI.MoreTab)) {
    uiStore.setCurrentMoreTab(sub as UI.MoreTab);
  }
}

watch(() => route.query, (query) => applyRouteTab(query));

let hideTimer: number | null = null;
let rafId = 0;

onMounted(() => {
  applyRouteTab(route.query);
  // 尊重减弱动效偏好：直接跳过入场遮罩，避免无谓的全屏合成
  const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  if (reduce) return;
  shouldShowOverlay.value = true;
  rafId = requestAnimationFrame(() => {
    overlayOpacity.value = 1;
  });
  hideTimer = window.setTimeout(() => {
    shouldShowOverlay.value = false;
    hideTimer = null;
  }, 300);
});

onUnmounted(() => {
  if (hideTimer) clearTimeout(hideTimer);
  if (rafId) cancelAnimationFrame(rafId);
  overlayOpacity.value = 0;
});
</script>

<template>
  <div v-bind="$attrs">
    <div
      v-if="shouldShowOverlay"
      class="blur-overlay"
      :style="{ opacity: overlayOpacity }"
    ></div>
    <div class="settings-panel">
      <div class="nav">
        <SettingsNav />
      </div>
      <div class="pages">
        <MenuPage width="90%">
          <KeepAlive
            :include="keepAliveInclude"
            :max="10"
          >
            <component :is="currentComponent" />
          </KeepAlive>
        </MenuPage>
      </div>
    </div>
  </div>
</template>

<style scoped>
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
  opacity: 0;
  backdrop-filter: blur(2px);
  transition: opacity 0.3s ease;
  pointer-events: none;
}

@media screen and (max-width: 768px) {
  .nav {
    grid-template-columns: 1fr 32px;
  }
}
</style>
