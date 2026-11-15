<script setup lang="ts">
import { serviceService } from '@/api/services/service';
import { errorView, toApiClientError } from '@/api/decoder';

const props = withDefaults(
  defineProps<{
    /** 父层从 /service 拿到的实例；传入可省一次详情请求 */
    service?: API.ServiceInfoData | null;
    /** 仅有 id 时组件自己 GET /service/{id} */
    serviceId?: string;
    disabled?: boolean;
  }>(),
  { service: null, serviceId: '', disabled: false }
);

const emit = defineEmits<{
  /** 任何写操作完成后请父层刷新列表 */
  changed: [];
  error: [view: UI.AsyncErrorView];
}>();

const id = computed(() => props.service?.id || props.serviceId);
const info = shallowRef<API.ServiceInfoData | null>(props.service || null);
const viewState = ref<'loading' | 'ready' | 'error'>('loading');
const errView = ref<UI.AsyncErrorView | null>(null);
const busy = ref('');
const showConfig = ref(false);
const showTools = ref(false);

let disposed = false;
let detailToken = 0;

const state = computed(() => info.value?.state || 'unknown');
const stateText = computed(() => {
  const map: Record<string, string> = {
    running: '运行中',
    stopped: '已停止',
    not_enabled: '未启用',
    error: '异常',
  };
  // 未知状态原样展示，不猜测语义
  return map[state.value] || state.value;
});
const stateClass = computed(() => {
  if (state.value === 'running') return 'on';
  if (state.value === 'error') return 'err';
  if (state.value === 'not_enabled') return 'off';
  return 'idle';
});
const isRunning = computed(() => state.value === 'running');
const isBusy = computed(() => props.disabled || busy.value !== '');
const configKeyCount = computed(() => {
  const cfg = info.value?.config;
  return cfg && typeof cfg === 'object' ? Object.keys(cfg as Record<string, any>).length : 0;
});

function reportError(err: unknown) {
  const view = errorView(toApiClientError(err));
  errView.value = view;
  viewState.value = 'error';
  if (view) emit('error', view);
}

async function loadDetail() {
  const serviceId = id.value;
  if (!serviceId) return;
  const token = ++detailToken;
  viewState.value = 'loading';
  errView.value = null;
  try {
    const data = await serviceService.getService(serviceId);
    if (disposed || token !== detailToken || serviceId !== id.value) return;
    info.value = data;
    viewState.value = 'ready';
  } catch (err) {
    if (disposed || token !== detailToken || serviceId !== id.value) return;
    reportError(err);
  }
}

async function runAction(kind: 'start' | 'stop' | 'apply') {
  const serviceId = id.value;
  if (!serviceId || isBusy.value) return;
  busy.value = kind;
  try {
    if (kind === 'start') {
      await serviceService.startService(serviceId, {});
    } else if (kind === 'stop') {
      await serviceService.stopService(serviceId);
    } else {
      await serviceService.applyConfig(serviceId);
    }
    emit('changed');
    await loadDetail();
  } catch (err) {
    reportError(err);
  } finally {
    busy.value = '';
  }
}

function toggleSection(name: 'config' | 'tools') {
  if (name === 'config') {
    showConfig.value = !showConfig.value;
    if (showConfig.value) showTools.value = false;
  } else {
    showTools.value = !showTools.value;
    if (showTools.value) showConfig.value = false;
  }
}

watch(
  () => props.service,
  (next) => {
    if (next) {
      info.value = next;
      viewState.value = 'ready';
    }
  }
);

onMounted(() => {
  if (!info.value) void loadDetail();
  else viewState.value = 'ready';
});
onBeforeUnmount(() => {
  disposed = true;
  detailToken += 1;
});

defineExpose({ refresh: loadDetail });
</script>

<template>
  <AsyncState
    :state="viewState"
    :error="errView"
    compact
    loading-text="正在读取服务详情…"
    @retry="loadDetail"
  >
    <ServiceCard
      v-if="info"
      class="panel-card"
    >
      <div class="panel-head">
        <ServiceIcon :service-id="info.id" />
        <div class="panel-title">
          <h3>{{ info.name || info.id }}</h3>
          <span class="panel-id">{{ info.id }}</span>
        </div>
        <span
          class="state-chip"
          :class="stateClass"
        >{{ stateText }}</span>
      </div>

      <p class="panel-desc">{{ info.description || '（该服务未提供描述）' }}</p>

      <div class="panel-meta">
        <span v-if="info.main_thread">主线程服务</span>
        <span>配置字段 {{ configKeyCount }}</span>
        <span>state: {{ state }}</span>
      </div>

      <div class="panel-actions">
        <Button
          type="select"
          :disabled="isBusy || isRunning"
          @click="runAction('start')"
        >{{ busy === 'start' ? '启动中…' : '启动' }}</Button>
        <Button
          type="nav"
          :disabled="isBusy || !isRunning"
          @click="runAction('stop')"
        >{{ busy === 'stop' ? '停止中…' : '停止' }}</Button>
        <Button
          type="nav"
          :disabled="isBusy"
          @click="runAction('apply')"
        >{{ busy === 'apply' ? '应用中…' : '应用配置' }}</Button>
        <Button
          type="nav"
          :disabled="isBusy"
          @click="loadDetail"
        >↻ 刷新</Button>
      </div>

      <div class="panel-tabs">
        <Button
          type="nav"
          :class="{ 'is-active': showConfig }"
          @click="toggleSection('config')"
        >
          <Icon
            icon="settings"
            :size="14"
          /> 配置
        </Button>
        <Button
          type="nav"
          :class="{ 'is-active': showTools }"
          @click="toggleSection('tools')"
        >
          <Icon
            icon="list"
            :size="14"
          /> 工具
        </Button>
      </div>

      <div
        v-if="showConfig"
        class="panel-section"
      >
        <ServiceConfigForm
          :service-id="info.id"
          :disabled="isBusy"
          @saved="emit('changed')"
          @applied="emit('changed')"
          @error="(view) => emit('error', view)"
        />
      </div>
      <div
        v-else-if="showTools"
        class="panel-section"
      >
        <ServiceToolList
          :service-id="info.id"
          @error="(view) => emit('error', view)"
        />
      </div>
      <StatusMessage v-else>
        选择「配置」或「工具」以从服务端读取对应数据
      </StatusMessage>
    </ServiceCard>

    <StatusMessage v-else>
      暂无服务详情
    </StatusMessage>
  </AsyncState>
</template>

<style scoped>
.panel-card {
  padding: 14px 16px 16px;
  color: var(--text-color);
}

.panel-head {
  display: flex;
  align-items: center;
  gap: 12px;
}

.panel-title {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.panel-title h3 {
  margin: 0;
  font-size: 17px;
  font-weight: 600;
  color: #fff;
  text-shadow: 0 2px 4px rgba(0, 0, 0, 0.5);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.panel-id {
  font-family: 'Maoken Assorted Sans', ui-monospace, Menlo, monospace;
  font-size: 11px;
  opacity: 0.6;
}

.state-chip {
  margin-left: auto;
  flex: 0 0 auto;
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 11px;
  border: 1px solid rgba(255, 255, 255, 0.18);
  background: rgba(255, 255, 255, 0.08);
  color: #fff;
  text-shadow: 0 2px 4px rgba(0, 0, 0, 0.4);
}

.state-chip.on {
  background: rgba(74, 222, 128, 0.22);
  color: #bbf7d0;
}

.state-chip.err {
  background: rgba(248, 113, 113, 0.22);
  color: #fecaca;
}

.state-chip.off {
  opacity: 0.6;
}

.panel-desc {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  opacity: 0.82;
}

.panel-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  font-size: 11px;
}

.panel-meta span {
  padding: 2px 8px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.06);
  opacity: 0.7;
}

.panel-actions,
.panel-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.panel-tabs :deep(.is-active) {
  background: rgba(255, 255, 255, 0.14);
  color: var(--primary-color);
}

.panel-section {
  border-top: 1px solid rgba(255, 255, 255, 0.14);
  padding-top: 10px;
}
</style>
