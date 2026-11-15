<script setup lang="ts">
/**
 * 存档时间线与回档预览 —— FX-06 / FrontendPlan F1-08
 *
 * 显示 revision 树与 memory_impact；明确区分 Slot（路径指针/部分配置）
 * 与 Full Snapshot，旧槽绝不被误标为完整存档。
 * 长列表走固定行高虚拟滚动，零测量开销。
 */
import { computed, onMounted, ref, shallowRef } from 'vue';
import { saveService } from '@/api/services/save';
import { errorView, toApiClientError } from '@/api/decoder';
import VirtualList from '@/components/common/VirtualList.vue';
import AsyncState from '@/components/common/AsyncState.vue';

interface TimelineNode {
  id: string;
  revision: string;
  parent: string;
  label: string;
  trigger: string;
  branchId: string;
  createdAt: string;
  snapshotType: 'full' | 'pointer' | 'unknown';
  memoryImpact?: Record<string, any>;
}

const props = withDefaults(
  defineProps<{
    slotId?: string;
    limit?: number;
  }>(),
  { slotId: '', limit: 120 }
);

const emit = defineEmits<{
  preview: [revision: string];
  restore: [revision: string];
  error: [view: UI.AsyncErrorView];
}>();

const nodes = shallowRef<TimelineNode[]>([]);
const slots = shallowRef<API.SlotInfoData[]>([]);
const head = ref('');
const viewState = ref<'loading' | 'ready' | 'empty' | 'error'>('loading');
const errView = ref<UI.AsyncErrorView | null>(null);

const rows = computed(() => nodes.value.slice(0, props.limit));
const currentSlot = computed(() => slots.value.find((s) => s.id === props.slotId) || null);

function toNodes(raw: any): TimelineNode[] {
  const list: any[] = Array.isArray(raw)
    ? raw
    : (raw?.nodes || raw?.revisions || raw?.graph?.nodes || raw?.items || []);
  return list.slice(0, props.limit).map((n: any, i: number) => {
    const revision = String(n.revision || n.id || n.rev || `rev_${i}`);
    const full = Boolean(
      n.snapshot_type === 'full' || n.full_snapshot === true || (n.manifest && n.revision)
    );
    return {
      id: `${revision}_${i}`,
      revision,
      parent: String(n.parent || n.parent_id || ''),
      label: String(n.label || n.name || ''),
      trigger: String(n.trigger || n.type || 'manual'),
      branchId: String(n.branch_id || n.branch || 'main'),
      createdAt: String(n.created_at || n.ts || ''),
      snapshotType: full ? 'full' : n.snapshot_path || n.pointer ? 'pointer' : 'unknown',
      memoryImpact: (n.memory_impact || n.memoryImpact) as Record<string, any> | undefined,
    } as TimelineNode;
  });
}

async function load() {
  viewState.value = 'loading';
  errView.value = null;
  try {
    // 三个只读端点并行，任一失败统一进入错误态
    const [graph, status, slotList] = await Promise.all([
      saveService.snapshotGraph(),
      saveService.snapshotStatus(),
      saveService.listSlots(),
    ]);
    const g = graph as unknown as Record<string, any>;
    const s = status as unknown as Record<string, any>;
    nodes.value = toNodes(g.raw || g.graph || g);
    head.value = String(s.revision || s.head || g.head || '');
    slots.value = (slotList.slots || []).slice(0, 40);
    viewState.value = nodes.value.length ? 'ready' : 'empty';
  } catch (err) {
    const view = errorView(toApiClientError(err));
    errView.value = view;
    viewState.value = 'error';
    if (view) emit('error', view);
  }
}

function fmt(t: string): string {
  if (!t) return '—';
  const d = new Date(t);
  return Number.isNaN(d.getTime()) ? t : d.toLocaleString();
}

onMounted(() => void load());

defineExpose({ refresh: load });
</script>

<template>
  <section class="timeline">
    <header class="timeline-head">
      <div>
        <h3>存档时间线</h3>
        <p class="sub">
          当前槽位 {{ slotId || '—' }} · HEAD {{ head || '—' }} · {{ nodes.length }} 个 revision
        </p>
      </div>
      <button
        class="btn"
        type="button"
        @click="load"
      >刷新</button>
    </header>

    <p
      v-if="currentSlot"
      class="slot-note"
    >
      槽位「{{ currentSlot.name || currentSlot.id }}」保存的是路径指针与部分配置，不等于 Full Snapshot；
      只有带 manifest/revision 的节点才是完整快照。
    </p>

    <AsyncState
      :state="viewState"
      :error="errView"
      loading-text="正在读取 revision 图与快照状态…"
      empty-text="暂无 revision 记录"
      @retry="load"
    >
      <VirtualList
        class="timeline-list"
        :items="rows"
        :measure="false"
        :item-size="76"
        key-field="id"
        height="100%"
      >
        <template #default="{ item }">
          <article
            class="node"
            :class="{ head: item.revision === head }"
          >
            <div class="rail">
              <span class="dot" />
            </div>
            <div class="node-main">
              <div class="node-line">
                <span class="rev">{{ item.revision.slice(0, 12) }}</span>
                <span
                  class="type"
                  :class="item.snapshotType"
                >{{ item.snapshotType === 'full' ? 'Full Snapshot' : item.snapshotType === 'pointer' ? '路径指针' : '类型未知' }}</span>
                <span
                  v-if="item.revision === head"
                  class="type head-tag"
                >HEAD</span>
                <span class="branch">{{ item.branchId }}</span>
                <span class="time">{{ fmt(item.createdAt) }}</span>
              </div>
              <div class="node-sub">
                <span>{{ item.label || '未命名版本' }}</span>
                <span class="sep">·</span>
                <span>触发 {{ item.trigger }}</span>
                <span
                  v-if="item.parent"
                  class="sep"
                >·</span>
                <span v-if="item.parent">父 {{ item.parent.slice(0, 8) }}</span>
              </div>
              <div
                v-if="item.memoryImpact"
                class="impact"
              >记忆影响：{{ Object.keys(item.memoryImpact).join('、') }}</div>
            </div>
            <div class="node-actions">
              <button
                class="mini"
                type="button"
                @click="emit('preview', item.revision)"
              >预演</button>
              <button
                class="mini danger"
                type="button"
                @click="emit('restore', item.revision)"
              >回档</button>
            </div>
          </article>
        </template>
      </VirtualList>
    </AsyncState>
  </section>
</template>

<style scoped>
.timeline {
  display: flex;
  flex-direction: column;
  gap: 10px;
  height: 100%;
  min-height: 260px;
  color: var(--text-color);
  font-size: 13px;
}

.timeline-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.timeline-head h3 {
  margin: 0;
  font-size: 15px;
}

.sub {
  margin: 4px 0 0;
  opacity: 0.6;
  font-size: 11px;
}

.slot-note {
  margin: 0;
  padding: 7px 10px;
  border-radius: 8px;
  font-size: 11px;
  line-height: 1.6;
  color: #fde68a;
  background: rgba(251, 191, 36, 0.09);
  border: 1px solid rgba(251, 191, 36, 0.24);
}

.timeline-list {
  height: 100%;
  min-height: 220px;
}

.node {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 76px;
  padding: 6px 10px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.node.head {
  background: rgba(59, 130, 246, 0.08);
}

.rail {
  flex: 0 0 14px;
  display: grid;
  place-items: center;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--primary-color);
  box-shadow: 0 0 8px rgba(59, 130, 246, 0.6);
}

.node-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.node-line,
.node-sub {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.rev {
  font-family: ui-monospace, Menlo, monospace;
  font-weight: 600;
}

.type {
  font-size: 10px;
  padding: 1px 7px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.08);
}

.type.full {
  background: rgba(74, 222, 128, 0.18);
  color: #bbf7d0;
}

.type.pointer {
  background: rgba(251, 191, 36, 0.18);
  color: #fde68a;
}

.head-tag {
  background: rgba(59, 130, 246, 0.25);
  color: #bfdbfe;
}

.branch,
.time,
.impact {
  opacity: 0.55;
  font-size: 11px;
}

.sep {
  opacity: 0.35;
}

.node-actions {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}

.btn,
.mini {
  border: 1px solid rgba(255, 255, 255, 0.16);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.06);
  color: inherit;
  cursor: pointer;
  font-size: 11px;
  padding: 4px 10px;
}

.btn:hover,
.mini:hover {
  background: rgba(255, 255, 255, 0.14);
}

.mini.danger {
  color: #fca5a5;
  border-color: rgba(248, 113, 113, 0.35);
}
</style>
