<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue';
import { useUserStore } from '@/stores/user';

const userStore = useUserStore();
const draft = ref('');
const sending = ref(false);
const listRef = ref<HTMLElement | null>(null);

const messages = computed(() => userStore.dialogHistory);

const scrollToBottom = () => {
  nextTick(() => {
    if (listRef.value) {
      listRef.value.scrollTop = listRef.value.scrollHeight;
    }
  });
};

watch(messages, scrollToBottom, { deep: true });

const appendMessage = (message: DialogMessageItem) => {
  userStore.appendDialog(message);
};

const sendMessage = () => {
  const text = draft.value.trim();
  if (!text || sending.value) return;
  sending.value = true;
  const baseId = Date.now();
  appendMessage({
    id: baseId,
    type: 'message',
    role: 'user',
    content: text,
    timestamp: Date.now(),
  });
  draft.value = '';
  setTimeout(() => {
    appendMessage({
      id: baseId + 1,
      type: 'reply',
      role: 'assistant',
      content: '已收到。我会保持上下文，请继续。',
      timestamp: Date.now(),
    });
    sending.value = false;
  }, 450);
};

const onKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
};
</script>

<template>
  <section class="chat-shell">
    <header class="chat-header">
      <div class="brand">
        <div class="brand-mark">Q</div>
        <div class="brand-text">
          <div class="title">QianLing Live</div>
          <div class="subtitle">实时对话 · 语音链路 · Live2D</div>
        </div>
      </div>
      <div class="status">
        <span class="dot"></span>
        <span>在线</span>
      </div>
    </header>

    <div class="chat-body">
      <aside class="chat-side">
        <div class="side-card">
          <div class="side-title">场景模式</div>
          <div class="side-pill">直播互动</div>
          <div class="side-pill ghost">语音助手</div>
          <div class="side-pill ghost">主持人</div>
        </div>
        <div class="side-card">
          <div class="side-title">链路状态</div>
          <div class="side-row">
            <span>ASR</span>
            <span class="badge ok">Ready</span>
          </div>
          <div class="side-row">
            <span>LLM</span>
            <span class="badge ok">Stream</span>
          </div>
          <div class="side-row">
            <span>TTS</span>
            <span class="badge warn">Idle</span>
          </div>
          <div class="side-row">
            <span>Live2D</span>
            <span class="badge ok">Sync</span>
          </div>
        </div>
        <div class="side-card">
          <div class="side-title">快捷动作</div>
          <button class="side-action">场景切换</button>
          <button class="side-action ghost">一键静音</button>
        </div>
      </aside>

      <main class="chat-main">
        <div
          class="message-list"
          ref="listRef"
        >
          <div
            class="message-row"
            v-for="message in messages"
            :key="message.id"
            :class="message.role"
          >
            <div class="avatar">
              <span>{{ message.role === 'user' ? '你' : '灵' }}</span>
            </div>
            <div class="bubble">
              <div class="bubble-role">
                {{ message.role === 'user' ? '你' : '千灵' }}
              </div>
              <div class="bubble-text">{{ message.content }}</div>
              <div class="bubble-meta">
                {{ message.timestamp ? new Date(message.timestamp).toLocaleTimeString() : '' }}
              </div>
            </div>
          </div>
        </div>

        <div class="composer">
          <textarea
            v-model="draft"
            class="composer-input"
            rows="2"
            placeholder="输入内容，Enter 发送，Shift+Enter 换行"
            @keydown="onKeydown"
          ></textarea>
          <div class="composer-actions">
            <button
              class="icon-btn ghost"
              type="button"
            >语音</button>
            <button
              class="icon-btn ghost"
              type="button"
            >图片</button>
            <button
              class="icon-btn"
              type="button"
              @click="sendMessage"
            >发送</button>
          </div>
        </div>
      </main>
    </div>
  </section>
</template>

<style scoped>
.chat-shell {
  position: relative;
  width: min(1200px, 92vw);
  height: 88vh;
  margin: 4vh auto;
  border-radius: 28px;
  background: linear-gradient(140deg, rgba(255, 255, 255, 0.12), rgba(255, 255, 255, 0.03));
  border: 1px solid rgba(255, 255, 255, 0.2);
  box-shadow: 0 30px 80px rgba(3, 7, 18, 0.7);
  overflow: hidden;
  display: grid;
  grid-template-rows: auto 1fr;
  backdrop-filter: blur(14px);
}

.chat-shell::before {
  content: '';
  position: absolute;
  inset: -40% 0 auto 0;
  height: 60%;
  background: radial-gradient(circle at 20% 20%, rgba(68, 226, 255, 0.25), transparent 60%),
    radial-gradient(circle at 80% 40%, rgba(255, 122, 162, 0.2), transparent 65%);
  opacity: 0.8;
  pointer-events: none;
}

.chat-header {
  position: relative;
  z-index: 1;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 22px 28px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.brand {
  display: flex;
  align-items: center;
  gap: 16px;
}

.brand-mark {
  width: 46px;
  height: 46px;
  border-radius: 14px;
  background: linear-gradient(135deg, #44e2ff, #9bffd1);
  color: #04101f;
  font-family: var(--font-display);
  font-weight: 700;
  display: grid;
  place-items: center;
  letter-spacing: 1px;
}

.brand-text .title {
  font-family: var(--font-display);
  font-size: 20px;
  letter-spacing: 0.5px;
}

.brand-text .subtitle {
  font-size: 12px;
  color: rgba(226, 232, 240, 0.7);
  margin-top: 4px;
}

.status {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  background: rgba(15, 23, 42, 0.6);
  padding: 8px 14px;
  border-radius: 999px;
  font-size: 12px;
}

.status .dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #44e2ff;
  box-shadow: 0 0 12px rgba(68, 226, 255, 0.8);
}

.chat-body {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: 240px 1fr;
  height: 100%;
}

.chat-side {
  padding: 22px;
  display: flex;
  flex-direction: column;
  gap: 18px;
  border-right: 1px solid rgba(255, 255, 255, 0.08);
}

.side-card {
  background: rgba(10, 15, 31, 0.65);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 18px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.side-title {
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 1.2px;
  color: rgba(226, 232, 240, 0.6);
}

.side-pill {
  background: rgba(68, 226, 255, 0.18);
  color: #e2f8ff;
  padding: 8px 12px;
  border-radius: 999px;
  font-size: 12px;
  width: fit-content;
}

.side-pill.ghost {
  background: rgba(255, 255, 255, 0.06);
  color: rgba(226, 232, 240, 0.75);
}

.side-row {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: rgba(226, 232, 240, 0.8);
}

.badge {
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
}

.badge.ok {
  background: rgba(155, 255, 209, 0.2);
  color: #9bffd1;
}

.badge.warn {
  background: rgba(255, 209, 102, 0.2);
  color: #ffd166;
}

.side-action {
  border: none;
  background: linear-gradient(135deg, rgba(68, 226, 255, 0.35), rgba(155, 255, 209, 0.25));
  color: #e2f8ff;
  padding: 10px 12px;
  border-radius: 12px;
  cursor: pointer;
  font-size: 12px;
  text-align: left;
}

.side-action.ghost {
  background: rgba(255, 255, 255, 0.06);
  color: rgba(226, 232, 240, 0.8);
}

.chat-main {
  display: grid;
  grid-template-rows: 1fr auto;
  padding: 22px 26px;
  gap: 16px;
}

.message-list {
  overflow-y: auto;
  padding-right: 10px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.message-row {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.message-row.user {
  flex-direction: row-reverse;
}

.message-row.user .bubble {
  background: linear-gradient(135deg, rgba(68, 226, 255, 0.2), rgba(155, 255, 209, 0.15));
}

.message-row.user .bubble-role {
  text-align: right;
}

.avatar {
  width: 36px;
  height: 36px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.08);
  display: grid;
  place-items: center;
  font-size: 12px;
  font-family: var(--font-display);
}

.bubble {
  max-width: 70%;
  background: rgba(15, 23, 42, 0.8);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 18px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.bubble-role {
  font-size: 11px;
  letter-spacing: 1px;
  text-transform: uppercase;
  color: rgba(226, 232, 240, 0.6);
}

.bubble-text {
  font-size: 14px;
  line-height: 1.5;
}

.bubble-meta {
  font-size: 10px;
  color: rgba(226, 232, 240, 0.5);
}

.composer {
  background: rgba(10, 15, 31, 0.75);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 18px;
  padding: 12px;
  display: grid;
  gap: 10px;
}

.composer-input {
  width: 100%;
  background: transparent;
  border: none;
  color: #e2e8f0;
  resize: none;
  outline: none;
  font-family: var(--font-sans);
}

.composer-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.icon-btn {
  border: none;
  border-radius: 12px;
  padding: 8px 14px;
  background: linear-gradient(135deg, rgba(68, 226, 255, 0.35), rgba(155, 255, 209, 0.2));
  color: #e2f8ff;
  cursor: pointer;
  font-size: 12px;
}

.icon-btn.ghost {
  background: rgba(255, 255, 255, 0.08);
  color: rgba(226, 232, 240, 0.75);
}

@media (max-width: 980px) {
  .chat-shell {
    height: auto;
    margin: 12px;
  }

  .chat-body {
    grid-template-columns: 1fr;
  }

  .chat-side {
    border-right: none;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    flex-direction: row;
    flex-wrap: wrap;
  }

  .side-card {
    flex: 1 1 180px;
  }

  .bubble {
    max-width: 100%;
  }
}
</style>