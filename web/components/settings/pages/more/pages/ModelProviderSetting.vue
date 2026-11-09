<script lang="ts" setup>
import { defaultUIStore } from '@/stores/ui';
import { useUserStore } from '@/stores/user';
const uiStore = defaultUIStore();
const userStore = useUserStore();
const componentMap: Record<UI.ModelProviderTab, Component> = {
  llm: defineAsyncComponent(() => import("@/components/settings/pages/more/pages/models/LLM.vue")),
  // tts: defineAsyncComponent(() => import("@/components/settings/pages/more/pages/models/TTS.vue")),
  asr: defineAsyncComponent(() => import("@/components/settings/pages/more/pages/models/ASR.vue"))
}
const activeIndex = ref(0);
const menus: UI.MenuItem[] = [
  {
    name: "大模型",
    clickAction: () => {
      uiStore.setCurrentModelProvider("llm");
    },
  },
  {
    name: "语言模型",
    clickAction: () => {
      uiStore.setCurrentModelProvider("tts");
    },
  },
  {
    name: "语音识别",
    clickAction: () => {
      uiStore.setCurrentModelProvider("asr");
    },
  }
]

const currentComponent = computed(() => {
  return componentMap[uiStore.currentTab.modelProvider] || null;
})

const keepAliveInclude = computed(() => {
  return Object.keys(componentMap).join(',')
})
</script>

<template>
  <header class="flex justify-center items-center w-full">
    <Navigator
      :isliquid="userStore.config.animations.liquid"
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
/* ---------- 整体容器 ---------- */
.model-list {
  display: flex;
  flex-direction: column;
  gap: 20px;
  padding: 20px;
  max-height: 90%;
  overflow-y: auto;
  flex: 1;
  display: flex;
  flex-direction: row;
  flex-wrap: wrap;
}
</style>
