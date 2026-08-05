<script lang="ts" setup>
import { defaultUIStore } from '@/stores/ui';
const uiStore = defaultUIStore();
const componentMap: Record<UI.ModelProviderTab, any> = {
  llm: defineAsyncComponent(() => import("@/components/home/pages/models/LLM.vue")),
  // tts: defineAsyncComponent(() => import("@/components/home/pages/models/TTS.vue")),
  asr: defineAsyncComponent(() => import("@/components/home/pages/models/ASR.vue"))
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
  return componentMap[uiStore.currentModelProvider] || null;
})

const keepAliveInclude = computed(() => {
  return Object.keys(componentMap).join(',')
})
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
