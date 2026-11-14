<script setup lang="ts">
/**
 * 会话 / 角色切换条 —— FrontendPlan F0-06 / F1-06 / F1-05
 * 每次请求都显式带 session_id / character_id，不依赖隐式全局当前会话。
 * 切换前先 await onBeforeSwitch（父视图取消或 detach 旧流），避免迟到事件覆盖新会话。
 */
import { computed, onBeforeUnmount, onMounted, ref, shallowRef } from 'vue';
import { historyService } from '@/api/services/history';
import { characterService } from '@/api/services/character';
import { statusService } from '@/api/services/status';
import { errorView, toApiClientError } from '@/api/decoder';
import AsyncState from '@/components/common/AsyncState.vue';

const props = withDefaults(
  defineProps<{
    sessionId?: string;
    characterId?: string;
    streamPhase?: UI.StreamPhase;
    disabled?: boolean;
    onBeforeSwitch?: () => void | Promise<void>;
  }>(),
  {
    sessionId: '',
    characterId: '',
    streamPhase: 'idle',
    disabled: false,
  }
);

const emit = defineEmits<{
  'switch-session': [id: string];
  'switch-character': [id: string];
  'create-session': [];
  error: [view: UI.AsyncErrorView];
}>();

const MAX_VISIBLE = 30;

const rootRef = ref<HTMLElement | null>(null);
const sessions = shallowRef<API.SessionInfoData[]>([]);
const characters = shallowRef<API.CharacterInfoData[]>([]);
const abilities = shallowRef<Record<string, boolean>>({});
const viewState = ref<'loading' | 'ready' | 'error'>('loading');
const errView = ref<UI.AsyncErrorView | null>(null);
const expanded = ref(false);

const short = (v?: string) => (v ? (v.length > 10 ? `${v.slice(0, 10)}…` : v) : '未选择');
const isStreaming = computed(
  () => props.streamPhase === 'connecting' || props.streamPhase === 'streaming'
);

async function load() {
  viewState.value = 'loading';
  errView.value = null;
  try {
    // 三个只读请求并行；失败互不影响后续刷新
    const [s, c, st] = await Promise.all([
      historyService.listSessions(),
      characterService.listCharacters(),
      statusService.status(),
    ]);
    sessions.value = (s.sessions || []).slice(0, MAX_VISIBLE);
    characters.value = (c.characters || []).slice(0, MAX_VISIBLE);
    const raw = st as unknown as Record<string, any>;
    const flag = (v: any) => !!(v && (v.initialized === true || v.available === true || v.ready === true));
    abilities.value = {
      llm: flag(raw.llm),
      tts: flag(raw.tts),
      asr: flag(raw.asr),
      embedding: flag(raw.embedding),
      overall: raw.ready !== false,
    };
    viewState.value = 'ready';
  } catch (err) {
    const view = errorView(toApiClientError(err));
    errView.value = view;
    viewState.value = 'error';
    if (view) emit('error', view);
  }
}

/** 事件委托：列表再长也只挂一个监听器（复用 Nav.vue 的做法）。 */
function onDelegatedClick(e: MouseEvent) {
  const root = rootRef.value;
  const target = e.target as HTMLElement | null;
  if (!root || !target) return;
  const trigger = target.closest('[data-session-id], [data-character-id]') as HTMLElement | null;
  if (!trigger || !root.contains(trigger)) return;
  if (props.disabled) return;

  const sessionId = trigger.dataset.sessionId;
  const characterId = trigger.dataset.characterId;
  void (async () => {
    await props.onBeforeSwitch?.();
    if (sessionId && sessionId !== props.sessionId) {
      emit('switch-session', sessionId);
      expanded.value = false;
    } else if (characterId && characterId !== props.characterId) {
      emit('switch-character', characterId);
      expanded.value = false;
    }
  })();
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') expanded.value = false;
}

onMounted(() => {
  void load();
  document.addEventListener('keydown', onKeydown);
});

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown);
});

defineExpose({ refresh: load });
</script>

<template>
  <div
    ref="rootRef"
    class="session-bar"
    @click="onDelegatedClick"
  >
    <div class="bar-head">
      <span class="bar-title">会话上下文</span>
      <span class="chip">session: {{ short(sessionId) }}</span>
      <span class="chip">character: {{ short(characterId) }}</span>
      <span
        class="chip stream"
        :class="{ on: isStreaming }"
      >{{ isStreaming ? '流式中' : '空闲' }}</span>
      <button
        class="head-btn"
        type="button"
        :disabled="disabled"
        @click="emit('create-session')"
      >新会话</button>
      <button
        class="head-btn"
        type="button"
        @click="expanded = !expanded"
      >{{ expanded ? '收起 ▴' : '切换 ▾' }}</button>
      <button
        class="head-btn ghost"
        type="button"
        aria-label="刷新会话与角色"
        @click="load"
      >↻</button>
    </div>

    <div
      v-show="expanded"
      class="bar-body"
    >
      <AsyncState
        :state="viewState"
        :error="errView"
        compact
        loading-text="正在读取会话、角色与能力状态…"
        @retry="load"
      >
        <div class="columns">
          <section class="column">
            <h4>会话（{{ sessions.length }}）</h4>
            <ul class="items">
              <li
                v-for="s in sessions"
                :key="s.id"
                class="item"
                :class="{ active: s.id === sessionId }"
                :data-session-id="s.id"
              >
                <span class="item-name">{{ s.name || s.id }}</span>
                <span class="item-meta">{{ s.message_count ?? 0 }} 条</span>
              </li>
              <li
                v-if="!sessions.length"
                class="item muted"
              >暂无会话</li>
            </ul>
          </section>

          <section class="column">
            <h4>角色（{{ characters.length }}）</h4>
            <ul class="items">
              <li
                v-for="c in characters"
                :key="c.id"
                class="item"
                :class="{ active: c.id === characterId }"
                :data-character-id="c.id"
              >
                <span class="item-name">{{ c.name || c.id }}</span>
                <span class="item-meta">{{ c.status || '—' }}</span>
              </li>
              <li
                v-if="!characters.length"
                class="item muted"
              >暂无角色</li>
            </ul>
          </section>

          <section class="column abilities">
            <h4>能力就绪</h4>
            <div class="ability-grid">
              <span
                v-for="(ok, key) in abilities"
                :key="key"
                class="ability"
                :class="{ on: ok }"
              >{{ key }} · {{ ok ? '就绪' : '未就绪' }}</span>
            </div>
          </section>
        </div>
      </AsyncState>
    </div>
  </div>
</template>

<style scoped>
.session-bar {
  position: sticky;
  top: 10px;
  z-index: 5;
  margin: 10px;
  border-radius: 10px;
  color: var(--text-color);
  background: rgba(0, 14, 39, 0.42);
  border: 1px solid rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(4px);
  font-size: 12px;
}

.bar-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  flex-wrap: wrap;
}

.bar-title {
  font-weight: 600;
  letter-spacing: 0.5px;
}

.chip {
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.08);
  opacity: 0.8;
  font-family: ui-monospace, Menlo, monospace;
}

.chip.stream.on {
  background: rgba(96, 165, 250, 0.28);
  color: #bfdbfe;
  opacity: 1;
}

.head-btn {
  border: 1px solid rgba(255, 255, 255, 0.16);
  background: rgba(255, 255, 255, 0.06);
  color: inherit;
  border-radius: 6px;
  padding: 3px 10px;
  cursor: pointer;
  font-size: 12px;
}

.head-btn:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.14);
}

.head-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.head-btn.ghost {
  background: transparent;
  margin-left: auto;
}

.bar-body {
  padding: 0 12px 12px;
}

.columns {
  display: grid;
  grid-template-columns: 1fr 1fr 0.8fr;
  gap: 12px;
  max-height: 260px;
}

.column {
  min-width: 0;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.04);
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.column h4 {
  margin: 0;
  font-size: 12px;
  opacity: 0.7;
  font-weight: 600;
}

.items {
  margin: 0;
  padding: 0;
  list-style: none;
  overflow-y: auto;
  max-height: 210px;
}

.item {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  padding: 5px 8px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s ease;
}

.item:hover {
  background: rgba(255, 255, 255, 0.1);
}

.item.active {
  background: rgba(59, 130, 246, 0.22);
}

.item.muted {
  opacity: 0.5;
  cursor: default;
}

.item-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.item-meta {
  opacity: 0.55;
  flex-shrink: 0;
}

.ability-grid {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.ability {
  padding: 4px 8px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.05);
  opacity: 0.6;
}

.ability.on {
  background: rgba(74, 222, 128, 0.18);
  color: #bbf7d0;
  opacity: 1;
}

@media (max-width: 900px) {
  .columns {
    grid-template-columns: 1fr;
    max-height: 320px;
  }
}
</style>
