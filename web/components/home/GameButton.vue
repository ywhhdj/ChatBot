<script setup lang="ts">
withDefaults(defineProps<{
  name: string;
  desc: string;
}>(), {
  name: '开始',
  desc: 'Start Game',
});
</script>

<template>
  <button @click="$emit('click')">
    <div class="button-content">
      <span class="button-name">{{ name }}</span>
      <span class="button-desc">{{ desc }}</span>
    </div>
    <div class="line"></div>
  </button>
</template>

<style scoped>
button {
  position: relative;
  height: 6rem;
  width: 14rem;
  transition-property: all;
  display: flex;
  align-items: center;
  flex-direction: column;
  justify-content: center;
  --tw-scale-x: 1.05;
  --tw-scale-y: 1.05;
  --tw-skew-x: -12deg;
  border-width: 2px;
  border-right: 0.9rem;
  cursor: pointer;
  transition-duration: 300ms;
  transition-timing-function: cubic-bezier(0, 0, 0.2, 1);
  transform: translate(var(--tw-translate-x), var(--tw-translate-y)) rotate(var(--tw-rotate)) skewX(var(--tw-skew-x)) skewY(var(--tw-skew-y)) scaleX(var(--tw-scale-x)) scaleY(var(--tw-scale-y));
  box-shadow: rgba(195, 219, 244, 0.4) 0px 10px 25px -5px;
  background-color: rgba(255, 255, 255, 0.15);
}

.button-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  transform: translate(var(--tw-translate-x), var(--tw-translate-y)) rotate(var(--tw-rotate)) skewX(var(--tw-skew-x)) skewY(var(--tw-skew-y)) scaleX(var(--tw-scale-x)) scaleY(var(--tw-scale-y));
}

.button-name {
  font-size: 1.875rem;
  line-height: 2.25rem;
  color: rgba(255, 255, 255, 0.9);
  letter-spacing: 0.025em;
  font-weight: 900;
  font-family: "Quicksand", "Noto Sans SC", sans-serif;
}

.button-desc {
  font-size: 0.75rem;
  line-height: 1rem;
  --tw-text-opacity: 1;
  /* color: rgba(255, 255, 255, var(--tw-text-opacity)); */
  letter-spacing: 0.1rem;
  text-transform: uppercase;
  font-weight: 700;
  margin-top: 0.125rem;
}

.line {
  position: absolute;
  top: 0.25rem;
  right: 0.25rem;
  width: 0.5rem;
  height: 0.5rem;
}

@media(max-width: 768px) {
  button {
    height: 5rem;
    width: 10rem;
  }
}
</style>