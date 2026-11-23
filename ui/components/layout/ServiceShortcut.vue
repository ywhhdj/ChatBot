<script setup lang="ts">
import { serviceService } from '@/api/services/service';
import { errorView, toApiClientError } from '@/api/decoder';
import { defaultUIStore } from '@/stores/ui';
import { serviceStateText, serviceStateTone } from '@/components/configs/serviceConfig';
import { useRouter } from 'vue-router';

const emit = defineEmits<{
  error: [view: UI.AsyncErrorView];
}>();

const router = useRouter();
const uiStore = defaultUIStore();

const services = shallowRef<API.ServiceInfoData[]>([]);
const viewState = ref<'loading' | 'ready' | 'empty' | 'error'>('loading');
const errView = ref<UI.AsyncErrorView | null>(null);

let loadToken = 0;
let disposed = false;

/** 悬浮窗只看运行中的服务；有界缓冲避免长列表拖慢拖拽 */
const runningServices = computed(() =>
  services.value.filter((s) => s.state === 'running').slice(0, 8)
);
const totalCount = computed(() => services.value.length);

const badge = computed(() => {
  if (viewState.value === 'loading') return '读取中…';
  if (viewState.value === 'error') return '读取失败';
  if (viewState.value === 'empty') return '尚未注册服务';
  return `运行中 ${runningServices.value.length} / 已注册 ${totalCount.value}`;
});

async function load() {
  const token = ++loadToken;
  viewState.value = 'loading';
  errView.value = null;
  try {
    const data = await serviceService.listServices();
    if (disposed || token !== loadToken) return;
    services.value = (data.services || []).slice(0, 30);
    viewState.value = services.value.length ? 'ready' : 'empty';
  } catch (err) {
    if (disposed || token !== loadToken) return;
    const view = errorView(toApiClientError(err));
    errView.value = view;
    viewState.value = 'error';
    if (view) emit('error', view);
  }
}

/** 设置页「其它 → 服务」是唯一管理入口；query 让该位置可刷新/深链接 */
function openServices() {
  uiStore.setCurrentSettingsTab('more');
  uiStore.setCurrentMoreTab('services');
}

onMounted(() => void load());
onBeforeUnmount(() => {
  disposed = true;
  loadToken += 1;
});

//只有当前页面不是setting and service 显示
watch(ui.currentMoreTab)

defineExpose({ refresh: load });
</script>

<template>
  <Float
    title="服务状态"
    icon="plugin"
    width="268px"
    collapsible
  >
    <template #badge>{{ badge }}</template>

    <template #actions>
      <Button
        type="nav"
        :disabled="viewState === 'loading'"
        aria-label="刷新服务状态"
        @click="load"
      >↻</Button>
    </template>

    <template #default>
      <AsyncState
        :state="viewState"
        :error="errView"
        compact
        loading-text="正在读取服务状态…"
        empty-text="后端尚未注册服务"
        @retry="load"
      >
        <ul
          v-if="runningServices.length"
          class="ss-list"
        >
          <li
            v-for="s in runningServices"
            :key="s.id"
            class="ss-item"
          >
            <ServiceIcon
              :service-id="s.id"
              :size="13"
            />
            <span
              class="ss-name"
              :title="s.name || s.id"
            >{{ s.name || s.id }}</span>
            <span
              class="ss-state"
              :class="serviceStateTone(s.state)"
            >{{ serviceStateText(s.state) }}</span>
          </li>
        </ul>
        <p
          v-else
          class="ss-idle"
        >
          当前没有运行中的服务<br />
          <small>已注册 {{ totalCount }} 个</small>
        </p>
      </AsyncState>
    </template>

    <template #footer>
      <Button
        type="menu"
        class="ss-open"
        @click="openServices"
      >
        <Icon
          icon="settings"
          :size="14"
        />
        查看全部服务 ▸
      </Button>
    </template>
  </Float>
</template>

<style scoped>
.ss-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.ss-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 8px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.06);
  font-size: 12px;
}

.ss-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ss-state {
  margin-left: auto;
  flex: 0 0 auto;
  font-size: 11px;
  opacity: 0.6;
}

.ss-state.on {
  color: #bbf7d0;
  opacity: 1;
}

.ss-state.err {
  color: #fecaca;
  opacity: 1;
}

.ss-idle {
  margin: 4px 0;
  font-size: 12px;
  line-height: 1.7;
  opacity: 0.76;
  text-align: center;
}

.ss-idle small {
  font-size: 11px;
  opacity: 0.7;
}

.ss-open {
  display: inline-flex !important;
  align-items: center;
  gap: 6px;
  font-size: 13px !important;
  padding: 4px 8px !important;
  margin: 0 !important;
  text-shadow: 0 2px 4px rgba(0, 0, 0, 0.5);
}

.ss-open:hover {
  color: var(--primary-color);
}
</style>
