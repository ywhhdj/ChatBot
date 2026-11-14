import { serviceService } from "@/api/services/service";
import type { SlotInfo } from "@/typings/config";
import { loadStorage, saveStorage } from "@/utils/util";
import { defineStore } from "pinia";

export const useUserStore = defineStore("user", {
  state: (): User.State => ({
    config: {
      historyPath: "",
      textSpeed: 50,
      bgVolume: 50,
      soundVolume: 50,
      roleVolume: 50,
      bgPath: "",
      soundPath: "",
      isAutoSend: false,
      animations: {
        snowFlakes: true,
        liquid: true,
      },
    },
    clientId: ""
  }),
  actions: {
    saveConfig() {
      saveStorage("userConfig", this.$state.config);
    },
  
    loadUIConfig() {
      const config = loadStorage("userConfig");
      if (config) {
        this.$patch(config);
      }
    }
  },
});