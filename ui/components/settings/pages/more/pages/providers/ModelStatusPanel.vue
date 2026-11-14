<script setup lang="ts">
const props = withDefaults(defineProps<{
  status: Model.ProviderStatus | null;
  detail: Model.ProviderDetail | null;
  usage: Model.AdapterUsage | null;
  provider: Model.ProviderItem | null;
  models: Model.ModelItem[];
  warnings?: string[];
  missingEnv?: string[];
  progress?: number;
  phase?: string;
  offline?: boolean;
}>(), {
  warnings: () => [],
  missingEnv: () => [],
  progress: 0,
  phase: "",
  offline: false,
});

const selectedLabel = computed(() => {
  const id = props.status?.selected_model ?? props.detail?.selected_model ?? "";
  const hit = props.models.find((m) => m.id === id);
  return hit ? `${hit.label} · ${id}` : id || "—";
});

const rows = computed(() => {
  const s = props.status;
  const d = props.detail;
  const p = props.provider;
  const list: { label: string; value: string; tone?: string }[] = [
    { label: "当前供应商", value: s?.label ?? d?.meta?.label ?? p?.label ?? "—" },
    { label: "当前模型", value: selectedLabel.value },
    { label: "部署方式", value: s?.deployment ?? p?.deployment ?? "—" },
    { label: "传输 / 协议", value: [s?.transport, s?.protocol].filter(Boolean).join(" / ") || "—" },
    { label: "运行时", value: s?.runtime ?? "—" },
    {
      label: "可用状态",
      value: props.offline ? "离线描述" : s?.available === false || d?.available === false ? "未就绪" : "可用",
      tone: s?.available === false || d?.available === false ? "warn" : "ok",
    },
    {
      label: "已初始化",
      value: props.usage?.initialized ? "是" : props.usage ? "否" : "—",
    },
  ];
  return list;
});

const usageRows = computed(() =>
  Object.entries(props.usage?.usage ?? {}).slice(0, 4).map(([key, value]) => ({
    label: key,
    value: typeof value === "object" ? JSON.stringify(value) : String(value),
  })),
);

const downloadRows = computed(() => {
  const raw = props.status?.download_status ?? {};
  return Object.entries(raw)
    .filter(([, value]) => typeof value !== "object")
    .slice(0, 3)
    .map(([key, value]) => ({ label: key, value: String(value) }));
});
</script>

<template>
  <div class="status-panel">
    <StatusMessage v-if="!status && !detail && !usage">
      尚未读取到模型状态
    </StatusMessage>
    <template v-else>
      <div class="status-rows">
        <RowItem
          v-for="row in rows"
          :key="row.label"
          class="status-row"
        >
          <template #left><span class="row-label">{{ row.label }}</span></template>
          <template #right>
            <span class="row-value" :class="`tone-${row.tone ?? 'plain'}`">{{ row.value }}</span>
          </template>
        </RowItem>
        <RowItem v-for="row in usageRows" :key="`u-${row.label}`" class="status-row">
          <template #left><span class="row-label">用量 · {{ row.label }}</span></template>
          <template #right><span class="row-value mono">{{ row.value }}</span></template>
        </RowItem>
        <RowItem v-for="row in downloadRows" :key="`d-${row.label}`" class="status-row">
          <template #left><span class="row-label">文件 · {{ row.label }}</span></template>
          <template #right><span class="row-value mono">{{ row.value }}</span></template>
        </RowItem>
      </div>

      <div v-if="missingEnv.length" class="env-box">
        <span class="env-title">待配置环境变量</span>
        <span v-for="name in missingEnv" :key="name" class="env-tag">{{ name }}</span>
        <span class="env-hint">仅显示变量名，凭据不会回显</span>
      </div>

      <div v-if="warnings.length" class="warn-box">
        <span v-for="(text, index) in warnings" :key="index" class="warn-line">⚠ {{ text }}</span>
      </div>

      <div v-if="phase" class="download-box">
        <RowItem>
          <template #left><span class="row-label">{{ phase }}</span></template>
          <template #right><span class="row-value mono">{{ Math.round(progress) }}%</span></template>
        </RowItem>
        <div class="progress-track">
          <div class="progress-fill" :style="{ width: `${Math.max(0, Math.min(100, progress))}%` }"></div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.status-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.status-rows {
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(0, 0, 0, 0.18);
  overflow: hidden;
}

.status-row {
  border-bottom: 1px solid rgba(255, 255, 255, 0.07);
}

.status-row:last-child {
  border-bottom: none;
}

.row-label {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.72);
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.5);
}

.row-value {
  font-size: 13px;
  font-weight: 600;
  color: #fff;
  text-shadow: 0 2px 4px rgba(0, 0, 0, 0.5);
}

.row-value.mono {
  font-family: var(--font-mono);
  font-size: 12px;
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tone-ok {
  color: #b8f5d0;
}

.tone-warn {
  color: #ffe58a;
}

.env-box,
.warn-box,
.download-box {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 10px;
  border: 1px solid rgba(255, 215, 0, 0.28);
  background: rgba(255, 215, 0, 0.07);
  font-size: 11px;
  color: #ffe58a;
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.5);
}

.warn-box {
  flex-direction: column;
  align-items: flex-start;
  border-color: rgba(255, 160, 140, 0.28);
  background: rgba(255, 120, 100, 0.07);
  color: #ffc4b8;
}

.warn-line {
  line-height: 1.4;
}

.env-title {
  font-weight: 600;
}

.env-tag {
  padding: 1px 7px;
  border-radius: 999px;
  border: 1px solid rgba(255, 215, 0, 0.45);
  font-family: var(--font-mono);
}

.env-hint {
  margin-left: auto;
  color: rgba(255, 255, 255, 0.55);
}

.download-box {
  flex-direction: column;
  align-items: stretch;
  border-color: rgba(121, 217, 255, 0.3);
  background: rgba(24, 144, 255, 0.08);
  color: #a9e6ff;
}

.progress-track {
  width: 100%;
  height: 8px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.14);
  overflow: hidden;
  box-shadow: inset 0 1px 3px rgba(0, 0, 0, 0.35);
}

.progress-fill {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, var(--primary-color), #79d9ff);
  box-shadow: 0 0 12px rgba(121, 217, 255, 0.65);
  transition: width 0.25s ease;
}
</style>
