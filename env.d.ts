/// <reference types="vite/client" />

declare module "*.vue" {
  import type { DefineComponent } from "vue";
  const component: DefineComponent<
    Record<string, unknown>,
    Record<string, unknown>,
    any
  >;
  export default component;
}

//扩展ImportMeta
declare interface ImportMeta {
  env: {
    DEV: boolean;
    PROD: boolean;
    SSR: boolean;
  };
}
