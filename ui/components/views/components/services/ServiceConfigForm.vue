<script setup lang="ts">
import { serviceService } from '@/api/services/service';
import { errorView, toApiClientError } from '@/api/decoder';

interface ServiceField {
  key: string;
  label: string;
  type: string;
  default: any;
  description?: string;
  options?: any[];
  min?: number;
  max?: number;
  step?: number;
  [key: string]: any;
}

const props = withDefaults(
  defineProps<{
    serviceId: string;
    disabled?: boolean;
  }>(),
  { disabled: false }
);

const emit = defineEmits<{
  saved: [config: Record<string, any>];
  applied: [config: Record<string, any>];
  error: [view: UI.AsyncErrorView];
}>();

const fields = shallowRef<ServiceField[]>([]);
const draft = ref<Record<string, any>>({});
/** 后端确实存了密钥的字段：用于「已配置 · 留空不修改」提示 */
const storedSecrets = shallowRef<Record<string, boolean>>({});
const viewState = ref<'loading' | 'ready' | 'empty' | 'error'>('loading');
const errView = ref<UI.AsyncErrorView | null>(null);
const busy = ref<'saving' | 'applying' | ''>('');

let loadToken = 0;
let disposed = false;

const isDisabled = computed(() => props.disabled || busy.value !== '');

function optionList(field: ServiceField) {
  return (field.options || []).map((o: any) =>
    typeof o === 'object' && o !== null
      ? { id: o.value ?? o.id ?? o.key, label: o.label ?? String(o.value ?? o.id ?? o.key) }
      : { id: o, label: String(o) }
  );
}

function setField(key: string, value: any) {
  // 不可变替换，避免深层响应式代理；字段数量由后端描述决定，规模有界
  draft.value = { ...draft.value, [key]: value };
}

function displayValue(field: ServiceField): string {
  const value = draft.value[field.key];
  if (value === null || value === undefined) return '';
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }
  return String(value);
}

function hasSlider(field: ServiceField): boolean {
  return field.type === 'number' && Number.isFinite(field.min) && Number.isFinite(field.max);
}

function secretPlaceholder(field: ServiceField): string {
  return storedSecrets.value[field.key]
    ? '已配置 · 留空不修改'
    : '输入密钥（不会回显）';
}

/** 构造提交体：跳过空密码、把 object 文本还原为结构（解析失败保留原字符串）。 */
function buildPayload(): Record<string, any> {
  const payload: Record<string, any> = {};
  for (const field of fields.value) {
    const value = draft.value[field.key];
    if (field.type === 'password' && (value === '' || value === null || value === undefined)) {
      continue;
    }
    if (field.type === 'object' && typeof value === 'string') {
      try {
        payload[field.key] = JSON.parse(value);
      } catch {
        payload[field.key] = value;
      }
      continue;
    }
    payload[field.key] = value;
  }
  return payload;
}

async function load() {
  const id = props.serviceId;
  if (!id) return;
  const token = ++loadToken;
  viewState.value = 'loading';
  errView.value = null;
  try {
    // 两个只读请求并行；都成功才允许编辑，避免用未知现值覆盖服务端配置
    const [uiRes, configRes] = await Promise.all([
      serviceService.serviceUi(id),
      serviceService.getConfig(id),
    ]);
    if (disposed || token !== loadToken || id !== props.serviceId) return;

    const list = (uiRes.fields || []) as ServiceField[];
    const raw = (configRes || {}) as Record<string, any>;
    const config =
      raw.config && typeof raw.config === 'object' && !Array.isArray(raw.config)
        ? (raw.config as Record<string, any>)
        : raw;

    const next: Record<string, any> = {};
    const secrets: Record<string, boolean> = {};
    for (const field of list) {
      // 默认值来自后端 UI 描述，是真实字段定义而非前端臆造
      next[field.key] = config[field.key] ?? field.default;
      if (field.type === 'password') {
        secrets[field.key] = Boolean(config[field.key]);
        next[field.key] = ''; // 密钥永不回显
      }
    }

    fields.value = list;
    draft.value = next;
    storedSecrets.value = secrets;
    viewState.value = list.length ? 'ready' : 'empty';
  } catch (err) {
    if (disposed || token !== loadToken || id !== props.serviceId) return;
    const view = errorView(toApiClientError(err));
    errView.value = view;
    viewState.value = 'error';
    if (view) emit('error', view);
  }
}

function reportError(err: unknown) {
  const view = errorView(toApiClientError(err));
  errView.value = view;
  viewState.value = 'error';
  if (view) emit('error', view);
}

async function saveInternal(): Promise<Record<string, any> | null> {
  try {
    const payload = buildPayload();
    const res = await serviceService.updateConfig(props.serviceId, { config: payload });
    const raw = (res || {}) as Record<string, any>;
    return (raw.config as Record<string, any>) || payload;
  } catch (err) {
    reportError(err);
    return null;
  }
}

async function onSave() {
  if (isDisabled.value) return;
  busy.value = 'saving';
  const saved = await saveInternal();
  busy.value = '';
  if (!saved) return;
  emit('saved', saved);
  await load();
}

async function onApply() {
  if (isDisabled.value) return;
  busy.value = 'applying';
  const saved = await saveInternal();
  if (!saved) {
    busy.value = '';
    return;
  }
  try {
    // 后端 apply 会先保存配置再停→启；不传 body 以免覆盖刚保存的值
    const res = await serviceService.applyConfig(props.serviceId);
    const raw = (res || {}) as Record<string, any>;
    emit('applied', (raw.config as Record<string, any>) || saved);
    await load();
  } catch (err) {
    reportError(err);
  } finally {
    busy.value = '';
  }
}

onMounted(() => void load());
onBeforeUnmount(() => {
  disposed = true;
  loadToken += 1;
});

defineExpose({ refresh: load });
</script>

<template>
  <AsyncState
    :state="viewState"
    :error="errView"
    compact
    loading-text="正在读取服务配置与字段描述…"
    empty-text="该服务未声明可配置项"
    @retry="load"
  >
    <div class="config-form">
      <FormRow
        v-for="field in fields"
        :key="field.key"
        :label="field.label || field.key"
        :description="field.description || ''"
        :model-value="draft[field.key]"
        :disabled="isDisabled"
        @update:model-value="(v) => setField(field.key, v)"
      >
        <template #default="{ update }">
          <Checkbox
            v-if="field.type === 'boolean'"
            :checked="Boolean(draft[field.key])"
            @click="(v) => update(v)"
          />

          <Select
            v-else-if="field.type === 'select' || (field.options && field.options.length)"
            :model-value="displayValue(field)"
            :options="optionList(field)"
            :disabled="isDisabled"
            @change="(v) => update(v)"
          />

          <Silder
            v-else-if="hasSlider(field)"
            :value="Number(draft[field.key] ?? field.default ?? 0)"
            :min="field.min"
            :max="field.max"
            :step="field.step || 1"
            @change="(v) => update(v)"
          />

          <Input
            v-else-if="field.type === 'password'"
            type="password"
            :model-value="displayValue(field)"
            :placeholder="secretPlaceholder(field)"
            :disabled="isDisabled"
            @change="(v) => update(v)"
            @enter="(v) => update(v)"
          />

          <Input
            v-else
            :model-value="displayValue(field)"
            :disabled="isDisabled"
            @change="(v) => update(v)"
            @enter="(v) => update(v)"
          />
        </template>
      </FormRow>

      <div class="config-actions">
        <Button
          type="select"
          :disabled="isDisabled"
          @click="onSave"
        >{{ busy === 'saving' ? '保存中…' : '保存配置' }}</Button>
        <Button
          type="big"
          :disabled="isDisabled"
          @click="onApply"
        >{{ busy === 'applying' ? '应用中…' : '应用（停→启）' }}</Button>
        <Button
          type="nav"
          :disabled="isDisabled"
          @click="load"
        >刷新</Button>
        <span class="config-tip">密码字段留空即不修改</span>
      </div>
    </div>
  </AsyncState>
</template>

<style scoped>
.config-form {
  display: flex;
  flex-direction: column;
  gap: 2px;
  width: 100%;
  color: var(--text-color);
}

.config-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 10px;
}

.config-tip {
  margin-left: auto;
  font-size: 11px;
  opacity: 0.6;
}
</style>
