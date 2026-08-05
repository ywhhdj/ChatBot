import { DEFAULT_CONFIG } from '@/config';
import { defineStore } from 'pinia';

export const defaultUIStore = defineStore('ui', {
  state: (): UI.State => ({
    currentHomeTab: "services",
    currentSettingsTab: "general",
    currentModelProvider: "llm",
    currentServiceTab: "live2d",
  }),
  actions: {
    setCurrentHomeTab(tab: UI.HomeTab) {
      this.currentHomeTab = tab;
    },
    setCurrentSettingsTab(tab: UI.SettingsTab) {
      this.currentSettingsTab = tab;
    },
    setCurrentModelProvider(tab: UI.ModelProviderTab) {
      this.currentModelProvider = tab;
    },
    setCurrentServiceTab(tab: UI.ServiceTab) {
      this.currentServiceTab = tab;
    },
  },
});

export const useTempStore = defineStore('temp', {
  state: (): UI.TempState => ({
      bgList: [DEFAULT_CONFIG.background],
      musicList: [DEFAULT_CONFIG.sound.audio],
  }),
});