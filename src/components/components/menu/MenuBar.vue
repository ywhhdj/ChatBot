<script setup lang="ts">
type IsTopRight = "true" | "false"
type JustifyContent = "start" | "end" | "center"

const props = withDefaults(defineProps<{
  zIndex?: number;
  isTopRight?: IsTopRight | boolean;
  justify?: JustifyContent;
  isBoxShadow?: boolean;
}>(),{
  zIndex: 1000,
  isTopRight: false,
  justify: "start",
  isBoxShadow: false
});



const classType = computed(() => {
  return {
    'box-shadow': props.isBoxShadow,
  }
});

</script>

<template>
  <div
    :class="['menu-bar', isTopRight, justify, classType]"
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