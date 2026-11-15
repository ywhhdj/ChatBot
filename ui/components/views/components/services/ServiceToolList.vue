<script setup lang="ts">
import { serviceService } from '@/api/services/service';
import { errorView, toApiClientError } from '@/api/decoder';

interface ToolView {
  key: string;
  name: string;
  description: string;
  parameterCount: number;
}

const props = withDefaults(
  defineProps<{
    /** 为空时展示全部服务工具 */
    serviceId?: string;
    max?: number;
  }>(),
  { serviceId: '', max: 40 }
);

const emit = defineEmits<{
  error: [view: UI.AsyncErrorView];
}>();

const tools = shallowRef<ToolView[]>([]);
const total = ref(0);
const viewState = ref<'loading' | 'ready' | 'empty' | 'error'>('loading');
const errView = ref<UI.AsyncErrorView | null>(null);
const expandedKey = ref('');

let loadToken = 0;
let disposed = false;

/** OpenAI function 格式与裸定义都兼容，取值一律来自响应对象。 */
function normalize(item: any, index: number): ToolView {
  const fn = item?.function || item;
  const propsSchema = fn?.parameters || fn?.params || fn?.input_schema;
  const properties = propsSchema?.properties;
  const count = properties && typeof properties === 'object'
    ? Object.keys(properties).length
    : 0;
  return {
    key: `${fn?.name || item?.name || 'tool'}_${index}`,
    name: String(fn?.name || item?.name || item?.id || `工具 ${index + 1}`),
    description: String(fn?.description || item?.description || ''),
    parameterCount: count,
  };
}

function extract(data: API.ToolData): any[] {
  const services = (data?.services || {}) as Record<string, any>;
  if (Array.isArray(services.tools)) return services.tools;
  if (Array.isArray(services)) return services;
  // 后端固定用 {"tools": [...]}；其它形状不猜测，按空处理
  return [];
}

async function load() {
  const id = props.serviceId;
  const token = ++loadToken;
  viewState.value = 'loading';
  errView.value = null;
  try {
    const data = id
      ? await serviceService.serviceTools(id)
      : await serviceService.listTools();
    if (disposed || token !== loadToken) return;
    const raw = extract(data);
    total.value = Number(data?.total ?? raw.length);
    tools.value = raw.slice(0, props.max).map(normalize);
    viewState.value = tools.value.length ? 'ready' : 'empty';
  } catch (err) {
    if (disposed || token !== loadToken) return;
    const view = errorView(toApiClientError(err));
    errView.value = view;
    viewState.value = 'error';
    if (view) emit('error', view);
  }
}

const summary = computed(() =>
  props.serviceId
    ? `${props.serviceId} · ${total.value} 个工具`
    : `全部服务 · ${total.value} 个工具`
);

watch(() => props.serviceId, () => void load());
onMounted(() => void load());
onBeforeUnmount(() => {
  disposed = true;
  loadToken += 1;
});

defineExpose({ refresh: load });
</script>

<template>
  <section class="tool-list">
    <header class="tool-head">
      <Icon
        icon="code"
        :size="16"
      />
      <span class="tool-title">工具定义</span>
      <span class="tool-summary">{{ summary }}</span>
    </header>

    <AsyncState
      :state="viewState"
      :error="errView"
      compact
      loading-text="正在读取工具定义…"
      @retry="load"
    >
      <ul class="tool-rows">
        <li
          v-for="tool in tools"
          :key="tool.key"
          class="tool-row"
        >
          <button
            class="tool-name"
            type="button"
            :aria-expanded="expandedKey === tool.key"
            @click="expandedKey = expandedKey === tool.key ? '' : tool.key"
          >
            <span>{{ tool.name }}</span>
            <span class="tool-meta">{{ tool.parameterCount }} 参数</span>
            <span class="tool-arrow">{{ expandedKey === tool.key ? '▴' : '▾' }}</span>
          </button>
          <p
            v-if="expandedKey === tool.key"
            class="tool-desc"
          >{{ tool.description || '（该工具未提供描述）' }}</p>
        </li>
      </ul>
    </AsyncState>
  </section>
</template>

<style scoped>
.tool-list {
  width: 100%;
  color: var(--text-color);
}

.tool-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.tool-title {
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.5px;
}

.tool-summary {
  margin-left: auto;
  font-size: 11px;
  opacity: 0.6;
}

.tool-rows {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 220px;
  overflow-y: auto;
}

.tool-row {
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(255, 255, 255, 0.04);
  overflow: hidden;
}

.tool-name {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border: none;
  background: transparent;
  color: inherit;
  cursor: pointer;
  font-size: 12px;
  text-align: left;
  text-shadow: 0 2px 4px rgba(0, 0, 0, 0.4);
}

.tool-name:hover {
  background: rgba(255, 255, 255, 0.08);
}

.tool-meta {
  margin-left: auto;
  opacity: 0.55;
  font-size: 11px;
}

.tool-arrow {
  opacity: 0.6;
}

.tool-desc {
  margin: 0;
  padding: 6px 10px 8px;
  font-size: 12px;
  line-height: 1.6;
  opacity: 0.78;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
