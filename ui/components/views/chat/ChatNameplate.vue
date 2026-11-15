<script setup lang="ts">
/**
 * galgame 名牌栏 —— FrontendPlan Step 3
 *
 * 视觉基线取自 ChatDialog.vue：角色名 / 副标题 / 情绪三段式 + 右上角快捷按钮，
 * 保持白色文字、Maoken 字体、文字阴影与半透明按钮，不引入新配色。
 * 组件复用：base/Button.vue（含 base/Icon.vue）、chat/buttons/VoiceRecord.vue。
 * 只负责展示与事件转发，不持有会话状态、不直接调 API。
 */
import { computed } from 'vue';
import Button from '@/components/base/Button.vue';
import VoiceRecord from '@/components/chat/buttons/VoiceRecord.vue';

const props = withDefaults(
  defineProps<{
    name?: string;
    subtitle?: string;
    emotion?: string;
    streaming?: boolean;
    micGranted?: boolean;
    agentVisible?: boolean;
    busy?: boolean;
  }>(),
  {
    name: '灵',
    subtitle: '',
    emotion: '',
    streaming: false,
    micGranted: false,
    agentVisible: false,
    busy: false,
  }
);

const emit = defineEmits<{
  'toggle-agent': [];
  'open-restore': [];
  'open-history': [];
  'open-settings': [];
  'voice-start': [];
  'voice-stop': [text: string];
}>();

interface NameplateAction {
  icon: UI.IconType;
  label: string;
  active?: boolean;
  disabled?: boolean;
  run: () => void;
}

/** 静态菜单 + 计算属性：只在依赖变化时重算，事件由父容器统一编排。 */
const actions = computed<NameplateAction[]>(() => [
  {
    icon: 'history',
    label: '历史记录',
    run: () => emit('open-history'),
  },
  {
    icon: 'save',
    label: '恢复计划',
    disabled: props.busy,
    run: () => emit('open-restore'),
  },
  {
    icon: 'aside',
    label: props.agentVisible ? '收起后台任务' : '后台任务',
    active: props.agentVisible,
    run: () => emit('toggle-agent'),
  },
  {
    icon: 'settings',
    label: '游戏设置',
    run: () => emit('open-settings'),
  },
]);
</script>

<template>
  <div class="chatbox-title-part">
    <div class="nameplate">
      <div class="chatbox-title">{{ name }}</div>
      <div class="chatbox-subtitle">{{ subtitle }}</div>
      <div class="chatbox-emotion">{{ emotion }}</div>
    </div>

    <div class="chatbox-buttons">
      <Button
        v-for="action in actions"
        :key="action.icon"
        type="nav"
        :icon="action.icon"
        :title="action.label"
        :aria-label="action.label"
        :disabled="action.disabled"
        :class="{ 'is-active': action.active }"
        @click="action.run()"
      />
      <VoiceRecord
        :disabled="!micGranted || streaming"
        @start="emit('voice-start')"
        @stop="emit('voice-stop', $event)"
      />
    </div>
  </div>
</template>

<style scoped>
.chatbox-title-part {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
  color: #fff;
  text-shadow: 0 2px 4px rgba(0, 0, 0, 0.5);
}

.nameplate {
  display: flex;
  align-items: baseline;
  gap: 12px;
  min-width: 0;
}

.chatbox-title,
.chatbox-subtitle,
.chatbox-emotion {
  font-family:
    'Maoken Assorted Sans',
    -apple-system,
    BlinkMacSystemFont,
    'Segoe UI',
    sans-serif;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.chatbox-title {
  font-size: 24px;
  font-weight: bold;
  color: #fff;
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
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
}

.chatbox-buttons :deep(button) {
  font-size: 14px;
  padding: 6px 10px;
}

.chatbox-buttons :deep(.is-active) {
  background: rgba(255, 255, 255, 0.14);
  color: var(--primary-color);
}

@media (max-width: 768px) {
  .chatbox-title {
    font-size: 20px;
  }

  .chatbox-subtitle,
  .chatbox-emotion {
    font-size: 16px;
  }
}
</style>
