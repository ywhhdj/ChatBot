<script lang="ts" setup>
import { defaultUIStore } from '@/stores/ui';
import { useUserStore } from '@/stores/user';
const uiStore = defaultUIStore();
const userStore = useUserStore();

// 1. 定义 activeIndex 和 capability 的映射
const activeIndex = ref(0);
const tabKeys = ["llm", "tts", "asr", "ocr", "embedding", "image"] as const;

// 使用 computed 动态获取当前 capability
const capability = computed(() => uiStore.currentTab.modelProvider || "llm");

const menus: UI.MenuItem[] = [
  {
    name: "大模型",
    clickAction: () => {
      activeIndex.value = 0;
      uiStore.setCurrentModelProvider("llm");
    },
  },
  {
    name: "语音合成",
    clickAction: () => {
      activeIndex.value = 1;
      uiStore.setCurrentModelProvider("tts");
    },
  },
  {
    name: "语音识别",
    clickAction: () => {
      activeIndex.value = 2;
      uiStore.setCurrentModelProvider("asr");
    },
  },
  {
    name: "OCR",
    clickAction: () => {
      activeIndex.value = 3;
      uiStore.setCurrentModelProvider("ocr");
    },
  },
  {
    name: "图像",
    clickAction: () => {
      activeIndex.value = 4;
      uiStore.setCurrentModelProvider("image");
    },
  },
];

// 2. KeepAlive 的 include 必须是数组 (且组件内部必须有 defineOptions({ name: 'xxx' }))
const keepAliveInclude = ['LLM', 'TTS', 'ASR', 'OCR',  'Image'];

// 3. 监听 tab 切换，同步 activeIndex (如果 v-model 驱动了的话)
watch(() => uiStore.currentTab.modelProvider, (val) => {
  const idx = tabKeys.indexOf(val as any);
  if (idx !== -1) activeIndex.value = idx;
});
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
    <!-- 使用 computed 的 capability 作为 key 进行切页 -->
    <KeepAlive :include="keepAliveInclude" :max="6">
      <ModelPage
        :key="capability"
        :capability="capability"
      />
    </KeepAlive>
  </MenuPage>
</template>