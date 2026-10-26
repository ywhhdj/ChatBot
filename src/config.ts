import { LogLevel } from "./typings/enums";

export const CONFIG: AppOptions = {
  websocket: {
    maxReconnectAttempts: 5,
    reconnectInterval: 1000,
  },
  text: {
    speed: 100,
    volume: 100,
  },
  background: {
    name: "黑夜",
    duration: 0.5,
    url: "/static/images/background/night.webp",
    index: 0,
  },
  sound: {
    audio: {
      name: "夏·烟火",
      url: "/static/audios/夏·烟火.mp3",
      progress: 0,
    },
  },
  logger: {
    enabled: true,
    minLevel: LogLevel.INFO,
    exclude: {
      enabled: false,
      length: 100, // 排除的模式数量
      patterns: [], // 排除的模式
    },
    mode: "real-time",
  },
  save: {
    MAX_SLOTS: 10,
    MIN_SLOTS: 2,
  },
  env: {
    API_BASE_URL: "http://localhost:8000",
    WS_API_BASE_URL: "ws://localhost:8000/",
    TIMEOUT: 100000,
  },
};
