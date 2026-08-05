<script setup lang="ts">
const props = defineProps({
  bgColor: {
    type: String,
    default: 'transparent'
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