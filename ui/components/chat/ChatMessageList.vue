<script setup lang="ts">
/**
 * 长历史虚拟滚动 + 增量渲染 —— FrontendPlan F2-01 / F2-07 / F1-04
 *
 * - 复用现有 VirtualList（动态测高 + sticky + rAF 节流），chunk 到达不重绘整列表；
 * - 工具结果与 assistant 正文拆成不同行，task.update 不会污染聊天正文；
 * - 默认纯文本插值渲染，避免 v-html 与「虚拟列表套虚拟列表」的高度问题；
 *   需要富文本时传 markdown=true，由固定高度的 Markdown 容器承载。
 * - 字体/主题变化后 bump measureVersion 重测，避免首屏高度偏差。
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import VirtualList from '@/components/common/VirtualList.vue';
import Markdown from '@/components/common/Markdown.vue';
import ToolCallCard from '@/components/chat/tools/ToolCallCard.vue';
import ToolStepGroup from '@/components/chat/tools/ToolStepGroup.vue';
import AsyncState from '@/components/common/AsyncState.vue';

type Row = {
  id: string;
  kind: 'message' | 'tool' | 'tool-group';
  messageId: string;
  message?: UI.ChatMessage;
  tool?: UI.ToolCallItem;
  tools?: UI.ToolCallItem[];
};

const props = withDefaults(
  defineProps<{
    messages: UI.ChatMessage[];
    loading?: boolean;
    error?: UI.AsyncErrorView | null;
    streaming?: boolean;
    showTools?: boolean;
    markdown?: boolean;
  }>(),
  {
    loading: false,
    error: null,
    streaming: false,
    showTools: true,
    markdown: false,
  }
);

const emit = defineEmits<{ retry: [] }>();

const listRef = ref<any>(null);
const measureVersion = ref(0);
let stickRaf: number | null = null;

const viewState = computed<'ready' | 'loading' | 'empty' | 'error'>(() => {
  if (props.loading && !props.messages.length) return 'loading';
  if (props.error) return 'error';
  if (!props.messages.length) return 'empty';
  return 'ready';
});

/** 扁平化：一条消息一行；工具调用单独成行，>=3 步折叠成组。 */
const rows = computed<Row[]>(() => {
  const out: Row[] = [];
  for (const m of props.messages) {
    out.push({ id: `m_${m.id}`, kind: 'message', messageId: m.id, message: m });
    if (!props.showTools || m.role === 'user') continue;
    const tools = m.tools || [];
    if (tools.length >= 3) {
      out.push({ id: `g_${m.id}`, kind: 'tool-group', messageId: m.id, tools });
    } else {
      for (const t of tools) {
        out.push({ id: `t_${m.id}_${t.id}`, kind: 'tool', messageId: m.id, tool: t });
      }
    }
  }
  return out;
});

/** 只把真正影响高度的内容列入依赖，避免无关字段触发全量重测。 */
const sizeDeps = (item: Row): unknown[] => {
  if (item.kind === 'message') return [item.message?.content, item.message?.phase];
  if (item.kind === 'tool') {
    return [item.tool?.status, JSON.stringify(item.tool?.result ?? null)];
  }
  return [item.tools?.map((t) => `${t.id}:${t.status}`).join('|') ?? ''];
};

const scheduleStick = () => {
  if (stickRaf !== null) return;
  stickRaf = requestAnimationFrame(() => {
    stickRaf = null;
    nextTick(() => listRef.value?.scrollToBottom?.());
  });
};

// 流式正文增长时，行数与末尾 key 都不变，需手动吸底；rAF 合并到一帧一次
watch(
  () => [
    props.messages.length,
    props.messages.length ? props.messages[props.messages.length - 1]?.content : '',
  ],
  () => {
    if (props.streaming) scheduleStick();
  },
  { flush: 'post' }
);

onMounted(async () => {
  await document.fonts?.ready;
  measureVersion.value += 1;
});

onBeforeUnmount(() => {
  if (stickRaf !== null) cancelAnimationFrame(stickRaf);
});

function formatTime(ts?: number): string {
  if (!ts) return '';
  try {
    return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch {
    return '';
  }
}

const refreshMeasure = () => (measureVersion.value += 1);
const scrollToBottom = () => listRef.value?.scrollToBottom?.();

defineExpose({ scrollToBottom, refreshMeasure });
</script>

<template>
  <AsyncState
    :state="viewState"
    :error="error"
    loading-text="正在加载会话消息…"
    empty-text="还没有消息，说点什么吧"
    @retry="emit('retry')"
  >
    <VirtualList
      ref="listRef"
      class="message-scroller"
      :items="rows"
      :measure="true"
      :item-size="72"
      key-field="id"
      :size-dependencies="sizeDeps"
      :measure-version="measureVersion"
      :sticky="true"
      :sticky-threshold="64"
      height="100%"
    >
      <template #default="{ item }">
        <div
          v-if="item.kind === 'message'"
          class="message-row"
          :class="item.message?.role"
        >
          <div class="avatar">{{ item.message?.role === 'user' ? '你' : '灵' }}</div>
          <div class="bubble">
            <div class="bubble-head">
              <span class="role">{{ item.message?.role === 'user' ? '你' : '助手' }}</span>
              <span
                v-if="item.message?.phase && item.message.phase !== 'done'"
                class="phase"
              >{{ item.message.phase }}</span>
              <span class="time">{{ formatTime(item.message?.createdAt) }}</span>
            </div>

            <!-- 用户输入只做插值，绝不注入 HTML -->
            <div
              v-if="item.message?.role === 'user'"
              class="plain"
            >{{ item.message?.content }}</div>

            <div
              v-else-if="item.message?.content"
              class="md-wrap"
              :class="{ rich: markdown }"
            >
              <Markdown
                v-if="markdown"
                :content="item.message.content"
              />
              <div
                v-else
                class="plain"
              >{{ item.message.content }}</div>
            </div>

            <div
              v-else
              class="thinking"
            >
              <span class="typing" /> 正在思考…
            </div>
          </div>
        </div>

        <div
          v-else
          class="tool-row"
        >
          <ToolCallCard
            v-if="item.kind === 'tool' && item.tool"
            :tool="item.tool"
          />
          <ToolStepGroup
            v-else-if="item.kind === 'tool-group' && item.tools"
            :tools="item.tools"
          />
        </div>
      </template>

      <template #empty>
        <span class="list-empty">暂无消息</span>
      </template>
    </VirtualList>
  </AsyncState>
</template>

<style scoped>
.message-scroller {
  height: 100%;
  padding: 10px 4px 16px;
  color: var(--text-color);
}

.message-row {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 6px 10px;
}

.message-row.user {
  flex-direction: row-reverse;
}

.avatar {
  flex: 0 0 32px;
  width: 32px;
  height: 32px;
  border-radius: 10px;
  display: grid;
  place-items: center;
  font-size: 12px;
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.12);
}

.bubble {
  max-width: min(760px, 78%);
  min-width: 0;
  padding: 10px 14px;
  border-radius: 14px;
  background: rgba(15, 23, 42, 0.72);
  border: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.18);
}

.user .bubble {
  background: linear-gradient(135deg, rgba(68, 226, 255, 0.18), rgba(155, 255, 209, 0.12));
}

.bubble-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
  font-size: 11px;
  opacity: 0.65;
}

.role {
  font-weight: 600;
  letter-spacing: 0.5px;
}

.phase {
  padding: 1px 6px;
  border-radius: 999px;
  background: rgba(96, 165, 250, 0.2);
  color: #bfdbfe;
}

.time {
  font-variant-numeric: tabular-nums;
}

.md-wrap {
  min-height: 1em;
}

/* 富文本模式给内部虚拟列表一个确定高度，避免嵌套自适应塌陷 */
.md-wrap.rich {
  height: 320px;
  max-height: 42vh;
  overflow: hidden;
}

.plain {
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.6;
  font-size: 15px;
}

.thinking {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  opacity: 0.7;
}

.typing {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--primary-color);
  animation: pulse 1.1s ease-in-out infinite;
}

.tool-row {
  padding: 0 10px 0 52px;
}

.list-empty {
  font-size: 13px;
  opacity: 0.6;
}

@keyframes pulse {
  50% {
    opacity: 0.25;
    transform: scale(0.8);
  }
}

@media (max-width: 768px) {
  .bubble {
    max-width: 88%;
  }

  .tool-row {
    padding-left: 16px;
  }
}
</style>
