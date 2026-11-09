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
    class="flex justify-between items-center"
    style="padding: 10px 12px;"
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