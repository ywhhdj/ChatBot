<script setup lang="ts">
/**
 * 聊天舞台
 */
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  shallowRef,
  withDefaults,
  defineProps,
} from 'vue';
import { useRouter } from 'vue-router';
import { useChatStore } from '@/stores/chat';
import { defaultUIStore } from '@/stores/ui';
import { historyService } from '@/api/services/history';
import { characterService } from '@/api/services/character';
import { saveService } from '@/api/services/save';
import { useChatStream } from '@/api/processing/useChatStream';
import { ApiClientError, errorView, toApiClientError } from '@/api/decoder';
import notification from '@/utils/notification';
import {
  registerRecordHandler,
  unregisterRecordHandler,
} from '@/api/websocket/handlers/record';

// 编辑立绘时历史卷轴让位、对话框隐藏，避免半透明层挡住贴纸拖拽
const props = withDefaults(defineProps<{
  avatarEditing?: boolean
}>(), {
  avatarEditing: false,
});

const router = useRouter();
const uiStore = defaultUIStore();
const store = useChatStore();

// ---------- 视图状态 ----------
const sessionId = ref('');
const characterId = ref('');
const sessions = shallowRef<API.SessionInfoData[]>([]);
const characters = shallowRef<API.CharacterInfoData[]>([]);

const bootView = ref<'loading' | 'ready' | 'error'>('loading');
const bootError = ref<UI.AsyncErrorView | null>(null);
const historyState = ref<'loading' | 'ready' | 'error'>('ready');
const historyError = ref<UI.AsyncErrorView | null>(null);

const draft = ref('');
const routeChoice = ref('');
const markdown = ref(false);
const agentVisible = ref(false);
const micGranted = ref(false);

const slotPickerVisible = ref(false);
const slotOptions = shallowRef<{ id: string; label: string }[]>([]);
const slotChoice = ref('');
const restoreVisible = ref(false);
const restoreSlotId = ref('');
const operationId = ref<string | null>(null);

const warnings = ref<string[]>([]);
const lastWarning = computed(() => warnings.value[warnings.value.length - 1] || '');
const sessionBarRef = ref<any>(null);
const messageListRef = ref<any>(null);

watch(
  () => props.avatarEditing,
  (editing) => {
    if (!editing) return;
    agentVisible.value = false;
    restoreVisible.value = false;
    slotPickerVisible.value = false;
  }
);

const routeOptions = [
  { id: '', label: '自动路由' },
  { id: 'pure_chat', label: '纯对话' },
  { id: 'tool_call', label: '工具调用' },
  { id: 'mixed', label: '混合' },
];

// ---------- 流（唯一状态机） ----------
function pushWarning(message: string) {
  // 有界缓冲：异常流刷警告时只保留最近 5 条
  warnings.value = [...warnings.value.slice(-4), message];
}

function notifyError(err: unknown) {
  const apiErr = err instanceof ApiClientError ? err : toApiClientError(err);
  // 用户主动取消不是错误通知
  if (apiErr.kind === 'cancelled') return;
  const view = errorView(apiErr);
  notification.showError({
    title: view?.title || '请求失败',
    message: view?.message || '请稍后重试',
  });
}

const {
  phase,
  state,
  isBusy,
  send,
  cancel,
  detach,
  retry,
  resetError,
} = useChatStream({
  sessionId: () => sessionId.value,
  characterId: () => characterId.value,
  onError: (err) => notifyError(err),
  onWarning: (message) => pushWarning(message),
});

const messages = computed<UI.ChatMessage[]>(() => store.messages);
const currentCharacter = computed(() =>
  characters.value.find((c) => c.id === characterId.value)
);
const characterName = computed(() => currentCharacter.value?.name || '灵');
const subtitle = computed(() => {
  const status = currentCharacter.value?.status;
  return status ? `状态 · ${status}` : '';
});
const emotion = computed(() => {
  if (phase.value === 'connecting') return '连线中…';
  if (phase.value === 'streaming') return '思考中…';
  if (phase.value === 'failed') return '似乎出了点状况';
  return '';
});

// ---------- 启动 / 会话 ----------
let bootToken = 0;
let loadToken = 0;

function normalizeTimestamp(ts?: number): number {
  if (!ts || !Number.isFinite(ts)) return Date.now();
  // 后端 MessageItem.timestamp 可能是秒或毫秒
  return ts > 1e12 ? ts : ts * 1000;
}

function applySession(sid: string, cid: string) {
  sessionId.value = sid;
  characterId.value = cid;
  // 会话切换是状态边界：旧流在 store 层标 detached
  store.setActive(sid, cid);
}

async function boot() {
  const token = ++bootToken;
  bootView.value = 'loading';
  bootError.value = null;
  try {
    // 三个只读请求互不阻塞：角色列表失败不该让会话服务不可用
    const [sessionsResult, charactersResult] = await Promise.allSettled([
      historyService.listSessions(),
      characterService.listCharacters(),
    ] as const);
    if (token !== bootToken) return;
    if (sessionsResult.status === 'rejected') throw sessionsResult.reason;

    const list = sessionsResult.value;
    characters.value =
      charactersResult.status === 'fulfilled'
        ? (charactersResult.value.characters || []).slice(0, 30)
        : [];

    let visibleSessions = (list.sessions || []).slice(0, 30);
    let target = list.current || visibleSessions[0]?.id || '';
    let targetCharacter = visibleSessions.find((s) => s.id === target)?.character_id || '';

    if (!target) {
      const created = await historyService.createSession({
        name: '新的对话',
        character_id: characters.value[0]?.id || '',
      });
      if (token !== bootToken) return;
      visibleSessions = [created];
      target = created.id;
      targetCharacter = created.character_id || characters.value[0]?.id || '';
    }

    sessions.value = visibleSessions;
    applySession(target, targetCharacter || characters.value[0]?.id || '');
    bootView.value = 'ready';
    await loadMessages();
  } catch (err) {
    if (token !== bootToken) return;
    bootError.value = errorView(toApiClientError(err));
    bootView.value = 'error';
  }
}

async function loadMessages() {
  const sid = sessionId.value;
  if (!sid) return;
  const token = ++loadToken;
  historyState.value = 'loading';
  historyError.value = null;
  try {
    const data = await historyService.messages(sid, { limit: 200 });
    // 归属校验：切换会话后的迟到响应不得写入当前 store
    if (token !== loadToken || sid !== sessionId.value) return;
    const mapped: UI.ChatMessage[] = (data.messages || []).map((m, i) => ({
      id: `hist_${sid}_${i}_${m.timestamp}`,
      role:
        m.role === 'assistant' || m.role === 'system'
          ? (m.role as UI.ChatRole)
          : 'user',
      content: m.content || '',
      phase: 'done',
      createdAt: normalizeTimestamp(m.timestamp),
    }));
    store.setMessages(sid, mapped);
    historyState.value = 'ready';
    await nextTick();
    messageListRef.value?.scrollToBottom?.();
  } catch (err) {
    if (token !== loadToken || sid !== sessionId.value) return;
    historyError.value = errorView(toApiClientError(err));
    historyState.value = 'error';
  }
}

/** ChatSessionBar 在切换前 await：先取消/分离旧流，再加载新上下文。 */
async function detachBeforeSwitch() {
  detach();
}

async function onSwitchSession(id: string) {
  if (!id || id === sessionId.value) return;
  try {
    // 以后端切换结果为准，不用前端选中态冒充全局当前会话（F1-05）
    await historyService.switchSession(id);
  } catch (err) {
    notifyError(err);
    return;
  }
  const cid = sessions.value.find((s) => s.id === id)?.character_id || characterId.value;
  applySession(id, cid);
  await loadMessages();
  sessionBarRef.value?.refresh?.();
}

async function onSwitchCharacter(id: string) {
  if (!id || id === characterId.value) return;
  try {
    await characterService.switchCharacter(id);
  } catch (err) {
    notifyError(err);
    return;
  }
  characterId.value = id;
  store.setActive(sessionId.value, id);
  sessionBarRef.value?.refresh?.();
}

async function onCreateSession() {
  try {
    const created = await historyService.createSession({
      name: `新的对话 ${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`,
      character_id: characterId.value,
    });
    detach();
    sessions.value = [created, ...sessions.value].slice(0, 30);
    applySession(created.id, created.character_id || characterId.value);
    await loadMessages();
    sessionBarRef.value?.refresh?.();
    notification.showSuccess({
      title: '新会话',
      message: '已创建并切换到新会话'
    });
  } catch (err) {
    notifyError(err);
  }
}

// ---------- 发送 / 取消 / 重试 ----------
function onSend(text: string) {
  if (!sessionId.value) {
    notification.showError({
      title: '无法发送',
      message: '请先选择或创建会话'
    });
    return;
  }
  // 显式隔离维度由 useChatStream 注入；route 只取 ChatRequest 声明值
  const extra = routeChoice.value ? { route: routeChoice.value } : {};
  send(text, extra);
}

function onCancel() {
  cancel();
}

function onRetryStream() {
  resetError();
  retry();
}

// ---------- 导航与录音 ----------
function openHistory() {
  uiStore.setCurrentSettingsTab('history');
  void router.push('/settings');
}

function openSettings() {
  void router.push('/settings');
}

async function checkMicPermission() {
  try {
    const status = await navigator.permissions.query({
      name: 'microphone' as PermissionName,
    });
    micGranted.value = status.state === 'granted';
    status.onchange = () => {
      micGranted.value = status.state === 'granted';
    };
  } catch {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach((track) => track.stop());
      micGranted.value = true;
    } catch {
      micGranted.value = false;
    }
  }
}

let recordActive = false;
function onVoiceStart() {
  if (recordActive) return;
  recordActive = true;
  registerRecordHandler((text: string) => {
    if (text) draft.value = (draft.value + text).slice(0, 4000);
  });
}

async function onVoiceStop() {
  if (!recordActive) return;
  recordActive = false;
  try {
    await unregisterRecordHandler();
  } catch (err) {
    notifyError(err);
  }
}

// ---------- 存档恢复预演 ----------
async function openRestore() {
  slotPickerVisible.value = true;
  try {
    const data = await saveService.listSlots();
    slotOptions.value = (data.slots || []).slice(0, 30).map((s) => ({
      id: s.id,
      label: s.name || s.id,
    }));
    slotChoice.value = data.current || slotOptions.value[0]?.id || '';
  } catch (err) {
    notifyError(err);
  }
}

function confirmRestore() {
  if (!slotChoice.value) {
    notification.showWarning({
      title: '恢复计划',
      message: '请先选择存档槽'
    });
    return;
  }
  restoreSlotId.value = slotChoice.value;
  slotPickerVisible.value = false;
  restoreVisible.value = true;
}

function onRestored(snapshot: UI.OperationSnapshot) {
  // 用户点击后不立刻显示成功：只按服务端终态更新 UI
  if (snapshot.phase === 'succeeded') {
    notification.showSuccess({
      title: '恢复完成',
      message: '存档已按服务端终态恢复'
    });
  } else if (snapshot.phase === 'partial_failure') {
    notification.showWarning({
      title: '恢复未完全成功',
      message: '部分内容已恢复，请查看操作记录与警告',
    });
  }
  const raw = snapshot.result || {};
  const taskId = String(raw.task_id || raw.operation_id || '');
  // 只有后端真的返回任务 id 才启用轮询，不把 revision 当 task_id
  operationId.value = taskId || null;
  void refreshAfterOperation();
}

function onPartialFailure(detail: Record<string, any>) {
  pushWarning(`部分恢复失败：${Object.keys(detail).length} 项记录需人工确认`);
}

function onOperationSettled() {
  operationId.value = null;
  void refreshAfterOperation();
}

function onOperationError(view: UI.AsyncErrorView) {
  notification.showError({ title: view.title || '操作状态查询失败', message: view.message });
}

async function refreshAfterOperation() {
  sessionBarRef.value?.refresh?.();
  await loadMessages();
}

// ---------- 生命周期 ----------
onMounted(() => {
  void boot();
  void checkMicPermission();
});

onBeforeUnmount(() => {
  detach();
  if (recordActive) {
    recordActive = false;
    void unregisterRecordHandler();
  }
  warnings.value = [];
  // 只清 UI 展示缓存，后端 session/memory 仍是权威
  store.clear();
});
</script>

<template>
  <div
    class="chat-stage"
    :class="{ 'is-avatar-editing': props.avatarEditing }"
  >
    <ChatSessionBar
      ref="sessionBarRef"
      :session-id="sessionId"
      :character-id="characterId"
      :stream-phase="phase"
      :disabled="bootView === 'loading'"
      :on-before-switch="detachBeforeSwitch"
      :initial-sessions="sessions"
      :initial-characters="characters"
      @switch-session="onSwitchSession"
      @switch-character="onSwitchCharacter"
      @create-session="onCreateSession"
    />

    <!-- 历史卷轴：保持立绘可见，长历史由 VirtualList 承接；编辑态让位给贴纸拖拽 -->
    <section
      class="history-wrap"
      :class="{ 'is-editing': props.avatarEditing }"
    >
      <ChatMessageList
        ref="messageListRef"
        :messages="messages"
        :loading="historyState === 'loading'"
        :error="historyError"
        :streaming="isBusy"
        :markdown="markdown"
        @retry="loadMessages"
      />
    </section>

    <!-- 底部 galgame 对话框：非编辑态常驻、贴底且 z 高于立绘（半透明渐变透出立绘下半身）-->
    <section
      v-show="!props.avatarEditing"
      class="dialog"
    >
      <div class="chatbox-box">
        <div class="chatbox-main">
          <ChatNameplate
            :name="characterName"
            :subtitle="subtitle"
            :emotion="emotion"
            :streaming="isBusy"
            :mic-granted="micGranted"
            :agent-visible="agentVisible"
            :busy="isBusy"
            @toggle-agent="agentVisible = !agentVisible"
            @open-restore="openRestore"
            @open-history="openHistory"
            @open-settings="openSettings"
            @voice-start="onVoiceStart"
            @voice-stop="onVoiceStop"
          />

          <div class="chatbox-line"></div>

          <div class="status-row">
            <StreamStatus
              :state="state"
              :phase="phase"
              @cancel="onCancel"
            />
            <Button
              v-if="phase === 'failed'"
              type="select"
              @click="onRetryStream"
            >重试</Button>
            <span
              v-if="lastWarning"
              class="warning-text"
              :title="lastWarning"
            >{{ lastWarning }}</span>
          </div>

          <ChatComposer
            v-model="draft"
            :streaming="isBusy"
            :disabled="!sessionId"
            @send="onSend"
            @cancel="onCancel"
          />

          <div class="stage-tools">
            <span class="tool-label">路由</span>
            <Select
              v-model="routeChoice"
              :options="routeOptions"
              :disabled="isBusy"
            />
            <Button
              type="nav"
              :class="{ 'is-active': markdown }"
              @click="markdown = !markdown"
            >{{ markdown ? '富文本' : '纯文本' }}</Button>
            <span class="tool-spacer"></span>
            <OperationStatus
              v-if="operationId"
              :operation-id="operationId"
              label="存档恢复"
              @settled="onOperationSettled"
              @error="onOperationError"
            />
          </div>
        </div>
      </div>
    </section>

    <AgentSidePanel
      v-model:visible="agentVisible"
      :messages="messages"
    />

    <RestorePlanDialog
      v-model:visible="restoreVisible"
      :slot-id="restoreSlotId"
      @restored="onRestored"
      @partial-failure="onPartialFailure"
    />

    <Transition name="fade">
      <div
        v-if="slotPickerVisible"
        class="slot-picker"
        role="dialog"
        aria-label="选择存档槽"
      >
        <div class="slot-picker-head">选择存档槽 · 恢复预演是只读操作</div>
        <Select
          v-model="slotChoice"
          :options="slotOptions"
        />
        <div class="slot-picker-actions">
          <Button
            type="select"
            :disabled="!slotChoice"
            @click="confirmRestore"
          >查看恢复计划</Button>
          <Button
            type="nav"
            @click="slotPickerVisible = false"
          >取消</Button>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.stage-root {
  width: 100%;
  height: 100%;
  color: var(--text-color);
}

.chat-stage {
  position: relative;
  z-index: 20;
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  min-height: 0;
}

.chat-stage.is-avatar-editing {
  pointer-events: none;
}

.chat-stage.is-avatar-editing> :first-child,
.chat-stage.is-avatar-editing .slot-picker,
.chat-stage.is-avatar-editing :deep(.side-panel),
.chat-stage.is-avatar-editing :deep(.restore-dialog) {
  pointer-events: auto;
}

/* 历史卷轴在编辑态完全让位：不抢指针、不遮挡画布 */
.chat-stage.is-avatar-editing .history-wrap {
  opacity: 0;
  pointer-events: none;
}

/* 历史卷轴：半透明渐变，立绘与背景仍可见 */
.history-wrap {
  flex: 1 1 auto;
  min-height: 0;
  width: min(60%, 860px);
  margin: 0 auto;
  border-radius: 12px 12px 0 0;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-bottom: none;
  background: linear-gradient(to top,
      rgba(0, 14, 39, 0.62) 0%,
      rgba(0, 14, 39, 0.05) 100%);
  backdrop-filter: blur(1px);
  box-shadow: 0 -10px 30px rgba(0, 0, 0, 0.25);
  overflow: hidden;
  transition: opacity 0.16s ease-out;
}

/* Step 11：编辑立绘时历史卷轴彻底让位（opacity 不改变布局尺寸，虚拟列表不重算），
   返回对话时原位恢复 */
.history-wrap.is-editing {
  opacity: 0;
  pointer-events: none;
}

.dialog {
  position: relative;
  z-index: 2;
  flex: 0 0 auto;
}

.chatbox-box {
  position: relative;
  display: flex;
  justify-content: center;
  width: 100%;
  z-index: 2;
  background: var(--dialog-bg-color);
  padding: 15px;
  backdrop-filter: blur(1px);
  color: #fff;
  text-shadow: 0 2px 4px rgba(0, 0, 0, 0.5);
  scrollbar-width: thin;
  scrollbar-color: var(--primary-color) transparent;
}

.chatbox-box::before {
  content: '';
  position: absolute;
  top: -40px;
  left: 0;
  right: 0;
  height: 40px;
  background: linear-gradient(to bottom,
      transparent 0%,
      rgba(0, 14, 39, 0.3) 50%,
      rgba(0, 14, 39, 0.6) 100%);
  pointer-events: none;
}

.chatbox-main {
  width: 60%;
  min-width: 0;
}

.chatbox-line {
  height: 1px;
  background: rgba(255, 255, 255, 0.3);
  margin: 6px 0;
}

/* 输入框沿用对话框背景，避免双层渐变上沿 */
.chatbox-box :deep(.composer) {
  background: transparent;
  border-top: none;
  padding: 4px 0 0;
}

.chatbox-box :deep(.composer::before) {
  display: none;
}

.chatbox-box :deep(.composer-main) {
  width: 100%;
  margin: 0;
}

.status-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin: 4px 0 6px;
}

.warning-text {
  max-width: 320px;
  font-size: 11px;
  color: #fbbf24;
  opacity: 0.85;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.stage-tools {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 6px;
}

.tool-label {
  font-size: 12px;
  opacity: 0.7;
}

.stage-tools :deep(select) {
  width: 140px;
}

.tool-spacer {
  flex: 1 1 auto;
}

.stage-tools :deep(.is-active) {
  background: rgba(255, 255, 255, 0.14);
  color: var(--primary-color);
}

.slot-picker {
  position: fixed;
  z-index: 12;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  width: min(420px, 90vw);
  padding: 16px;
  border-radius: 12px;
  background: rgba(0, 14, 39, 0.9);
  border: 1px solid rgba(255, 255, 255, 0.18);
  backdrop-filter: blur(6px);
  box-shadow: 0 18px 60px rgba(0, 0, 0, 0.55);
  color: #fff;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.slot-picker-head {
  font-size: 14px;
  font-weight: 600;
}

.slot-picker-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

@media (max-width: 768px) {

  .chatbox-main,
  .history-wrap {
    width: 90%;
  }
}
</style>
