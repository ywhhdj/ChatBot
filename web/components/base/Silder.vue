<script setup lang="ts">
const props = defineProps({
  value: {
    type: Number,
    required: false
  },
  min: {
    type: Number,
    default: 0
  },
  max: {
    type: Number,
    default: 100
  },
  step: {
    type: Number,
    default: 1
  }
});
const value = ref(props.value ?? (props.max + props.min) / 2);
const emit = defineEmits(['input', 'change']);

watch(() => props.value, (newValue) => {
  if (newValue !== value.value) {
    value.value = Number(newValue);
  }
});

const onInput = (event: Event) => {
  const nextValue = Number((event.target as HTMLInputElement).value);
  value.value = nextValue;
  emit('input', nextValue);
};

const onChange = (event: Event) => {
  const nextValue = Number((event.target as HTMLInputElement).value);
  value.value = nextValue;
  emit('change', nextValue);
};
</script>

<template>
  <div class="slider">
    <span>
      <slot name="left"></slot>
    </span>
    <input
      type="range"
      :min="min"
      :step="step"
      :max="max"
      :value="value"
      @input="onInput"
      @change="onChange"
      class="slider-input"
    >
    <span>
      <slot name="right"></slot>
    </span>
  </div>
</template>

<style scoped>
div {
  gap: 15px;
  display: flex;
  align-items: center;
  color: rgba(255, 255, 255, 0.9);
  /* 白色文字 */
  text-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
}

.slider-input {
  flex-grow: 1;
  outline: none;
  margin: 10px 0;
  appearance: none;
  position: relative;
  -webkit-appearance: none;
  background-color: transparent;

  &::-webkit-slider-runnable-track {
    width: 100%;
    height: 8px;
    border-radius: 4px;
    transition: all 0.3s ease;
    background: rgba(255, 255, 255, 0.2);
    /* 透明白色轨道 */
    border: 1px solid rgba(255, 255, 255, 0.1);
    box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.2);
  }

  &:hover::-webkit-slider-runnable-track {
    height: 10px;
    background: rgba(255, 255, 255, 0.25);
  }

  &::-webkit-slider-thumb {
    z-index: 2;
    width: 22px;
    height: 22px;
    cursor: grab;
    appearance: none;
    margin-top: -7px;
    position: relative;
    border-radius: 50%;
    -webkit-appearance: none;
    transform-origin: center;
    border: 2px solid rgba(255, 255, 255, 0.8);
    /* 半透明白色边框 */
    transition: all 0.2s cubic-bezier(0.25, 0.8, 0.25, 1);
    background: linear-gradient(135deg, var(--primary-color), #64b5f6);
    /* 渐变背景 */
    box-shadow:
      0 4px 12px rgba(121, 217, 255, 0.4),
      0 2px 4px rgba(0, 0, 0, 0.2);
  }

  &:active::-webkit-slider-thumb {
    cursor: grabbing;
  }
}

.slider-input::-webkit-slider-thumb:hover,
.slider-input::-webkit-slider-thumb:active {
  transform: scale(1.15);
  background: linear-gradient(135deg, #64b5f6, var(--primary-color));
  box-shadow:
    0 6px 20px rgba(121, 217, 255, 0.6),
    0 4px 8px rgba(0, 0, 0, 0.3);
}
</style>
