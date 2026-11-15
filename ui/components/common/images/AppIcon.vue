<script setup lang="ts">
const props = withDefaults(
  defineProps<{
    size?: number;
    label?: string;
    badge?: string;
  }>(),
  {
    size: 96,
    label: 'ChatBot',
    badge: '',
  }
);

const failed = ref(false);
watch(
  () => props.size,
  () => {
    if (failed.value) failed.value = false;
  }
);
</script>

<template>
  <div
    class="app-icon"
    :style="{ width: `${size}px`, height: `${size}px` }"
    role="img"
    :aria-label="label"
  >
    <img
      v-if="!failed"
      src="/static/icons/chatbot.ico"
      :alt="label"
      :width="size"
      :height="size"
      draggable="false"
      @error="failed = true"
    />
    <Icon
      v-else
      icon="chat"
      :size="Math.round(size * 0.62)"
    />
    <span
      v-if="badge"
      class="app-icon-badge"
    >{{ badge }}</span>
  </div>
</template>

<style scoped>
.app-icon {
  position: relative;
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  border-radius: 24px;
  border: 1px solid rgba(255, 255, 255, 0.45);
  background: rgba(255, 255, 255, 0.08);
  backdrop-filter: blur(3px) saturate(160%);
  -webkit-backdrop-filter: blur(3px) saturate(160%);
  box-shadow:
    0 8px 30px rgba(0, 0, 0, 0.35),
    0 0 18px rgba(121, 217, 255, 0.28),
    inset 0 1px 1px rgba(255, 255, 255, 0.6);
  color: #fff;
  text-shadow: 0 2px 4px rgba(0, 0, 0, 0.5);
  overflow: hidden;
}

.app-icon img {
  display: block;
  width: 78%;
  height: 78%;
  object-fit: contain;
  border-radius: 14px;
  filter: drop-shadow(0 3px 8px rgba(0, 0, 0, 0.4));
}

.app-icon-badge {
  position: absolute;
  right: -6px;
  bottom: -6px;
  max-width: 120px;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  background: rgba(0, 14, 39, 0.8);
  border: 1px solid rgba(255, 255, 255, 0.25);
}
</style>
