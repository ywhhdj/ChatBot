<script setup lang="ts">
defineProps({
  width: {
    type: String,
    default: '100%',
  }
})
</script>

<template>
  <div
    class="menu-page"
    :style="{ width: width }"
  >
    <slot></slot>
  </div>
</template>

<style scoped>
.menu-page {
  display: flex;
  color: white;
  justify-items: center;
  align-items: flex-start;
  overflow: auto;
  padding-block: calc(0.25rem* 6);
  padding-inline: calc(0.25rem* 3);
  gap: calc(0.25rem* 5);
  height: fit-content;
  max-height: 100%;
  flex-wrap: wrap;
}

@media (max-width: 1024px) {
  .menu-page {
    width: 100%;
  }
}
</style>