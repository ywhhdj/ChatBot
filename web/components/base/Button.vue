<script setup lang="ts">
defineProps<{
  type?: UI.ButtonType;
  icon?: UI.IconType;
  iconSize?: number;
  titleButtonDisabled?: boolean;
  buttonText?: string;
  disabled?: boolean;
}>();
const emit = defineEmits(['click', 'mousedown', 'mouseup']);
</script>

<template>
  <button
    :class="type"
    @click="emit('click')"
    :disabled="disabled"
    @pointerdown="emit('mousedown', true)"
    @pointerup="emit('mouseup', false)"
  >
    <Icon
      v-if="icon"
      :icon="icon"
      :size="iconSize"
    ></Icon>
    <slot></slot>
  </button>
</template>

<style scoped>
button {
  padding: 8px 16px;
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
  color: var(--text-color);
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
    color: var(--primary-color);
  }

  svg {
    width: 18px;
    height: 18px;
    stroke-width: 2.5px;
    flex-shrink: 0;
  }

  &.active {
    background-color: rgba(255, 255, 255, 0.1);
    color: var(--primary-color);

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
    background-color: var(--primary-color);
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
    background-color: var(--primary-color);
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