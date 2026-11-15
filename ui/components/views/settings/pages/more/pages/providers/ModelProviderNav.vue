<script setup lang="ts">
import { providerIcon, tagLabel } from "@/composables/modelPresets";

const props = withDefaults(defineProps<{
  providers: Model.ProviderItem[];
  activeName: string;
  loading?: boolean;
  offline?: boolean;
  disabled?: boolean;
}>(), {
  loading: false,
  offline: false,
  disabled: false,
});

const emit = defineEmits<{
  (e: "select", name: string): void;
  (e: "refresh"): void;
}>();

const active = computed(() => props.providers.find((p) => p.name === props.activeName) ?? null);

const activeSummary = computed(() => {
  const p = active.value;
  if (!p) return "";
  const where = p.deployment === "local" ? "本地运行" : "云端服务";
  const tags = (p.tags ?? []).slice(0, 3).map(tagLabel).join(" · ");
  return tags ? `${where} · ${tags}` : where;
});
</script>

<template>
  <div class="provider-nav">
    <RowItem class="nav-head">
      <template #left>
        <span class="nav-title">供应商</span>
        <span class="nav-count">{{ providers.length }} 个</span>
      </template>
      <template #right>
        <Button
          type="select"
          :disabled="disabled || loading"
          @click="emit('refresh')"
        >刷新</Button>
      </template>
    </RowItem>

    <div class="provider-list" role="tablist">
      <Button
        v-for="p in providers"
        :key="p.name"
        type="nav"
        :icon="providerIcon(p.name)"
        :class="['provider-btn', { 'is-active': p.name === activeName }]"
        :disabled="disabled"
        @click="emit('select', p.name)"
      >
        <span class="provider-name">{{ p.label }}</span>
        <span class="provider-badges">
          <span class="dot" :class="p.available === false ? 'dot-off' : 'dot-on'"></span>
          <span v-if="p.deployment === 'local'" class="mini-tag">本地</span>
          <span v-else class="mini-tag mini-cloud">云端</span>
        </span>
      </Button>
      <StatusMessage v-if="!providers.length">暂未发现可用供应商</StatusMessage>
    </div>

    <p v-if="activeSummary" class="provider-summary">{{ activeSummary }}</p>
    <p v-if="offline" class="provider-offline">✦ 离线描述预览 · 连接后端后可切换</p>
  </div>
</template>

<style scoped>
.provider-nav {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.nav-head {
  border-bottom: 1px solid rgba(255, 255, 255, 0.14);
}

.nav-title {
  font-size: 14px;
  font-weight: 600;
  color: #fff;
  text-shadow: 0 2px 4px rgba(0, 0, 0, 0.5);
}

.nav-count {
  margin-left: 10px;
  font-family: var(--font-mono);
  font-size: 11px;
  color: rgba(255, 255, 255, 0.6);
}

.provider-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  max-height: 190px;
  overflow-y: auto;
  padding: 2px;
}

.provider-btn {
  min-width: 150px;
  justify-content: space-between;
  gap: 10px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  background: rgba(255, 255, 255, 0.06);
  color: #fff;
  text-shadow: 0 2px 4px rgba(0, 0, 0, 0.45);
  transition: all 0.25s cubic-bezier(0.25, 0.8, 0.25, 1);
}

.provider-btn:hover:not(:disabled) {
  border-color: rgba(255, 255, 255, 0.35);
  transform: translateY(-2px);
}

.provider-btn.is-active {
  border-color: var(--primary-color);
  background: linear-gradient(135deg, rgba(24, 144, 255, 0.28), rgba(255, 255, 255, 0.08));
  box-shadow: 0 0 0 1px rgba(121, 217, 255, 0.4), 0 0 18px rgba(121, 217, 255, 0.28);
}

.provider-name {
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
}

.provider-badges {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
}

.dot-on {
  background: #7ee2a8;
  box-shadow: 0 0 8px rgba(126, 226, 168, 0.8);
}

.dot-off {
  background: #9ca3af;
}

.mini-tag {
  padding: 1px 6px;
  font-size: 10px;
  border-radius: 999px;
  border: 1px solid rgba(126, 226, 168, 0.45);
  color: #b8f5d0;
}

.mini-cloud {
  border-color: rgba(121, 217, 255, 0.45);
  color: #a9e6ff;
}

.provider-summary,
.provider-offline {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.62);
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.5);
}

.provider-offline {
  color: #ffe58a;
}
</style>
