<script setup lang="ts">
defineProps({
  wave: {
    type: Number,
    default: 5,
  },
})
</script>

<template>
  <div class="wave-animation">
    <span
      v-for="i in wave"
      :key="i"
      class="wave-bar"
      :style="{ animationDelay: `${i * 0.1}s` }"
    ></span>
  </div>
  <slot></slot>
</template>

<style scoped>
.wave-animation {
  display: flex;
  align-items: center;
  gap: 2px;
  height: 20px;
}

@keyframes wave {
  0% {
    height: 20%;
  }

  100% {
    height: 100%;
  }
}

.wave-bar {
  width: 3px;
  height: 100%;
  background: var(--primary-color);
  border-radius: 2px;
  animation: wave 0.5s ease-in-out infinite alternate;
}

.duration {
  font-size: 18px;
  font-weight: bold;
  font-family: monospace;
}

.hint {
  font-size: 12px;
  opacity: 0.8;
}
</style>