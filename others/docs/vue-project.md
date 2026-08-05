# Vue 项目结构与代码

## 文件树

```
📁 api/
  api/📄 chat.ts
  api/📄 config.ts
  api/📄 download.ts
  api/📄 history.ts
  api/📄 logger.ts
  api/📄 model.ts
  api/📄 services.ts
📄 App.vue
📁 components/
  components/📄 Acknowledgements.vue
  components/📄 BalanceSelector.vue
  components/📁 base/
    components/base/📁 items/
      components/base/items/📁 Cards/
        components/base/items/Cards/📄 BackgroundCard.vue
        components/base/items/Cards/📄 CharacterCard.vue
        components/base/items/Cards/📄 FormCard.vue
        components/base/items/Cards/📄 PluginCard.vue
        components/base/items/Cards/📄 ServiceCard.vue
      components/base/items/📁 Lists/
        components/base/items/Lists/📄 BackgroundList.vue
        components/base/items/Lists/📄 CharacterList.vue
        components/base/items/Lists/📄 MusicList.vue
        components/base/items/Lists/📄 PluginList.vue
      components/base/items/📄 MenuItem.vue
      components/base/items/📄 RowItem.vue
    components/base/📁 weight/
      components/base/weight/📄 Button.vue
      components/base/weight/📄 Checkbox.vue
      components/base/weight/📄 Code.vue
      components/base/weight/📄 Icon.vue
      components/base/weight/📄 Input.vue
      components/base/weight/📄 InputForm.vue
      components/base/weight/📄 Nav.vue
      components/base/weight/📄 Select.vue
      components/base/weight/📄 Silder.vue
      components/base/weight/📄 Table.vue
      components/base/weight/📄 Text.vue
  components/📁 chat/
    components/chat/📄 GameButton.vue
    components/chat/📄 GameDialog.vue
    components/chat/📁 history/
      components/chat/history/📄 HistoryButton.vue
      components/chat/history/📄 HistoryCharacter.vue
      components/chat/history/📄 HistoryChat.vue
      components/chat/history/📄 HistorySession.vue
  components/📄 chat_test.vue
  components/📁 common/
    components/common/📄 Logo.vue
    components/common/📄 RecycleScroller.vue
  components/📁 components/
    components/components/📁 animations/
      components/components/animations/📄 ImageAcrossFade.vue
    components/components/📁 menu/
      components/components/menu/📄 MenuBar.vue
      components/components/menu/📄 MenuPage.vue
    components/components/📁 nav/
      components/components/nav/📄 AIModelNav.vue
  components/📁 home/
    components/home/📄 HomeAside.vue
    components/home/📁 pages/
      components/home/pages/📁 configs/
        components/home/pages/configs/📄 AdvancedConfig.vue
        components/home/pages/configs/📄 SystemConfig.vue
      components/home/pages/📄 LoggerPage.vue
      components/home/pages/📁 plugins/
      components/home/pages/📄 ServicePage.vue
  components/📁 layout/
    components/layout/📄 BackgroundGroup.vue
    components/layout/📄 HeaderNav.vue
    components/layout/📄 Notification.vue
  components/📁 main/
    components/main/📄 GameNav.vue
  components/📁 settings/
    components/settings/📁 pages/
      components/settings/pages/📄 BackgroundSetting.vue
      components/settings/pages/📄 CharacterSetting.vue
      components/settings/pages/📄 GeneralSetting.vue
      components/settings/pages/📄 HistorySetting.vue
      components/settings/pages/📄 SoundSetting.vue
    components/settings/📄 SettingsNav.vue
📁 composables/
  composables/📄 useForceLandscape.ts
📄 config.ts
📄 events.ts
📄 main.ts
📁 plugins/
  plugins/📄 LogForwarder.ts
  plugins/📄 transport.ts
📁 stores/
  stores/📄 index.ts
  stores/📄 ui.ts
  stores/📄 user.ts
📁 views/
  views/📄 ChatView.vue
  views/📄 HomeView.vue
  views/📄 MainMemu.vue
  views/📄 NotFoundView.vue
  views/📄 SettingsView.vue
```

---

## `api/chat.ts`

```ts
import { registerEventListeners, unregisterAllEventListeners } from "@/events";
import transport from "@/plugins/transport";
import { WebSocketEvent } from "@/typings/enums";

enum ChatEvent {
  TEXT_DELTA = "pipeline.text_delta",
  FINAL_TEXT = "pipeline.final_text",
  AUDIO_CHUNK = "pipeline.audio_chunk",
  FINAL_AUDIO = "pipeline.final_audio",
  ERROR = "pipeline.error",
}

type ChatCallbacks = {
  /** 收到文本增量 */
  onTextDelta: (data:{
    text: string,
    progress: number
  }) => void;
  /** 收到最终文本 */
  onFinalText?: (data: {
    text: string
  }) => void;
  /** 收到音频块 */
  onAudioChunk?: (data: {
    audioName: string,
    chunk: ArrayBuffer
  }) => void;
  /** 收到最终音频 */
  onFinalAudio?: (data: {
    audioName: string,
    chunksCount: number
  }) => void;
  /** 聊天完成 */
  onComplete?: (data: string) => void;
  /** 发生错误 */
  onError?: (data: {
    code: number,
    message: string
  }) => void;
}



export function chat(
  options: {
    callbacks: ChatCallbacks;
  } & API.ChatOptions
) {
  const sessionId = options.session_id || `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  if (!transport.websocket) {
    console.error('[WebSocket] WebSocket not initialized');
    return;
  }
  
  const events = {
    [ChatEvent.TEXT_DELTA]: options.callbacks.onTextDelta,
    [ChatEvent.AUDIO_CHUNK]: options.callbacks.onAudioChunk,
    [ChatEvent.FINAL_AUDIO]: options.callbacks.onFinalAudio,
    [ChatEvent.ERROR]: options.callbacks.onError,
    // [ChatEvent.CHAT]: options.callbacks.onChat,
    // [ChatEvent.STOP]: options.callbacks.onStop,
  } as Record<ChatEvent, (event: any) => void>;
  function complete() {
    options.callbacks.onComplete?.(sessionId);
    unregisterAllEventListeners(events);
  }
  events[ChatEvent.FINAL_TEXT] = complete;
  registerEventListeners(events);
  transport.websocket.send<API.ChatOptions>({
    type: WebSocketEvent.CHAT,
    data: {
      message: options.message,
      session_id: sessionId,
      source: options.source || 'text'
    }
  });
}
```

## `api/config.ts`

```ts
import http from "@/utils/http";

export interface AdvancedConfig {
  install_components: string[];
  code_highlight: {
    enabled: boolean;
    theme: string;
  };
  extra: Record<string, unknown>;
}

export async function openFolder(folderPath: string): Promise<boolean> {
  return http.get<boolean>('/open-folder', { folderPath });
}

export async function getConfig(): Promise<AdvancedConfig> {
  return http.get<AdvancedConfig>('/config');
}

// export interface SystemConfig {
//   log_config: {
//     level: string;
//     dir: string;
//   };
//   network_config: {
//     port: number;
//     timeout: number;
//   };
// }


```

## `api/download.ts`

```ts
import { registerEventListeners } from "@/events";
import transport from "@/plugins/transport";
import { WebSocketEvent } from "@/typings/enums";

enum DownloadModelEvent {
  STARTED = "download_started",
  RUNNING = "download_running",
  COMPLETED = "download_completed",
  FAILED = "download_failed",
  ERROR = "download_error"
}

type DownloadModelResponse= {
  model_name: string;
  progress?: number;
  message?: string;
}

type DownloadModelCallback = {
  onStarted?: (data: DownloadModelResponse) => void;
  onRunning?: (data: DownloadModelResponse) => void;
  onCompleted?: (data: DownloadModelResponse) => void;
  onFailed?: (data: DownloadModelResponse) => void;
  onError?: (data: DownloadModelResponse) => void;
}

export function downloadModel(options: {
  callbacks: DownloadModelCallback;
} & API.DownloadModelOptions) {
  const events = {
    [DownloadModelEvent.STARTED]: options.callbacks.onStarted,
    [DownloadModelEvent.COMPLETED]: options.callbacks.onCompleted,
    [DownloadModelEvent.FAILED]: options.callbacks.onFailed,
    [DownloadModelEvent.RUNNING]: options.callbacks.onRunning,
  } as Record<string, (data: DownloadModelResponse) => void>;
  registerEventListeners(events);
  transport.websocket?.send<API.DownloadModelOptions>({
    type: WebSocketEvent.DOWNLOAD_MODEL,
    data: options
  });
}
```

## `api/history.ts`

```ts
import type { HistoryItems } from "@/typings/system-types";
import HttpUtil from "@/utils/http";

export async function getHistory(params?: string[][] | Record<string, string> | string | URLSearchParams, callback?: (data: HistoryItems) => void) {
  const query: Record<string, string> = {};
  if (params && typeof params === 'object' && !Array.isArray(params) && !(params instanceof URLSearchParams)) {
    Object.assign(query, params);
  }
  const res = await HttpUtil.get<HistoryItems>('/history', query);
  if (res) {
    if (callback) {
      return callback(res);
    }
    return res;
  }
}

```

## `api/logger.ts`

```ts
import { LogSource, type LogLevel } from "@/typings/enums";
import http from "@/utils/http";

export interface LogRecord {
  log_name: string;
  timestamp?: string;
  level: LogLevel;
  message: string;
  source?: LogSource;
  stack_trace?: string;
  metadata?: Record<string, unknown>;
}

export interface LoggerState {
  current_level: string;
  levels: string[];
}


export async function getLoggerState(): Promise<LoggerState> {
  return http.get<LoggerState>('/logger/levels');
}

export async function setLoggerLevel(level: LogLevel | string): Promise<boolean> {
  return http.put<boolean>('/logger/level', { level: String(level).toUpperCase() });
}

export async function getLoggerRecords(limit = 200): Promise<LogRecord[]> {
  return http.get<LogRecord[]>('/logger/records', { limit: String(limit) });
}

export async function clearLoggerRecords(): Promise<boolean> {
  return http.delete<boolean>('/logger/records');
}

export async function pushLog(record: LogRecord): Promise<boolean> {
  return http.post<boolean>('/logger/push', {
    log_name: record.log_name,
    level: String(record.level).toUpperCase(),
    message: record.message,
    logger: record.source || LogSource.FRONTEND,
  });
}


```

## `api/model.ts`

```ts
import http from '@/utils/http';

interface LLMConfig {
  model: string;
  apiBaseURL: string;
  apiKey: string;
}

export async function setLLMConfig(config: LLMConfig, callback: (data: boolean) => void) {
  const res = await http.put<boolean>('/llm/setConfig', config);
  if (res) {
    if (callback) {
      return callback(res);
    }
    return res;
  }
}

export async function getLLMProviderList() {
  const res = await http.get<string[]>('/model/list');
  if (res) {
    return res;
  }
  return [];
}

```

## `api/services.ts`

```ts
import http from "@/utils/http";

export function getServiceList(){
  return http.get<API.ServiceInfoResponse<any[]>[]>("/service/list");
};

export function startLive2DService(serviceId?: string) {
  return http.post<API.ServiceInfoResponse<{
    service_id: string;
    message: string;
  }>>("/service/live2d/start", {
    service_id: serviceId,
  });
}

export function stopLive2DService(serviceId?: string) {
  return http.post<API.ServiceInfoResponse<{
    service_id: string;
    message: string;
  }>>("/service/live2d/stop", {
    service_id: serviceId,
  });
}

export function getServiceConfigInfoAll() {
  return http.get<API.ServiceConfigItem[]>("/service/config");
}


```

## `App.vue`

```vue
<script setup lang="ts">
import { useForceLandscape } from '@/composables/useForceLandscape';
import { websocket } from './events';
import { useUserStore } from './stores/user';
const forceLandscape = new useForceLandscape();
const useUser = useUserStore();
websocket.sendCallback = (data) => {
  if (data) {
    return {
      ...data,
      client_id: useUser.clientId || "",
    };
  } else {
    return {
      client_id: useUser.clientId || "",
    };
  }
};

onMounted(() => {
  forceLandscape.init();
  forceLandscape.tryLock();
  const url = import.meta.env.VITE_WS_URL || "ws://localhost:8000/ws";
  console.log("连接到WebSocket服务器: " + url);
  websocket.connect(
    url,
    (data) => {
      useUser.clientId = data.client_id;
      console.log("连接成功" + data);
    },
    undefined,
    undefined,
    () => {
      useUser.clientId = "";
      console.log("连接取消");
    }
  );
});
onUnmounted(() => {
  forceLandscape.unlock();
  forceLandscape.destroy();
});
</script>

<template>
  <div class="bg-group">
    <Notification />
    <BackgroundGroup />
  </div>
  <RouterView class="main-container" />
</template>

<style scoped>
.main-container {
  width: 98%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}
</style>

```

## `components/Acknowledgements.vue`

```vue
<template>
  
</template>
```

## `components/BalanceSelector.vue`

```vue
<template>
  <div class="balance-selector">
    <div class="provider-selector">
      <span>Deepseek</span>
    </div>
  </div>
</template>
```

## `components/base/items/Cards/BackgroundCard.vue`

```vue
<script setup lang="ts">
defineProps<{
  isSelected: boolean;
}>();
</script>

<template>
  <div :class="['bg-card', { selected: isSelected }]">
    <slot></slot>
  </div>
</template>

<style scoped>
.bg-card {
  border-radius: 10px;
  position: relative;
  display: flex;
  flex-direction: column;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  transition: all 0.3s ease;
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.125);
  box-shadow:
    0 8px 32px rgba(0, 0, 0, 0.1),
    inset 0 1px 1px rgba(255, 255, 255, 0.1);
}

/* 交互效果 */
.bg-card:hover {
  background: rgba(255, 255, 255, 0.15);
  transform: translateY(-4px) scale(1.01);
  box-shadow:
    0 12px 40px rgba(0, 0, 0, 0.15),
    inset 0 2px 2px rgba(255, 255, 255, 0.15);

  .background-image {
    transform: scale(1.03);
  }
}

.bg-card.selected {
  border: 2px solid #3bc7f6d8;
  box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.3);
}
</style>
```

## `components/base/items/Cards/CharacterCard.vue`

```vue
<script setup lang="ts">
defineProps({
  avatar: {
    type: String,
    default: ''
  },
  name: String,
  desc: {
    type: String,
    default: ''
  }
});
</script>

<template>
  <div class="character-card">
    <div class="character-avatar-container">
      <img :src="avatar" :alt="name" class="character-avatar" />
    </div>
    <div class="character-content">
      <h5 class="character-title">{{ name }}</h5>
      <p class="character-description">{{ desc }}</p>

      <div class="character-actions">
        <slot name="actions"></slot>
      </div>
    </div>
  </div>
</template>

<style scoped>
.character-card {
  display: flex;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 16px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  overflow: hidden;
  transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
  border: 1px solid rgba(0, 0, 0, 0.05);
  height: 180px;
  /* 固定高度保持统一 */
}

.character-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.12);
}

.character-avatar-container {
  width: 180px;
  height: 180px;
  padding: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: #f8f9fa;
  border-right: 1px solid rgba(0, 0, 0, 0.05);
  border-radius: 16px;
}

.character-avatar {
  width: 180px;
  height: 180px;
  object-fit: contain;
  /* 保持原始比例，完整显示 */
  border-radius: 8px;
  padding: 5px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
}

.character-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 12px;
  position: relative;
}

.character-title {
  font-size: 18px;
  font-weight: 600;
  color: #ffffff;
  margin-bottom: 8px;
  font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
}

.character-description {
  font-size: 13px;
  color: #f8f9fa;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  overflow: hidden;
  margin-bottom: 15px;
  height: 100px;
}

/* 响应式调整 */
@media (max-width: 768px) {
  .character-card {
    height: 120px;
  }

  .character-avatar-container {
    width: 100px;
    height: 100%;
  }

  .character-avatar {
    width: 85px;
    height: 85px;
  }

  .character-title {
    font-size: 16px;
  }

  .character-description {
    font-size: 12px;
  }

  .character-select-btn {
    padding: 5px 10px;
    font-size: 12px;
  }
}
</style>
```

## `components/base/items/Cards/FormCard.vue`

```vue
<script setup lang="ts">
import type { IconType } from '@/typings/ui-types';
defineProps({
  icon: {
    type: String as () => IconType,
    default: ''
  },
  title: {
    type: String,
    required: true
  }
});
</script>

<template>
  <div class="form-card">
    <div class="form-card-left">
      <div v-if="icon" style="margin-right: 4px;">
        <Icon :icon="icon" :size="18" />
      </div>
      <h2 class="form-card-title">{{ title }}</h2>
    </div>
    <div class="form-card-content">
      <slot></slot>
    </div>
  </div>
</template>

<style scoped>
.form-card {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px;
}

.form-card-left {
  display: flex;
  align-items: center;
  flex-direction: row;
}

.form-card-title {
  font-size: 16px;
  font-weight: 600;
}

.form-card-content {
  display: flex;
  align-items: center;
  flex-direction: row;
}

.form-card:hover {
  background-color: rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  color: var(--accent-color);
}
</style>

```

## `components/base/items/Cards/PluginCard.vue`

```vue
﻿<script setup lang="ts">
const props = defineProps({
  avatar: {
    type: String,
    default: '',
  },
  name: {
    type: String,
    default: '',
  },
  desc: {
    type: String,
    default: '',
  },
  category: {
    type: String,
    default: 'service',
  },
});
</script>

<template>
  <article class="plugin-card">
    <div class="plugin-header">
      <div class="plugin-avatar-container">
        <img v-if="avatar" :src="avatar" :alt="name" class="plugin-avatar" />
        <div v-else class="plugin-avatar-fallback">{{ name.slice(0, 1).toUpperCase() }}</div>
      </div>
      <span class="plugin-tag">{{ category }}</span>
    </div>

    <div class="plugin-content">
      <h5 class="plugin-title">{{ name }}</h5>
      <p class="plugin-description">{{ desc || '暂无描述' }}</p>
      <div class="plugin-actions">
        <slot name="actions"></slot>
      </div>
    </div>
  </article>
</template>

<style scoped>
.plugin-card {
  border: 1px solid rgba(255, 255, 255, 0.16);
  border-radius: 12px;
  padding: 14px;
  background: rgba(12, 22, 40, 0.42);
  color: #fff;
  display: grid;
  gap: 12px;
}

.plugin-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.plugin-avatar-container {
  width: 44px;
  height: 44px;
}

.plugin-avatar,
.plugin-avatar-fallback {
  width: 100%;
  height: 100%;
  border-radius: 10px;
}

.plugin-avatar-fallback {
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.16);
  font-weight: 700;
}

.plugin-tag {
  font-size: 12px;
  opacity: 0.9;
  padding: 3px 8px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.13);
}

.plugin-title {
  margin: 0;
  font-size: 16px;
}

.plugin-description {
  opacity: 0.9;
  margin: 8px 0 10px;
  min-height: 38px;
}

.plugin-actions {
  display: flex;
  justify-content: flex-end;
}
</style>

```

## `components/base/items/Cards/ServiceCard.vue`

```vue
<template>
  <div class="transparent-glass service-card">
    <slot></slot>
  </div>
</template>

<style scoped>
.service-card {
  backdrop-filter: blur(1px);
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
</style>
```

## `components/base/items/Lists/BackgroundList.vue`

```vue
<template>
  <div class="bg-list">
    <slot></slot>
  </div>
</template>

<style scoped>
.bg-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 20px;
  width: 100%;
  padding: 20px;
  border-radius: 10px;
  box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
  max-width: 1200px;
  margin: 0 auto;
}

@media (max-width: 768px) {
  .bg-list {
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    gap: 16px;
    padding: 12px;
  }
}

@media (max-width: 480px) {
  .bg-list {
    grid-template-columns: 1fr;
  }
}
</style>
```

## `components/base/items/Lists/CharacterList.vue`

```vue
<template>
  <div class="character-list">
    <slot></slot>
  </div>
</template>

<style scoped>
.character-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
  gap: 20px;
  padding: 15px;
  width: 100%;
  overflow-y: auto;
}

@media (max-width: 768px) {
  .character-list {
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  }
}
</style>
```

## `components/base/items/Lists/MusicList.vue`

```vue
<template>
  <div class="music-list">
    <slot></slot>
  </div>
</template>

<style scoped>
.music-list {
  max-height: 200px;
  overflow-y: auto;
  margin-top: 15px;
  border: 1px solid #555;
  padding: 5px;
  background-color: rgba(0, 0, 0, 0.2);
  border-radius: 10px;
}
</style>
```

## `components/base/items/Lists/PluginList.vue`

```vue
<template>
  <div class="plugin-list">
    <slot></slot>
  </div>
</template>

<style scoped>
.plugin-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 20px;
  width: 100%;
  padding: 20px;
  border-radius: 10px;
  box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
  max-width: 1200px;
  margin: 0 auto;
}
</style>
```

## `components/base/items/MenuItem.vue`

```vue
<script setup lang="ts">
import type { IconType } from '@/typings/ui-types';
defineProps({
  icon: {
    type: String as () => IconType,
    default: '',
  },
  title: {
    type: String,
    default: '默认标题',
  },
  size: {
    type: String as () => 'small' | 'large',
    default: 'large',
    validator: (value: string) => ['small', 'large'].includes(value),
  },
  buttonText: {
    type: String,
    required: false
  }
});
const emit = defineEmits(['click']);
</script>

<template>
  <section :class="['menu-item', size]">
    <div style="display: flex;">
      <div class="menu-item-title">
        <div class="title-left">
          <div v-if="icon" style="margin-right: 8px;">
            <Icon :icon="icon" />
          </div>
          <div class="title-text">
            {{ title }}
          </div>
        </div>
        <div v-if="buttonText" style="justify-self: flex-end;width: max-content;height: min-content;">
          <Button type="big" @click="$emit('click')">{{ buttonText }}</Button>
        </div>
      </div>
    </div>
    <div class="menu-item-content">
      <slot></slot>
    </div>
  </section>
</template>

<style scoped>
section {
  box-shadow: 0 0 10px rgba(0, 0, 0, 0.8);
  background: rgba(255, 255, 255, 0.1);
  border-radius: 12px;
  padding: 15px;
}

section.large {
  width: 100%;
}

section.small {
  width: calc(50% - 12.5px);
  /* 减去一半的margin */
}

.menu-item-title {
  width: 100%;
  display: flex;
  align-items: center;
  border-bottom: 2px solid var(--accent-color);
  padding-bottom: 8px;
  margin-bottom: 15px;
  justify-content: space-between;
}

h4 {
  margin: 0;
  font-size: 18px;
  color: #fff;
  font-weight: 600;
  text-shadow: 0 0 2px rgba(0, 0, 0, 0.5);
}

.title-text {
  font-weight: 600;
}

slot {
  display: flex;
}

.title-left {
  display: flex;
  align-items: center;
  justify-self: flex-start;
}

/* 响应式设计 - 在小屏幕上让small菜单项变为全宽 */
@media (max-width: 768px) {
  section.small {
    width: 100%;
    max-width: 900px;
  }
}
</style>

```

## `components/base/items/RowItem.vue`

```vue
<script setup lang="ts">
const props = defineProps({
  bgColor: {
    type: String,
    default: 'rgba(0, 0, 0, 0.15)'
  },
});
</script>

<template>
  <div
    class="row-item"
    :style="{ backgroundColor: bgColor }"
  >
    <div>
      <slot name="left"></slot>
    </div>
    <div>
      <slot name="right"></slot>
    </div>
  </div>
</template>

<style scoped>
.row-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  background: rgba(0, 0, 0, 0.15);
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.06);
}
</style>
```

## `components/base/weight/Button.vue`

```vue
<script setup lang="ts">
defineProps<{
  type?: UI.ButtonType;
  icon?: UI.IconType;
  iconSize?: number;
  titleButtonDisabled?: boolean;
  buttonText?: string;
}>();
const emit = defineEmits(['click']);
</script>

<template>
  <button
    :class="type"
    @click="emit('click')"
  >
    <Icon
      v-if="icon"
      :icon="icon"
      :icon-size="iconSize"
    ></Icon>
    <slot></slot>
  </button>
</template>

<style scoped>
button {
  border-radius: 8px;
  border: none;
  outline: none;
  background-color: #ffffff1a;
  cursor: pointer;
  font-weight: 200;
  padding: 8px 16px;
  transition: all .2s ease;
}

/* 禁用状态 */
.base-button--disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* 特定组件样式 */

.menu {
  background: transparent;
  /* 去除背景 */
  color: white;
  border: none;
  /* 去除边框 */
  padding: 15px;
  margin: 10px 0;
  border-radius: 12px;
  /* 使用clamp()实现响应式字体大小 */
  /* 最小32px, 根据视口宽度的4%缩放, 最大72px */
  font-size: clamp(32px, 4vw, 72px);
  font-weight: normal;
  /* 字体加粗 */
  font-family:
    'Maoken Assorted Sans',
    -apple-system,
    BlinkMacSystemFont,
    'Segoe UI',
    Roboto,
    'Helvetica Neue',
    Arial,
    sans-serif;
  /* 应用自定义字体，并提供备用字体 */
  cursor: pointer;
  transition:
    color 0.3s,
    text-shadow 0.3s;
  /* 平滑过渡 */
  text-shadow: 0 2px 4px rgba(0, 0, 0, 0.5);
  /* 加一点文字阴影以保证清晰度 */
  text-align: left;
  /* 文字左对齐 */

  &:hover {
    color: #f0f0f0;
    text-shadow: 0 0 10px rgba(255, 255, 255, 0.8);
    /* 悬停时发光效果 */
    transform: none;
    /* 移除之前的缩放效果 */
  }
}

.start {
  background-color: #4caf50;

  &:hover {
    background-color: #45a049;
  }
}


.close {
  background-color: #f44336;

  &:hover {
    background-color: #d32f2f;
  }
}

.nav {
  color: var(--vt-c-white-light);
  /* 改为白色 */
  background: none;
  text-align: center;
  padding: 10px 15px;
  cursor: pointer;
  margin: 0 5px;
  font-size: 16px;
  font-weight: bold;
  position: relative;
  z-index: 1;
  transition:
    color 0.3s ease,
    background-color 0.3s ease;
  display: flex;
  align-items: center;
  gap: 8px;
  text-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
  border-radius: 8px;

  &:hover {
    background-color: rgba(255, 255, 255, 0.1);
    color: var(--accent-color);
  }

  svg {
    width: 18px;
    height: 18px;
    stroke-width: 2.5px;
    flex-shrink: 0;
  }

  &.active {
    background-color: rgba(255, 255, 255, 0.1);
    color: var(--accent-color);

    &:hover {
      background-color: rgba(255, 255, 255, 0.15);
    }
  }
}

.big {
  width: 100%;
  padding: 12px;
  font-size: 16px;
  font-weight: bold;
  border-radius: 8px;
  border: none;
  cursor: pointer;
  background-color: #e9ecef;
  color: #495057;
  transition: all 0.2s ease;

  &:hover {
    background-color: var(--accent-color);
    color: white;
    transform: translateY(-2px);
    box-shadow: 0 4px 10px rgba(121, 217, 255, 0.4);
  }
}

.select {
  align-self: flex-end;
  /* 按钮靠右 */
  background-color: #ccc;
  color: #666;
  border: none;
  padding: 8px 15px;
  border-radius: 20px;
  cursor: pointer;
  transition: all 0.2s ease;
  font-size: 13px;
  font-weight: 500;

  &.selected {
    background-color: var(--accent-color);
    color: white;
  }

  &:not(.selected):hover {
    background-color: #555;
    color: white;
  }
}


@media (max-width: 768px) {
  .moreMenu {
    background-color: rgba(0, 160, 255, 0.5) !important;
  }
}
</style>
```

## `components/base/weight/Checkbox.vue`

```vue
<script lang="ts" setup>
defineProps<{
  checked?: boolean
}>()

const emit = defineEmits<{
  (e: 'checked', value: boolean): void
}>()

function handleChange(event: Event) {
  const target = event.target as HTMLInputElement
  emit('checked', target.checked)
}
</script>

<template>
  <div class="flex items-center cursor-pointer select-none">
    <input
      id="checkbox-toggle"
      type="checkbox"
      class="hidden peer"
      :checked="checked"
      @change="handleChange"
    />
    <label
      for="checkbox-toggle"
      class="relative cursor-pointer text-white text-[14px] select-none inline-flex items-center"
      style="text-shadow: rgba(0, 0, 0, 0.3) 0px 2px 4px;"
    >
      <span
        class="relative inline-block w-12.5 h-6.5 rounded-[13px] transition-all duration-300 ease-in-out mr-2 border border-white/30 bg-white/20 peer-checked:bg-[rgba(121,217,255,0.3)] peer-checked:border-(--accent-color) peer-checked:shadow-[0_0_10px_rgba(121,217,255,0.3)]"
      >
        <span
          class="absolute top-1/2 -translate-y-1/2 w-5 h-5 rounded-full transition-all duration-300 ease-in-out left-1 bg-linear-to-br from-white to-[#f0f0f0] shadow-[0_2px_6px_rgba(0,0,0,0.3),0_1px_2px_rgba(0,0,0,0.1)] peer-checked:left-6.5 peer-checked:bg-linear-to-br peer-checked:from-(--accent-color) peer-checked:to-[#64b5f6] peer-checked:shadow-[0_3px_8px_rgba(121,217,255,0.4),0_1px_3px_rgba(0,0,0,0.2)]"
        ></span>
      </span>
      <slot></slot>
    </label>
  </div>
</template>

<style scoped></style>

```

## `components/base/weight/Code.vue`

```vue
<script setup lang="ts">
import "highlight.js/styles/atom-one-dark-reasonable.css"
import hljs from 'highlight.js/lib/core';
const props = defineProps({
  language: {
    type: String,
    default: "json"
  },
  code: {
    type: String,
    default: ""
  },
  editable: {
    type: Boolean,
    default: false
  },
  backgroundColor: {
    type: String,
    default: "#282c34"
  }
})
const code = ref(props.code);
const emit = defineEmits(['update:code'])

const handleInput = (e: InputEvent) => {
  code.value = (e.target as HTMLElement).textContent || "";
  if (code.value) {
    emit('update:code', code.value);
  }
}

const highlightedCode = computed(() => hljs.highlight(props.code, { language: props.language }).value.trim())

const typeClass = computed(() => props.language)

const copyCode = () => {
  navigator.clipboard.writeText(code.value).then(() => {
    console.log('复制成功');
  }).catch(() => {
    console.log('复制失败');
  })
}

</script>

<template>
  <pre
    :class="['hljs', typeClass]"
    :style="{ background: props.backgroundColor }"
  >
    <div class="header">
      <span class="language">{{ props.language }}</span>
      <button class="copy-btn" @click="copyCode">复制</button>
    </div>
    <div style="overflow: auto;" >
      <code class="code-content" v-html="highlightedCode"
      :contenteditable="editable" @input="handleInput" />
    </div>

  </pre>
</template>

<style scoped>
.hljs {
  border-radius: 8px;
  width: 100%;
  height: min-content;
}

.copy-btn {
  background: transparent;
  color: #fff;
  border: none;
  cursor: pointer;
}

.header {
  padding-bottom: 5px;
  padding-left: 10px;
  padding-right: 10px;
  border-color: #666;
  border-bottom: 1px solid #e5e5e5;
  font-size: 14px;
  display: flex;
  justify-content: space-between;
}

.language {
  font-weight: bold;
  color: #fff;
}

.code-content {
  border: none;
  outline: none;
  white-space: pre;

}
</style>

```

## `components/base/weight/Icon.vue`

```vue
<script setup lang="ts">
const props = defineProps({
  icon: {
    type: String as () => UI.IconType,
    default: ''
  },
  size: {
    type: Number,
    default: 24
  }
});

const svg = computed(() => {
  return svgHtml[props.icon as UI.IconType];
});

const svgHtml: Record<UI.IconType, string> = {
  none: '',
  url: `<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-link" aria-hidden="true"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"></path><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"></path></svg>`,
  key: `<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-key" aria-hidden="true"><path d="m15.5 7.5 2.3 2.3a1 1 0 0 0 1.4 0l2.1-2.1a1 1 0 0 0 0-1.4L19 4"></path><path d="m21 2-9.6 9.6"></path><circle cx="7.5" cy="15.5" r="5.5"></circle></svg>`,
  chip: `<div style="background-color: rgb(168 85 247 / 1);color: rgb(255 255 255 / var(--tw-text-opacity, 1));transition-property: all;
    transition-timing-function: cubic-bezier(.4, 0, .2, 1);"><svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-cpu" aria-hidden="true"><path d="M12 20v2"></path><path d="M12 2v2"></path><path d="M17 20v2"></path><path d="M17 2v2"></path><path d="M2 12h2"></path><path d="M2 17h2"></path><path d="M2 7h2"></path><path d="M20 12h2"></path><path d="M20 17h2"></path><path d="M20 7h2"></path><path d="M7 20v2"></path><path d="M7 2v2"></path><rect x="4" y="4" width="16" height="16" rx="2"></rect><rect x="8" y="8" width="8" height="8" rx="1"></rect></svg></div>`,
  chat: `<svg viewBox="0 0 1024 1024" xmlns="http://www.w3.org/2000/svg" width="24" height="24"><path d="M312.459636 881.524364l10.821819 5.329454A423.726545 423.726545 0 0 0 512 930.909091c230.981818 0 418.909091-182.714182 418.909091-407.272727C930.909091 299.077818 742.981818 116.363636 512 116.363636S93.090909 299.077818 93.090909 523.636364c0 86.551273 27.997091 169.518545 80.989091 239.918545l11.310545 15.010909-50.059636 140.241455 177.128727-37.282909zM512 1000.727273c-72.564364 0-142.661818-15.453091-208.546909-45.986909L129.349818 991.418182a58.181818 58.181818 0 0 1-66.746182-76.544l44.544-124.788364C52.200727 710.912 23.272727 619.194182 23.272727 523.636364 23.272727 260.561455 242.525091 46.545455 512 46.545455s488.727273 214.016 488.727273 477.090909S781.474909 1000.727273 512 1000.727273z m-186.181818-477.090909A46.545455 46.545455 0 1 1 232.727273 523.636364 46.545455 46.545455 0 0 1 325.818182 523.636364m232.727273 0A46.545455 46.545455 0 1 1 465.454545 523.636364 46.545455 46.545455 0 0 1 558.545455 523.636364m232.727272 0A46.545455 46.545455 0 1 1 698.181818 523.636364 46.545455 46.545455 0 0 1 791.272727 523.636364" fill="#ffffff"></path></svg>`,
  record: `<svg viewBox="0 0 1024 1024" xmlns="http://www.w3.org/2000/svg" width="24" height="24"><path d="M500.363636 814.545455C327.214545 814.545455 186.181818 689.338182 186.181818 535.272727c0-12.8 10.472727-23.272727 23.272727-23.272727s23.272727 10.472727 23.272728 23.272727c0 128.232727 120.087273 232.727273 267.636363 232.727273S768 663.505455 768 535.272727c0-12.8 10.472727-23.272727 23.272727-23.272727s23.272727 10.472727 23.272728 23.272727c0 154.065455-141.032727 279.272727-314.181819 279.272728z" fill="#ffffff"></path><path d="M500.363636 721.454545c-98.443636 0-178.501818-71.68-178.501818-159.883636V206.429091C321.861818 118.225455 401.92 46.545455 500.363636 46.545455s178.501818 71.68 178.501819 159.883636v92.625454c0 12.8-10.472727 23.272727-23.272728 23.272728s-23.272727-10.472727-23.272727-23.272728V206.429091C632.32 143.825455 573.207273 93.090909 500.363636 93.090909s-131.956364 50.734545-131.956363 113.338182v355.141818c0 62.370909 59.112727 113.338182 131.956363 113.338182s131.956364-50.734545 131.956364-113.338182V421.236364c0-12.8 10.472727-23.272727 23.272727-23.272728s23.272727 10.472727 23.272728 23.272728v140.334545c0 88.203636-80.058182 159.883636-178.501819 159.883636zM500.363636 954.181818c-12.8 0-23.272727-10.472727-23.272727-23.272727v-139.636364c0-12.8 10.472727-23.272727 23.272727-23.272727s23.272727 10.472727 23.272728 23.272727v139.636364c0 12.8-10.472727 23.272727-23.272728 23.272727z" fill="#ffffff"></path><path d="M725.178182 977.454545H275.549091c-12.8 0-23.272727-10.472727-23.272727-23.272727s10.472727-23.272727 23.272727-23.272727h449.629091c12.8 0 23.272727 10.472727 23.272727 23.272727s-10.472727 23.272727-23.272727 23.272727z" fill="#ffffff"></path></svg>`,
  openai: `<img src="/images/AiLog/openai.webp" alt="openai" width="24" height="24">`,
  deepseek: `<img src="/images/AiLog/deepseek.webp" alt="deepseek" width="24" height="24">`,
  plugin: `<svg viewBox="0 0 1024 1024" xmlns="http://www.w3.org/2000/svg" width="24" height="24"><path d="M804.912 1024H0V733.228c23.814 9.933 38.896 15.679 45.247 17.238 11.907 2.338 23.814 0 33.34 0 69.06 0 126.214-56.11 126.214-123.909S147.648 502.648 78.587 502.648c-9.526 0-21.433-2.338-33.34 0C37.309 504.207 22.227 507.324 0 512V229.114h207.181c-2.381-11.689-2.381-23.379-2.381-35.068C204.8 86.503 292.912 0 402.456 0s197.656 86.502 197.656 194.046c0 11.689 0 23.379-2.381 35.068h207.181v203.397h21.433c109.544 0 197.656 86.502 197.656 194.046s-88.112 194.046-197.656 194.046h-21.433V1024zM73.143 820.134v130.723h655.089V721.522c18.422 13.154 31.586 20.509 39.493 22.065 14.233 4.669 43.172 6.516 57.405 6.516 68.794 0 125.727-56.024 125.727-123.72s-56.933-123.72-125.727-123.72c-14.233 0-43.172 2.334-57.405 9.337-7.907 3.112-21.072 10.881-39.493 23.306V299.575H512c3.073-9.325 7.15-20.993 12.232-35.005 7.623-21.018 5.364-49.031 5.364-67.706 0-67.696-57.923-123.72-126.717-123.72s-128.635 56.024-128.635 123.72c0 18.675 2.909 53.8 11.964 74.01 6.037 13.473 10.161 23.04 12.373 28.702H73.144v130.723c111.493-4.669 204.009 84.036 204.009 193.751 0 107.38-87.771 193.751-196.893 193.751-2.372 2.334-4.744 2.334-7.117 2.334z" fill="#ffffff"></path></svg>`,
  home: `<svg viewBox="0 0 1024 1024" xmlns="http://www.w3.org/2000/svg" width="24" height="24"><path fill='#ffffff' d="M946.5 505L560.1 118.8l-25.9-25.9c-12.3-12.2-32.1-12.2-44.4 0L77.5 505c-12.3 12.3-18.9 28.6-18.8 46 0.4 35.2 29.7 63.3 64.9 63.3h42.5V940h691.8V614.3h43.4c17.1 0 33.2-6.7 45.3-18.8 12.1-12.1 18.7-28.2 18.7-45.3 0-17-6.7-33.1-18.8-45.2zM568 868H456V664h112v204z m217.9-325.7V868H632V640c0-22.1-17.9-40-40-40H432c-22.1 0-40 17.9-40 40v228H238.1V542.3h-96l370-369.7 23.1 23.1L882 542.3h-96.1z"></path></svg>`,
  menu: `<svg viewBox="0 0 1024 1024" xmlns="http://www.w3.org/2000/svg" width="24" height="24" ><path fill='#ffffff' d="M508.472 383.852c67.346 0 122.15 54.805 122.15 122.15s-54.804 122.15-122.15 122.15-122.15-54.805-122.15-122.15 54.805-122.15 122.15-122.15m0-54.289c-97.448 0-176.439 78.99-176.439 176.44s78.99 176.438 176.44 176.438 176.438-78.99 176.438-176.439-78.99-176.439-176.439-176.439m436.186 284.16c7.758-33.082 11.71-67.147 11.71-101.722 0-34.575-3.952-68.64-11.71-101.722-3.425-14.602-18.038-23.664-32.64-20.24-14.603 3.425-23.665 18.039-20.24 32.641 6.806 29.024 10.276 58.927 10.276 89.321s-3.47 60.297-10.276 89.32c-3.425 14.603 5.637 29.217 20.24 32.641 14.602 3.425 29.215-5.637 32.64-20.24z m-32.086 20.848c1.718 0 3.155 0.026 4.466 0.083 14.985 0.652 27.66-10.967 28.312-25.952 0.651-14.984-10.968-27.66-25.952-28.311a155.244 155.244 0 0 0-6.826-0.134c-14.999 0-27.157 12.158-27.157 27.157 0 14.998 12.158 27.157 27.157 27.157z m-88.67 163.374c-11.086-17.03-17.072-36.87-17.072-57.632 0-58.4 47.342-105.742 105.742-105.742 14.998 0 27.157-12.159 27.157-27.157 0-14.999-12.159-27.158-27.157-27.158-88.397 0-160.057 71.66-160.057 160.057 0 31.37 9.088 61.489 25.87 87.265 8.183 12.57 25.006 16.126 37.576 7.942 12.57-8.183 16.125-25.006 7.942-37.575z m-183.785 139.66c67.576-20.297 129.146-56.495 179.854-105.271 10.809-10.398 11.143-27.59 0.745-38.4s-27.59-11.142-38.4-0.744c-44.525 42.83-98.555 74.595-157.823 92.395-14.364 4.314-22.512 19.457-18.197 33.821 4.314 14.365 19.456 22.512 33.821 18.198z m-223.82-14.449c17.308-36.785 54.332-60.762 95.704-60.762 41.38 0 78.426 23.984 95.731 60.762 6.386 13.572 22.564 19.397 36.135 13.012 13.572-6.386 19.397-22.564 13.012-36.135C630.696 844.386 574.615 808.08 512 808.08c-62.61 0-118.666 36.302-144.85 91.953-6.386 13.57-0.56 29.75 13.01 36.135 13.572 6.385 29.75 0.56 36.136-13.012zM205.25 833.495c50.49 48.178 111.615 83.952 178.655 104.107 14.364 4.318 29.508-3.825 33.826-18.189 4.319-14.363-3.825-29.508-18.188-33.826-58.81-17.68-112.458-49.078-156.796-91.387-10.851-10.354-28.041-9.952-38.396 0.9s-9.952 28.04 0.9 38.395zM113.276 634.57c58.4 0 105.742 47.342 105.742 105.742 0 21.123-6.193 41.291-17.634 58.497-8.304 12.49-4.912 29.347 7.577 37.652 12.49 8.304 29.347 4.912 37.652-7.577 17.32-26.047 26.72-56.662 26.72-88.572 0-88.397-71.66-160.056-160.057-160.056-14.998 0-27.157 12.159-27.157 27.157s12.159 27.157 27.157 27.157z m-5.974 0.15c1.83-0.101 3.809-0.15 5.974-0.15 14.999 0 27.158-12.159 27.158-27.157 0-14.999-12.16-27.158-27.158-27.158-3.112 0-6.073 0.073-8.954 0.231-14.976 0.823-26.45 13.63-25.627 28.607 0.823 14.976 13.63 26.45 28.607 25.626zM79.37 410.202c-7.77 33.163-11.736 67.251-11.736 101.798S71.6 580.636 79.37 613.8c3.422 14.603 18.034 23.667 32.637 20.246 14.603-3.422 23.667-18.034 20.246-32.637-6.822-29.115-10.305-59.046-10.305-89.407 0-30.361 3.483-60.292 10.305-89.407 3.422-14.603-5.643-29.215-20.246-32.637-14.603-3.421-29.215 5.643-32.637 20.246z m33.906-20.772c-2.165 0-4.144-0.049-5.974-0.15-14.977-0.822-27.784 10.651-28.607 25.627-0.823 14.976 10.65 27.784 25.627 28.607 2.88 0.158 5.842 0.23 8.954 0.23 14.999 0 27.158-12.158 27.158-27.157 0-14.998-12.16-27.157-27.158-27.157z m88.108-164.239c11.443 17.208 17.634 37.377 17.634 58.524 0 58.393-47.335 105.715-105.742 105.715-14.998 0-27.157 12.159-27.157 27.157 0 14.999 12.159 27.158 27.157 27.158 88.401 0 160.057-71.636 160.057-160.03 0-31.933-9.398-62.548-26.72-88.598-8.305-12.49-25.162-15.882-37.652-7.577s-15.881 25.162-7.577 37.651zM383.905 86.4c-67.04 20.155-128.166 55.93-178.655 104.107-10.85 10.355-11.253 27.545-0.899 38.396 10.355 10.851 27.545 11.254 38.396 0.9 44.338-42.31 97.986-73.708 156.796-91.388 14.363-4.318 22.507-19.463 18.188-33.826-4.318-14.364-19.462-22.507-33.826-18.189z m223.827 14.446c-17.303 36.775-54.348 60.762-95.704 60.762-41.396 0-78.421-23.974-95.73-60.762-6.386-13.572-22.565-19.397-36.136-13.011-13.571 6.385-19.397 22.564-13.01 36.135 26.186 55.654 82.244 91.952 144.877 91.952 62.59 0 118.67-36.31 144.85-91.952 6.385-13.572 0.56-29.75-13.011-36.135-13.572-6.386-29.75-0.56-36.136 13.01z m212.233 90.817c-50.705-48.745-112.27-84.94-179.838-105.262-14.363-4.32-29.508 3.822-33.828 18.185s3.822 29.508 18.185 33.828c59.273 17.827 113.31 49.596 157.839 92.404 10.812 10.395 28.004 10.056 38.399-0.757s10.055-28.004-0.757-38.398z m92.607 197.768c-58.407 0-105.742-47.322-105.742-105.715 0-20.786 5.985-40.627 17.073-57.658 8.183-12.57 4.627-29.393-7.942-37.576-12.57-8.184-29.393-4.628-37.576 7.942-16.784 25.78-25.87 55.9-25.87 87.292 0 88.394 71.656 160.03 160.057 160.03 14.998 0 27.157-12.159 27.157-27.158 0-14.998-12.159-27.157-27.157-27.157z m4.466-0.083c-1.31 0.057-2.748 0.083-4.466 0.083-14.999 0-27.157 12.159-27.157 27.158 0 14.998 12.158 27.157 27.157 27.157 2.451 0 4.652-0.04 6.825-0.134 14.985-0.652 26.604-13.327 25.952-28.312-0.651-14.984-13.326-26.603-28.31-25.952z"></path></svg>`,
  character: `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path fill='none' d="M18 20a6 6 0 0 0-12 0"/><circle cx="12" cy="10" r="4"/><circle cx="12" cy="12" r="10"/></svg>`,
  text: `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="21" y1="10" x2="3" y2="10"/><line x1="21" y1="6" x2="3" y2="6"/><line x1="21" y1="14" x2="3" y2="14"/><line x1="21" y1="18" x2="3" y2="18"/></svg>`,
  background: `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="18" x="3" y="3" rx="2" ry="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/></svg>`,
  sound: `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 10v3M6 7v9M10 4v15M14 7v9M18 10v3"/></svg>`,
  history: `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-history-icon lucide-history"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l4 2"/></svg>`,
  box: `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="20" height="5" x="2" y="4" rx="2"/><path d="M4 9v9a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9"/><path d="M10 13h4"/></svg>`,
  play: `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-play-icon lucide-play"><path d="M5 5a2 2 0 0 1 3.008-1.728l11.997 6.998a2 2 0 0 1 .003 3.458l-12 7A2 2 0 0 1 5 19z"/></svg>`,
  save: `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-book-marked-icon lucide-book-marked"><path d="M10 2v8l3-3 3 3V2"/><path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H19a1 1 0 0 1 1 1v18a1 1 0 0 1-1 1H6.5a1 1 0 0 1 0-5H20"/></svg>`,
  advance: `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="4" x2="4" y1="21" y2="14" /><line x1="4" x2="4" y1="10" y2="3" /><line x1="12" x2="12" y1="21" y2="12" /><line x1="12" x2="12" y1="8" y2="3" /><line x1="20" x2="20" y1="21" y2="16" /><line x1="20"x2="20" y1="12" y2="3" /><line x1="2" x2="6" y1="14" y2="14" /><line x1="10" x2="14" y1="8" y2="8" /><line x1="18" x2="22" y1="16" y2="16" /></svg>`,
  close: `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>`,
  schedule: `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-clipboard-list-icon lucide-clipboard-list"><rect width="8" height="4" x="8" y="2" rx="1" ry="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="M12 11h4"/><path d="M12 16h4"/><path d="M8 11h.01"/><path d="M8 16h.01"/></svg>`,
  update: `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-rss-icon lucide-rss"><path d="M4 11a9 9 0 0 1 9 9"/><path d="M4 4a16 16 0 0 1 16 16"/><circle cx="5" cy="19" r="1"/></svg>`,
  volume: `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-volume2-icon lucide-volume-2"><path d="M11 4.702a.705.705 0 0 0-1.203-.498L6.413 7.587A1.4 1.4 0 0 1 5.416 8H3a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h2.416a1.4 1.4 0 0 1 .997.413l3.383 3.384A.705.705 0 0 0 11 19.298z"/><path d="M16 9a5 5 0 0 1 0 6"/><path d="M19.364 18.364a9 9 0 0 0 0-12.728"/></svg>`,
  microphone: `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-mic-icon lucide-mic"><path d="M12 19v3"></path><path d="M19 10v2a7 7 0 0 1-14 0v-2"></path><rect x="9" y="2" width="6" height="13" rx="3"></rect></svg>`
};
</script>

<template>
  <span
    v-html="svg"
    :style="{ width: `${props.size}px`, height: `${props.size}px` }"
  ></span>
</template>

<style scoped>
span {
  display: inline-flex;
  min-width: 12px;
  min-height: 12px;
}

span :deep(svg) {
  fill: none;
  width: 100%;
  height: 100%;
  stroke: currentColor;
  min-width: 12px;
  min-height: 12px;
}
</style>
```

## `components/base/weight/Input.vue`

```vue
<script setup lang="ts">
defineProps<{
  value?: string;
  placeholder?: string;
}>()
const emit = defineEmits(['change', 'input']);
const handleChange = (e: Event) => {
  const target = e.target as HTMLInputElement;
  emit('change', target.value)
}
const handleInput = (e: Event) => {
  const target = e.target as HTMLInputElement;
  emit('input', target.value)
}
</script>

<template>
  <div class="form-group">
    <input
      :value="value"
      class="text-input"
      type="text"
      @change="handleChange"
      @input="handleInput"
      :placeholder="placeholder"
    >
  </div>
</template>

<style scoped>
.text-input {
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 8px;
  padding: 6px 12px;
  color: #fff;
  font-size: 14px;
  outline: none;
  transition: border-color 0.2s;
  width: 100%;
}

.text-input:focus {
  border-color: var(--accent-color);
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
}
</style>

```

## `components/base/weight/InputForm.vue`

```vue
<script setup lang="ts">
const props = withDefaults(defineProps<{
  labelName: string
  inputMessage: string
  placeholder: string
}>(),
  {
    labelName: '请输入消息',
    inputMessage: '',
    placeholder: '请输入消息...',
  }
);
const emit = defineEmits(['input', 'change']);
</script>

<template>
  <div class="input-form">
    <label>{{ labelName }}</label>
    <span>: </span>
    <input
      type="text"
      :v-model="inputMessage"
      @change="emit('change')"
      @input="emit('input')"
      :placeholder="placeholder"
    >
  </div>
</template>

<style scoped>
.input-form {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  padding-bottom: 10px;
}

label {
  font-weight: bold;
  font-size: 14px;
}

span {
  padding-left: 10px;
  padding-right: 10px;
}

input {
  color: #ffffff;
  min-height: 2.5em;
  padding: 15px 20px;
  border-radius: 12px;
  backdrop-filter: blur(10px);
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: inset 0 2px 8px rgba(0, 0, 0, 0.2);
  font-family: 'Courier New', Courier, monospace;
  flex: 1;
}

input:focus {
  outline: none;
}
</style>
```

## `components/base/weight/Nav.vue`

```vue
﻿<script setup lang="ts">

const props = withDefaults(
  defineProps<{
    menus: UI.MenuItem[]
    direction?: 'column' | 'row'
    hideText?: boolean
    depth?: number
    fontFamily?: 'maokenAssorted' | ''
  }>(),
  {
    menus: () => [],
    direction: 'column',
    hideText: false,
    depth: 0,
    fontFamily: '',
  },
);

const expandedMap = ref<Record<string, boolean>>({});
const rootRef = ref<HTMLElement | null>(null);

const keyOf = (index: number) => {
  return `${props.depth}-${index}`;
};

const menuActionMap = computed(() => {
  const map: Record<string, UI.MenuItem> = {};
  props.menus.forEach((menu, index) => {
    map[keyOf(index)] = menu;
  });
  return map;
});

const onDelegatedClick = (event: MouseEvent) => {
  const root = rootRef.value;
  if (!root) {
    return;
  }
  const target = event.target as HTMLElement | null;
  if (!target) {
    return;
  }
  const trigger = target.closest('[data-menu-key]') as HTMLElement | null;
  if (!trigger || !root.contains(trigger)) {
    return;
  }
  const menuKey = trigger.dataset.menuKey;
  if (!menuKey) {
    return;
  }
  const menu = menuActionMap.value[menuKey];
  if (!menu) {
    return;
  }
  if (menu.children && menu.children.length > 0) {
    expandedMap.value[menuKey] = !expandedMap.value[menuKey];
  }
  menu.clickAction?.();
};
const spanClass = computed(() => {
  return props.hideText ? 'hide' : '';
});

const isExpanded = (index: number) => {
  return !!expandedMap.value[keyOf(index)];
};

</script>

<template>
  <div
    ref="rootRef"
    class="nav-tree"
    :class="[`direction-${direction}`, `depth-${depth}`]"
    @click="onDelegatedClick"
  >
    <div
      v-for="(menu, index) in menus"
      :key="keyOf(index)"
      class="menu-node"
    >
      <Button
        :type="menu.type"
        :icon="menu.icon"
        class="menu-trigger"
        :class="['menu-trigger', props.fontFamily, { 'expandable': !!menu.children?.length }]"
        :data-menu-key="keyOf(index)"
      >
        <span :class="spanClass">{{ menu.name }}</span>
        <span
          v-if="menu.children?.length"
          class="expand-indicator"
        >
          {{ isExpanded(index) ? '▾' : '▸' }}
        </span>
      </Button>

      <div
        v-if="menu.children?.length"
        v-show="isExpanded(index)"
        class="submenu-wrap"
      >
        <Nav
          :menus="menu.children || []"
          :direction="direction"
          :hide-text="hideText"
          :depth="depth + 1"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.nav-tree {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.direction-row {
  flex-direction: row;
}

.menu-trigger {
  width: 100%;
}

.menu-trigger.maokenAssorted {
  font-family: 'maokenAssorted';
}

.expand-indicator {
  opacity: 0.8;
  font-size: 12px;
}

.submenu-wrap {
  margin-top: 4px;
  margin-left: 14px;
  padding-left: 10px;
  border-left: 1px solid rgba(255, 255, 255, 0.2);
}

.depth-1 :deep(.nav) {
  font-size: 14px;
  font-weight: 600;
  opacity: 0.95;
}

.depth-2 :deep(.nav) {
  font-size: 13px;
  font-weight: 500;
  opacity: 0.9;
}

@media screen and (max-width: 768px) {
  .hide {
    display: none;
  }
}
</style>

```

## `components/base/weight/Select.vue`

```vue
<script setup lang="ts">
defineProps<{
  value: string;
  options: any[];
}>()
const emit = defineEmits<{
  (e: 'change', value: string): void
}>()
function handleChange(event: Event) {
  const target = event.target as HTMLSelectElement
  emit('change', target.value)
}
</script>

<template>
  <select
    :value="value"
    @change="handleChange"
    name="select"
    id="select"
    class="w-full px-3 py-2 rounded-lg border border-white/12 bg-white/8 text-white text-sm outline-none focus:border-[var(--accent-color)] backdrop-blur-md"
  >
    <slot></slot>
    <option
      class=" bg-[#424141] backdrop-blur-md"
      v-for="(item, index) in options"
      :key="index"
      :value="item"
    >{{ item }}
    </option>
  </select>
</template>

```

## `components/base/weight/Silder.vue`

```vue
<script setup lang="ts">
const props = defineProps({
  Value: {
    type: Number,
    required: false
  },
  min: {
    type: Number,
    default: 0
  },
  max: {
    type: Number,
    default: 100
  },
  step: {
    type: Number,
    default: 1
  }
});
const value = ref(props.Value ?? (props.max + props.min) / 2);
const emit = defineEmits(['input', 'change']);

watch(() => props.Value, (newValue) => {
  if (newValue !== value.value) {
    value.value = Number(newValue);
  }
});

const onInput = (event: Event) => {
  const nextValue = Number((event.target as HTMLInputElement).value);
  value.value = nextValue;
  emit('input', nextValue);
};

const onChange = (event: Event) => {
  const nextValue = Number((event.target as HTMLInputElement).value);
  value.value = nextValue;
  emit('change', nextValue);
};
</script>

<template>
  <div class="slider">
    <span>
      <slot name="left"></slot>
    </span>
    <input
      type="range"
      :min="min"
      :step="step"
      :max="max"
      :value="value"
      @input="onInput"
      @change="onChange"
      class="slider-input"
    >
    <span>
      <slot name="right"></slot>
    </span>
  </div>
</template>

<style scoped>
div {
  gap: 15px;
  display: flex;
  align-items: center;
  color: rgba(255, 255, 255, 0.9);
  /* 白色文字 */
  text-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
}

.slider-input {
  flex-grow: 1;
  outline: none;
  margin: 10px 0;
  appearance: none;
  position: relative;
  -webkit-appearance: none;
  background-color: transparent;

  &::-webkit-slider-runnable-track {
    width: 100%;
    height: 8px;
    border-radius: 4px;
    transition: all 0.3s ease;
    background: rgba(255, 255, 255, 0.2);
    /* 透明白色轨道 */
    border: 1px solid rgba(255, 255, 255, 0.1);
    box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.2);
  }

  &:hover::-webkit-slider-runnable-track {
    height: 10px;
    background: rgba(255, 255, 255, 0.25);
  }

  &::-webkit-slider-thumb {
    z-index: 2;
    width: 22px;
    height: 22px;
    cursor: grab;
    appearance: none;
    margin-top: -7px;
    position: relative;
    border-radius: 50%;
    -webkit-appearance: none;
    transform-origin: center;
    border: 2px solid rgba(255, 255, 255, 0.8);
    /* 半透明白色边框 */
    transition: all 0.2s cubic-bezier(0.25, 0.8, 0.25, 1);
    background: linear-gradient(135deg, var(--accent-color), #64b5f6);
    /* 渐变背景 */
    box-shadow:
      0 4px 12px rgba(121, 217, 255, 0.4),
      0 2px 4px rgba(0, 0, 0, 0.2);
  }

  &:active::-webkit-slider-thumb {
    cursor: grabbing;
  }
}

.slider-input::-webkit-slider-thumb:hover,
.slider-input::-webkit-slider-thumb:active {
  transform: scale(1.15);
  background: linear-gradient(135deg, #64b5f6, var(--accent-color));
  box-shadow:
    0 6px 20px rgba(121, 217, 255, 0.6),
    0 4px 8px rgba(0, 0, 0, 0.3);
}
</style>

```

## `components/base/weight/Table.vue`

```vue
<script lang="ts" setup>
defineProps({
  header: {
    type: Array as PropType<string[]>,
    default: () => [],
  },
  data: {
    type: Array as PropType<any[]>,
    default: () => [],
  },
  emptyText: {
    type: String,
    default: '暂无数据',
  },
  loading: {
    type: Boolean,
    default: false,
  },
});
</script>

<template>
  <table class="table">
    <tr class="header">
      <th v-for="item in header" :key="item">{{ item }}</th>
    </tr>
    <tr v-if="loading" class="loading">
      <td colspan="100%" class="loading-text">加载中...</td>
    </tr>
    <tr v-else-if="data.length === 0" class="empty">
      <td colspan="100%" class="empty-text">{{ emptyText }}</td>
    </tr>
    <tr v-else class="row" v-for="(row, index) in data" :key="index">
      <slot :name="index" :row="row" :index="index"></slot>
    </tr>
  </table>
</template>

<style scoped>
.table {
  border-collapse: collapse;
  width: 100%;
  border: 1px solid rgba(255, 255, 255, 0.16);
  border-radius: 8px;
  overflow: hidden;
}

.header {
  height: 44px;
  background: rgba(255, 255, 255, 0.08);
  border-top: none;
  font-weight: 700;
}

.row {
  border: 1px solid rgba(255, 255, 255, 0.16);
  padding: 12px;
}

.loading {
  padding: 14px;
  opacity: 0.85;
}
</style>

```

## `components/base/weight/Text.vue`

```vue
<script setup lang="ts">
import { DEFAULT_CONFIG } from '@/config';
const props = defineProps({
  speed: {
    type: Number,
    default: DEFAULT_CONFIG.text.speed
  },
  minDelay: {
    type: Number,
    default: 10
  },
  maxDelay: {
    type: Number,
    default: 200
  },
  showCursor: {
    type: Boolean,
    default: true
  }
});

const text = ref('');
let interval: number | undefined;
const slots = useSlots();
const sampleText = ref('');
let typingTimeout: number | undefined = undefined;

const stopTyping = () => {
  if (interval !== undefined) {
    cancelAnimationFrame(interval);
    interval = undefined;
  }
  if (typingTimeout !== undefined) {
    clearTimeout(typingTimeout);
    typingTimeout = undefined;
  }
};

const typeWrite = (speed: number, fullText: string) => {
  stopTyping();
  text.value = '';
  if (!fullText) {
    emit('complete');
    return;
  }
  const temp = props.maxDelay - props.minDelay + 1;
  const delay = props.maxDelay - Math.floor(((speed - 1) / 99) * temp);
  let i = 0;
  let lastTime = 0;
  const animate = (currentTime: number) => {
    if (!lastTime) lastTime = currentTime;
    const elapsed = currentTime - lastTime;

    if (elapsed >= delay) {
      if (i < fullText.length) {
        text.value += fullText.charAt(i);
        i += 1;
        lastTime = currentTime;
        // 触发打字事件
        emit('typing', {
          currentText: text.value,
          currentIndex: i,
          totalLength: fullText.length
        });
      } else {
        stopTyping();
        emit('complete');
        return;
      }
    }
    if (interval !== undefined) {
      interval = requestAnimationFrame(animate);
    }
  };
  interval = requestAnimationFrame(animate);
};
let debounceTimer: number | undefined = undefined;
const startTypingDebounced = (speed: number, fullText: string) => {
  if (debounceTimer !== undefined) {
    clearTimeout(debounceTimer);
  }
  debounceTimer = setTimeout(() => {
    typeWrite(speed, fullText);
  }, 50) as unknown as number;
};

watch(
  [() => props.speed, sampleText],
  ([newSpeed, newText]) => {
    startTypingDebounced(newSpeed, newText);
  },
  { immediate: true }
);

onBeforeUnmount(() => {
  stopTyping();
  if (typingTimeout !== undefined) {
    clearTimeout(typingTimeout);
  }
  if (debounceTimer !== undefined) {
    clearTimeout(debounceTimer);
  }
});

onMounted(() => {
  const nodes = slots.default?.() ?? [];
  const firstTextNode = nodes.find((n) => typeof n.children === 'string');
  sampleText.value = typeof firstTextNode?.children === 'string' ? firstTextNode.children : '';
});

const restart = () => {
  typeWrite(props.speed, sampleText.value);
};

const emit = defineEmits<{
  typing: [payload: { currentText: string; currentIndex: number; totalLength: number }];
  complete: [];
}>();

const skip = () => {
  stopTyping();
  text.value = sampleText.value;
  emit('complete');
};

defineExpose({
  restart,
  skip
});

</script>

<template>
  <div
    class="text"
    :aria-busy="interval !== undefined"
    :aria-label="sampleText"
  >
    <p>{{ text }}</p>
    <span
      v-if="showCursor && interval !== undefined"
      aria-hidden="true"
    ></span>
  </div>
</template>

<style scoped>
div {
  color: #ffffff;
  min-height: 2.5em;
  padding: 15px 20px;
  border-radius: 12px;
  backdrop-filter: blur(10px);
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: inset 0 2px 8px rgba(0, 0, 0, 0.2);
  font-family: 'Courier New', Courier, monospace;
}

p {
  display: inline;
}

span {
  width: 3px;
  height: 1.2em;
  margin-left: 4px;
  display: inline-block;
  vertical-align: text-bottom;
  background-color: var(--accent-color);
  animation: cursor-blink 0.8s infinite;
}
</style>

```

## `components/chat/GameButton.vue`

```vue
<script setup lang="ts">
defineProps({
  name: {
    type: String,
    default: '开始',
  },
  desc: {
    type: String,
    default: 'Start Game',
  },
});

const emit = defineEmits(['click']);
</script>

<template>
  <button @click="emit('click')">
    <div class="button-content">
      <span class="button-name">{{ name }}</span>
      <span class="button-desc">{{ desc }}</span>
    </div>
    <div class="line"></div>
  </button>
</template>

<style scoped>
button {
  position: relative;
  height: 6rem;
  width: 14rem;
  transition-property: all;
  display: flex;
  align-items: center;
  flex-direction: column;
  justify-content: center;
  --tw-scale-x: 1.05;
  --tw-scale-y: 1.05;
  --tw-skew-x: -12deg;
  border-width: 2px;
  border-right: 0.9rem;
  cursor: pointer;
  transition-duration: 300ms;
  transition-timing-function: cubic-bezier(0, 0, 0.2, 1);
  transform: translate(var(--tw-translate-x), var(--tw-translate-y)) rotate(var(--tw-rotate)) skewX(var(--tw-skew-x)) skewY(var(--tw-skew-y)) scaleX(var(--tw-scale-x)) scaleY(var(--tw-scale-y));
  box-shadow: rgba(195, 219, 244, 0.4) 0px 10px 25px -5px;
  background-color: rgba(255, 255, 255, 0.15);
}

.button-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  transform: translate(var(--tw-translate-x), var(--tw-translate-y)) rotate(var(--tw-rotate)) skewX(var(--tw-skew-x)) skewY(var(--tw-skew-y)) scaleX(var(--tw-scale-x)) scaleY(var(--tw-scale-y));
}

.button-name {
  font-size: 1.875rem;
  line-height: 2.25rem;
  color: rgba(255, 255, 255, 0.9);
  letter-spacing: 0.025em;
  font-weight: 900;
  font-family: "Quicksand", "Noto Sans SC", sans-serif;
}

.button-desc {
  font-size: 0.75rem;
  line-height: 1rem;
  --tw-text-opacity: 1;
  /* color: rgba(255, 255, 255, var(--tw-text-opacity)); */
  letter-spacing: 0.1rem;
  text-transform: uppercase;
  font-weight: 700;
  margin-top: 0.125rem;
}

.line {
  position: absolute;
  top: 0.25rem;
  right: 0.25rem;
  width: 0.5rem;
  height: 0.5rem;
}

@media(max-width: 768px) {
  button {
    height: 5rem;
    width: 10rem;
  }
}
</style>
```

## `components/chat/GameDialog.vue`

```vue
<script setup lang="ts">
import { defaultUIStore } from '@/stores/ui';
import { useRouter } from 'vue-router';

const uiStore = defaultUIStore();
const router = useRouter();
const inputMessage = ref('');
const isInputEnabled = ref(true);
const isSending = ref(false);

const clickHistory = () => {
  uiStore.setCurrentSettingsTab('history');
  router.push('/settings');
}

const menus: UI.MenuItem[] = [
  {
    type: 'nav',
    icon: 'play',
    clickAction: () => {
      console.log('点击角色');
    },
  },
  {
    type: 'nav',
    icon: 'history',
    clickAction: clickHistory,
  }
];

const sendOrContinue = () => {
  // if (inputMessage.value.trim() !== '') {
  //   sendMessage(inputMessage.value);
  //   inputMessage.value = '';
  // } else {
  //   continueConversation();
  // }
};
</script>

<template>
  <div class="chatbox-box">
    <div class="chatbox-main">
      <div class="chatbox-title-part">
        <div class="chatbox-title">
          <!-- <div id="character">{{ uiStore.showCharacterTitle }}</div> -->
        </div>
        <div class="chatbox-subtitle">
          <!-- <div id="character-sub">{{ uiStore.showCharacterSubtitle }}</div> -->
        </div>
        <div class="chatbox-emotion">
          <!-- <div id="character-emotion">{{ uiStore.showCharacterEmotion }}</div> -->
        </div>
        <div class="chatbox-buttons">
          <Button
            v-for="(menu, index) in menus"
            :key="index"
            :type="menu.type"
            :icon="menu.icon"
            @click="menu.clickAction && menu.clickAction()"
          />
        </div>
      </div>
      <div class="chatbox-line"></div>
      <div class="chatbox-inputbox">
        <textarea
          id="inputMessage"
          ref="textareaRef"
          placeholder="请输入消息..."
          v-model="inputMessage"
          @keydown.enter.exact.prevent="sendOrContinue"
          :readonly="!isInputEnabled"
        ></textarea>
        <button
          id="sendButton"
          :disabled="isSending"
          @click="sendOrContinue"
        >▼</button>
      </div>
    </div>
  </div>
</template>

<style>
.chatbox-box {
  position: relative;
  display: flex;
  justify-content: center;
  width: 100%;
  z-index: 2;
  background: linear-gradient(to top, rgba(0, 14, 39, 0.7) 0%, rgba(0, 14, 39, 0.6) 100%);
  padding: 15px;
  backdrop-filter: blur(1px);
  scrollbar-width: thin;
  scrollbar-color: var(--accent-color) transparent;
}

.chatbox-box::before {
  content: '';
  position: absolute;
  top: -40px;
  left: 0;
  right: 0;
  height: 40px;
  background: linear-gradient(to bottom,
      transparent 0%,
      rgba(0, 14, 39, 0.3) 50%,
      rgba(0, 14, 39, 0.6) 100%);
  pointer-events: none;
}

.chatbox-main {
  width: 60%;
}

.chatbox-title-part {
  display: flex;
  align-items: baseline;
  margin-bottom: 10px;
}

/* 确保所有文本元素都继承相同的字体和文字阴影 */
.chatbox-title,
.chatbox-subtitle,
#inputMessage,
#sendButton {
  font-family: inherit;
  /* 继承父元素字体 */
  text-shadow: inherit;
  /* 继承文字阴影 */
}

/* 调整特定元素的字体大小和粗细 */
.chatbox-title {
  font-size: 24px;
  font-weight: bold;
  color: white;
  margin-right: 15px;
}

.chatbox-subtitle {
  font-size: 20px;
  font-weight: bold;
  color: #6eb4ff;
}

.chatbox-emotion {
  font-size: 20px;
  font-weight: bold;
  color: #ff77dd;
  margin: auto;
}

.chatbox-buttons {
  display: flex;
}

.chatbox-line {
  height: 1px;
  background: rgba(255, 255, 255, 0.3);
  margin: 6px 0 6px 0;
}

.chatbox-inputbox {
  display: flex;
  flex-direction: column;
  white-space: pre-line;
  width: 100%;
  min-height: 40px;
  background: rgba(255, 255, 255, 0);
  border: none;
  color: white;
  font-size: 20px;
  font-weight: bold;
  resize: none;
  margin: 5px 0px;
  outline: none;
  transition: all 0.3s;
}

#inputMessage {
  font-size: 20px;
  font-weight: bold;
  width: 100%;
  min-height: 40px;
  background: rgba(255, 255, 255, 0);
  border: none;
  color: white;
  font-size: 20px;
  font-weight: bold;
  resize: none;
  margin: 5px 0px;
  outline: none;
  transition: all 0.3s;
}

#inputMessage::placeholder {
  color: rgba(255, 255, 255, 0.5);
  /* 明亮的灰色 */
  text-shadow: none;
  /* 移除阴影 */
}

#sendButton {
  align-self: flex-end;
  background: rgba(0, 14, 39, 0);
  color: rgb(4, 188, 255);
  border: none;
  padding: 4px 10px;
  border-radius: 5px;
  cursor: pointer;
  transition: all 0.3s;
  font-size: 20px;
  font-weight: bold;
  transform: scaleX(1.5);
}

#sendButton:hover {
  background: rgba(0, 14, 39, 0);
  color: rgba(136, 255, 251, 0.827);
}

#sendButton:disabled {
  background: #333;
  cursor: not-allowed;
  opacity: 0.7;
}

@media (max-width: 768px) {
  .chatbox-main {
    width: 90%;
  }
}
</style>

```

## `components/chat/history/HistoryButton.vue`

```vue
<script setup lang="ts">
defineProps<{
  text: string;
}>();
</script>

<template>
  <div class="history-button">
    <div class="history-button-icon">
      <i class="fas fa-history">{{ text }}</i>
    </div>
  </div>
</template>

<style scoped>
.history-button {
  position: fixed;
  bottom: 20px;
  right: 20px;
  width: 50px;
  height: 50px;
  background: linear-gradient(35deg, #dbdbdb, #197dea);
  opacity: 0.8;
  color: #fff;
  border-radius: 50%;
  text-align: center;
  align-items: center;
  line-height: 40px;
  cursor: pointer;
  z-index: 100;
  font-size: 14px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.3);
  user-select: none;
}
</style>
```

## `components/chat/history/HistoryCharacter.vue`

```vue
<script setup lang="ts">
defineProps<{
  role: string;
  content: string;
  // emotionTag: string;
  // emotionText: string;
}>();

const emit = defineEmits(['click']);
</script>

<template>
  <div class="message" :title="`情感: `">
    <div>
      <span class="name">{{ role }}</span>
      <span class="symbol">:&nbsp</span>
      <span class="content">{{ content }}</span>
      <span class="symbol">&nbsp</span>
    </div>
    <span class="icon">
      <Icon icon="volume" @click="$emit('click')" />
    </span>
  </div>
</template>

<style scoped>
span {
  vertical-align: middle;
}

.name {
  font-weight: bold;
}

.symbol {
  font-weight: bold;
}

.icon {
  cursor: pointer;
}

.message {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
```

## `components/chat/history/HistoryChat.vue`

```vue
<script setup lang="ts">
defineProps<{
  role: string;
  content: string;
}>();
</script>

<template>
  <div></div>
  <span class="role">{{ role }}</span>
  <span>: </span>
  <span>{{ content }}</span>
</template>

<style>
span {
  vertical-align: middle;
}

.role {
  font-weight: bold;
}
</style>
```

## `components/chat/history/HistorySession.vue`

```vue
<script setup lang="ts">
import type { DialogMessageItem } from '@/typings/user-types';

defineProps<{
  history: DialogMessageItem[];
}>();
const roleName = computed(() => (role: 'user' | 'assistant') => {
  return role === 'user' ? '我' : '千灵';
});
</script>

<template>
  <div class="message-item" v-for="message in history" :key="message.id">
    <div class="history-item" v-if="message.type === 'message'">
      <HistoryChat :content="message.content" :role="roleName(message.role)" />
    </div>
    <div class="history-character" v-if="message.type === 'reply'">
      <HistoryCharacter :role="roleName(message.role)" :content="message.content" />
    </div>
  </div>
</template>

<style scoped>
.message-item {
  line-height: 1.2;
  word-wrap: break-word;
  margin-bottom: 5px;
  padding: 30px 12px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  font-size: 12px;
  border-left: 10px solid rgba(var(--accent-color), 0.75);
  box-shadow: 2px 2px 4px rgba(0, 0, 0, 0.25);
  word-break: break-all;
  animation: 'fadeIn 0.3s ease';
}

.play-message {
  cursor: pointer;
  display: inline-block;
  /* 让边框包裹内容 */
}

.character-reply {
  cursor: help;
  display: inline-block;
  /* 让边框包裹内容 */
}

/* 为 isFinal 消息的间隔元素添加样式 */
.final-spacer {
  height: 1em;
  /* 高度约等于一个空行 */
}
</style>
```

## `components/chat_test.vue`

```vue
<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue';
import { useUserStore } from '@/stores/user';
import type { DialogMessageItem } from '@/typings/user-types';

const userStore = useUserStore();
const draft = ref('');
const sending = ref(false);
const listRef = ref<HTMLElement | null>(null);

const messages = computed(() => userStore.dialogHistory);

const scrollToBottom = () => {
  nextTick(() => {
    if (listRef.value) {
      listRef.value.scrollTop = listRef.value.scrollHeight;
    }
  });
};

watch(messages, scrollToBottom, { deep: true });

const appendMessage = (message: DialogMessageItem) => {
  userStore.appendDialog(message);
};

const sendMessage = () => {
  const text = draft.value.trim();
  if (!text || sending.value) return;
  sending.value = true;
  const baseId = Date.now();
  appendMessage({
    id: baseId,
    type: 'message',
    role: 'user',
    content: text,
    timestamp: Date.now(),
  });
  draft.value = '';
  setTimeout(() => {
    appendMessage({
      id: baseId + 1,
      type: 'reply',
      role: 'assistant',
      content: '已收到。我会保持上下文，请继续。',
      timestamp: Date.now(),
    });
    sending.value = false;
  }, 450);
};

const onKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
};
</script>

<template>
  <!-- <section class="chat-shell">
    <header class="chat-header">
      <div class="brand">
        <div class="brand-mark">Q</div>
        <div class="brand-text">
          <div class="title">QianLing Live</div>
          <div class="subtitle">实时对话 · 语音链路 · Live2D</div>
        </div>
      </div>
      <div class="status">
        <span class="dot"></span>
        <span>在线</span>
      </div>
    </header>

    <div class="chat-body">
      <aside class="chat-side">
        <div class="side-card">
          <div class="side-title">场景模式</div>
          <div class="side-pill">直播互动</div>
          <div class="side-pill ghost">语音助手</div>
          <div class="side-pill ghost">主持人</div>
        </div>
        <div class="side-card">
          <div class="side-title">链路状态</div>
          <div class="side-row">
            <span>ASR</span>
            <span class="badge ok">Ready</span>
          </div>
          <div class="side-row">
            <span>LLM</span>
            <span class="badge ok">Stream</span>
          </div>
          <div class="side-row">
            <span>TTS</span>
            <span class="badge warn">Idle</span>
          </div>
          <div class="side-row">
            <span>Live2D</span>
            <span class="badge ok">Sync</span>
          </div>
        </div>
        <div class="side-card">
          <div class="side-title">快捷动作</div>
          <button class="side-action">场景切换</button>
          <button class="side-action ghost">一键静音</button>
        </div>
      </aside>

      <main class="chat-main">
        <div class="message-list" ref="listRef">
          <div class="message-row" v-for="message in messages" :key="message.id" :class="message.role">
            <div class="avatar">
              <span>{{ message.role === 'user' ? '你' : '灵' }}</span>
            </div>
            <div class="bubble">
              <div class="bubble-role">
                {{ message.role === 'user' ? '你' : '千灵' }}
              </div>
              <div class="bubble-text">{{ message.content }}</div>
              <div class="bubble-meta">
                {{ message.timestamp ? new Date(message.timestamp).toLocaleTimeString() : '' }}
              </div>
            </div>
          </div>
        </div>

        <div class="composer">
          <textarea v-model="draft" class="composer-input" rows="2" placeholder="输入内容，Enter 发送，Shift+Enter 换行"
            @keydown="onKeydown"></textarea>
          <div class="composer-actions">
            <button class="icon-btn ghost" type="button">语音</button>
            <button class="icon-btn ghost" type="button">图片</button>
            <button class="icon-btn" type="button" @click="sendMessage">发送</button>
          </div>
        </div>
      </main>
    </div>
  </section> -->
  <Code language="json" code="{}" editable />
</template>

<style scoped>
.chat-shell {
  position: relative;
  width: min(1200px, 92vw);
  height: 88vh;
  margin: 4vh auto;
  border-radius: 28px;
  background: linear-gradient(140deg, rgba(255, 255, 255, 0.12), rgba(255, 255, 255, 0.03));
  border: 1px solid rgba(255, 255, 255, 0.2);
  box-shadow: 0 30px 80px rgba(3, 7, 18, 0.7);
  overflow: hidden;
  display: grid;
  grid-template-rows: auto 1fr;
  backdrop-filter: blur(14px);
}

.chat-shell::before {
  content: '';
  position: absolute;
  inset: -40% 0 auto 0;
  height: 60%;
  background: radial-gradient(circle at 20% 20%, rgba(68, 226, 255, 0.25), transparent 60%),
    radial-gradient(circle at 80% 40%, rgba(255, 122, 162, 0.2), transparent 65%);
  opacity: 0.8;
  pointer-events: none;
}

.chat-header {
  position: relative;
  z-index: 1;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 22px 28px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.brand {
  display: flex;
  align-items: center;
  gap: 16px;
}

.brand-mark {
  width: 46px;
  height: 46px;
  border-radius: 14px;
  background: linear-gradient(135deg, #44e2ff, #9bffd1);
  color: #04101f;
  font-family: var(--font-display);
  font-weight: 700;
  display: grid;
  place-items: center;
  letter-spacing: 1px;
}

.brand-text .title {
  font-family: var(--font-display);
  font-size: 20px;
  letter-spacing: 0.5px;
}

.brand-text .subtitle {
  font-size: 12px;
  color: rgba(226, 232, 240, 0.7);
  margin-top: 4px;
}

.status {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  background: rgba(15, 23, 42, 0.6);
  padding: 8px 14px;
  border-radius: 999px;
  font-size: 12px;
}

.status .dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #44e2ff;
  box-shadow: 0 0 12px rgba(68, 226, 255, 0.8);
}

.chat-body {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: 240px 1fr;
  height: 100%;
}

.chat-side {
  padding: 22px;
  display: flex;
  flex-direction: column;
  gap: 18px;
  border-right: 1px solid rgba(255, 255, 255, 0.08);
}

.side-card {
  background: rgba(10, 15, 31, 0.65);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 18px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.side-title {
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 1.2px;
  color: rgba(226, 232, 240, 0.6);
}

.side-pill {
  background: rgba(68, 226, 255, 0.18);
  color: #e2f8ff;
  padding: 8px 12px;
  border-radius: 999px;
  font-size: 12px;
  width: fit-content;
}

.side-pill.ghost {
  background: rgba(255, 255, 255, 0.06);
  color: rgba(226, 232, 240, 0.75);
}

.side-row {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: rgba(226, 232, 240, 0.8);
}

.badge {
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
}

.badge.ok {
  background: rgba(155, 255, 209, 0.2);
  color: #9bffd1;
}

.badge.warn {
  background: rgba(255, 209, 102, 0.2);
  color: #ffd166;
}

.side-action {
  border: none;
  background: linear-gradient(135deg, rgba(68, 226, 255, 0.35), rgba(155, 255, 209, 0.25));
  color: #e2f8ff;
  padding: 10px 12px;
  border-radius: 12px;
  cursor: pointer;
  font-size: 12px;
  text-align: left;
}

.side-action.ghost {
  background: rgba(255, 255, 255, 0.06);
  color: rgba(226, 232, 240, 0.8);
}

.chat-main {
  display: grid;
  grid-template-rows: 1fr auto;
  padding: 22px 26px;
  gap: 16px;
}

.message-list {
  overflow-y: auto;
  padding-right: 10px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.message-row {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.message-row.user {
  flex-direction: row-reverse;
}

.message-row.user .bubble {
  background: linear-gradient(135deg, rgba(68, 226, 255, 0.2), rgba(155, 255, 209, 0.15));
}

.message-row.user .bubble-role {
  text-align: right;
}

.avatar {
  width: 36px;
  height: 36px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.08);
  display: grid;
  place-items: center;
  font-size: 12px;
  font-family: var(--font-display);
}

.bubble {
  max-width: 70%;
  background: rgba(15, 23, 42, 0.8);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 18px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.bubble-role {
  font-size: 11px;
  letter-spacing: 1px;
  text-transform: uppercase;
  color: rgba(226, 232, 240, 0.6);
}

.bubble-text {
  font-size: 14px;
  line-height: 1.5;
}

.bubble-meta {
  font-size: 10px;
  color: rgba(226, 232, 240, 0.5);
}

.composer {
  background: rgba(10, 15, 31, 0.75);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 18px;
  padding: 12px;
  display: grid;
  gap: 10px;
}

.composer-input {
  width: 100%;
  background: transparent;
  border: none;
  color: #e2e8f0;
  resize: none;
  outline: none;
  font-family: var(--font-sans);
}

.composer-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.icon-btn {
  border: none;
  border-radius: 12px;
  padding: 8px 14px;
  background: linear-gradient(135deg, rgba(68, 226, 255, 0.35), rgba(155, 255, 209, 0.2));
  color: #e2f8ff;
  cursor: pointer;
  font-size: 12px;
}

.icon-btn.ghost {
  background: rgba(255, 255, 255, 0.08);
  color: rgba(226, 232, 240, 0.75);
}

@media (max-width: 980px) {
  .chat-shell {
    height: auto;
    margin: 12px;
  }

  .chat-body {
    grid-template-columns: 1fr;
  }

  .chat-side {
    border-right: none;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    flex-direction: row;
    flex-wrap: wrap;
  }

  .side-card {
    flex: 1 1 180px;
  }

  .bubble {
    max-width: 100%;
  }
}
</style>
```

## `components/common/Logo.vue`

```vue
<template>
  <h1 class="logo">
    <div class="logo-prefix">Neuro</div>
    <div class="logo-suffix">Chat</div>
  </h1>
</template>

<style scoped>
.logo {
  -webkit-text-stroke: 8px white;
  paint-order: stroke;
  font-family: "Quicksand", "Noto Sans SC", sans-serif;
  color: rgb(149, 47, 47);
  paint-order: stroke;
  letter-spacing: -0.05em;
  color: rgba(255, 255, 255, 0.8);
  line-height: 0.8;
  font-style: italic;
  font-weight: 900;
  z-index: 10;
  position: relative;
  font-size: 100%;
}

.logo-prefix {
  --tw-gradient-from: #ff7eb3 0%;
  --tw-gradient-to: #e11d48 100%;
  --tw-gradient-stops: var(--tw-gradient-from), var(--tw-gradient-to);
  --tw-drop-shadow: drop-shadow(4px 4px 0px rgba(255, 182, 193, 1));
}

.logo-suffix {
  --tw-gradient-from: #60a5fa 0%;
  --tw-gradient-to: #2563eb 100%;
  --tw-gradient-stops: var(--tw-gradient-from), var(--tw-gradient-to);
  --tw-drop-shadow: drop-shadow(4px 4px 0px rgba(147, 197, 253, 1));
  margin-left: 6rem;
}

div {
  color: transparent;
  background-clip: text;
  filter: var(--tw-drop-shadow);
  background-image: linear-gradient(to bottom, var(--tw-gradient-stops));
}
</style>
```

## `components/common/RecycleScroller.vue`

```vue
<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'

const props = withDefaults(defineProps<{
  minHeight?: number
  items: any[]
  itemHeight?: number
  overscan?: number
  getKey?: (item: any) => string | number | undefined
}>(), {
  itemHeight: 22,
  overscan: 30,
})

const emit = defineEmits<{
  (e: 'scroll', payload: { scrollTop: number; atBottom: boolean }): void
}>()

const viewport = ref<HTMLDivElement>()
const scrollTop = ref(0)

const totalHeight = computed(() => props.items.length * props.itemHeight)

const visibleStart = computed(() => {
  const s = Math.floor(scrollTop.value / props.itemHeight)
  return Math.max(0, s - props.overscan)
})

const visibleEnd = computed(() => {
  if (!viewport.value) return 0
  const containerHeight = viewport.value.clientHeight
  const visibleCount = Math.ceil(containerHeight / props.itemHeight)
  return Math.min(props.items.length, Math.floor(scrollTop.value / props.itemHeight) + visibleCount + props.overscan)
})

const visibleItems = computed(() =>
  props.items.slice(visibleStart.value, visibleEnd.value)
)

const offset = computed(() => visibleStart.value * props.itemHeight)

function onScroll() {
  const el = viewport.value
  if (!el) return
  scrollTop.value = el.scrollTop
  const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 2
  emit('scroll', { scrollTop: scrollTop.value, atBottom })
}

/** 外部调用滚动到底部 */
function scrollToBottom() {
  nextTick(() => {
    const el = viewport.value
    if (!el) return
    el.scrollTop = el.scrollHeight
  })
}

defineExpose({ scrollToBottom, viewport })
</script>

<template>
  <div
    ref="viewport"
    class="virtual-list-viewport"
    @scroll="onScroll"
  >
    <div :style="{ minHeight: minHeight + 'px', height: totalHeight + 'px', position: 'relative' }">
      <div :style="{ transform: `translateY(${offset}px)` }">
        <div
          v-for="(item, idx) in visibleItems"
          :key="getKey ? getKey(item) : idx"
          class="virtual-list-item"
          :style="{ height: itemHeight + 'px' }"
        >
          <slot
            name="item"
            :item="item"
            :index="visibleStart + idx"
          />
        </div>
      </div>
    </div>
  </div>
</template>


<style scoped>
.virtual-list-viewport {
  height: 100%;
  flex: 1;
  overflow-y: auto;
}

.virtual-list-item {
  contain: layout style;
}
</style>
```

## `components/components/animations/ImageAcrossFade.vue`

```vue
<script setup lang="ts">
const props = withDefaults(
  defineProps<{
    src: string
    duration?: number
    objectFit?: string
    position?: string
    className?: string
  }>(),
  {
    duration: 300,
    objectFit: 'contain',
    position: 'center bottom',
  }
)
const currentImageUrl = ref("");
const nextImageUrl = ref("");
const isFadingIn = ref(false);
const isMounted = ref(false);
const topImageRef = ref<HTMLDivElement | null>(null);
let currentImageLoadPromise: Promise<any> | null = null;
const topImageClasses = computed(() => ({
  'opacity-0': isFadingIn.value,
  'opacity-100': !isFadingIn.value
}));

const updateImage = async (url: string) => {
  if (!url || url === currentImageUrl.value) return;
  let resolveLoad!: (value?: void) => void;
  // 新图片加载完成,切换到新图片
  const loadPromise = new Promise((resolve) => {
    resolveLoad = resolve;
  });
  currentImageLoadPromise = loadPromise;
  const img = new Image();
  img.onload = async () => {
    try {
      // 使用 decode() 替代 onload 的回调
      await img.decode().catch(() => { });
    } catch (error) {
      console.error('图片解码失败:', error);
    } finally {
      resolveLoad();
    }
  };
  img.onerror = () => {
    console.error('图片加载失败:', url);
    resolveLoad(); // 确保 Promise 被解决
  };

  img.src = url;
  await loadPromise;
  if (!isMounted.value || currentImageLoadPromise !== loadPromise) return;
  if (currentImageLoadPromise === loadPromise) {
    if (isFadingIn.value) {
      currentImageUrl.value = nextImageUrl.value || currentImageUrl.value;
      isFadingIn.value = false;
    }
    nextImageUrl.value = url;
    await nextTick();
    if (topImageRef.value) {
      //强制触发布局,确保图片加载完成
      topImageRef.value.getBoundingClientRect();
    }
    requestAnimationFrame(() => {
      isFadingIn.value = true;
    });
  }
}

const onTransitionEnd = () => {
  if (isFadingIn.value) {
    currentImageUrl.value = nextImageUrl.value || currentImageUrl.value;
    isFadingIn.value = false; // 切换完成后,重置状态
  }
}

watch(() => props.src, (newSrc) => {
  updateImage(newSrc);
}, { immediate: true });

onMounted(() => {
  isMounted.value = true;
  // 如果已经有 src 且还没加载过，手动触发
  if (props.src && !currentImageUrl.value) {
    updateImage(props.src);
  }
});
// 等待图片加载完成
const waitForLoad = () => {
  if (!isMounted.value) {
    return Promise.reject(new Error('Component is not mounted'));
  }
  return currentImageLoadPromise || Promise.resolve();
}
defineExpose({
  waitForLoad,
})
</script>

<template>
  <div class="image-across-fade">
    <slot></slot>
    <div
      class="image-across-fade-container"
      :style="{
        backgroundImage: `url(${currentImageUrl})`,
        backgroundSize: objectFit,
        backgroundPosition: position,
      }"
    />
    <!--  顶层图片,准备切换-->
    <div
      ref="topImageRef"
      class="image-across-fade-top-image"
      :class="topImageClasses"
      :style="{
        backgroundImage: `url(${nextImageUrl})`,
        backgroundSize: objectFit,
        backgroundPosition: position,
        transition: `opacity ${duration}ms ease-in-out`,
      }"
      @transitionend="onTransitionEnd"
    />
  </div>
</template>

<style>
.image-across-fade-container {
  width: 100%;
  height: 100%;
}

.opacity-0 {
  opacity: 0;
}

.opacity-100 {
  opacity: 1;
}
</style>

```

## `components/components/menu/MenuBar.vue`

```vue
<script setup lang="ts">
type Direction = "row" | "column"
type IsTopRight = "true" | "false"
type JustifyContent = "start" | "end" | "center"

defineProps({
  zIndex: {
    type: Number,
    default: 1000
  },
  isTopRight: {
    type: String as PropType<IsTopRight>,
    default: "true"
  },
  justify: {
    type: String as PropType<JustifyContent>,
    default: "start"
  },
  isBoxShadow: {
    type: String as PropType<"box-shadow" | "no-box-shadow">,
    default: "box-shadow"
  }
});
</script>

<template>
  <div
    :class="['menu-bar', isTopRight, justify, isBoxShadow]"
    :style="{ zIndex: zIndex }"
  >
    <slot></slot>
  </div>
</template>

<style scoped>
.menu-bar {
  display: flex;
  overflow: auto;

}

.menu-bar.box-shadow {
  box-shadow: 0 0 10px rgba(0, 0, 0, 0.5);
}

.menu-bar.start {
  justify-content: flex-start;
}

.menu-bar.end {
  justify-content: flex-end;
}

.menu-bar.center {
  justify-content: center;
}

.menu-bar.true {
  z-index: 1000;
  top: 20px;
  right: 20px;
}
</style>
```

## `components/components/menu/MenuPage.vue`

```vue
<script setup lang="ts">
defineProps({
  width: {
    type: String,
    default: '100%',
  }
})
</script>

<template>
  <div
    class="menu-page"
    :style="{ width: width }"
  >
    <slot></slot>
  </div>
</template>

<style scoped>
.menu-page {
  display: flex;
  color: white;
  justify-items: center;
  align-items: flex-start;
  overflow: auto;
  padding-block: calc(0.25rem* 6);
  padding-inline: calc(0.25rem* 3);
  gap: calc(0.25rem* 5);
  height: fit-content;
  max-height: 100%;
  flex-wrap: wrap;
}

@media (max-width: 1024px) {
  .menu-page {
    width: 100%;
  }
}
</style>
```

## `components/components/nav/AIModelNav.vue`

```vue
﻿<script lang="ts" setup>
import { getLLMProviderList } from '@/api/model';
import { useRouter } from 'vue-router';

const router = useRouter();
const menus = ref<UI.MenuItem[]>([]);
async function getMenus(): Promise<UI.MenuItem[]> {
  const providerList = await getLLMProviderList();
  const providerEntries = providerList.map((provider) => [provider, provider]); // 过滤掉数字索引，只保留字符串键值对
  return providerEntries.map(([key, value]) => ({
    type: 'nav' as UI.ButtonType,
    name: key,
    icon: value as UI.IconType,
    clickAction: () => router.push(`/modelprovider?modelType=${value}`)
  }))
}

onMounted(() => {
  getMenus().then(ms => {
    menus.value = ms
  });
})
</script>

<template>
  <MenuBar
    direction="column"
    class="ai-model-nav"
  >
    <Nav :menus="menus" />
  </MenuBar>
</template>

<style scoped>
.ai-model-nav {
  width: 160px;
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
}

@media screen and (max-width: 768px) {
  .ai-model-nav {
    width: 100%;
  }
}
</style>

```

## `components/home/HomeAside.vue`

```vue
<script setup lang="ts">
import { defaultUIStore } from '@/stores/ui';

const uiStore = defaultUIStore();

const menus: UI.MenuItem[] = [
  {
    type: 'nav',
    name: '模型供应商',
    icon: 'box',
    clickAction: () => uiStore.setCurrentHomeTab('modelprovider'),
  },
  {
    type: 'nav',
    name: '日志',
    icon: 'schedule',
    clickAction: () => uiStore.setCurrentHomeTab('logger'),
  },
  {
    type: 'nav',
    name: '服务',
    clickAction: () => uiStore.setCurrentHomeTab('services'),
  },
  {
    type: 'nav',
    name: '插件',
    icon: 'plugin',
  },
  // {
  //   type: 'nav',
  //   name: '配置',
  //   icon: 'advance',
  //   children: [
  //     {
  //       type: 'nav',
  //       name: '高级配置',
  //       clickAction: () => router.push('configs'),
  //     },
  //     {
  //       type: 'nav',
  //       name: '系统配置',
  //       clickAction: () => router.push('/configs/system'),
  //     }
  //   ],
  // },
];
</script>

<template>
  <div class="nav-item">
  </div>
  <div class="nav-item">
    <MenuBar
      direction="column"
      justify="center"
      is-top-right="false"
    >
      <Nav :menus="menus" />
    </MenuBar>
  </div>
  <div class="nav-item">

  </div>
</template>

<style scoped>
.nav-item {
  justify-items: center;
  gap: 10px;
  border-radius: 8px;
  padding: 10px;
  flex: 1;
}
</style>
```

## `components/home/pages/configs/AdvancedConfig.vue`

```vue
<script setup lang="ts">
import { getAdvancedConfig, saveAdvancedConfig } from '@/api/config';
import type { AdvancedConfig } from '@/api/config';

const defaultConfig: AdvancedConfig = {
  install_components: [],
  code_highlight: {
    enabled: true,
    theme: 'github-dark',
  },
  extra: {},
};

const jsonText = ref(JSON.stringify(defaultConfig, null, 2));
const saving = ref(false);
const statusText = ref('');

const loadConfig = async () => {
  try {
    const data = await getAdvancedConfig();
    jsonText.value = JSON.stringify(data, null, 2);
  } catch (error) {
    statusText.value = `加载失败: ${String(error)}`;
  }
};

const saveConfig = async () => {
  saving.value = true;
  statusText.value = '';
  try {
    const parsed = JSON.parse(jsonText.value) as AdvancedConfig;
    await saveAdvancedConfig(parsed);
    statusText.value = '高级配置保存成功';
  } catch (error) {
    statusText.value = `保存失败: ${String(error)}`;
  } finally {
    saving.value = false;
  }
};

onMounted(loadConfig);
</script>

<template>
  <MenuPage>
    <MenuItem title="高级配置 JSON" button-text="保存" @click="saveConfig">
      <Code language="json" class="json-editor" editable :code="jsonText" />
      <p class="status">{{ saving ? '保存中...' : statusText }}</p>
    </MenuItem>
  </MenuPage>
</template>

<style scoped>
.tips {
  margin-bottom: 10px;
  opacity: 0.9;
}

.json-editor {
  width: 100%;
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.35);
  color: #f7f8ff;
  padding: 10px 12px;
  font-family: Consolas, Monaco, monospace;
}

.status {
  margin-top: 8px;
  min-height: 22px;
  color: #c7ffd5;
}
</style>


```

## `components/home/pages/configs/SystemConfig.vue`

```vue
<script setup lang="ts">
import { getSystemConfig, saveSystemConfig, type SystemConfig } from '@/api/config';

const systemConfig = ref<SystemConfig>({
  log_config: {
    level: "INFO",
    dir: "logs"
  },
  network_config: {
    port: 0,
    timeout: 30000
  }
});
const saving = ref(false);
const statusText = ref('');

const loadConfig = async () => {
  try {
    systemConfig.value = await getSystemConfig();
  } catch (error) {
    statusText.value = `加载失败: ${String(error)}`;
  }
};

const saveConfig = async () => {
  saving.value = true;
  statusText.value = '';
  try {
    await saveSystemConfig(systemConfig.value);
    statusText.value = '系统配置保存成功';
  } catch (error) {
    statusText.value = `保存失败: ${String(error)}`;
  } finally {
    saving.value = false;
  }
};

onMounted(loadConfig);
</script>

<template>
  <MenuPage>
    <MenuItem title="日志配置" button-text="保存" @click="saveConfig" size="small">
    <div class="field">
      <FormCard title="日志等级">
        <select v-model="systemConfig.log_config.level">
          <option value="INFO">INFO</option>
          <option value="DEBUG">DEBUG</option>
          <option value="WARNING">WARNING</option>
          <option value="ERROR">ERROR</option>
        </select>
      </FormCard>
    </div>
    <div class="field">
      <FormCard title="日志目录">
        <input v-model="systemConfig.log_config.dir" placeholder="logs" />
      </FormCard>
    </div>
    <p class="status">{{ saving ? '保存中...' : statusText }}</p>
    </MenuItem>
    <MenuItem title="网络配置" button-text="保存" @click="saveConfig" size="small">
    <div class="field">
      <FormCard title="网络超时(ms)">
        <input v-model="systemConfig.network_config.timeout" placeholder="30000" />
      </FormCard>
    </div>
    <p class="status">{{ saving ? '保存中...' : statusText }}</p>
    </MenuItem>
  </MenuPage>
</template>

<style scoped>
.field {
  display: grid;
  gap: 6px;
  margin-bottom: 10px;
}

input {
  height: 38px;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.2);
  color: #fff;
  background: rgba(0, 0, 0, 0.3);
  padding: 0 12px;
}

.status {
  margin-top: 6px;
  color: #c7ffd5;
  min-height: 22px;
}
</style>

```

## `components/home/pages/LoggerPage.vue`

```vue
<script setup lang="ts">
import { ref, inject, computed, nextTick, watch, onBeforeUnmount } from 'vue'
import { LogLevel } from '@/typings/enums'
import type { LogRecord } from '@/api/logger'

const logs = inject<LogRecord[]>('loggerLogs')!
const virtualListRef = ref()
const atBottom = ref(true)
const isAtBottom = ref(true)

// 过滤（此处可扩展为根据级别过滤，暂不过滤）
const filteredLogs = computed(() => logs)

// 格式化时间（只显示时分秒毫秒）
function formatTime(iso: string) {
  const d = new Date(iso)
  return d.toLocaleTimeString('zh-CN', { hour12: false }) + '.' + String(d.getMilliseconds()).padStart(3, '0')
}

// 级别标签
function levelLabel(level: LogLevel): string {
  const map: Record<LogLevel, string> = {
    [LogLevel.TRACE]: 'TRACE',
    [LogLevel.DEBUG]: 'DEBUG',
    [LogLevel.LOG]: 'LOG',
    [LogLevel.INFO]: 'INFO',
    [LogLevel.WARN]: 'WARNING',
    [LogLevel.ERROR]: 'ERROR',
  }
  return map[level] || '???'
}

// 级别对应 CSS class
function getLevelClass(level: LogLevel): string {
  const classMap: Record<LogLevel, string> = {
    [LogLevel.TRACE]: 'level-trace',
    [LogLevel.DEBUG]: 'level-debug',
    [LogLevel.LOG]: 'level-log',
    [LogLevel.INFO]: 'level-info',
    [LogLevel.WARN]: 'level-warn',
    [LogLevel.ERROR]: 'level-error',
  }
  return classMap[level] || ''
}

// 级别列表
const levels = ['TRACE', 'DEBUG', 'LOG', 'INFO', 'WARN', 'ERROR']

// 筛选
const levelFilter = ref('ALL')
const filtered = computed(() =>
  levelFilter.value
    ? logs.filter(l => l.level === (LogLevel as any)[levelFilter.value])
    : logs
)



function onVirtualScroll(payload: { atBottom: boolean }) {
  atBottom.value = payload.atBottom
}

function filterChange(value: string) {
  levelFilter.value = value
}

function scrollToBottom() {
  virtualListRef.value?.scrollToBottom()
}

watch(filtered, () => {
  if (atBottom.value) {
    scrollToBottom()
  }
})



function clear() {
  logs.splice(0, logs.length)
}
</script>

<template>
  <div class="transparent-glass logger-page">
    <div
      class="log-terminal"
      ref="terminalRef"
    >
      <!-- 工具栏 -->
      <div class="toolbar">
        <span class="badge">{{ levelFilter || 'ALL' }}</span>
        <Select
          :options="levels"
          @change="filterChange"
          :value="levelFilter"
          class="filter-select"
        >
          <option value="">ALL</option>
        </Select>
        <span class="count">{{ filtered.length }} / {{ logs.length }}</span>
        <button
          class="btn"
          @click="clear"
        >清空</button>
        <button
          v-if="!atBottom"
          class="btn accent"
          @click="scrollToBottom"
        >↓ 底部</button>
      </div>

      <!-- 虚拟滚动容器 -->
      <RecycleScroller
        ref="virtualListRef"
        :min-height="500"
        :items="filtered"
        :item-height="22"
        :get-key="(item: LogRecord) => item.timestamp"
        @scroll="onVirtualScroll"
      >
        <template #item="{ item }">
          <div
            class="log-line"
            :class="getLevelClass(item.level)"
          >
            <div class="flex gap-1">
              <span class="log-time">{{ formatTime(item.timestamp) }}</span>
              <span class="log-level">{{ levelLabel(item.level) }}</span>
            </div>
            <!-- 最右边 -->
            <div class="flex-1 text-right">
              <span class="log-message">{{ item.message }}</span>
            </div>

          </div>
        </template>
      </RecycleScroller>
    </div>
  </div>

</template>

<style scoped>
.logger-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
  padding: 10px;
}

.log-terminal {
  display: flex;
  flex-direction: column;
  width: 99%;
  height: 100%;
  background: #0d1117;
  border-radius: 8px;
  overflow: hidden;
  font-family: 'Fira Code', 'Consolas', monospace;
  font-size: 13px;
  line-height: 1.5;
  color: #c9d1d9;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  background: #161b22;
  border-bottom: 1px solid #30363d;
  flex-shrink: 0;
}

.badge {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 4px;
  background: #30363d;
  color: #8b949e;
}

.filter-select {
  width: 120px;
  background: #0d1117;
  color: #c9d1d9;
  border: 1px solid #30363d;
  border-radius: 4px;
  font-size: 12px;
  padding: 2px 4px;
}

.count {
  font-size: 12px;
  color: #484f58;
  margin-left: auto;
}

.btn {
  background: transparent;
  border: 1px solid #30363d;
  color: #8b949e;
  padding: 2px 8px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}

.btn:hover {
  background: #21262d;
  color: #c9d1d9;
}

.btn.accent {
  color: #58a6ff;
  border-color: #58a6ff;
}

.scroller {
  flex: 1;
  overflow-y: auto;
  padding: 4px 0;
}

.log-line {
  display: flex;
  flex-direction: row;
  gap: 8px;
  padding: 1px 12px;
  white-space: nowrap;
  min-height: 22px;
  align-items: baseline;
  justify-content: space-between;
  width: 100%;
  align-items: center;
  overflow: hidden;
}

.log-time {
  color: #484f58;
  flex-shrink: 0;
  min-width: 90px;
}

.log-level {
  flex-shrink: 0;
  min-width: 34px;
  font-weight: bold;
}

.log-message {
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 级别颜色 */
.level-trace .log-level {
  color: #8b949e;
}

.level-debug .log-level {
  color: #58a6ff;
}

.level-log .log-level {
  color: #c9d1d9;
}

.level-info .log-level {
  color: #3fb950;
}

.level-warn .log-level {
  color: #d29922;
}

.level-error .log-level {
  color: #f85149;
}

/* 整行背景微色（可选） */
.level-error {
  background: rgba(248, 81, 73, 0.04);
}

.level-warn {
  background: rgba(210, 153, 34, 0.03);
}
</style>
```

## `components/home/pages/ServicePage.vue`

```vue
<script setup lang="ts">
import { getServiceConfigInfoAll } from '@/api/services';

const services = ref<UI.ServiceInfo[]>([]);
const check = ref(false);
const updateServiceConfig = () => {
  getServiceConfigInfoAll().then((res) => {
    res.forEach((item) => {
      services.value.push({
        id: item.name,
        name: item.name,
        description: item.description,
        status: item.config.some((configItem) => configItem.name === 'enabled' && configItem.value === true) ? 'running' : 'not_enabled',
        config: item.config.map((configItem) => {
          return {
            type: typeof configItem.value === 'boolean' ? 'boolean' : typeof configItem.value === 'string' ? 'string' : 'select',
            label: configItem.name,
            description: configItem.description,
            value: configItem.value,
            options: configItem.options || undefined
          }
        })
      });
    });
    console.log(services.value);
  });
};

onMounted(() => {
  updateServiceConfig();
});



// 每个服务的展开状态（默认全部收起）
const expandedMap = reactive(new Map<string, boolean>())

function toggleExpand(id: string) {
  expandedMap.set(id, !expandedMap.get(id))
}

function isExpanded(id: string) {
  return expandedMap.get(id) ?? false
}

const statusColor = (status: API.ServiceStatus): string => {
  switch (status) {
    case 'running': return '#22c55e'  // 绿色
    case 'stopped': return '#ef4444'  // 红色
    case 'not_enabled': return '#9ca3af' // 灰色
    default: return '#9ca3af'
  }
}

const statusLabel = (status: API.ServiceStatus): string => {
  switch (status) {
    case 'running': return '运行中'
    case 'stopped': return '已停止'
    case 'not_enabled': return '未启用'
    default: return '未知'
  }
}

function updateConfig(serviceId: string, index: number, newValue: boolean | string) {
  const svc = services.value.find(s => s.id === serviceId)
  if (svc && svc.config[index]) {
    svc.config[index].value = newValue
  }
}
</script>

<template>
  <div class="service-list">
    <ServiceCard
      v-for="service in services"
      :key="service.id"
      class="service-item"
    >
      <!-- 顶部：名称 + 描述 + 状态指示灯 -->
      <div
        class="service-header"
        @click="toggleExpand(service.id)"
      >
        <div class="header-left">
          <h3 class="service-name">{{ service.name }}</h3>
          <p class="service-desc">{{ service.description }}</p>
        </div>
        <div class="header-right">
          <span
            class="status-indicator"
            :style="{
              backgroundColor: statusColor(service.status)
            }"
          ></span>
          <span class="status-text">{{ statusLabel(service.status) }}</span>
          <span class="expand-icon">{{ isExpanded(service.id) ? '▾' : '▸' }}</span>
        </div>
      </div>
      <!-- 底部配置区（展开时显示） -->
      <div
        v-show="isExpanded(service.id)"
        class="service-config"
      >
        <RowItem
          v-for="(configItem, index) in service.config"
          :key="index"
          class="config-row"
        >
          <!-- 左侧：标签 + 描述 -->
          <template #left>
            <div class="config-label">
              <span class="config-title">{{ configItem.label }}</span>
              <span
                v-if="configItem.description"
                class="config-desc"
              >{{ configItem.description }}</span>
            </div>
          </template>

          <!-- 右侧：根据类型渲染控件 -->
          <template
            #right
            class="config-control"
          >
            <Checkbox
              v-if="configItem.type === 'boolean'"
              :checked="configItem.value as boolean"
              @checked="(val: boolean) => updateConfig(service.id, index, val)"
            />
            <Select
              :options="configItem.options!"
              v-else-if="configItem.type === 'select'"
              :model-value="configItem.value as string"
              @change="(val: string) => updateConfig(service.id, index, val)"
            />
            <Input
              v-else-if="configItem.type === 'string'"
              class="config-input"
              :value="configItem.value as string"
              @input="(val: string | boolean) => updateConfig(service.id, index, val)"
            />
          </template>
        </RowItem>
      </div>
    </ServiceCard>
  </div>
</template>

<style scoped>
/* ---------- 整体容器 ---------- */
.service-list {
  display: flex;
  flex-direction: column;
  gap: 20px;
  padding: 20px;
  max-height: 90%;
  overflow-y: auto;
}


/* ---------- 顶部头部（可点击展开/收起） ---------- */
.service-header {
  border-radius: 10px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  cursor: pointer;
  user-select: none;
  transition: background 0.2s;
}

.service-header:hover {
  background: rgba(255, 255, 255, 0.05);
}

.header-left {
  flex: 1;
}

.service-name {
  font-size: 18px;
  font-weight: 600;
  color: #fff;
  margin: 0;
  text-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
}

.service-desc {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.6);
  margin: 4px 0 0 0;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.status-indicator {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  display: inline-block;
  box-shadow: 0 0 6px currentColor;
}

.status-text {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.75);
}

.expand-icon {
  font-size: 16px;
  color: rgba(255, 255, 255, 0.5);
  transition: transform 0.2s;
}

/* ---------- 配置区域 ---------- */
.service-config {
  display: flex;
  flex-direction: column;
  gap: 6px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  padding: 10px;
}

.config-label {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 120px;
}

.config-title {
  font-size: 14px;
  font-weight: 500;
  color: #fff;
}

.config-desc {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.45);
}

.config-control {
  flex-shrink: 0;
}

.service-list,
.service-info,
.service-config {
  width: 100%;
}

.service-list {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 20px;
}



.service-content {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
</style>

```

## `components/layout/BackgroundGroup.vue`

```vue
<script setup lang="ts">
import router from '@/router';
import { useUIBackgroundStore } from '@/stores/ui'
const uiStore = useUIBackgroundStore();
const showNav = computed(() => {
  return router.currentRoute.value.path !== '/' && router.currentRoute.value.path !== '/settings'
})
</script>

<template>
  <HeaderNav v-show="showNav" />
  <ImageAcrossFade
    class="background-image"
    :src="uiStore.currentBackground.url"
    position="center center"
    object-fit="cover"
    :duration="uiStore.currentBackground.transition"
  />
</template>

<style scoped>
.background-image {
  position: fixed;
  left: 0;
  top: 0;
  width: 100%;
  height: 100%;
  background-size: cover;
  background-position: center center;
  background-attachment: fixed;
  background-repeat: no-repeat;
  z-index: -2;
}
</style>
```

## `components/layout/HeaderNav.vue`

```vue
<script lang="ts" setup>
import { useRouter } from 'vue-router';
const router = useRouter();

const menus: UI.MenuItem[] = [
  {
    type: 'nav',
    name: '首页',
    icon: 'home',
    clickAction: () => router.push("/home"),
  },
  {
    type: 'nav',
    name: '菜单',
    icon: 'menu',
    clickAction: () => router.push("/settings"),
  },
  {
    type: 'nav',
    name: '聊天',
    icon: 'chat',
    clickAction: () => router.push("/chat"),
  }
];
</script>

<template>
  <MenuBar
    class="header-nav"
    justify="end"
    is-box-shadow="no-box-shadow"
  >
    <Nav
      :menus="menus"
      :hideText="true"
      direction="row"
    />
  </MenuBar>
</template>

<style scoped>
.header-nav {
  border-radius: 8px;
  max-height: 50px;
  top: 20px;
  position: sticky;
  z-index: 1000;
}
</style>
```

## `components/layout/Notification.vue`

```vue
<script setup lang="ts">
import { Notification } from '@/stores/ui';

const notificationStore = Notification();
// v -if= "notificationStore.isVisible"
// 根据类型返回对应的CSS类
const typeClass = computed(() => `notification-${notificationStore.type}`)
</script>

<template>
  <div class="notifictiy">
    <Transition name="slide-in">
      <div
        class="notification"
        :class="[
          'fixed top-5 left-0 z-[10000] flex items-center gap-4 px-6 py-4 min-w-80 max-w-[480px]',
          typeClass
        ]"
      >
        <!-- 角色头像区域 -->
        <div
          class="shrink-0 w-16 h-16 rounded-full overflow-hidden flex items-center justify-center notification-avatar"
        >
          <img
            v-if="notificationStore.avatarUrl"
            :src="notificationStore.avatarUrl"
            alt="avatar"
            class="w-full h-full object-cover"
          />
        </div>

        <!-- 文字内容区域 -->
        <div class="flex-1 flex flex-col gap-1.5">
          <div class="text-base font-semibold notification-title">
            {{ notificationStore.title || '[通知标题]' }}
          </div>
          <div class="text-sm leading-relaxed notification-message">
            {{ notificationStore.message || '[通知内容]' }}
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.notifictiy {
  position: fixed;
  z-index: 9999;
  left: 0;
  min-width: 400px;
}

.notification {
  /* 玻璃态效果 */
  background: linear-gradient(135deg, rgba(30, 30, 40, 0.95) 0%, rgba(20, 20, 30, 0.9) 100%);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);

  border-radius: 0 16px 16px 0;
  box-shadow:
    4px 4px 20px rgba(0, 0, 0, 0.4),
    inset 0 1px 0 rgba(255, 255, 255, 0.1);
}

/* 类型样式 */
.notification-error {
  box-shadow:
    0 0 15px rgba(255, 100, 100, 0.5),
    0 0 30px rgba(255, 100, 100, 0.3),
    0 0 45px rgba(255, 100, 100, 0.15),
    inset 0 0 20px rgba(255, 100, 100, 0.1);
}

.notification-success {
  box-shadow:
    0 0 15px rgba(100, 255, 150, 0.5),
    0 0 30px rgba(100, 255, 150, 0.3),
    0 0 45px rgba(100, 255, 150, 0.15),
    inset 0 0 20px rgba(100, 255, 150, 0.1);
}

.notification-info {
  box-shadow:
    0 0 15px rgba(100, 180, 255, 0.5),
    0 0 30px rgba(100, 180, 255, 0.3),
    0 0 45px rgba(100, 180, 255, 0.15),
    inset 0 0 20px rgba(100, 180, 255, 0.1);
}

.notification-warning {
  box-shadow:
    0 0 15px rgba(255, 200, 100, 0.5),
    0 0 30px rgba(255, 200, 100, 0.3),
    0 0 45px rgba(255, 200, 100, 0.15),
    inset 0 0 20px rgba(255, 200, 100, 0.1);
}

.notification-avatar {
  background: rgba(255, 255, 255, 0.1);
}

.notification-title {
  color: rgba(255, 255, 255, 0.95);
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
}

.notification-error .notification-title {
  color: rgba(255, 150, 150, 1);
}

.notification-success .notification-title {
  color: rgba(150, 255, 180, 1);
}

.notification-info .notification-title {
  color: rgba(150, 200, 255, 1);
}

.notification-warning .notification-title {
  color: rgba(255, 220, 150, 1);
}

.notification-message {
  color: rgba(255, 255, 255, 0.8);
}

/* 动画 */
.slide-in-enter-active,
.slide-in-leave-active {
  transition:
    transform 0.4s cubic-bezier(0.16, 1, 0.3, 1),
    opacity 0.4s cubic-bezier(0.16, 1, 0.3, 1);
}

.slide-in-enter-from {
  transform: translateX(-100%);
  opacity: 0;
}

.slide-in-leave-to {
  transform: translateX(-100%);
  opacity: 0;
}

/* 响应式 */
@media (max-width: 520px) {
  .notification {
    max-width: calc(100vw - 20px);
    min-width: 280px;
  }
}
</style>
```

## `components/main/GameNav.vue`

```vue
<script setup lang="ts">
import { useRouter } from 'vue-router';

const router = useRouter()
const gameNav: UI.MenuItem[] = [
  {
    type: 'menu',
    name: '开始游戏',
  },
  {
    type: 'menu',
    name: '继续游戏',
  },
  {
    type: 'menu',
    name: '游戏设置',
    clickAction: () => router.push('/settings')
  },
  {
    type: 'menu',
    name: '退出游戏',
    clickAction: () => window.close(),
  },
]
</script>

<template>
  <div class="game-nav">
    <Nav
      class="menu-item"
      :menus="gameNav"
      font-family="maokenAssorted"
    />
  </div>
</template>

<style scoped>
.menu-item {
  font-family: 'maokenAssorted';
}

.game-nav {
  display: flex;
  flex-direction: column;
}
</style>
```

## `components/settings/pages/BackgroundSetting.vue`

```vue
<script setup lang="ts">
import { openFolder } from '@/api/config';
import { useUIBackgroundStore } from '@/stores/ui';

const uiStore = useUIBackgroundStore();
const backgroundList = ref<UI.Background[]>([]);

const fileInputType = ['.jpeg', '.png', '.webp', '.bmp', '.svg', '.tif', '.gif'];
const uploadInput = ref<HTMLInputElement | null>(null);
const currentIndex = ref(0);

const getfileType = computed(() => {
  return fileInputType.join(',');
});

const isSelected = (index: number) => {
  return index === currentIndex.value;
};
const selectBackground = (url: string, index: number, transition?: number) => {
  currentIndex.value = index;
  uiStore.setCurrentBackground(url, transition);
};
const triggerUpload = () => {
  if (uploadInput.value) {
    uploadInput.value.click();
  }
};

const handleFileUpload = async (event: Event) => {
  const target = event.target as HTMLInputElement;
  const files = Array.from(target.files || []);
  if (files && files.length > 0) {
    files.forEach((file) => {
      if (!file) {
        return;
      }
      console.log(file);
      //获取文件类型
      if (!file.type.startsWith('image/')) {
        return;
      }
      const fileType = file.type.split('/').pop()?.toLowerCase();
      if (!fileType || !fileInputType.includes(`.${fileType}`)) {
        console.error('文件类型错误:', fileType);
        return;
      }
      const reader = new FileReader();
      reader.onload = () => {
        try {
          if (reader.result) {
            // const name = file.name.split('.')[0] as string;
            // if (backgroundList.value.find((item) => item.name === name)) {
            //   console.error('文件已存在:', name);
            //   return;
            // }
            // uiStore.addBackground({
            //   url: URL.createObjectURL(file),
            //   title: name,
            // });
          }
        } catch (error) {
          console.error('上传背景失败:', error);
        }
      };
      reader.readAsDataURL(file);
    });
  }
  if (target) target.value = '';
};

const openBackgroundFolder = async () => {
  await openFolder("static/images/background");
};

const deleteBackground = (index: number) => {
  if (index === 0) {
    return;
  }
  backgroundList.value.splice(index, 1);
  selectBackground(backgroundList.value?.[index]?.url || '', index);
};

</script>

<template>
  <MenuItem title="选择背景">
  <div class="background-container">
    <BackgroundList>
      <BackgroundCard
        v-for="(background, index) in backgroundList"
        :key="index"
        :isSelected="background.index === currentIndex"
      >
        <div class="background-image-container">
          <img
            :src="background.url"
            :alt="background.name"
            class="background-image"
          />
        </div>
        <div class="background-title">
          <div style="display: flex; gap: 8px;">
            <Button
              :class="['background-select-btn', { selected: isSelected(index) }]"
              @click="selectBackground(background.url, index, background.transition)"
            >
              {{ isSelected(index) ? '已选中' : '选择' }}
            </Button>
            <Button
              class="background-delete-btn"
              @click="deleteBackground(index)"
            >
              删除
            </Button>
          </div>
        </div>
      </BackgroundCard>
    </BackgroundList>
    <Button
      type="big"
      @click="triggerUpload"
    >上传自定义背景</Button>
    <Button
      type="big"
      @click="openBackgroundFolder"
    >打开背景文件夹</Button>
    <input
      multiple
      type="file"
      ref="uploadInput"
      @change="handleFileUpload"
      :accept="getfileType"
      style="display: none"
    />
  </div>
  </MenuItem>
</template>

<style scoped>
/*什么？你问我为什么这里是character-grid? 灵式编程懂不懂！ */
.character-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 20px;
  padding-bottom: 20px;
  width: 100%;
}

/* 图片容器 */
/* 图片容器添加伪元素增强效果 */
.background-image-container::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: linear-gradient(to bottom, transparent 60%, rgba(0, 0, 0, 0.3) 100%);
  z-index: 1;
  pointer-events: none;
}

.background-image-container {
  flex: 1;
  /* 占据剩余空间 */
  position: relative;
  overflow: hidden;
}

/* 图片样式 */
.background-image {
  position: relative;
  width: 100%;
  height: 100%;
  object-fit: cover;
  aspect-ratio: 16/9;
  /* 保持图片比例 */
  transition: transform 0.3s ease;
}

/* 底部信息区域 */
/* 修改卡片底部背景为毛玻璃效果 */
.background-title {
  padding: 12px 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: rgba(255, 255, 255, 0.15);
  /* 更透明的背景 */
  backdrop-filter: blur(10px);
  /* 毛玻璃效果 */
  -webkit-backdrop-filter: blur(10px);
  /* Safari 支持 */
  border-top: 1px solid rgba(255, 255, 255, 0.2);
  /* 更柔和的边框 */
  position: relative;
  z-index: 2;
}

/* 标题文本样式 */
/* 标题文字颜色调整以适应毛玻璃背景 */
.background-title::before {
  content: attr(data-title);
  font-weight: 500;
  color: rgba(255, 255, 255, 0.9);
  /* 更亮的文字颜色 */
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 70%;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
}

.background-delete-btn,
.background-select-btn {
  padding: 6px 12px;
  color: white;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  flex-shrink: 0;
}

/* 选择按钮 */
.background-select-btn {
  background: #4f46e5;
}

.background-select-btn:hover {
  background: #4338ca;
  transform: translateY(-1px);
}

.background-delete-btn {
  background: #ef4444;

  &:hover {
    background: #b91c1c;
    transform: translateY(-1px);
  }
}

.background-select-btn:active {
  transform: translateY(0);
}

.effect-list {
  display: flex;
  justify-content: space-around;
  gap: 20px;
  align-items: center;
}

@media (max-width: 768px) {

  /*什么？你问我为什么这里是character-grid? 灵式编程懂不懂！ */
  .character-grid {
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  }
}


/* 已选中按钮样式 */
.background-select-btn.selected {
  background-color: #10b981 !important;
}
</style>
```

## `components/settings/pages/CharacterSetting.vue`

```vue
<script setup lang="ts">

const characterList = ref<CharacterItem[]>([
  {
    id: 1,
    name: '小王',
    desc: '小王是游戏里的一个角色，他很懒，什么都没干。',
    avatar: 'https://picsum.photos/200/300'
  }
]);
function isSelected(id: number): boolean {
  return true;
  // return gameStore.avatar.character_id === id;
}
const selectCharacter = async (characterId: number): Promise<void> => {
  try {
    // await characterSelect({
    //   user_id: userId.value.toString(),
    //   character_id: characterId.toString(),
    // });
    // updateSelectedStatus();
  } catch (error) {
    console.error('切换角色失败:', error);
  }
};
</script>

<template>

  <MenuItem
    title="角色列表"
    button-text="刷新"
    @click=""
  >
  <CharacterList>
    <CharacterCard
      v-for="(character, index) in characterList"
      :key="index"
      :avatar="character.avatar"
      :name="character.name"
      :desc="character.desc"
    >
      <template #actions>
        <Button
          type="select"
          :class="['character-select-btn', { selected: isSelected(character.id) }]"
          @click="selectCharacter(character.id)"
        >{{ isSelected(character.id) ? '√ 选中' : '选择' }}</Button>
      </template>
    </CharacterCard>
  </CharacterList>
  </MenuItem>
</template>

<style scoped>
.character-select-btn {
  position: absolute;
  bottom: 15px;
  right: 15px;
  background-color: #5e72e4;
  color: white;
  border: none;
  padding: 6px 12px;
  border-radius: 20px;
  cursor: pointer;
  transition: all 0.2s ease;
  font-size: 13px;
  font-weight: 500;
}

.character-select-btn:hover {
  background-color: #4a5acf;
  transform: translateY(-1px);
  box-shadow: 0 2px 6px rgba(94, 114, 228, 0.3);
}

.selected {
  background-color: #10b981 !important;
}
</style>
```

## `components/settings/pages/GeneralSetting.vue`

```vue
<script setup lang="ts">
import { useUserStore } from '@/stores/user';

const userStore = useUserStore()
// const APIBaseURL = ref('http://115.190.213.187:23817/v1');
// const APIKey = ref('sk-202603031555cheshi');
// const modelList = ref(['gpt5.1']);
// const selectedIndex = ref(0);

const textSpeedChange = (value: number) => {
  userStore.config.textSpeed = value;
};
</script>

<template>
  <MenuItem title="⚡ 文字显示速度">
  <Silder
    @change="textSpeedChange"
    :min="0"
    :max="100"
    :step="1"
    :Value="userStore.config.textSpeed"
  >
    <template #left>慢</template>
    <template #right>快</template>
  </Silder>
  </MenuItem>
  <MenuItem title="📝 显示文字样本">
  <Text :speed="userStore.config.textSpeed">
    你好，我是一个机器人。
  </Text>
  </MenuItem>
  <MenuItem
    title=" ✨ WebSocket状态"
    size="small"
    :disabled="true"
  >
  <div
    class="ws-status"
    :class="['ws-status', userStore.clientId ? 'connected' : 'disconnected']"
  >
    {{ userStore.clientId ? '√ 已连接' : ' X 未连接' }}
  </div>
  </MenuItem>
</template>

<style scoped>
.ws-status {
  text-align: center;
}

.ws-status.connected {
  color: #00ff00;
}

.ws-status.disconnected {
  color: #ff0000;
}
</style>
```

## `components/settings/pages/HistorySetting.vue`

```vue
<script setup lang="ts">
import { useUserStore } from '@/stores/user';
import type { DialogMessageItem } from '@/typings/user-types';

const user = useUserStore();
const dialogHistory = ref<DialogMessageItem[]>(user.dialogHistory);
</script>

<template>
  <MenuItem title="◈ 历史对话">
  <div class="history-container">
    <div v-if="dialogHistory.length === 0" class="status-message">
      暂无历史记录，去和ta聊聊天叭(*^▽^*)
    </div>
    <div v-else class="chat-history-container" ref="chatContainer">
      <HistorySession :history="dialogHistory" />
    </div>
  </div>
  </MenuItem>
</template>

<style scoped>
.history-container {
  height: 500px;
  /* 如果内容过多，可以设置最大高度和滚动条 */
}

.chat-history-container {
  padding: 10px;
  display: flex;
  flex-direction: column;
  /* 让消息垂直排列 */
  gap: 12px;
  /* 消息之间的间距 */
  font-size: 18px;
  max-height: 500px;
  /* 如果内容过多，可以设置最大高度和滚动条 */
  overflow-y: auto;
  scroll-behavior: smooth;
}

.status-message {
  display: flex;
  align-items: center;
  justify-content: center;
  color: #f5f5f5;
  padding: 2rem;
  font-size: 24px;
  font-weight: bold;
  height: 100%;
  text-shadow: 0 0 5px rgba(255, 255, 255, 0.5);
}
</style>

```

## `components/settings/pages/SoundSetting.vue`

```vue
<script setup lang="ts">
import { DEFAULT_CONFIG } from '@/config';
import { useUIBackgroundStore } from '@/stores/ui';

const uiStore = useUIBackgroundStore();
const audioFileTypes = ['.mp3', '.wav', '.ogg', '.m4a', '.aac', '.flac', '.webm'];
const currentIndex = ref(0);
const uploadInput = ref<HTMLInputElement | null>(null);
const getAudioFileType = computed(() => audioFileTypes.join(','));
const backgroundVolume = ref(50);
const isMusicPlaying = ref(false)
const playPauseButtonText = computed(() => (isMusicPlaying ? '⏸ 暂停' : '▶ 播放'));
const musicList = ref<UI.Music[]>([DEFAULT_CONFIG.sound.audio]);

const handlePlayPause = () => {
  if (uiStore.currentMusic.ref) {
    if (isMusicPlaying) {
      uiStore.currentMusic.ref.pause();
    } else {
      uiStore.currentMusic.ref.play();
    }
  }
};

const handleStop = () => {
  if (uiStore.currentMusic.ref) {
    uiStore.currentMusic.ref.pause();
    isMusicPlaying.value = false;
  }
};

watch(uiStore.currentMusic.progress, (newVal: number) => {
  musicList.value[currentIndex].progress = newVal;
})

const playMusic = (music: UI.Music) => {
  if (useUIStore) {
    // uiStore.currentMusic.info = music
    // uiStore.currentMusic.ref.volume = backgroundVolume.value / 100;
    // //设置当前时间
    // uiStore.backgroundAudioPlayer.currentTime = (music.progress / 100) * uiStore.backgroundAudioPlayer.duration;
    // console.log(uiStore.backgroundAudioPlayer.currentTime);
    // uiStore.backgroundAudioPlayer.play().catch(() => { console.log('播放失败'); });
    // uiStore.setIsMusicPlaying(true);
  }
};

const updateBackgroundVolume = (volume: number) => {
  if (uiStore.currentMusic) {
    uiStore.currentMusic.ref.volume = volume / 100;
  }
};

const triggerUpload = () => {
  uploadInput.value?.click();
};

const handleMusicUpload = (event: Event) => {
  const target = event.target as HTMLInputElement;
  const files = Array.from(target.files || []);

  files.forEach((file) => {
    if (!file || !file.type.startsWith('audio/')) {
      return;
    }
    const ext = `.${file.name.split('.').pop()?.toLowerCase() || ''}`;
    if (!audioFileTypes.includes(ext)) {
      return;
    }
    const musicName = file.name.replace(/\.[^.]+$/, '');
    if (musicList.value.some((item) => item.name === musicName)) {
      return;
    }
    musicList.value.push({
      name: musicName,
      url: URL.createObjectURL(file),
      progress: 0,
    });
  });

  if (target) {
    target.value = '';
  }
};

const deleteMusic = (index: number) => {
  if (index < 0 || index >= musicList.value.length || index === 0) return;
  try {
    musicList.value.splice(index, 1);
    currentIndex.value = index;
    if (index === 0) {
      currentIndex.value = 0;
    }
  } catch (error) {
    console.log(error);
  }
};

onUnmounted(() => {
  musicList.value.forEach((item) => URL.revokeObjectURL(item.url));
});
</script>

<template>

  <MenuItem
    title="角色音量"
    size="small"
  >
  <Silder>
    <template #left>弱</template>
    <template #right>强</template>
  </Silder>
  </MenuItem>
  <MenuItem
    title="🎶 背景音量"
    size="small"
  >
  <Silder
    :Value="backgroundVolume"
    @change="updateBackgroundVolume"
  >
    <template #left>弱</template>
    <template #right>强</template>
  </Silder>
  </MenuItem>
  <MenuItem
    title="音效音量"
    size="small"
  >
  <Silder>
    <template #left>弱</template>
    <template #right>强</template>
  </Silder>
  </MenuItem>
  <MenuItem title="⚙ 背景音乐设置">
  <div class="music-controls">
    <Button
      type="big"
      @click="handlePlayPause"
      class="left-button"
    >{{
      playPauseButtonText
    }}</Button>
    <Button
      type="big"
      @click="handleStop"
      class="left-button"
    >■ 停止</Button>
    <span class="music-name">当前: {{ musicList[currentIndex.value].name || '未选择音乐' }}</span>
  </div>
  <div class="music-list">
    <div
      v-if="musicList.length === 0"
      class="empty-list"
    >暂无音乐，请上传</div>
    <div
      v-for="(music, index) in musicList"
      :key="music.url"
      class="music-item"
      @click="playMusic(music)"
    >
      <div class="music-item-name">{{ music.name }}</div>
      <div class="music-item-progress">
        <Silder
          :Value="music.progress"
          @input="updateMusicProgress(index)"
          :max="100"
          :min="0"
          :step="0.1"
        />
      </div>
      <Button
        @click="deleteMusic(index)"
        class="action-btn-delete glass-effect"
      >删除</Button>
    </div>
  </div>
  <div class="music-upload">
    <Button
      type="big"
      @click="triggerUpload"
    >➕ 添加音乐</Button>
    <input
      ref="uploadInput"
      type="file"
      :accept="getAudioFileType"
      multiple
      style="display: none"
      @change="handleMusicUpload"
    />
  </div>
  </MenuItem>
  <audio ref="characterTestPlayer"></audio>
  <audio ref="bubbleTestPlayer"></audio>
</template>

<style scoped>
sound-test,
.music-controls,
.music-upload {
  display: flex;
  justify-content: space-around;
  gap: 20px;
  align-items: center;
}

.music-list {
  max-height: 200px;
  overflow-y: auto;
  margin-top: 15px;
  border: 1px solid #555;
  padding: 5px;
  background-color: rgba(0, 0, 0, 0.2);
  border-radius: 10px;
}

.music-name {
  flex-grow: 1;
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: #eee;
}

.empty-list {
  text-align: center;
  color: #999;
  padding: 20px;
}

.music-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  cursor: pointer;
  border-bottom: 1px solid #444;
  transition: background-color 0.2s;
}

.music-item:hover {
  background-color: rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  color: var(--accent-color);
}

.music-item:last-child {
  border-bottom: none;
}

.music-item-name {
  flex-grow: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.action-btn-delete {
  flex-shrink: 0;
  margin-left: 10px;
  /* 你可以为删除按钮定义更小的尺寸 */
  padding: 4px 8px;
  font-size: 12px;
}

.action-btn-delete.glass-effect {
  background: rgba(255, 0, 0, 0.3);
  transition: all 0.2s ease;
}

.action-btn-delete {
  padding: 8px 16px;
  border: 0px solid #555;
  color: #ddd;
  cursor: pointer;
  border-radius: 4px;
  transition:
    background-color 0.2s,
    border-color 0.2s;
  white-space: nowrap;
  font-weight: bold;
}

.action-btn-delete.glass-effect:hover {
  transform: translateY(-1px);
  background: rgba(207, 0, 0, 0.3);
}

.left-button.big {
  width: 20%;
}

.music-upload {
  margin-top: 15px;
}

@media (max-width: 426px) {
  .music-item-progress {
    display: none;
  }
}
</style>
```

## `components/settings/SettingsNav.vue`

```vue
﻿<script setup lang="ts">
import { defaultUIStore } from '@/stores/ui';
import { useRouter } from 'vue-router';
const router = useRouter();
const uiStore = defaultUIStore();
const menus: UI.MenuItem[] = [
  {
    type: 'nav',
    name: '通用',
    icon: 'advance',
    clickAction: () => uiStore.setCurrentSettingsTab('general'),
  },
  {
    type: 'nav',
    name: '背景',
    icon: 'background',
    clickAction: () => uiStore.setCurrentSettingsTab('background'),
  },
  {
    type: 'nav',
    name: '对话历史',
    icon: 'history',
    clickAction: () => uiStore.setCurrentSettingsTab('history'),
  },
  {
    type: 'nav',
    name: '角色',
    icon: 'character',
    clickAction: () => uiStore.setCurrentSettingsTab('character'),
  },

  {
    type: 'nav',
    name: '音效',
    icon: 'sound',
    clickAction: () => uiStore.setCurrentSettingsTab('sound'),
  }
];

const closeSettingsNav = () => {
  router.back();
}

</script>

<template>
  <div class="logo"></div>
  <MenuBar
    justify="center"
    class="nav-container"
    is-box-shadow="no-box-shadow"
  >
    <Nav
      :menus="menus"
      :hideText="true"
      direction="row"
    />
  </MenuBar>
  <div class="close-container">
    <Icon
      @click="closeSettingsNav"
      icon="close"
      :icon-size="24"
    />
  </div>
</template>

<style scoped>
.nav-container {
  display: flex;
  align-items: center;
}

.close-container {
  --tw-duration: 300ms;
  transition-duration: 300ms;
  color: white;
  cursor: pointer;
  display: flex;
  justify-items: center;
  align-items: center;
  transition-property: all;
  --tw-ease: var(--ease-in-out);
  transition-timing-function: var(--ease-in-out);
  padding: calc(var(--spacing) * 1.5);
  background-color: transparent;
  border-radius: calc(infinity * 1px);
}

.close-container:hover {
  color: var(--accent-color);
}
</style>

```

## `composables/useForceLandscape.ts`

```ts
export class useForceLandscape {
  constructor(breakpoint = 768) {
    this.breakpoint = breakpoint
  }

  breakpoint: number
  private isSmall(){
    return window.innerWidth <= this.breakpoint && window.innerHeight > window.innerWidth
  }

  private applyCssRotate(){
    document.body.classList.add('force-landscape')
  }

  private removeCssRotate(){
    document.body.classList.remove('force-landscape')
  }

  public async tryLock(){
    // 先试原生 API
    if (screen.orientation?.lock) {
      try {
        await screen.orientation.lock('landscape')
        return true
      } catch {
        // fall through
      }
    }
    // 降级 CSS
    this.applyCssRotate()
    return false
  }

  public unlock(){
    screen.orientation?.unlock()
    this.removeCssRotate()
  }

  // 旋转后也要重新判断（比如用户手动横过来再竖回去）
  public onResize = () => {
    if (this.isSmall()) {
      this.applyCssRotate()
    } else {
      this.removeCssRotate()
    }
  }

  public init(){
    if(this.isSmall()){
      this.applyCssRotate()
    }
    window.addEventListener('resize', this.onResize)
    window.addEventListener('orientationchange', this.onResize)
  }
  public destroy(){
    window.removeEventListener('resize', this.onResize)
    window.removeEventListener('orientationchange', this.onResize)
    this.removeCssRotate()
  }
}
```

## `config.ts`

```ts
import { LogLevel } from "./typings/enums";

export const DEFAULT_CONFIG: AppOptions = {
  websocket: {
    maxReconnectAttempts: 5,
    reconnectInterval: 1000,
  },
  text: {
    speed: 100,
    volume: 100,
  },
  background: {
    transition: 0.5,
    url: "/images/background/default_bg.jpg"
  },
  sound: {
    audio: {
      name: '夏·烟火',
      url: '/audios/夏·烟火.mp3',
      progress: 0,
    }
  },
  logger: {
    enabled: false,
    minLevel: LogLevel.INFO,
    exclude: {
      enabled: false,
      length: 100, // 排除的模式数量
      patterns: [],// 排除的模式
    }
  }
}
```

## `events.ts`

```ts
import WebSockets from "./utils/socket";
export const websocket = new WebSockets()

export function registerEventListener(type: string, callback: (...args: any[]) => void) {
  websocket.registerEventListener(type as string, callback);
}

export function unregisterEventListener(type: string, callback?: (event: any) => void) {
  websocket.removeEventListener(type as string, callback);
}

export function unregisterAllEventListeners(types: Record<string, (...args: any[]) => void>) {
  Object.keys(types).forEach(type => {
    unregisterEventListener(type, types[type as string]);
  });
}

//注册多事件{eventType, callback}
export function registerEventListeners(types: Record<string, (event: any) => void>) {
  Object.keys(types).forEach(type => {
    const callback = types[type as string] as (...args: any[]) => void;
    if (callback) {
      registerEventListener(type, callback);
    }
  });
}
```

## `main.ts`

```ts
﻿import './assets/css/main.css'

import 'highlight.js/lib/common'
import { createApp } from 'vue'

import App from './App.vue'
import router from './router'
import { installLogForwarderPlugin } from './plugins/LogForwarder'
import pinia from './stores'

const app = createApp(App)
app.use(pinia)
app.use(router)
app.use(installLogForwarderPlugin)
app.mount('#app')

```

## `plugins/LogForwarder.ts`

```ts
﻿import { pushLog, type LogRecord } from '@/api/logger';
import { DEFAULT_CONFIG } from '@/config';
import { LogLevel, LogSource, WebSocketEvent } from '@/typings/enums';
import WebSockets from '@/utils/socket';
import type { App, Plugin } from 'vue';

const levelOrder: Record<LogLevel, number> = {
  [LogLevel.TRACE]: 0,
  [LogLevel.DEBUG]: 1,
  [LogLevel.LOG]: 2,
  [LogLevel.INFO]: 3,
  [LogLevel.WARN]: 4,
  [LogLevel.ERROR]: 5,
};

export class LogForwarder {
  logs = reactive<LogRecord[]>([{
    log_name: 'log_forwarder_init',
    timestamp: new Date().toISOString(),
    level: LogLevel.INFO,
    message: 'LogForwarder initialized',
    source: LogSource.FRONTEND,
  }, {
    log_name: 'log_forwarder_init',
    timestamp: new Date().toISOString(),
    level: LogLevel.INFO,
    message: 'LogForwarder initialized',
    source: LogSource.FRONTEND,
  }]);//测试数据
  maxLogs = 2000;
  private flushTimer: number | null = null;
  private isFlushing = false;
  private initialized = false;

  init() {
    if (this.initialized || !DEFAULT_CONFIG.logger.enabled) {
      return;
    }
    this.initialized = true;
    this.overrideConsoleMethods();
    window.addEventListener("beforeunload", () => {
      void this.flushImmediately();
    });
  }

  private overrideConsoleMethods() {
    const methods = ["debug", "info", "warn", "error", "log"] as const;
    const origin: Record<string, (...args: unknown[]) => void> = {};
    ["debug", "info", "warn", "error", "log"].forEach((method) => {
      origin[method] = (console as any)[method];
    });

    methods.forEach((method) => {
      const mappedLevel = this.mapConsoleMethodToLevel(method);
      (console as any)[method] = (...args: unknown[]) => {
        this.captureLog(mappedLevel, args);
        origin[method]?.apply(console, args);
      };
    });
  }

  private mapConsoleMethodToLevel(method: keyof Console): LogLevel {
    if (method === "debug") return LogLevel.DEBUG;
    if (method === "info") return LogLevel.INFO;
    if (method === "warn") return LogLevel.WARN;
    if (method === "error") return LogLevel.ERROR;
    return LogLevel.LOG;
  }

  private captureLog(level: LogLevel, args: unknown[]) {
    if (!DEFAULT_CONFIG.logger.enabled || this.shouldSkipLevel(level)) {
      return;
    }

    const message = args
      .map((arg) => {
        if (typeof arg === "string") return arg;
        try {
          return JSON.stringify(arg);
        } catch {
          return String(arg);
        }
      })
      .join(" ");

    const record: LogRecord = {
      log_name: "web_console",
      timestamp: new Date().toISOString(),
      level,
      message,
      source: LogSource.FRONTEND,
      metadata: {
        userAgent: navigator.userAgent,
        platform: navigator.platform,
      },
    };

    this.addToQueue(record);
    this.logs.push(record)
    // 限制最大条数
    if (this.logs.length > this.maxLogs) {
      this.logs.splice(0, this.logs.length - (this.maxLogs * 0.8))  // 保留 maxLogs*0.8 条，丢弃最早的 *0.2 条
    }
  }

  private shouldSkipLevel(level: LogLevel): boolean {
    return (
      levelOrder[level] < levelOrder[DEFAULT_CONFIG.logger.minLevel as LogLevel]
    );
  }

  private addToQueue(record: LogRecord) {
    this.logs.push(record);
    if (this.flushTimer) {
      clearTimeout(this.flushTimer);
    }
    this.flushTimer = window.setTimeout(() => {
      this.flushTimer = null;
      void this.flush();
    }, 80);
  }

  async flush() {
    if (this.isFlushing || this.logs.length === 0) {
      return;
    }
    this.isFlushing = true;
    const batch = [...this.logs];
    this.logs = [];

    try {
      await Promise.all(
        batch.map((item) => {
          return pushLog(item);
        })
      );
    } catch {
      this.logs.unshift(...batch);
    } finally {
      this.isFlushing = false;
    }
  }

  async flushImmediately() {
    if (this.flushTimer) {
      clearTimeout(this.flushTimer);
      this.flushTimer = null;
    }
    await this.flush();
  }

  log(entry: LogRecord) {
    if (!DEFAULT_CONFIG.logger.enabled) {
      return;
    }
    this.addToQueue({
      timestamp: new Date().toISOString(),
      source: LogSource.FRONTEND,
      ...entry,
    });
    this.logs.push(entry)
    if (this.logs.length > this.maxLogs) {
      this.logs.splice(0, this.logs.length - (this.maxLogs * 0.8))
    }
  }

  destroy() {
    void this.flushImmediately();
  }
}

const logger = new LogForwarder();

const vueErrorHandler = (error: unknown, vm: any, info: string) => {
  const errorMessage = error instanceof Error ? error.message : String(error);
  const stackTrace = error instanceof Error ? error.stack : undefined;
  logger.log({
    log_name: 'vue_error',
    level: LogLevel.ERROR,
    message: `Vue component error: ${errorMessage}`,
    source: LogSource.FRONTEND,
    stack_trace: stackTrace,
    metadata: {
      component: vm?.$options?.name || 'UnknownComponent',
      info,
    },
  });
};

const globalErrorHandler = (event: ErrorEvent) => {
  logger.log({
    log_name: 'global_error',
    level: LogLevel.ERROR,
    message: event.message || 'Global error',
    source: LogSource.FRONTEND,
    stack_trace: event.error?.stack,
  });
};

const unhandledRejectionHandler = (event: PromiseRejectionEvent) => {
  logger.log({
    log_name: 'unhandled_rejection',
    level: LogLevel.ERROR,
    message: `Unhandled promise rejection: ${String(event.reason)}`,
    source: LogSource.FRONTEND,
  });
};

export const installLogForwarderPlugin: Plugin = {
  install(app: App) {
    logger.init();
    app.config.errorHandler = vueErrorHandler;
    window.addEventListener('error', globalErrorHandler);
    window.addEventListener('unhandledrejection', unhandledRejectionHandler);
    app.config.globalProperties.$log = logger;
    app.provide('logger', logger);
    app.provide('loggerLogs', logger.logs);
  },
};

export const useLogger = () => logger;

export default logger;

```

## `plugins/transport.ts`

```ts
﻿import { WebSocketEvent } from "@/typings/enums";
import { asyncCreateScriptTag } from "@/utils/util";
import WebSockets from "@/utils/socket";
import { useUserStore } from "@/stores/user";
import type { App, Plugin } from "vue";

interface QtApiObject {
};

class UnifiedRuntimeTransport {
  public mode: "desktop" | "web" = "web";
  public websocket: WebSockets | null = null;
  private heartbeatIntervalId: number | null = null;

  async init(): Promise<void> {
    // this.qtBridge = await this.tryConnectQtBridge();
    // this.mode = this.qtBridge ? "desktop" : "web";
    // if (this.qtBridge) {
    //   this.qtBridge.statusChanged.connect((payloadJson: string) => {
    //     let payload: unknown = payloadJson;
    //     try {
    //       payload = JSON.parse(payloadJson);
    //     } catch {
    //       payload = payloadJson;
    //     }
    //     this.statusHandlers.forEach((handler) => handler(payload));
    //   });

    //   this.qtBridge.taskCompleted.connect((payloadRaw: unknown) => {
    //     let payload: QtTaskCompleted;
    //     if (typeof payloadRaw === "string") {
    //       try {
    //         payload = JSON.parse(payloadRaw) as QtTaskCompleted;
    //       } catch {
    //         return;
    //       }
    //     } else {
    //       payload = payloadRaw as QtTaskCompleted;
    //     }
    //     if (!payload.requestId) return;

    //     const task = this.pending.get(payload.requestId);
    //     if (!task) return;
    //     this.pending.delete(payload.requestId);
    //     if (payload.success) {
    //       task.resolve(payload.data);
    //     } else {
    //       task.reject(new Error(payload.error || "Qt task failed"));
    //     }
    //   });
    //   this.qtBridge.logMessage.connect((text: string) => console.log("[qt]", text));
    // }
    await this.initWebSocket();
  }

  private async initWebSocket(): Promise<void> {
    const wsUrl = import.meta.env.VITE_WS_URL || "ws://localhost:8000/ws";

    this.websocket = new WebSockets(
      wsUrl,
      // onConnect
      (event) => {
        const response = event.data;
        if (response.type === WebSocketEvent.CONNECT && response.data) {
          console.log(response);
          const wsstore = useUserStore();
          wsstore.clientId = response.data.client_id;
          console.log(`[WebSocket] Connected in ${this.mode} mode:`, wsstore.clientId);
        }
      },
      // onError
      (event: Event) => {
        console.error("[WebSocket] Error:", event);
      },
      // onOpen
      () => {
        console.log("[WebSocket] Open");
        this.startHeartbeat();
      },
      // onClose
      (event: any) => {
        console.log("[WebSocket] Closed:", event.code, event.reason);
        const wsstore = useUserStore();
        wsstore.clientId = '';
        this.stopHeartbeat();
      }
    );
  }

  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.heartbeatIntervalId = window.setInterval(() => {
      if (this.websocket?.readyState === WebSocket.OPEN) {
        this.websocket.send({ type: WebSocketEvent.HEARTBEAT });
      }
    }, this.websocket?.heartbeatInterval || 30000);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatIntervalId !== null) {
      clearInterval(this.heartbeatIntervalId);
      this.heartbeatIntervalId = null;
    }
  }

  private async tryConnectQtBridge(): Promise<QtApiObject | null> {
    const qt = window.qt;
    if (!qt?.webChannelTransport) {
      return null;
    }
    await this.ensureQtWebChannelScript();

    return await new Promise<QtApiObject | null>((resolve) => {
      if (!window.QWebChannel) {
        resolve(null);
        return;
      }
      new window.QWebChannel(
        qt.webChannelTransport,
        (channel: { objects?: Record<string, unknown> }) => {
          resolve(
            channel.objects?.api as QtApiObject | undefined
            || null
          );
        }
      );
    });
  }

  private async ensureQtWebChannelScript(): Promise<void> {
    if (window.QWebChannel) {
      return;
    }
    await asyncCreateScriptTag("qrc:///qtwebchannel/qwebchannel.js");
  }
}

const transport = new UnifiedRuntimeTransport();

export const installruntimeTransportPlugin: Plugin = {
  install(app: App) {
    void transport.init();
  },
};

export default transport;

```

## `stores/index.ts`

```ts
import { createPinia } from 'pinia'

const pinia = createPinia()
export default pinia
```

## `stores/ui.ts`

```ts
﻿import { defineStore } from 'pinia';
import { DEFAULT_CONFIG } from '@/config';
export const useUIBackgroundStore = defineStore('ui-background', {
  state: () => ({
    currentBackground: {
      url: '/images/background/default_bg.jpg',
      transition: 0.5,
    },
    currentMusic: {
      url: '/audios/夏·烟火.mp3',
      progress: 0,
      index: 0
    }
  }),
  actions: {
    setCurrentBackground(url: string, transition?: number) {
      this.currentBackground = {
        url,
        transition: transition || this.currentBackground.transition
      };
    },
  }
});

export const defaultUIStore = defineStore('ui', {
  state: (): UI.State => ({
    currentHomeTab: "services",
    currentSettingsTab: "general"
  }),
  actions: {
    setCurrentHomeTab(tab: UI.HomeTab) {
      this.currentHomeTab = tab;
    },
    setCurrentSettingsTab(tab: UI.SettingsTab) {
      this.currentSettingsTab = tab;
    },
  },
})

let hideTimer: number | null = null; // 通知的定时器

// const notificationDebounceMap = new Map<string, number>()
const DEBOUNCE_MS_NETWORK = 10000 // "未注明的错误" 10秒
const DEBOUNCE_MS_DEFAULT = 3000

export const Notification = defineStore('ui-notification', {
  state: (): UI.NotificationState => ({
    isVisible: false,
    title: '',
    type: 'info',
    avatarUrl: '',
    message: '',
    duration: 3000,
  }),
  actions: {
    // 显示通知
    showNotification(options: {
      type?: UI.NotificationType,
      title?: string,
      avatarUrl?: string,
      message?: string,
      duration?: number
    }) {
      const defaultNotification = {
        duration: options.duration || DEBOUNCE_MS_DEFAULT,
        type: options.type || 'info',
        title: options.title || '',
        avatarUrl: options.avatarUrl || '',
        message: options.message || '',
      };
      this.isVisible = true;
      const now = Date.now();
      this.$state = {
        isVisible: true,
        ...defaultNotification
      }
      const isDefaultError = defaultNotification.type === 'error' && defaultNotification.message === '未知错误'
      const duration = isDefaultError ? DEBOUNCE_MS_NETWORK : defaultNotification.duration
      if (duration > 0) {
        hideTimer = window.setTimeout(() => {
          this.hideNotification()
        }, duration)
      }
    },

    // 隐藏通知
    hideNotification() {
      this.isVisible = false;
      if (hideTimer) {
        clearTimeout(hideTimer);
        hideTimer = null;
      }
    },

    // 显示错误通知
    showError(options: {
      title?: string,
      avatarUrl?: string,
      message?: string,
      duration?: number
    }) {
      this.showNotification({ ...options, type: 'error' })
    },

    // 显示成功通知
    showSuccess(options: {
      title?: string,
      avatarUrl?: string,
      message?: string,
      duration?: number
    }) {
      this.showNotification({ ...options, type: 'success' })
    },
    // 显示警告通知
    showWarning(options: {
      title?: string,
      avatarUrl?: string,
      message?: string,
      duration?: number
    }) {
      this.showNotification({ ...options, type: 'warning' })
    },
    // 显示信息通知
    showInfo(options: {
      title?: string,
      avatarUrl?: string,
      message?: string,
      duration?: number
    }) {
      this.showNotification({ ...options, type: 'info' })
    },
  }
})
```

## `stores/user.ts`

```ts
import { loadJsonFile, saveJsonFile } from '@/utils/util';
import { defineStore } from 'pinia';

export const useUserStore = defineStore('user', {
  state: (): User.State => ({
    config: {
      textSpeed: 50,
      bgVolume: 50,
      soundVolume: 50,
      roleVolume: 50,
      bgPath: '',
      soundPath: '',
    },
    clientId: ''
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

```

## `views/ChatView.vue`

```vue
<template>
  <div class="game-image"></div>
  <div class="game-dialog">
    <GameDialog />
  </div>
</template>

<style scoped>
.game-image {
  position: absolute;
}

.game-dialog {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: 2;
}
</style>

```

## `views/HomeView.vue`

```vue
<script setup lang="ts">
import { defaultUIStore } from '@/stores/ui';

const uiStore = defaultUIStore();
</script>

<template>
  <div class="home-view">
    <aside class="aside-nav">
      <HomeAside style="height: 100%;" />
    </aside>
    <main class="page">
      <MenuPage width="100%">
        <ServicePage v-show="uiStore.currentHomeTab === 'services'" />
        <LoggerPage v-show="uiStore.currentHomeTab === 'logger'" />
      </MenuPage>
    </main>
  </div>
</template>

<style scoped>
.home-view {
  display: flex;
  flex-direction: row;
  height: 100%;
  width: 100%;
}

.aside-nav {
  position: sticky;
  top: 0;
  left: 0;
  width: max-content;
  overflow: hidden;
  height: 100%;
}

.aside-nav {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
}

.page {
  flex: 1;
}

@media (max-width: 768px) {
  .aside-nav {
    display: none;
  }

  .page {
    width: 98%;
  }
}
</style>
```

## `views/MainMemu.vue`

```vue
<script setup lang="ts">
</script>

<template>
  <div class="main-page">
    <GameNav />
  </div>
</template>

<style scoped>
.main-page {
  display: flex;
  flex-direction: row;
  width: 80%;
}

@media screen and (max-width: 768px) {
  .main-page {
    width: 95%;
  }
}
</style>

```

## `views/NotFoundView.vue`

```vue
<script setup lang="ts">
import { useRouter } from 'vue-router';
const router = useRouter();
</script>

<template>
  <div class="not-found-container">
    <div class="error-visual">
      <div class="error-code">404</div>
    </div>
    <div class="error-content">
      <h1 class="error-title">抱歉，您访问的页面走丢了...</h1>
      <p class="error-description">
        我们找不到您请求的资源。它可能已被移动、删除，或者您输入了一个错误的网址。
      </p>
      <div class="recommend-actions">
        <Button
          type="nav"
          icon="home"
          size="large"
          @click="router.back()"
          class="home-button"
        >
          立即返回上一页
        </Button>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* -------------------- 整体容器 -------------------- */
.not-found-container {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 80vh;
  /* 确保占据屏幕大部分高度 */
  text-align: center;
  padding: 40px 20px;
  background-color: rgba(0, 0, 0, 0.15);
  /* 柔和的背景色 */
  font-family: 'Inter', 'Helvetica Neue', Helvetica, Arial, sans-serif;
}

/* -------------------- 视觉元素 -------------------- */
.error-visual {
  position: relative;
  margin-bottom: 40px;
}

.error-code {
  font-size: 180px;
  font-weight: 900;
  color: var(--accent-color);
  opacity: 0.25;
  position: absolute;
  top: -60px;
  left: 50%;
  transform: translateX(-50%);
  letter-spacing: 10px;
  user-select: none;
}

.error-illustration i {
  font-size: 80px;
  color: var(--accent-color);
  padding: 20px;
  border-radius: 50%;
  background-color: #ecf5ff;
  box-shadow: 0 5px 15px rgba(64, 158, 255, 0.1);
}

/* -------------------- 文本内容 -------------------- */
.error-content {
  max-width: 600px;
  z-index: 10;
}

.error-title {
  font-size: 36px;
  font-weight: 700;
  color: #303133;
  margin-top: 0;
  margin-bottom: 15px;
}

.error-description {
  font-size: 16px;
  color: #606266;
  margin-bottom: 30px;
}

/* -------------------- 操作区域 -------------------- */
.recommend-actions {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.home-button {
  margin-bottom: 30px;
  padding: 15px 30px;
  font-size: 18px;
  border-radius: 8px;
  font-weight: 600;
}



/* -------------------- 响应式调整 -------------------- */
@media (max-width: 768px) {
  .error-code {
    font-size: 120px;
    top: -40px;
  }

  .error-title {
    font-size: 28px;
  }

}
</style>
```

## `views/SettingsView.vue`

```vue
<script setup lang="ts">
import { defaultUIStore } from '@/stores/ui';

const uiStore = defaultUIStore();
let shouldShowOverlay = false;
const overlayOpacity = ref(0);

onMounted(() => {
  setTimeout(() => overlayOpacity.value = 1, 10);
});

onUnmounted(() => {
  setTimeout(() => overlayOpacity.value = 0, 10);
});
</script>

<template>
  <div
    class="blur-overlay"
    v-show="shouldShowOverlay"
    :style="{ opacity: overlayOpacity }"
  ></div>
  <div class="settings-panel">
    <div class="nav">
      <SettingsNav />
    </div>
    <div class="pages">
      <MenuPage width="80%">
        <GeneralSetting v-show="uiStore.currentSettingsTab === 'general'" />
        <!-- <SettingsSave v-show="uiStore.currentSettingsTab === 'save'" />
          <SettingsText v-show="uiStore.currentSettingsTab === 'text'" /> -->
        <SoundSetting v-show="uiStore.currentSettingsTab === 'sound'" />
        <AdventureSetting v-show="uiStore.currentSettingsTab === 'adventure'" />
        <HistorySetting v-show="uiStore.currentSettingsTab === 'history'" />
        <CharacterSetting v-show="uiStore.currentSettingsTab === 'character'" />
        <BackgroundSetting v-show="uiStore.currentSettingsTab === 'background'" />
        <!-- <SettingsLog v-show="uiStore.currentSettingsTab === 'log'" /> -->
      </MenuPage>
    </div>
  </div>
</template>

<style scoped>
.header {
  display: flex;
  align-items: center;
  padding: 10px 15px;
  position: relative;
  justify-content: space-between;
  /* background: rgba(0, 0, 0, 0.2); */
}

.settings-panel {
  position: fixed;
  top: 0;
  right: 0;
  width: 100%;
  height: 100%;
  opacity: 1;
  padding: 0;
  box-sizing: border-box;
  z-index: 1000;
  color: #333;
  background-color: rgba(0, 0, 0, 0.15);
  background-color: transparent;
}

.nav {
  display: grid;
  grid-template-columns: 250px 2fr 50px;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 7vh;
  background: rgba(255, 255, 255, 0.1);
}

.pages {
  display: flex;
  justify-content: center;
  height: 93vh;
  overflow: auto;
  width: 100%;
}

.blur-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  z-index: 10;

  /* 初始状态 */
  opacity: 0;
  backdrop-filter: blur(5px);
  background-color: rgba(0, 0, 0, 0.45);

  /* 过渡效果 */
  transition: opacity 0.3s ease;

  /* 确保覆盖层可以点击穿透 */
  pointer-events: none;
}

@media screen and (max-width: 768px) {
  .nav {
    grid-template-columns: 10px 2fr 50px;
  }
}
</style>
```

