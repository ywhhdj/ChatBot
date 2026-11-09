/// <reference path="./types/index.d.ts" />

interface AppError extends Error {
  code: number;
  message: string;
}

interface AppOptions {
  text: {
    speed: number;
    volume: number;
  };
  background: UI.Background;
  sound: {
    audio: UI.Music;
  };
  websocket: {
    maxReconnectAttempts: number;
    reconnectInterval: number;
  };
  logger: {
    enabled: boolean;
    minLevel: LogLevel;
    exclude: {
      enabled: boolean;
      length: number;
      patterns: (string | RegExp)[];
    };
    mode: "real-time" | "forward";
  };
  save: {
    MAX_SLOTS: number;
    MIN_SLOTS: number;
  };
  env: Env;
}
