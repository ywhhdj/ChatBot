import type { App, Plugin } from "vue";
import { ForceLandscape } from "@/plugins/ForceLandscape";
import logger, { initLoggerPlugin } from "@/plugins/LogForwarder";
import { closeWebSocket, connectWebSocket } from "@/api/websocket";
import { CONFIG } from "@/config";

const appMountInit: Plugin = {
  async install(app: App) {
    const forceLandscape = new ForceLandscape();
    await forceLandscape.init();
    connectWebSocket(CONFIG.env.WS_API_BASE_URL);
    initLoggerPlugin(app);

    app.onUnmount(() => {
      closeWebSocket();
      forceLandscape.destroy();
      logger.destroy();
    });
  },
};

export default appMountInit;
