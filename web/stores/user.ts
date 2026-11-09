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
    dialogHistory: {
      default: [],
    },
    clientId: "",
    serviceConfig: {},
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
    },
  
    async getServiceConfig(service: API.ServiceId) {
      const res = await serviceService.serviceUi(service);
      if (res) {
        console.log("getServiceConfig", res);
        this.serviceConfig[service] = res;
      }
    },
  
    async saveServiceConfig(service: API.ServiceId,config: any) {
      await serviceService.updateConfig(service,config)
    }
  },
});