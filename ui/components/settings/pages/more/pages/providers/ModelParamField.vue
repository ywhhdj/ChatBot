<script setup lang="ts">
import { SCOPE_LABELS } from "@/composables/modelPresets";

const props = withDefaults(
  defineProps<{
    field: Model.ParamSpec;
    modelValue: Model.Value;
    masked?: boolean;
    disabled?: boolean;
    error?: string;
  }>(),
  {
    masked: false,
    disabled: false,
    error: "",
  },
);

const emit = defineEmits<{
  (e: "change", value: Model.Value): void;
  (e: "secret", value: string): void;
}>();

/** Code 组件带 highlight.js，只在存在 object/array 字段时加载 */
const CodeLazy = defineAsyncComponent(() => import("@/components/base/Code.vue"));

const selectOptions = computed(() =>
  (props.field.enum ?? []).map((item) => {
    if (typeof item === "object" && item !== null) {
      return { id: item.value, label: item.label };
    }
    return { id: item, label: String(item) };
  }),
);

const displayValue = computed(() => {
  const v = props.modelValue;
  if (v === null || v === undefined) return "";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
});

const numberValue = computed(() => {
  const n = Number(props.modelValue);
  return Number.isFinite(n) ? n : 0;
});

const localError = ref("");
let jsonTimer: number | undefined;
const jsonText = ref(
  typeof props.modelValue === "object" && props.modelValue !== null
    ? JSON.stringify(props.modelValue, null, 2)
    : String(props.modelValue ?? ""),
);

watch(
  () => props.modelValue,
  (v) => {
    if (typeof v === "object" && v !== null) {
      const next = JSON.stringify(v, null, 2);
      if (next !== jsonText.value) jsonText.value = next;
    }
  },
);

watch(jsonText, (text) => {
  if (props.field.ui !== "json") return;
  if (jsonTimer !== undefined) clearTimeout(jsonTimer);
  jsonTimer = window.setTimeout(() => {
    try {
      const parsed = text.trim() ? JSON.parse(text) : props.field.type === "array" ? [] : {};
      localError.value = "";
      emit("change", parsed);
    } catch {
      localError.value = "JSON 格式不正确";
    }
  }, 150);
});

onBeforeUnmount(() => {
  if (jsonTimer !== undefined) clearTimeout(jsonTimer);
});

function coerceEnum(raw: string | number): Model.Value {
  const hit = (props.field.enum ?? []).find((item) => {
    const val = typeof item === "object" && item !== null ? item.value : item;
    return String(val) === String(raw);
  });
  if (hit === undefined) return raw;
  return typeof hit === "object" && hit !== null ? hit.value : hit;
}

function coerceScalar(raw: string | number): Model.Value {
  if (props.field.type !== "number" && props.field.type !== "integer") return raw;
  const n = Number(raw);
  if (!Number.isFinite(n)) {
    localError.value = "请输入数字";
    return props.modelValue;
  }
  if (props.field.type === "integer" && !Number.isInteger(n)) {
    localError.value = "请输入整数";
    return props.modelValue;
  }
  if (typeof props.field.min === "number" && n < props.field.min) {
    localError.value = `不得小于 ${props.field.min}`;
  } else if (typeof props.field.max === "number" && n > props.field.max) {
    localError.value = `不得大于 ${props.field.max}`;
  } else {
    localError.value = "";
  }
  return props.field.type === "integer" ? Math.trunc(n) : n;
}

/** 把控件原始值统一转换为字段值 */
function coerce(raw: unknown): Model.Value {
  switch (props.field.ui) {
    case "select":
      return coerceEnum(raw as string | number);
    case "slider": {
      const n = Number(raw);
      return props.field.type === "integer" ? Math.trunc(n) : n;
    }
    case "boolean":
      return Boolean(raw);
    case "json":
      return raw as Model.Value;
    default:
      return coerceScalar(raw as string | number);
  }
}

/** 统一入口：插槽里的控件通过 update() 回写到这里 */
const proxy = computed<Model.Value>({
  get: () => props.modelValue,
  set: (raw) => {
    if (props.field.secret) {
      emit("secret", String(raw ?? ""));
      return;
    }
    emit("change", coerce(raw));
  },
});

const hint = computed(() => localError.value || props.error || "");
</script>

<template>
  <FormRow
    v-model="proxy"
    :label="field.label"
    :description="field.description"
    :required="field.required"
    :icon="field.secret ? 'key' : ''"
    :badge="hideBadge || !field.scope ? '' : SCOPE_LABELS[field.scope]"
    :badge-class="`scope-${field.scope}`"
    :hint="hint"
    :disabled="disabled"
  >
    <!-- 右侧控件：由 ParamField 按 ui 决定，通过 update() 回写 -->
    <template #default="{ update }">
      <!-- 凭据：只写不读，绝不回显掩码值 -->
      <Input
        v-if="field.ui === 'secret'"
        type="password"
        :placeholder="masked ? '已配置 · 留空不修改' : '输入后仅在本次切换提交'"
        :disabled="disabled"
        @change="update($event)"
        @enter="update($event)"
      />

      <Input
        v-else-if="field.ui === 'password'"
        type="password"
        :model-value="displayValue"
        :disabled="disabled"
        @change="update($event)"
        @enter="update($event)"
      />

      <!-- 枚举 -->
      <Select
        v-else-if="field.ui === 'select'"
        :model-value="displayValue"
        :options="selectOptions"
        :disabled="disabled"
        @change="update($event)"
      />

      <!-- 滑块 -->
      <div v-else-if="field.ui === 'slider'" class="slider-wrap">
        <Silder
          :value="numberValue"
          :min="field.min ?? 0"
          :max="field.max ?? 100"
          :step="field.step ?? 1"
          @change="update($event)"
        />
        <span class="slider-value">{{ displayValue }}</span>
      </div>

      <!-- 布尔 -->
      <Checkbox
        v-else-if="field.ui === 'boolean'"
        :checked="Boolean(modelValue)"
        @click="update($event)"
      >
        启用
      </Checkbox>

      <!-- JSON：内部保持防抖 + 解析 -->
      <CodeLazy
        v-else-if="field.ui === 'json'"
        class="param-code"
        language="json"
        editable
        v-model="jsonText"
      />

      <!-- 普通输入 -->
      <Input
        v-else
        :model-value="displayValue"
        :placeholder="field.key"
        :disabled="disabled"
        :inputmode="field.type === 'number' || field.type === 'integer' ? 'decimal' : 'text'"
        @change="update($event)"
        @enter="update($event)"
      />
    </template>
  </FormRow>
</template>

<style scoped>
.slider-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
}

.slider-value {
  min-width: 44px;
  text-align: right;
  font-family: var(--font-mono);
  font-size: 13px;
  color: #a9e6ff;
  text-shadow: 0 0 8px rgba(121, 217, 255, 0.5);
}

.param-code {
  width: 100%;
  max-height: 180px;
  overflow: auto;
}

/* 业务徽标样式从 FormRow 透传 class，用 :deep 命中 */
:deep(.scope-init) {
  border-color: rgba(121, 217, 255, 0.5);
  color: #a9e6ff;
}
</style>