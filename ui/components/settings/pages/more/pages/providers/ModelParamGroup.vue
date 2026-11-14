<script setup lang="ts">
import { SCOPE_LABELS } from "@/composables/modelPresets";

const props = withDefaults(defineProps<{
  scope: Model.Scope;
  fields: Model.ParamSpec[];
  values: Record<string, Model.Value>;
  maskedKeys?: string[];
  disabled?: boolean;
}>(), {
  maskedKeys: () => [],
  disabled: false,
});

const emit = defineEmits<{
  (e: "change", key: string, value: Model.Value): void;
  (e: "secret", key: string, value: string): void;
}>();

const title = computed(() => {
  if (props.scope === "init") return "初始化参数";
  if (props.scope === "request") return "请求参数";
  return "其它参数";
});

const list = computed(() => props.fields.filter((f) => f.scope === props.scope));

const errorOf = (field: Model.ParamSpec) => {
  if (!field.required || field.secret) return "";
  const v = props.values[field.key];
  return v === "" || v === null || v === undefined ? "必填" : "";
};
</script>

<template>
  <section v-if="list.length" class="param-group">
    <RowItem class="group-head">
      <template #left>
        <span class="group-title">{{ title }}</span>
        <span class="group-scope">{{ SCOPE_LABELS[scope] }}</span>
      </template>
      <template #right>
        <span class="group-count">{{ list.length }} 项</span>
      </template>
    </RowItem>
    <ModelParamField
      v-for="field in list"
      :key="field.key"
      :field="field"
      :model-value="values[field.key]"
      :masked="maskedKeys.includes(field.key)"
      :disabled="disabled"
      :error="errorOf(field)"
      @change="(value) => emit('change', field.key, value)"
      @secret="(value) => emit('secret', field.key, value)"
    />
  </section>
</template>

<style scoped>
.param-group {
  margin-bottom: 12px;
  border-radius: 10px;
  background: rgba(0, 0, 0, 0.18);
  border: 1px solid rgba(255, 255, 255, 0.1);
  overflow: hidden;
}

.group-head {
  border-bottom: 1px solid rgba(255, 255, 255, 0.14);
}

.group-title {
  font-size: 14px;
  font-weight: 600;
  color: #fff;
  text-shadow: 0 2px 4px rgba(0, 0, 0, 0.5);
}

.group-scope {
  margin-left: 8px;
  padding: 1px 8px;
  font-size: 10px;
  border-radius: 999px;
  border: 1px solid rgba(121, 217, 255, 0.45);
  color: #a9e6ff;
}

.group-count {
  font-family: var(--font-mono);
  font-size: 11px;
  color: rgba(255, 255, 255, 0.6);
}
</style>
