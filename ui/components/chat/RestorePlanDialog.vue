<script setup lang="ts">
/**
 * 恢复预演与确认 —— FrontendPlan F1-09 / 存档交互状态机 / FX-06
 *
 * 恢复前必须展示 RestorePlan：覆盖范围、缺失资产、迁移、警告与记忆影响。
 * 用户点击「保存/恢复」后不能立刻显示成功，只按服务端返回的状态更新 UI；
 * partial_failure 必须呈现明确警告与操作记录，不当作普通 toast 隐藏。
 */
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue';
import { saveService } from '@/api/services/save';
import { errorView, toApiClientError } from '@/api/decoder';
import AsyncState from '@/components/common/AsyncState.vue';

const props = withDefaults(
  defineProps<{
    visible: boolean;
    slotId: string;
    revision?: string;
  }>(),
  { revision: '' }
);

const emit = defineEmits<{
  'update:visible': [v: boolean];
  restored: [snapshot: UI.OperationSnapshot];
  'partial-failure': [detail: Record<string, any>];
  error: [view: UI.AsyncErrorView];
}>();

type Stage = 'preview' | 'error' | 'ready' | 'confirm' | 'restoring' | 'result';

const stage = ref<Stage>('preview');
const plan = shallowRef<UI.RestorePlan | null>(null);
const result = shallowRef<UI.OperationSnapshot | null>(null);
const errView = ref<UI.AsyncErrorView | null>(null);
const confirmView = shallowRef<UI.ConfirmView | null>(null);

const asyncState = computed<'loading' | 'error' | 'ready' | 'confirm'>(() => {
  if (stage.value === 'preview' || stage.value === 'restoring') return 'loading';
  if (stage.value === 'error') return 'error';
  if (stage.value === 'confirm') return 'confirm';
  return 'ready';
});

const loadingText = computed(() =>
  stage.value === 'restoring' ? '正在执行恢复事务，请勿关闭页面…' : '正在读取恢复预演（只读，无副作用）…'
);

function toArray(v: unknown): string[] {
  if (Array.isArray(v)) return v.map((x) => String(x)).slice(0, 40);
  if (typeof v === 'string' && v.trim()) return [v];
  if (v && typeof v === 'object') return Object.keys(v as Record<string, any>).slice(0, 40);
  return [];
}

/** 后端 raw 字段做宽松兼容；只有明确带 manifest/revision 的才标为 Full Snapshot（F1-08）。 */
function normalize(data: API.SnapshotActionData): UI.RestorePlan {
  const raw = (data.raw || {}) as Record<string, any>;
  const isFull = Boolean(
    raw.snapshot_type === 'full' ||
    raw.full_snapshot === true ||
    (raw.manifest && raw.revision)
  );
  const snapshotType: UI.RestorePlan['snapshotType'] = isFull
    ? 'full'
    : raw.snapshot_path || raw.pointer || data.action === 'record'
      ? 'pointer'
      : 'unknown';
  return {
    slotId: data.slot_id || props.slotId,
    revision: data.revision || props.revision,
    snapshotType,
    coverage: toArray(raw.coverage ?? raw.sections ?? raw.scope),
    missingAssets: toArray(raw.missing_assets ?? raw.missingAssets ?? raw.missing),
    migrations: toArray(raw.migrations ?? raw.migration),
    warnings: toArray(raw.warnings),
    memoryImpact: (raw.memory_impact ?? raw.memoryImpact) as Record<string, any> | undefined,
    raw,
  };
}

async function loadPreview() {
  stage.value = 'preview';
  errView.value = null;
  result.value = null;
  try {
    const data = await saveService.snapshotPreview({
      slot_id: props.slotId,
      revision: props.revision,
    });
    plan.value = normalize(data);
    stage.value = 'ready';
  } catch (err) {
    const view = errorView(toApiClientError(err));
    errView.value = view;
    stage.value = 'error';
    if (view) emit('error', view);
  }
}

function askConfirm() {
  const p = plan.value;
  if (!p) return;
  confirmView.value = {
    title: '确认恢复到该版本？',
    message: `覆盖范围 ${p.coverage.length} 项，缺失资产 ${p.missingAssets.length} 项，迁移 ${p.migrations.length} 项。恢复会覆盖当前运行态，失败将自动回滚。`,
    confirmText: '执行恢复',
    cancelText: '返回',
    danger: true,
  };
  stage.value = 'confirm';
}

async function runRestore() {
  if (!plan.value) return;
  stage.value = 'restoring';
  try {
    const data = await saveService.snapshotRestore({
      slot_id: props.slotId,
      revision: props.revision,
      trigger: 'manual',
    });
    const raw = (data.raw || {}) as Record<string, any>;
    const rawState = String(raw.state || raw.status || data.action || (data.ok ? 'restored' : 'failed'));
    const phaseTable: Record<string, UI.OperationPhase> = {
      restored: 'succeeded',
      committed: 'succeeded',
      done: 'succeeded',
      rolled_back: 'rolled_back',
      partial_failure: 'partial_failure',
      failed: 'failed',
      error: 'failed',
      cancelled: 'cancelled',
      timeout: 'timeout',
    };
    const phase = phaseTable[rawState] || (data.ok ? 'succeeded' : 'failed');
    const snapshot: UI.OperationSnapshot = {
      operationId: data.revision || data.slot_id || props.slotId,
      phase,
      percent: phase === 'succeeded' ? 100 : 0,
      message: String(raw.message || data.code || ''),
      warnings: toArray(raw.warnings),
      result: raw,
      startedAt: Date.now(),
      updatedAt: Date.now(),
    };
    result.value = snapshot;
    emit('restored', snapshot);
    if (phase === 'partial_failure') emit('partial-failure', raw);
    stage.value = 'result';
  } catch (err) {
    const view = errorView(toApiClientError(err));
    errView.value = view;
    stage.value = 'error';
    if (view) emit('error', view);
  }
}

function close() {
  emit('update:visible', false);
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && props.visible) close();
}

watch(
  () => props.visible,
  (v) => {
    if (v) void loadPreview();
  },
  { immediate: true }
);

onMounted(() => document.addEventListener('keydown', onKeydown));
onBeforeUnmount(() => document.removeEventListener('keydown', onKeydown));
</script>

<template>
  <Teleport to="body">
    <Transition name="fade">
      <div
        v-if="visible"
        class="mask"
        @click.self="close"
      >
        <section
          class="dialog"
          role="dialog"
          aria-modal="true"
          aria-label="恢复预演"
        >
          <header class="dialog-head">
            <div>
              <h3>恢复预演 · RestorePlan</h3>
              <p class="sub">槽位 {{ slotId }} · 版本 {{ revision || 'HEAD' }}</p>
            </div>
            <button
              class="close"
              type="button"
              aria-label="关闭"
              @click="close"
            >✕</button>
          </header>

          <div class="dialog-body">
            <AsyncState
              :state="asyncState"
              :error="errView"
              :confirm="confirmView"
              :loading-text="loadingText"
              @retry="loadPreview"
              @confirm="runRestore"
              @cancel="stage = 'ready'"
            >
              <template v-if="plan">
                <div class="plan">
                  <div class="plan-badges">
                    <span
                      class="badge"
                      :class="plan.snapshotType"
                    >{{ plan.snapshotType === 'full' ? 'Full Snapshot' : plan.snapshotType === 'pointer' ? '路径指针 / 部分存档' : '类型未知' }}</span>
                    <span class="badge ghost">revision {{ plan.revision || '—' }}</span>
                  </div>

                  <p
                    v-if="plan.snapshotType !== 'full'"
                    class="notice"
                  >该槽位只保存路径指针与部分配置，不是完整快照；未被覆盖的内容不会被恢复。</p>

                  <div class="plan-grid">
                    <div class="plan-col">
                      <h4>覆盖范围（{{ plan.coverage.length }}）</h4>
                      <ul><li
                          v-for="(c, i) in plan.coverage"
                          :key="i"
                        >{{ c }}</li><li
                          v-if="!plan.coverage.length"
                          class="muted"
                        >无</li></ul>
                    </div>
                    <div class="plan-col">
                      <h4>缺失资产（{{ plan.missingAssets.length }}）</h4>
                      <ul><li
                          v-for="(c, i) in plan.missingAssets"
                          :key="i"
                        >{{ c }}</li><li
                          v-if="!plan.missingAssets.length"
                          class="muted"
                        >无</li></ul>
                    </div>
                    <div class="plan-col">
                      <h4>迁移（{{ plan.migrations.length }}）</h4>
                      <ul><li
                          v-for="(c, i) in plan.migrations"
                          :key="i"
                        >{{ c }}</li><li
                          v-if="!plan.migrations.length"
                          class="muted"
                        >无</li></ul>
                    </div>
                  </div>

                  <div
                    v-if="plan.warnings.length"
                    class="warnings"
                  >
                    <h4>警告</h4>
                    <ul><li
                        v-for="(w, i) in plan.warnings"
                        :key="i"
                      >{{ w }}</li></ul>
                  </div>

                  <div
                    v-if="plan.memoryImpact"
                    class="memory-impact"
                  >
                    <h4>记忆影响</h4>
                    <pre>{{ JSON.stringify(plan.memoryImpact, null, 2) }}</pre>
                  </div>
                </div>
              </template>

              <template v-if="result">
                <div
                  class="result"
                  :class="{ warn: result.phase === 'partial_failure' || result.phase === 'rolled_back' }"
                >
                  <h4>操作记录 · {{ result.phase }}</h4>
                  <p>operation_id: {{ result.operationId }}</p>
                  <ul><li
                      v-for="(w, i) in result.warnings"
                      :key="i"
                    >{{ w }}</li></ul>
                  <p
                    v-if="result.phase === 'partial_failure'"
                    class="strong"
                  >部分内容已恢复，其余已回滚。请逐项核对，不要当作普通失败忽略。</p>
                </div>
              </template>
            </AsyncState>
          </div>

          <footer class="dialog-foot">
            <button
              class="btn ghost"
              type="button"
              @click="close"
            >关闭</button>
            <button
              v-if="stage === 'ready' && plan"
              class="btn primary"
              type="button"
              @click="askConfirm"
            >确认恢复</button>
            <button
              v-else-if="stage === 'result'"
              class="btn ghost"
              type="button"
              @click="loadPreview"
            >重新预演</button>
          </footer>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.mask {
  position: fixed;
  inset: 0;
  z-index: 9000;
  display: grid;
  place-items: center;
  background: rgba(3, 7, 18, 0.55);
  backdrop-filter: blur(3px);
}

.dialog {
  width: min(720px, 92vw);
  max-height: 84vh;
  display: flex;
  flex-direction: column;
  border-radius: 16px;
  overflow: hidden;
  color: var(--text-color);
  background: linear-gradient(160deg, rgba(20, 30, 55, 0.96), rgba(10, 16, 32, 0.96));
  border: 1px solid rgba(255, 255, 255, 0.14);
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.55);
}

.dialog-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.dialog-head h3 {
  margin: 0;
  font-size: 16px;
}

.sub {
  margin: 4px 0 0;
  opacity: 0.6;
  font-size: 12px;
}

.close {
  border: none;
  background: transparent;
  color: inherit;
  cursor: pointer;
  font-size: 16px;
  opacity: 0.7;
}

.dialog-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
}

.dialog-foot {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 12px 20px;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
}

.plan {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.plan-badges {
  display: flex;
  gap: 8px;
}

.badge {
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 11px;
  background: rgba(96, 165, 250, 0.22);
  color: #bfdbfe;
}

.badge.full {
  background: rgba(74, 222, 128, 0.2);
  color: #bbf7d0;
}

.badge.pointer {
  background: rgba(251, 191, 36, 0.2);
  color: #fde68a;
}

.badge.ghost {
  background: rgba(255, 255, 255, 0.08);
  opacity: 0.7;
}

.notice {
  margin: 0;
  padding: 8px 12px;
  border-radius: 8px;
  font-size: 12px;
  color: #fde68a;
  background: rgba(251, 191, 36, 0.1);
  border: 1px solid rgba(251, 191, 36, 0.25);
}

.plan-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.plan-col {
  min-width: 0;
  padding: 10px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.04);
}

.plan-col h4,
.warnings h4,
.memory-impact h4,
.result h4 {
  margin: 0 0 8px;
  font-size: 12px;
  opacity: 0.75;
}

.plan-col ul,
.warnings ul,
.result ul {
  margin: 0;
  padding-left: 16px;
  font-size: 12px;
  max-height: 160px;
  overflow-y: auto;
}

.muted {
  opacity: 0.45;
  list-style: none;
  margin-left: -16px;
}

.warnings {
  padding: 10px;
  border-radius: 10px;
  color: #fde68a;
  background: rgba(251, 191, 36, 0.08);
}

.memory-impact pre,
.result pre {
  margin: 0;
  max-height: 160px;
  overflow: auto;
  font-size: 11px;
  background: rgba(0, 0, 0, 0.28);
  padding: 8px;
  border-radius: 8px;
}

.result {
  margin-top: 12px;
  padding: 12px;
  border-radius: 10px;
  background: rgba(74, 222, 128, 0.1);
  font-size: 12px;
}

.result.warn {
  background: rgba(251, 191, 36, 0.12);
  color: #fde68a;
}

.result .strong {
  font-weight: 600;
}

.btn {
  border: 1px solid rgba(255, 255, 255, 0.18);
  border-radius: 8px;
  padding: 6px 16px;
  background: rgba(255, 255, 255, 0.08);
  color: inherit;
  cursor: pointer;
  font-size: 13px;
}

.btn.ghost {
  background: transparent;
}

.btn.primary {
  background: linear-gradient(135deg, rgba(68, 226, 255, 0.3), rgba(155, 255, 209, 0.2));
  border-color: rgba(68, 226, 255, 0.4);
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

@media (max-width: 720px) {
  .plan-grid {
    grid-template-columns: 1fr;
  }
}
</style>
