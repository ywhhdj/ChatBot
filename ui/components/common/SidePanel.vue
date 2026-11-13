<script setup lang="ts">
const props = withDefaults(defineProps<{
  visible: boolean;
  position?: 'left' | 'right';
  width?: string;
  closeOnOverlay?: boolean;
}>(), {
  position: 'right',
  width: '320px',
  closeOnOverlay: true,
});

const emit = defineEmits<{
  (e: 'update:visible', val: boolean): void;
  (e: 'close'): void;
}>();

const panelWidth = props.width;

const close = () => {
  if (!props.closeOnOverlay) return;
  emit('update:visible', false);
  emit('close');
};

// ESC 键关闭
const handleKeydown = (e: KeyboardEvent) => {
  if (e.key === 'Escape' && props.visible) {
    close();
  }
};

onMounted(() => {
  document.addEventListener('keydown', handleKeydown);
});

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown);
});
</script>

<template>
  <Teleport to="body">
    <Transition name="slide">
      <div
        v-if="visible"
        class="side-overlay"
        @click.self="close"
      >
        <aside
          class="side-panel"
          :class="[position, { 'has-header': $slots.header, 'has-footer': $slots.footer }]"
          :style="{ width: panelWidth }"
        >
          <!-- 头部 -->
          <header
            v-if="$slots.header"
            class="side-header"
          >
            <RowItem style="width: 100%;">
              <template #left>
                <slot name="header" />
              </template>
              <template #right>
                <Button
                  :icon-size="14"
                  type="nav"
                  icon="collapse"
                  @click="close"
                />
              </template>
            </RowItem>
          </header>
          <!-- 主体 -->
          <div class="side-body">
            <slot></slot>
          </div>
        </aside>
      </div>
    </Transition>
  </Teleport>
</template>



<style scoped>
.side-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 8888;
}

.side-panel {
  position: fixed;
  top: 0;
  bottom: 0;
  box-shadow: 0 0 10px rgba(0, 0, 0, 0.8);
  background: var(--dialog-bg-color);
  border: 1px solid rgba(255, 255, 255, 0.1);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: transform 0.28s cubic-bezier(0.23, 1, 0.32, 1);
}

.side-panel.left {
  left: 0;
  border-radius: 12px 0 0 12px;
  box-shadow: 4px 0 12px rgba(0, 0, 0, 0.06);
}

.side-panel.right {
  right: 0;
  border-radius: 12px 12px 0 0;
}

.side-header {
  color: var(--text-color);
  font-size: 16px;
  border-bottom: 1px solid var(--primary-color);
}

.side-header :deep(*) {
  margin: 0;
}

.side-close-btn {
  background: transparent;
  border: none;
  font-size: 24px;
  cursor: pointer;
  color: #888;
  line-height: 1;
  padding: 0 2px;
}

.side-close-btn:hover {
  color: #333;
}

.side-body {
  flex: 1;
  padding: 20px;
  overflow-y: auto;
}

/* 滑入动画 */
.slide-enter-active .side-panel,
.slide-leave-active .side-panel {
  transition: transform 0.28s cubic-bezier(0.23, 1, 0.32, 1);
}

.slide-enter-from .side-panel.right,
.slide-leave-to .side-panel.right {
  transform: translateX(100%);
}

.slide-enter-from .side-panel.left,
.slide-leave-to .side-panel.left {
  transform: translateX(-100%);
}

@media screen and (max-width: 768px) {
  .side-panel {
    width: 100%;
  }
}
</style>