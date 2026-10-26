<script setup lang="ts">
import { supportedSetSinkId } from '@/utils/bowser';

const emit = defineEmits<{
  (e: 'change', deviceId: string): void
  (e: 'error', message: string): void
}>();

export interface AudioDevice {
  deviceId: string;
  groupId: string;
  label: string;
  kind: MediaDeviceKind;
  /** 是否为系统默认设备（deviceId 为 'default' 或 ''） */
  isDefault: boolean;
}

const devices = ref<AudioDevice[]>([
  {
    deviceId: "default",
    groupId: "",
    label: "系统默认设备",
    kind: "audiooutput",
    isDefault: true,
  }
]);
const selectedId = ref<string>("");
const loading = ref(false);
const error = ref("");
const hasPermission = ref(false);
const supported = supportedSetSinkId();

/** 音频上下文，用于 setSinkId 的宿主 */
let audioCtx: AudioContext | null = null;

function ensureAudioCtx(): AudioContext {
  if (!audioCtx) {
    const AC = window.AudioContext || (window as any).webkitAudioContext;
    audioCtx = new AC();
  }
  if (audioCtx.state === "suspended") {
    audioCtx.resume().catch(() => { });
  }
  return audioCtx;
}

/** 枚举所有音频输出设备 */
async function refresh() {
  if (!navigator.mediaDevices?.enumerateDevices) {
    error.value = "当前浏览器不支持 enumerateDevices";
    return;
  }
  loading.value = true;
  error.value = "";
  try {
    const all = await navigator.mediaDevices.enumerateDevices();
    devices.value = all
      .filter((d) => d.kind === "audiooutput")
      .map((d) => ({
        deviceId: d.deviceId,
        groupId: d.groupId,
        // 未授权时 label 为空字符串
        label: d.label || `输出设备 ${d.deviceId.slice(0, 6)}`,
        kind: d.kind,
        isDefault: d.deviceId === "default" || d.deviceId === "",
      }));

    // 若当前选中的设备已不在列表里（被拔出），回退到 default
    if (
      selectedId.value &&
      !devices.value.some((d) => d.deviceId === selectedId.value)
    ) {
      selectedId.value = "";
    }
    // 首次加载时默认选中系统默认设备
    if (!selectedId.value) {
      const def = devices.value.find((d) => d.isDefault) || devices.value[0];
      selectedId.value = def?.deviceId ?? "";
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
  }
}

/**
 * 申请麦克风权限。
 * 只有拿到 MediaStreamTrack 后，enumerateDevices 的 label 才不为空。
 * 用完立即停止轨道，不占用麦克风。
 */
async function requestPermission(): Promise<boolean> {
  if (!navigator.mediaDevices?.getUserMedia) {
    error.value = "当前浏览器不支持 getUserMedia";
    return false;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    stream.getTracks().forEach((t) => t.stop());
    hasPermission.value = true;
    await refresh();
    return true;
  } catch (e: any) {
    if (e?.name === "NotAllowedError") {
      error.value = "权限被拒绝，无法获取设备名称";
    } else if (e?.name === "NotFoundError") {
      error.value = "未检测到音频输入设备";
    } else {
      error.value = e instanceof Error ? e.message : String(e);
    }
    return false;
  }
}

/** 切换输出设备，返回是否成功 */
async function select(deviceId: string): Promise<boolean> {
  if (!supported) {
    error.value = "当前浏览器不支持切换输出设备";
    return false;
  }
  try {
    // 先枚举一次，确认设备还在
    await navigator.mediaDevices.enumerateDevices();

    // 用一个静音的 audio 元素做 sink 宿主
    const el = document.createElement("audio");
    el.muted = true;

    // setSinkId 在部分浏览器要传 { type: 'none' } 表示"不输出"
    const target = deviceId || "default";
    await el.setSinkId(target);

    // AudioContext 也切换（若已创建）
    if (audioCtx && "setSinkId" in audioCtx) {
      // @ts-expect-error AudioContext.setSinkId 非标准
      await audioCtx.setSinkId(target);
    }

    selectedId.value = deviceId;
    error.value = "";
    return true;
  } catch (e: any) {
    error.value =
      e?.name === "NotAllowedError"
        ? "切换输出设备需要用户手势触发"
        : e instanceof Error
          ? e.message
          : String(e);
    return false;
  }
}

/** 设备拔插监听 */
function onDeviceChange() {
  refresh();
}

const current = computed(() => {
  return devices.value.find((d) => d.deviceId === selectedId.value) ?? null
})

const switching = ref(false)

async function onChange(id: string) {
  switching.value = true
  const ok = await select(id)
  switching.value = false
  if (ok) {
    emit('change', id)
  } else if (error.value) {
    emit('error', error.value)
  }
}

const options = computed(() => {
  return devices.value.map((d) => d.label)
})

onMounted(() => {
  refresh();
  navigator.mediaDevices?.addEventListener?.("devicechange", onDeviceChange);
  // 初次检查权限：如果 enumerateDevices 已返回 label，说明已授权
  navigator.mediaDevices?.enumerateDevices?.().then((list) => {
    hasPermission.value = list.some(
      (d) => d.kind === "audiooutput" && d.label
    );
  });
});

onUnmounted(() => {
  navigator.mediaDevices?.removeEventListener?.(
    "devicechange",
    onDeviceChange
  );
  audioCtx?.close().catch(() => { });
  audioCtx = null;
});

</script>

<template>
  <Select
    v-model="selectedId"
    :options="options"
    :disabled="switching"
    @change="onChange"
  />
</template>

<style scoped>
.audio-output-selector {
  --border: #e5e7eb;
  --muted: #6b7280;
  --primary: #2563eb;
  --danger: #dc2626;
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-size: 14px;
  color: #111827;
}

.row.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-weight: 500;
  color: #374151;
}

.icon-btn {
  background: transparent;
  border: none;
  color: var(--muted);
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  display: inline-flex;
  align-items: center;
  transition: background .15s, color .15s;
}

.icon-btn:hover:not(:disabled) {
  background: #f3f4f6;
  color: #111827;
}

.icon-btn:disabled {
  opacity: .5;
  cursor: not-allowed;
}

.spin {
  animation: rot 1s linear infinite;
}

@keyframes rot {
  to {
    transform: rotate(360deg);
  }
}

.select-wrap {
  position: relative;
  display: flex;
  align-items: center;
}

.select-wrap.disabled {
  opacity: .6;
}

.select {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: #fff;
  font-size: 14px;
  font-family: inherit;
  color: #111827;
  outline: none;
  cursor: pointer;
  appearance: none;
  background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24'><path fill='%236b7280' d='M7 10l5 5 5-5z'/></svg>");
  background-repeat: no-repeat;
  background-position: right 10px center;
  padding-right: 32px;
}

.select:focus {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, .15);
}

.select:disabled {
  cursor: not-allowed;
  background-color: #f9fafb;
}

.spinner {
  position: absolute;
  right: 32px;
  width: 14px;
  height: 14px;
  border: 2px solid #d1d5db;
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: rot .8s linear infinite;
}

.meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--muted);
}

.badge {
  padding: 1px 6px;
  border-radius: 6px;
  font-size: 11px;
}

.badge.muted {
  background: #f3f4f6;
  color: var(--muted);
}

.badge.ok {
  background: #dcfce7;
  color: #166534;
}

.notice {
  padding: 8px 10px;
  border-radius: 6px;
  font-size: 12px;
  line-height: 1.5;
}

.notice.warn {
  background: #fffbeb;
  color: #92400e;
}

.notice.error {
  background: #fef2f2;
  color: var(--danger);
  margin: 0;
}

.hint {
  opacity: .75;
}

.link {
  background: none;
  border: none;
  color: var(--primary);
  cursor: pointer;
  padding: 0;
  font-size: 12px;
  text-decoration: underline;
  font-family: inherit;
}

.link:hover {
  color: #1d4ed8;
}
</style>