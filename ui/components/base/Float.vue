<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from 'vue';
import { useDraggable, type DraggablePoint } from '@/composables/useDraggable';

const props = withDefaults(
  defineProps<{
    title: string;
    icon?: UI.IconType;
    width?: string;
    initial?: DraggablePoint;
    collapsible?: boolean;
    draggable?: boolean;
    defaultCollapsed?: boolean;
    zIndex?: number;
  }>(),
  {
    icon: 'none',
    width: '288px',
    collapsible: true,
    draggable: true,
    defaultCollapsed: false,
    zIndex: 20,
  }
);

const emit = defineEmits<{
  'update:collapsed': [value: boolean];
  toggle: [value: boolean];
}>();

const panelRef = ref<HTMLElement | null>(null);
const handleRef = ref<HTMLElement | null>(null);
const collapsed = ref(props.defaultCollapsed);

const { isDragging, start, stop, reset, clampToViewport } = useDraggable({
  handle: handleRef,
  panel: panelRef,
  initial: props.initial,
  disabled: () => !props.draggable,
});

function toggle() {
  collapsed.value = !collapsed.value;
  emit('update:collapsed', collapsed.value);
  emit('toggle', collapsed.value);
}

// 折叠会改变面板高度，重新钳制避免浮层底部超出视口
watch(collapsed, async () => {
  await nextTick();
  clampToViewport();
});

// useDraggable 通过 onScopeDispose 自行释放监听与 rAF，组件卸载无需额外清理
onMounted(async () => {
  await nextTick();
  start();
});

defineExpose({
  collapsed,
  toggle,
  reset,
  stop,
});
</script>

<template>
  <Teleport to="body">
    <section
      ref="panelRef"
      class="floating-panel"
      :class="{ 'is-dragging': isDragging, 'is-collapsed': collapsed }"
      :style="{ width, zIndex }"
      :aria-label="title"
    >
      <header
        ref="handleRef"
        class="fp-head"
        :class="{ 'can-drag': draggable }"
      >
        <Icon
          v-if="icon && icon !== 'none'"
          :icon="icon"
          :size="16"
        />
        <span class="fp-title">{{ title }}</span>
        <span
          v-if="$slots.badge"
          class="fp-badge"
        ><slot name="badge" /></span>

        <div
          class="fp-actions"
          data-no-drag
        >
          <slot name="actions" />
          <Button
            v-if="collapsible"
            type="nav"
            class="fp-toggle"
            :aria-expanded="!collapsed"
            :aria-label="collapsed ? '展开' : '折叠'"
            @click="toggle"
          >{{ collapsed ? '▴' : '▾' }}</Button>
        </div>
      </header>

      <div
        v-show="!collapsed"
        class="fp-body"
      >
        <slot />
      </div>

      <footer
        v-if="$slots.footer"
        v-show="!collapsed"
        class="fp-foot"
        data-no-drag
      >
        <slot name="footer" />
      </footer>
    </section>
  </Teleport>
</template>

<style scoped>
.floating-panel {
  position: fixed;
  top: 0;
  left: 0;
  max-width: calc(100vw - 24px);
  max-height: calc(100vh - 24px);
  display: flex;
  flex-direction: column;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.28);
  background: rgba(0, 14, 39, 0.62);
  backdrop-filter: blur(6px) saturate(150%);
  -webkit-backdrop-filter: blur(6px) saturate(150%);
  box-shadow:
    0 10px 36px rgba(0, 0, 0, 0.45),
    inset 0 1px 0 rgba(255, 255, 255, 0.18);
  color: var(--text-color);
  text-shadow: 0 2px 4px rgba(0, 0, 0, 0.5);
  overflow: hidden;
  touch-action: none;
}

.floating-panel.is-dragging {
  will-change: transform;
  user-select: none;
  box-shadow:
    0 16px 44px rgba(0, 0, 0, 0.55),
    0 0 0 1px rgba(121, 217, 255, 0.35);
}

.fp-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 0 0 auto;
  padding: 9px 10px 9px 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.16);
  background: linear-gradient(
    90deg,
    rgba(255, 255, 255, 0.12) 0%,
    rgba(255, 255, 255, 0.02) 100%
  );
}

.fp-head.can-drag {
  cursor: grab;
}

.floating-panel.is-dragging .fp-head.can-drag {
  cursor: grabbing;
}

.fp-title {
  font-family: 'Maoken Assorted Sans', -apple-system, BlinkMacSystemFont, sans-serif;
  font-size: 15px;
  font-weight: 600;
  white-space: nowrap;
}

.fp-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.1);
  white-space: nowrap;
  opacity: 0.85;
}

.fp-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-left: auto;
}

.fp-actions :deep(button) {
  font-size: 12px;
  padding: 3px 8px;
}

.fp-body {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  padding: 10px 12px;
}

.fp-foot {
  flex: 0 0 auto;
  padding: 8px 12px 10px;
  border-top: 1px solid rgba(255, 255, 255, 0.12);
  display: flex;
  justify-content: flex-end;
}
</style>
