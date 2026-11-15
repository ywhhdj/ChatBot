<script setup lang="ts">
export type GameMenuItem = {
  key: string;
  /** 主选项文案 */
  label: string;
  caption?: string;
  /** 可选图标，复用 base/Icon.vue 的既有图形 */
  icon?: UI.IconType;
  disabled?: boolean;
  action?: () => void;
}

const props = withDefaults(
  defineProps<{
    items: GameMenuItem[];
    modelValue?: number;
    numbered?: boolean;
    hint?: string;
    ariaLabel?: string;
  }>(),
  {
    modelValue: undefined,
    numbered: true,
    hint: '↑ ↓ 选择 · Enter 确认',
    ariaLabel: '主菜单',
  }
);

const emit = defineEmits<{
  'update:modelValue': [value: number];
  select: [item: GameMenuItem, index: number];
}>();

// 用组件实例 uid 保证同一页面多个菜单实例的 aria id 不冲突
const uid = `game-menu-${getCurrentInstance()?.uid ?? 0}`;

const rootRef = ref<HTMLElement | null>(null);
const inner = ref(props.modelValue ?? 0);
watch(
  () => props.modelValue,
  (v) => {
    if (typeof v === 'number' && v >= 0) inner.value = v;
  }
);

const active = computed(() =>
  Math.min(Math.max(inner.value, 0), Math.max(props.items.length - 1, 0))
);

function setActive(index: number) {
  if (inner.value === index) return;
  inner.value = index;
  emit('update:modelValue', index);
}

function choose(item: GameMenuItem, index: number) {
  if (item.disabled) return;
  setActive(index);
  emit('select', item, index);
  item.action?.();
}

function onKeydown(event: KeyboardEvent) {
  const list = props.items;
  const count = list.length;
  if (!count) return;

  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault();
    const dir = event.key === 'ArrowDown' ? 1 : -1;
    let next = active.value;
    for (let step = 0; step < count; step += 1) {
      next = (next + dir + count) % count;
      if (!list[next].disabled) break;
    }
    setActive(next);
    // 焦点收拢到容器，后续 Enter 只由本处理器执行一次
    rootRef.value?.focus();
    return;
  }

  if (event.key === 'Enter' || event.key === ' ') {
    const target = event.target as HTMLElement | null;
    // 焦点在原生 button 上时交给它的 click，避免同一动作执行两次
    if (target?.closest('button')) return;
    event.preventDefault();
    const item = list[active.value];
    if (item) choose(item, active.value);
  }
}

const itemId = (index: number) => `${uid}-item-${index}`;
</script>

<template>
  <nav
    ref="rootRef"
    class="game-menu"
    role="menu"
    :aria-label="ariaLabel"
    :aria-activedescendant="items.length ? itemId(active) : undefined"
    tabindex="0"
    @keydown="onKeydown"
  >
    <div class="gm-ornament">
      <span class="gm-line" />
      <Icon
        icon="play"
        :size="12"
      />
      <span class="gm-ornament-text">SELECT</span>
      <span class="gm-line" />
    </div>

    <ul class="gm-list">
      <li
        v-for="(item, index) in items"
        :id="itemId(index)"
        :key="item.key"
        class="gm-item"
        :class="{ 'is-active': index === active, 'is-disabled': item.disabled }"
        role="menuitem"
        :aria-disabled="item.disabled || undefined"
        @mouseenter="setActive(index)"
      >
        <span
          v-if="numbered"
          class="gm-no"
        >{{ String(index + 1).padStart(2, '0') }}</span>
        <span class="gm-marker" />
        <Icon
          v-if="item.icon"
          class="gm-icon"
          :icon="item.icon"
          :size="18"
        />
        <Button
          type="menu"
          :disabled="item.disabled"
          @click="choose(item, index)"
        >{{ item.label }}</Button>
        <span
          v-if="item.caption"
          class="gm-caption"
        >{{ item.caption }}</span>
        <span class="gm-arrow">▸</span>
      </li>
    </ul>

    <div class="gm-hint">
      <span class="gm-hint-mark">◆</span>
      {{ hint }}
    </div>
  </nav>
</template>

<style scoped>
.game-menu {
  width: 100%;
  padding: 16px 18px 12px;
  border-radius: 14px;
  border: 1px solid rgba(255, 255, 255, 0.22);
  background: linear-gradient(
    135deg,
    rgba(0, 14, 39, 0.58) 0%,
    rgba(0, 14, 39, 0.32) 100%
  );
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
  box-shadow:
    0 12px 40px rgba(0, 0, 0, 0.32),
    inset 0 1px 0 rgba(255, 255, 255, 0.16);
  color: #fff;
  text-shadow: 0 2px 4px rgba(0, 0, 0, 0.5);
  outline: none;
}

.game-menu:focus-visible {
  border-color: rgba(121, 217, 255, 0.65);
  box-shadow:
    0 12px 40px rgba(0, 0, 0, 0.32),
    0 0 0 2px rgba(121, 217, 255, 0.25);
}

.gm-ornament {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  opacity: 0.6;
  color: var(--primary-color);
}

.gm-line {
  flex: 1 1 auto;
  height: 1px;
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgba(255, 255, 255, 0.45) 50%,
    transparent 100%
  );
}

.gm-ornament-text {
  font-family: ui-monospace, Menlo, monospace;
  font-size: 10px;
  letter-spacing: 0.32em;
}

.gm-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
}

.gm-item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 2px 10px 2px 14px;
  border-left: 2px solid transparent;
  transition: transform 0.22s ease, background-color 0.22s ease;
}

.gm-item::after {
  content: '';
  position: absolute;
  left: 0;
  bottom: 0;
  width: 100%;
  height: 1px;
  background: linear-gradient(
    90deg,
    rgba(255, 255, 255, 0.18) 0%,
    transparent 85%
  );
}

.gm-item.is-active {
  border-left-color: var(--primary-color);
  background: linear-gradient(
    90deg,
    rgba(121, 217, 255, 0.16) 0%,
    transparent 100%
  );
  transform: translateX(6px);
}

.gm-item.is-disabled {
  opacity: 0.42;
  pointer-events: none;
}

.gm-no {
  flex: 0 0 auto;
  width: 24px;
  font-family: ui-monospace, Menlo, monospace;
  font-size: 11px;
  letter-spacing: 0.08em;
  opacity: 0.55;
}

.gm-marker {
  flex: 0 0 auto;
  width: 7px;
  height: 7px;
  transform: rotate(45deg);
  border: 1px solid rgba(255, 255, 255, 0.6);
  background: rgba(255, 255, 255, 0.12);
  transition: background-color 0.22s ease, box-shadow 0.22s ease;
}

.gm-item.is-active .gm-marker {
  background: var(--primary-color);
  border-color: #fff;
  box-shadow: 0 0 10px rgba(121, 217, 255, 0.9);
}

.gm-icon {
  flex: 0 0 auto;
  opacity: 0.7;
}

/* 复用 base Button 的 Maoken 字体与文字阴影，只覆盖排版尺寸 */
.gm-item :deep(button.menu) {
  flex: 1 1 auto;
  width: auto;
  min-width: 0;
  margin: 0;
  padding: 10px 0;
  font-size: clamp(22px, 2.6vw, 32px);
  line-height: 1.2;
  text-align: left;
  background: transparent;
}

.gm-item.is-active :deep(button.menu) {
  text-shadow:
    0 0 12px rgba(255, 255, 255, 0.9),
    0 2px 4px rgba(0, 0, 0, 0.6);
}

.gm-caption {
  flex: 0 0 auto;
  font-family: ui-monospace, Menlo, monospace;
  font-size: 10px;
  letter-spacing: 0.16em;
  opacity: 0.5;
  white-space: nowrap;
}

.gm-arrow {
  flex: 0 0 auto;
  width: 14px;
  color: var(--primary-color);
  opacity: 0;
  transform: translateX(-6px);
  transition: opacity 0.22s ease, transform 0.22s ease;
}

.gm-item.is-active .gm-arrow {
  opacity: 1;
  transform: translateX(0);
}

.gm-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px solid rgba(255, 255, 255, 0.12);
  font-family: ui-monospace, Menlo, monospace;
  font-size: 10px;
  letter-spacing: 0.1em;
  opacity: 0.55;
}

.gm-hint-mark {
  color: var(--primary-color);
}

@media (max-width: 768px) {
  .game-menu {
    padding: 12px 12px 10px;
  }

  .gm-item {
    gap: 8px;
  }

  .gm-caption {
    display: none;
  }
}
</style>
