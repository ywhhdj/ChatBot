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