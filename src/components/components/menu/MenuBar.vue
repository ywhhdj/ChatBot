<script setup lang="ts">
type Direction = "row" | "column"
type IsTopRight = "true" | "false"
type JustifyContent = "start" | "end" | "center"

defineProps({
  zIndex: {
    type: Number,
    default: 1000
  },
  isTopRight: {
    type: String as PropType<IsTopRight>,
    default: "true"
  },
  justify: {
    type: String as PropType<JustifyContent>,
    default: "start"
  },
  isBoxShadow: {
    type: Boolean,
    default: true
  }
});
</script>

<template>
  <div
    :class="['menu-bar', isTopRight, justify, { 'box-shadow': isBoxShadow }]"
    :style="{ zIndex: zIndex }"
  >
    <slot></slot>
  </div>
</template>

<style scoped>
.menu-bar {
  display: flex;
  overflow: auto;

}

.menu-bar.box-shadow {
  box-shadow: 0 0 10px rgba(0, 0, 0, 0.5);
}

.menu-bar.start {
  justify-content: flex-start;
}

.menu-bar.end {
  justify-content: flex-end;
}

.menu-bar.center {
  justify-content: center;
}

.menu-bar.true {
  z-index: 1000;
  top: 20px;
  right: 20px;
}
</style>