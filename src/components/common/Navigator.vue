<script setup lang="ts">
const props = defineProps({
  menus: {
    type: Array as PropType<UI.MenuItem[]>,
    required: true,
    default: () => []
  },
  modelValue: {
    type: Number,
    default: 0
  }
});

const rootRef = ref<HTMLElement | null>(null);
const keyOf = (index: number) => {
  return `${index}`;
};

// 定义触发的事件
const emit = defineEmits(['update:modelValue', 'menu-click']);

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
  menu.clickAction?.();
  emit('update:modelValue', Number(menuKey));
};

const activeClass = computed(() => (index: number) => {
  return {
    active: props.modelValue === index
  }
});

</script>

<template>
  <div
    ref="rootRef"
    class="liquid-nav-container"
    @click="onDelegatedClick"
  >
    <div
      v-for="(menu, index) in menus"
      :key="keyOf(index)"
      :data-menu-key="keyOf(index)"
      class="liquid-nav-item"
      :class="activeClass(index)"
    >
      <!-- 左侧图标 -->
      <div
        class="icon-wrapper"
        :style="{ backgroundColor: menu.iconBg || 'transparent' }"
      >
        <component
          :is="menu.icon"
          :color="modelValue === index ? '#FFD700' : '#888'"
          :size="20"
        />
      </div>

      <!-- 中间文字 -->
      <span class="nav-text">{{ menu.name }}</span>
      <!-- 液态光晕特效层 (仅选中时显示) -->
      <div
        v-show="modelValue === index"
        class="liquid-overlay"
      />
    </div>
  </div>
</template>



<style scoped>
.liquid-nav-container {
  overflow-x: auto;
  position: sticky;
  top: 0;
  left: 0;
  right: 0;
  width: max-content;
  position: relative;
  display: flex;
  gap: 20px;
  padding: 8px 30px;
  background: linear-gradient(90deg, rgba(0, 51, 255, 0.1) 0%, rgba(255, 255, 255, 0.1) 100%);
  border-radius: 26px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
}

.liquid-nav-item {
  max-width: 200px;
  min-width: 150px;
  position: relative;
  flex: 1;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 8px;
  border-radius: 16px;
  background: var(--accent-bg);
  /* 未选中时的基础液态背景 */
  cursor: pointer;
  overflow: hidden;
  border: none;
  transition: all 0.4s cubic-bezier(0.25, 0.8, 0.25, 1);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.5),
    0 2px 5px rgba(0, 0, 0, 0.05);
  color: var(--accent-color);
  font-weight: 500;
  justify-content: center;
}

.liquid-nav-item:hover:not(.active) {
  transform: translateY(-2px);
}

/* 选中状态的强化样式 */
.liquid-nav-item.active {
  background: rgba(255, 255, 255, 0.6);
  color: var(--accent-color);
  /* 选中时文字更清晰 */
  box-shadow:
    inset 0 2px 4px rgba(0, 0, 0, 0.7),
    /* 强烈的内部高光 */
    0 10px 25px rgba(0, 0, 0, 0.15),
    /* 加深的外部投影，提升立体感 */
    0 0 15px rgba(255, 215, 0, 0.3);
  /* 微弱的金色光晕 */
  transform: scale(1.02);
  z-index: 2;
}

.icon-wrapper {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.05);
  transition: background 0.3s ease;
  flex-shrink: 0;
}

.liquid-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  /* 使用 conic-gradient 创建旋转的高光带，模拟液态反光 */
  background: conic-gradient(from 180deg at 50% 50%,
      rgba(255, 255, 255, 0) 0deg,
      rgba(255, 255, 255, 0.6) 90deg,
      rgba(255, 255, 255, 0) 180deg,
      rgba(255, 255, 255, 0) 270deg,
      rgba(255, 255, 255, 0.3) 360deg);
  border-radius: inherit;
  opacity: 0.5;
  mix-blend-mode: overlay;
  /* 混合模式让光晕更自然 */
  pointer-events: none;
  animation: spin 4s linear infinite;
  /* 缓慢旋转动画 */
}

.liquid-nav-item.active .icon-wrapper {
  background: radial-gradient(circle, rgba(255, 223, 0, 0.2) 0%, rgba(255, 255, 255, 0) 70%);
  box-shadow: 0 0 10px rgba(255, 215, 0, 0.4);
}

.nav-text {
  font-size: 15px;
  letter-spacing: 0.5px;
  flex: 1;
}

.liquid-nav-item.active {
  opacity: 1;
  color: #555;
  transform: translateY(0);
}
</style>