/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue';
  const component: DefineComponent<Record<string, unknown>, Record<string, unknown>, any>;
  export default component;
}

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string = "http://localhost:8000/api";
  readonly VITE_WS_URL: string = "ws://localhost:8000/ws";
  readonly VITE_TIMEOUT: number = 100000;
  readonly AI_API_URL?: string;
  readonly AI_API_KEY?: string;
}


interface ImportMeta {
  readonly env: ImportMetaEnv;
}
