<script setup lang="ts">
const props = defineProps<{
  disabled?: boolean;
}>();

const emit = defineEmits<{
  (e: 'start'): void;
  (e: 'stop', text: string): void;
}>();

const duration = ref(0);
const isRecording = ref(false);
const isSending = ref(false);
const CANCEL_THRESHOLD = 100;
let startY = 0;
let durationTimer: number | null = null;

const buttonDisabled = computed(() => props.disabled || isRecording.value);

const formattedDuration = computed(() => {
  const minutes = Math.floor(duration.value / 60);
  const seconds = duration.value % 60;
  return `${minutes}:${seconds.toString().padStart(2, '0')}`;
});

const StartRecord = async () => {
  isRecording.value = true;
  duration.value = 0;
  durationTimer = window.setInterval(() => duration.value++, 1000);
  try {
    await emit('start');
  } catch (error) {
    StopRecord();
  }
};

const StopRecord = () => {
  if (!isRecording.value) return;
  isRecording.value = false;
  cancelRecording();
};

const cancelRecording = () => {
  try {
    emit('stop', '');
    if (durationTimer) {
      clearInterval(durationTimer);
      durationTimer = null;
    }
  } catch (error) {
    console.error('取消录音失败:', error);
  }
}

onUnmounted(() => {
  if (durationTimer) {
    clearInterval(durationTimer);
    durationTimer = null;
  }
});

const hint = computed(() => {
  return `松开${isSending.value ? '发送' : '取消'} · 滑动持续`;
});

const statusTipClass = computed(() => {
  return {
    visible: isRecording.value || isSending.value
  }
});

const typeClass = computed(() => {
  return {
    disabled: buttonDisabled.value,
    recording: isRecording.value
  }
});

</script>

<template>
  <div class="voice-recorder">
    <Button
      type="nav"
      icon="record"
      :class="typeClass"
      :disabled="buttonDisabled"
      @mousedown="StartRecord"
      @mouseup="StopRecord"
    />
    <div
      class="status-tip"
      :class="statusTipClass"
    >
      <Wave v-show="isRecording">
        <span class="duration">{{ formattedDuration }}</span>
        <span class="hint">{{ hint }}</span>
      </Wave>
    </div>
  </div>
</template>

<style scoped>
.voice-recorder {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
}

.record-button:hover {
  transform: scale(1.05);
  box-shadow: 0 6px 20px rgba(102, 126, 234, 0.6);
}

.record-button:active {
  transform: scale(0.95);
}

.record-button.recording {
  background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
  animation: pulse 1.5s infinite;
  box-shadow: 0 4px 20px rgba(245, 87, 108, 0.6);
}

.record-button.sending {
  background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
  animation: none;
}

.record-button.disabled {
  opacity: 0.5;
  cursor: not-allowed;
  pointer-events: none;
}


/* 脉冲动画 */
@keyframes pulse {
  0% {
    box-shadow: 0 4px 20px rgba(245, 87, 108, 0.6);
  }

  50% {
    box-shadow: 0 4px 35px rgba(245, 87, 108, 0.8);
  }

  100% {
    box-shadow: 0 4px 20px rgba(245, 87, 108, 0.6);
  }
}

.spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }

  to {
    transform: rotate(360deg);
  }
}

/* 状态提示 */
.status-tip {
  position: absolute;
  bottom: 70px;
  left: 50%;
  transform: translateX(-50%);
  background: var(--accent-bg);
  color: white;
  padding: 12px 20px;
  border-radius: 20px;
  display: flex;
  align-items: center;
  gap: 10px;
  opacity: 0;
  visibility: hidden;
  transition: all 0.3s ease;
  white-space: nowrap;
  z-index: 100;
}

.status-tip.visible {
  opacity: 1;
  visibility: visible;
  bottom: 80px;
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