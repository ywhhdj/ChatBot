<script setup lang="ts">
const flakesStr = ['❄', '❅', '❆', '✦'];
const props = defineProps({
  count: {
    type: Number,
    default: window.innerWidth < 768 ? 30 : 80
  }
})
const flakes = shallowRef(
  Array.from({ length: props.count }, () => flakesStr[Math.floor(Math.random() * flakesStr.length)])
);

const flakeStyle = () => {
  return {
    left: Math.random() * 100 + '%',
    top: '-10px',
    fontSize: (10 + Math.random() * 22) + 'px',
    transform: `translate3d(0,${Math.random() * 100}px,0.5turn) rotate(${Math.random() * 360}deg)`,
    animationDuration: `${Math.random() * 24 + 16}s`,
    animationDelay: `${Math.random() * 20}s`
  }
}
</script>

<template>
  <div class="snow-container">
    <span
      v-for="flake in flakes"
      :key="flake"
      class="snowflake"
      :style="flakeStyle()"
    >{{ flake }}</span>
  </div>
</template>

<style scoped>
@keyframes fall {
  0% {
    transform: translateY(-10px) rotate(0deg) scale(0.8);
    opacity: 0.9;
  }

  100% {
    transform: translateY(110vh) rotate(720deg) scale(0.3);
    opacity: 0.1;
  }
}

.snow-container {
  position: fixed;
  top: -10px;
  left: 0;
  width: 100%;
  height: 100%;
  z-index: 1000;
  overflow: hidden;
  pointer-events: none;
}

.snowflake {
  position: absolute;
  font-size: 10px;
  color: #fff;
  top: 0px;
  color: rgba(255, 255, 255, 0.5);
  will-change: transform;
  user-select: none;
  animation: fall linear infinite;
}
</style>