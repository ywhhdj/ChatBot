import { CONFIG } from "@/config";
import { defineStore } from "pinia";

export const defaultUIStore = defineStore("ui", {
  state: (): UI.State => ({
    currentTab: {
      settings: "general",
      modelProvider: "llm",
      service: "live2d",
      more: "modelprovider",
    },
  }),
  actions: {
    setCurrentSettingsTab(tab: UI.SettingsTab) {
      this.currentTab.settings = tab;
    },
    setCurrentMoreTab(tab: UI.MoreTab) {
      this.currentTab.more = tab;
    },
    setCurrentModelProvider(tab: UI.ModelProviderTab) {
      this.currentTab.modelProvider = tab;
    },
    setCurrentServiceTab(tab: UI.ServiceTab) {
      this.currentTab.service = tab;
    },
  },
});

export const useTempStore = defineStore("temp", () => {
  const bgList = shallowRef<UI.Background[]>([CONFIG.background]);
  const musicList = shallowRef<UI.Music[]>([CONFIG.sound.audio]);
  const clear = () => {
    if (bgList.value.length > 0) {
      bgList.value.forEach((item) => {
        if (item.url?.startsWith("blob:")) {
          URL.revokeObjectURL(item.url);
        }
      });
    }
    if (musicList.value.length > 0) {
      musicList.value.forEach((item) => {
        if (item.url?.startsWith("blob:")) {
          URL.revokeObjectURL(item.url);
        }
      });
    }
    bgList.value = [];
    musicList.value = [];
  };
  return {
    bgList,
    musicList,
    clear
  };
});
