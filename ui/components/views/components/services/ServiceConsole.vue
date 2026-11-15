<script setup lang="ts">
import { serviceService } from '@/api/services/service';
import { errorView, toApiClientError } from '@/api/decoder';
import { REGISTRABLE_SERVICE_IDS,serviceStateText, serviceStateTone } from './serviceConfig';

const emit = defineEmits<{
  error: [view: UI.AsyncErrorView];
}>();

const services = shallowRef<API.ServiceInfoData[]>([]);
const total = ref(0);
const viewState = ref<'loading' | 'ready' | 'empty' | 'error'>('loading');
const errView = ref<UI.AsyncErrorView | null>(null);
const activeIndex = ref(0);
const runningOnly = ref(false);
const registering = ref(false);
const registerChoice = ref('');
const showAllTools = ref(false);

let loadToken = 0;
let disposed = false;

/** 只有后端 `/service` 没返回的候选才允许注册，避免把未注册项画成已存在服务。 */
const registrable = computed(() =>
  REGISTRABLE_SERVICE_IDS
    .filter((sid) => !services.value.some((s) => s.id === sid))
    .map((sid) => ({ id: sid, label: sid }))
);

const activeService = computed<API.ServiceInfoData | null>(
  () => services.value[activeIndex.value] || null
);
const runningCount = computed(
  () => services.value.filter((s) => s.state === 'running').length
);

function reportError(err: unknown) {
  const view = errorView(toApiClientError(err));
  errView.value = view;
  viewState.value = 'error';
  if (view) emit('error', view);
}

async function load() {
  const token = ++loadToken;
  viewState.value = 'loading';
  errView.value = null;
  try {
    const data = await serviceService.listServices(
      runningOnly.value ? { running_only: true } : undefined
    );
    if (disposed || token !== loadToken) return;
    const list = (data.services || []).slice(0, 30);
    total.value = Number(data.total ?? list.length);
    services.value = list;
    // 选中索引收敛，避免过滤后指向不存在的服务
    if (activeIndex.value >= list.length) activeIndex.value = 0;
    if (!registrable.value.some((o) => o.id === registerChoice.value)) {
      registerChoice.value = registrable.value[0]?.id || '';
    }
    viewState.value = list.length ? 'ready' : 'empty';
  } catch (err) {
    if (disposed || token !== loadToken) return;
    reportError(err);
  }
}

async function onRegister() {
  const id = registerChoice.value;
  if (!id || registering.value) return;
  registering.value = true;
  try {
    await serviceService.registerService(id);
    // 注册后必须重新读取列表，以服务端结果为准
    await load();
    const index = services.value.findIndex((s) => s.id === id);
    if (index >= 0) activeIndex.value = index;
  } catch (err) {
    reportError(err);
  } finally {
    registering.value = false;
  }
}

function onRunningOnly(v: boolean) {
  runningOnly.value = v;
  void load();
}

onMounted(() => void load());
onBeforeUnmount(() => {
  disposed = true;
  loadToken += 1;
});

defineExpose({ refresh: load });
</script>

<template>
  <section class="console">
    <header class="console-head">
      <div class="console-title">
        <Icon
          icon="plugin"
          :size="20"
        />
        <span>服务管理</span>
      </div>
      <span class="console-summary">已注册 {{ total }} · 运行中 {{ runningCount }}</span>
      <div class="console-filter">
        <span class="filter-label">仅运行中</span>
        <Checkbox
          :checked="runningOnly"
          @click="onRunningOnly"
        />
      </div>
      <Button
        type="nav"
        :disabled="viewState === 'loading'"
        @click="load"
      >↻ 刷新</Button>
    </header>

    <AsyncState
      :state="viewState"
      :error="errView"
      loading-text="正在读取服务列表…"
      empty-text="后端尚未注册任何服务，可在下方注册候选服务"
      @retry="load"
    >
      <div
        class="console-nav"
        role="tablist"
        aria-label="已注册服务"
      >
        <Button
          v-for="(s, index) in services"
          :key="s.id"
          type="nav"
          class="service-tab"
          :class="{ active: index === activeIndex }"
          :aria-selected="index === activeIndex"
          @click="activeIndex = index"
        >
          <ServiceIcon
            :service-id="s.id"
            :size="14"
          />
          <span class="tab-name">{{ s.name || s.id }}</span>
          <span
            class="tab-state"
            :class="serviceStateTone(s.state)"
          >{{ serviceStateText(s.state) }}</span>
        </Button>
      </div>

      <ServicePanel
        v-if="activeService"
        :key="activeService.id"
        :service="activeService"
        @changed="load"
        @error="(view) => emit('error', view)"
      />

      <div class="console-tools">
        <Button
          type="nav"
          :class="{ 'is-active': showAllTools }"
          @click="showAllTools = !showAllTools"
        >
          <Icon
            icon="code"
            :size="14"
          /> 全部服务工具
        </Button>
        <ServiceToolList
          v-if="showAllTools"
          @error="(view) => emit('error', view)"
        />
      </div>
    </AsyncState>

    <footer class="console-register">
      <div class="register-label">注册服务实例</div>
      <Select
        v-model="registerChoice"
        :options="registrable"
        :disabled="registering || !registrable.length"
      />
      <Button
        type="select"
        :disabled="registering || !registerChoice"
        @click="onRegister"
      >{{ registering ? '注册中…' : '注册' }}</Button>
      <span class="register-hint">
        候选 id 来自后端可注册清单；注册成功后才会出现在上方列表
      </span>
    </footer>
  </section>
</template>

<style scoped>
.console {
  width: 100%;
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
  color: var(--text-color);
}

.console-head {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  padding: 8px 12px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  background: rgba(0, 14, 39, 0.42);
  backdrop-filter: blur(3px);
  text-shadow: 0 2px 4px rgba(0, 0, 0, 0.5);
}

.console-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-family: 'Maoken Assorted Sans', -apple-system, BlinkMacSystemFont, sans-serif;
  font-size: 18px;
  font-weight: 600;
}

.console-summary {
  font-size: 12px;
  opacity: 0.72;
}

.console-filter {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-left: auto;
}

.filter-label {
  font-size: 12px;
  opacity: 0.72;
}

.console-nav {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  padding: 2px 0 6px;
}

.service-tab {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}

.console-nav :deep(.service-tab.active) {
  background: rgba(255, 255, 255, 0.14);
  color: var(--primary-color);
}

.tab-name {
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tab-state {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.08);
  opacity: 0.8;
}

.tab-state.on {
  background: rgba(74, 222, 128, 0.22);
  color: #bbf7d0;
}

.tab-state.err {
  background: rgba(248, 113, 113, 0.22);
  color: #fecaca;
}

.tab-state.off {
  opacity: 0.5;
}

.console-tools {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.console-tools :deep(.is-active) {
  background: rgba(255, 255, 255, 0.14);
  color: var(--primary-color);
}

.console-register {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  background: rgba(0, 14, 39, 0.42);
  backdrop-filter: blur(3px);
}

.register-label {
  font-size: 13px;
  font-weight: 600;
}

.console-register :deep(select) {
  width: 180px;
}

.register-hint {
  margin-left: auto;
  max-width: 340px;
  font-size: 11px;
  opacity: 0.6;
  line-height: 1.5;
}

@media (max-width: 768px) {
  .console-summary,
  .register-hint {
    margin-left: 0;
  }
}
</style>
