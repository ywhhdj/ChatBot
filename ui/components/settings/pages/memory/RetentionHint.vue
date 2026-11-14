<script setup lang="ts">
/**
 * 记忆保持率只读提示 —— FX-07 / F2-06
 * 区分「已淡忘」与「已删除」；删除后同时清理页面、搜索结果和 store 缓存。
 * 写操作（pin / revive / delete）必须由用户显式点击，不自动执行。
 */
import { computed, onBeforeUnmount, onMounted, ref, shallowRef } from 'vue';
import { memoryService } from '@/api/services/memory';
import { useChatStore } from '@/stores/chat';
import { errorView, toApiClientError } from '@/api/decoder';
import AsyncState from '@/components/common/AsyncState.vue';

const props = withDefaults(
  defineProps<{
    sessionId: string;
    items?: UI.RetentionItem[];
  }>(),
  { items: undefined }
);

const emit = defineEmits<{
  invalidate: [memoryId: string];
  changed: [];
  error: [view: UI.AsyncErrorView];
}>();

const store = useChatStore();
const stats = shallowRef<API.MemoryStatsData | null>(null);
const viewState = ref<'loading' | 'ready' | 'error'>('loading');
const errView = ref<UI.AsyncErrorView | null>(null);
const busyId = ref('');
const confirmingId = ref<string | null>(null);
let confirmTimer: number | null = null;

const list = computed<UI.RetentionItem[]>(() => {
  if (props.items?.length) return props.items.slice(0, 100);
  return store.memoryPreview(props.sessionId);
});

async function load() {
  viewState.value = 'loading';
  errView.value = null;
  try {
    // 只读统计，不拉取记忆正文，避免把低置信记忆当事实展示
    stats.value = await memoryService.stats();
    viewState.value = 'ready';
  } catch (err) {
    const view = errorView(toApiClientError(err));
    errView.value = view;
    viewState.value = 'error';
    if (view) emit('error', view);
  }
}

function fail(err: unknown) {
  const view = errorView(toApiClientError(err));
  errView.value = view;
  viewState.value = 'error';
  if (view) emit('error', view);
}

async function act(kind: 'pin' | 'revive' | 'delete', item: UI.RetentionItem) {
  if (busyId.value) return;
  busyId.value = item.id;
  try {
    if (kind === 'delete') {
      await memoryService.deleteMemory(item.id);
      // 页面、搜索结果与缓存一起失效（F2-06）
      store.invalidateMemory(props.sessionId, item.id);
      emit('invalidate', item.id);
    } else if (kind === 'pin') {
      await memoryService.pin({
        memory_id: item.id,
        session_id: props.sessionId,
        pinned: !item.pinned,
        dry_run: false,
      });
    } else {
      await memoryService.revive({
        memory_id: item.id,
        session_id: props.sessionId,
        dry_run: false,
      });
    }
    emit('changed');
  } catch (err) {
    fail(err);
  } finally {
    busyId.value = '';
    confirmingId.value = null;
  }
}

/** 删除是二次确认，沿用 SaveSlotsPanel 的「再点一次」交互风格。 */
function onDelete(item: UI.RetentionItem) {
  if (confirmingId.value !== item.id) {
    confirmingId.value = item.id;
    if (confirmTimer !== null) clearTimeout(confirmTimer);
    confirmTimer = window.setTimeout(() => (confirmingId.value = null), 3000);
    return;
  }
  void act('delete', item);
}

onMounted(() => {
  void load();
});

onBeforeUnmount(() => {
  if (confirmTimer !== null) clearTimeout(confirmTimer);
});

defineExpose({ refresh: load });
</script>

<template>
  <section class="retention">
    <header class="head">
      <div>
        <h3>记忆保持率</h3>
        <p class="sub">只读提示 · 已淡忘 ≠ 已删除</p>
      </div>
      <button
        class="btn"
        type="button"
        @click="load"
      >刷新</button>
    </header>

    <AsyncState
      :state="viewState"
      :error="errView"
      compact
      loading-text="正在读取记忆统计…"
      @retry="load"
    >
      <div class="stats">
        <span>记录 {{ stats?.records ?? 0 }}</span>
        <span>已压缩 {{ stats?.compressed ?? 0 }}</span>
        <span>短期窗口 {{ stats?.short_term_days ?? 0 }} 天</span>
        <span>后端 {{ stats?.backend || '—' }}</span>
      </div>

      <ul
        v-if="list.length"
        class="items"
      >
        <li
          v-for="item in list"
          :key="item.id"
          class="item"
          :class="item.state"
        >
          <div class="bar">
            <div
              class="fill"
              :style="{ width: `${Math.round((item.strength ?? 0) * 100)}%` }"
            />
          </div>
          <div class="content">
            <span
              class="state"
              :class="item.state"
            >{{ item.state === 'deleted' ? '已删除' : item.state === 'fading' ? '已淡忘' : item.state === 'active' ? '保持中' : '未知' }}</span>
            <span class="text">{{ item.state === 'deleted' ? '（墓碑保留，内容不再回显）' : item.content }}</span>
          </div>
          <div
            v-if="item.state !== 'deleted'"
            class="actions"
          >
            <button
              class="mini"
              type="button"
              :disabled="busyId === item.id"
              @click="act('pin', item)"
            >{{ item.pinned ? '取消固定' : '固定' }}</button>
            <button
              v-if="item.state === 'fading'"
              class="mini"
              type="button"
              :disabled="busyId === item.id"
              @click="act('revive', item)"
            >唤醒</button>
            <button
              class="mini danger"
              type="button"
              :disabled="busyId === item.id"
              @click="onDelete(item)"
            >{{ confirmingId === item.id ? '确认删除?' : '删除' }}</button>
          </div>
        </li>
        <li
          v-if="!list.length"
          class="empty"
        >当前没有需要提示的记忆条目</li>
      </ul>
    </AsyncState>
  </section>
</template>

<style scoped>
.retention {
  display: flex;
  flex-direction: column;
  gap: 10px;
  color: var(--text-color);
  font-size: 12px;
}

.head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
}

.head h3 {
  margin: 0;
  font-size: 14px;
}

.sub {
  margin: 3px 0 0;
  opacity: 0.55;
  font-size: 11px;
}

.stats {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.05);
  opacity: 0.8;
}

.items {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 320px;
  overflow-y: auto;
}

.item {
  padding: 8px 10px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.item.deleted {
  opacity: 0.55;
}

.bar {
  height: 3px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.1);
  overflow: hidden;
  margin-bottom: 6px;
}

.fill {
  height: 100%;
  background: linear-gradient(90deg, var(--primary-color), #6ee7d7);
}

.content {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.state {
  flex-shrink: 0;
  font-size: 10px;
  padding: 1px 7px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.1);
}

.state.fading {
  background: rgba(251, 191, 36, 0.2);
  color: #fde68a;
}

.state.deleted {
  background: rgba(248, 113, 113, 0.2);
  color: #fecaca;
}

.state.active {
  background: rgba(74, 222, 128, 0.18);
  color: #bbf7d0;
}

.actions {
  display: flex;
  gap: 6px;
  margin-top: 6px;
}

.btn,
.mini {
  border: 1px solid rgba(255, 255, 255, 0.16);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.06);
  color: inherit;
  cursor: pointer;
  font-size: 11px;
  padding: 3px 9px;
}

.mini:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.mini.danger {
  color: #fca5a5;
  border-color: rgba(248, 113, 113, 0.35);
}

.empty {
  padding: 12px;
  text-align: center;
  opacity: 0.5;
}
</style>
