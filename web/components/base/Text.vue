<script setup lang="ts">
import { CONFIG } from '@/config';
const props = defineProps({
  speed: {
    type: Number,
    default: CONFIG.text.speed
  },
  minDelay: {
    type: Number,
    default: 10
  },
  maxDelay: {
    type: Number,
    default: 200
  },
  showCursor: {
    type: Boolean,
    default: true
  }
});

const text = ref('');
let interval: number | undefined;
const slots = useSlots();
const sampleText = ref('');
let typingTimeout: number | undefined = undefined;

const stopTyping = () => {
  if (interval !== undefined) {
    cancelAnimationFrame(interval);
    interval = undefined;
  }
  if (typingTimeout !== undefined) {
    clearTimeout(typingTimeout);
    typingTimeout = undefined;
  }
};

const typeWrite = (speed: number, fullText: string) => {
  stopTyping();
  text.value = '';
  if (!fullText) {
    emit('complete');
    return;
  }
  const temp = props.maxDelay - props.minDelay + 1;
  const delay = props.maxDelay - Math.floor(((speed - 1) / 99) * temp);
  let i = 0;
  let lastTime = 0;
  const animate = (currentTime: number) => {
    if (!lastTime) lastTime = currentTime;
    const elapsed = currentTime - lastTime;

    if (elapsed >= delay) {
      if (i < fullText.length) {
        text.value += fullText.charAt(i);
        i += 1;
        lastTime = currentTime;
        // 触发打字事件
        emit('typing', {
          currentText: text.value,
          currentIndex: i,
          totalLength: fullText.length
        });
      } else {
        stopTyping();
        emit('complete');
        return;
      }
    }
    if (interval !== undefined) {
      interval = requestAnimationFrame(animate);
    }
  };
  interval = requestAnimationFrame(animate);
};
let debounceTimer: number | undefined = undefined;
const startTypingDebounced = (speed: number, fullText: string) => {
  if (debounceTimer !== undefined) {
    clearTimeout(debounceTimer);
  }
  debounceTimer = setTimeout(() => {
    typeWrite(speed, fullText);
  }, 50) as unknown as number;
};

watch(
  [() => props.speed, sampleText],
  ([newSpeed, newText]) => {
    startTypingDebounced(newSpeed, newText);
  },
  { immediate: true }
);

onBeforeUnmount(() => {
  stopTyping();
  if (typingTimeout !== undefined) {
    clearTimeout(typingTimeout);
  }
  if (debounceTimer !== undefined) {
    clearTimeout(debounceTimer);
  }
});

onMounted(() => {
  const nodes = slots.default?.() ?? [];
  const firstTextNode = nodes.find((n) => typeof n.children === 'string');
  sampleText.value = typeof firstTextNode?.children === 'string' ? firstTextNode.children : '';
});

const restart = () => {
  typeWrite(props.speed, sampleText.value);
};

const emit = defineEmits<{
  typing: [payload: { currentText: string; currentIndex: number; totalLength: number }];
  complete: [];
}>();

const skip = () => {
  stopTyping();
  text.value = sampleText.value;
  emit('complete');
};

defineExpose({
  restart,
  skip
});

</script>

<template>
  <div
    class="text"
    :aria-busy="interval !== undefined"
    :aria-label="sampleText"
  >
    <p>{{ text }}</p>
    <span
      v-if="showCursor && interval !== undefined"
      aria-hidden="true"
    ></span>
  </div>
</template>

<style scoped>
div {
  color: var(--text-color);
  min-height: 2.5em;
  padding: 15px 20px;
  border-radius: 12px;
  backdrop-filter: blur(10px);
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: inset 0 2px 8px rgba(0, 0, 0, 0.2);
  font-family: var(--font-mono);
}

p {
  display: inline;
}

span {
  width: 3px;
  height: 1.2em;
  margin-left: 4px;
  display: inline-block;
  vertical-align: text-bottom;
  background-color: var(--primary-color);
  animation: cursor-blink 0.8s infinite;
}
</style>
