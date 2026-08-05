import { loadJsonFile, saveJsonFile } from '@/utils/util';
import { defineStore } from 'pinia';

export const useUserStore = defineStore('user', {
  state: (): User.State => ({
    config: {
      historyPath: '',
      textSpeed: 50,
      bgVolume: 50,
      soundVolume: 50,
      roleVolume: 50,
      bgPath: '',
      soundPath: '',
      animations: {
        snowFlakes: true,
      }
    },
    dialogHistory: {
      "default": [
        {
          id: '1',
          type: 'message',
          role: 'user',
          content: '你好',
        },
        {
          id: '2',
          type: 'message',
          role: 'assistant',
          content: '你好，我是千灵',
        },
      ],
    },
    clientId: '',
    serviceConfig: null,
    isAutoSend: false,
  }),
  actions: {
    saveConfig() {
      saveJsonFile('data/userConfig.json', this.config);
    },
    loadConfig() {
      loadJsonFile('data/userConfig.json').then((data) => {
        this.config = data;
      });
    }
  }
});
