<script setup lang="ts">
const props = withDefaults(defineProps<{
  pending: Model.PendingAction;
  dirty?: boolean;
  canApply?: boolean;
  canStop?: boolean;
  isLocal?: boolean;
  installed?: boolean;
  offline?: boolean;
  notice?: Model.Notice | null;
  invalidCount?: number;
}>(), {
  dirty: false,
  canApply: false,
  canStop: false,
  isLocal: false,
  installed: false,
  offline: false,
  notice: null,
  invalidCount: 0,
});

const emit = defineEmits<{
  (e: "apply"): void;
  (e: "stop"): void;
  (e: "download", force: boolean): void;
  (e: "refresh"): void;
}>();

type ConfirmKind = "" | "stop" | "download" | "force";
const confirming = ref<ConfirmKind>("");
let confirmTimer: number | undefined;

const busy = computed(() => props.pending !== null);

const pendingText = computed(() => {
  switch (props.pending) {
    case "load": return "读取模型描述中……";
    case "apply": return "切换中，请稍候……";
    case "stop": return "释放模型中……";
    case "download": return "提交下载任务……";
    case "refresh": return "刷新状态……";
    default: return "";
  }
});

function arm(kind: ConfirmKind) {
  if (busy.value) return;
  confirming.value = kind;
  if (confirmTimer !== undefined) clearTimeout(confirmTimer);
  confirmTimer = window.setTimeout(() => {
    confirming.value = "";
    confirmTimer = undefined;
  }, 4000);
}

function disarm() {
  confirming.value = "";
  if (confirmTimer !== undefined) {
    clearTimeout(confirmTimer);
    confirmTimer = undefined;
  }
}

function onStop() {
  if (confirming.value !== "stop") {
    arm("stop");
    return;
  }
  disarm();
  emit("stop");
}

function onDownload() {
  const kind: ConfirmKind = props.installed ? "force" : "download";
  if (confirming.value !== kind) {
    arm(kind);
    return;
  }
  disarm();
  emit("download", kind === "force");
}

onBeforeUnmount(disarm);
</script>

<template>
  <div class="action-bar">
    <div class="action-buttons">
      <Button
        type="big"
        :disabled="!canApply || busy"
        @click="emit('apply')"
      >{{ dirty ? "● 应用切换" : "应用切换" }}</Button>
      <Button
        v-if="isLocal && !offline"
        type="select"
        :disabled="busy"
        @click="onDownload"
      >{{ confirming === "force" ? "确认重新下载？" : confirming === "download" ? "确认下载？" : installed ? "重新下载" : "下载模型" }}</Button>
      <Button
        v-if="canStop && !offline"
        type="close"
        :disabled="busy"
        @click="onStop"
      >{{ confirming === "stop" ? "确认释放？" : "释放模型" }}</Button>
    </div>
    <div class="action-status" :class="notice ? `is-${notice.type}` : ''">
      <span v-if="pendingText">{{ pendingText }}</span>
      <span v-else-if="invalidCount" class="is-warning">还有 {{ invalidCount }} 项必填参数未完成</span>
      <span v-else-if="notice">{{ notice.text }}</span>
      <span v-else-if="offline">离线描述仅供预览，写操作已关闭</span>
      <span v-else>{{ dirty ? "有未应用的修改" : "与后端状态一致" }}</span>
    </div>
  </div>
</template>

<style scoped>
.action-bar {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 14px;
}

.action-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.action-status {
  min-height: 20px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.68);
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.5);
}

.action-status.is-success {
  color: #b8f5d0;
}

.action-status.is-error {
  color: #ffb4a8;
}

.action-status .is-warning {
  color: #ffe58a;
}

.action-status.is-info {
  color: #a9e6ff;
}
</style>
