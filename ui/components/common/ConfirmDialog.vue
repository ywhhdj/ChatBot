<script setup lang="ts">

const props = defineProps<{
  spec: UI.ConfirmSpec | null;
  /** 点击遮罩是否等同取消 */
  dismissible?: boolean;
}>();

const emit = defineEmits<{
  confirm: [];
  cancel: [];
}>();

const cancelRef = ref<any>(null);

watch(
  () => props.spec,
  async (spec) => {
    if (!spec) return;
    await nextTick();
    (cancelRef.value?.$el as HTMLElement | undefined)?.focus?.();
  }
);
</script>

<template>
  <Teleport to="body">
    <Transition name="confirm-fade">
      <div
        v-if="spec"
        class="confirm-mask"
        @click.self="dismissible !== false && emit('cancel')"
      >
        <div
          class="confirm-box"
          role="dialog"
          aria-modal="true"
          :aria-label="spec.title"
        >
          <h2>{{ spec.title }}</h2>
          <p>{{ spec.message }}</p>
          <div class="confirm-actions">
            <Button
              ref="cancelRef"
              type="nav"
              @click="emit('cancel')"
            >{{ spec.cancelText }}</Button>
            <Button
              type="select"
              :class="{ 'is-danger': spec.danger }"
              @click="emit('confirm')"
            >{{ spec.confirmText }}</Button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.confirm-mask {
  position: fixed;
  inset: 0;
  z-index: 40;
  display: grid;
  place-items: center;
  background: rgba(0, 8, 24, 0.45);
  backdrop-filter: blur(2px);
}

.confirm-box {
  width: min(400px, 90vw);
  padding: 20px;
  border-radius: 14px;
  border: 1px solid rgba(255, 255, 255, 0.24);
  background: rgba(0, 14, 39, 0.92);
  box-shadow: 0 18px 60px rgba(0, 0, 0, 0.55);
  color: #fff;
  text-shadow: 0 2px 4px rgba(0, 0, 0, 0.5);
}

.confirm-box h2 {
  margin: 0 0 8px;
  font-family: 'Maoken Assorted Sans', -apple-system, BlinkMacSystemFont, sans-serif;
  font-size: 18px;
  font-weight: normal;
}

.confirm-box p {
  margin: 0 0 16px;
  font-size: 13px;
  line-height: 1.7;
  opacity: 0.85;
}

.confirm-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.confirm-box :deep(.is-danger) {
  background: rgba(244, 67, 54, 0.75);
  color: #fff;
}

.confirm-fade-enter-active,
.confirm-fade-leave-active {
  transition: opacity 0.16s ease-out;
}

.confirm-fade-enter-from,
.confirm-fade-leave-to {
  opacity: 0;
}

@media (prefers-reduced-motion: reduce) {
  .confirm-fade-enter-active,
  .confirm-fade-leave-active {
    transition: none;
  }
}
</style>
