<script setup lang="ts" generic="T = unknown">
/**
 * 通用键值对表单行
 * - 左侧：label / required / 徽标 / description
 * - 右侧：默认插槽，作用域暴露 { modelValue, update, disabled }
 * - 底部：hint（错误或提示），支持 hint 插槽自定义
 */
const props = withDefaults(
  defineProps<{
    /** 左侧键名 */
    label: string;
    /** 绑定的值（v-model） */
    modelValue?: T;
    /** 说明文字 */
    description?: string;
    /** 必填标记 */
    required?: boolean;
    /** 左侧图标名 */
    icon?: string;
    /** 徽标文案，例如 scope 标签 */
    badge?: string;
    /** 徽标附加 class，例如 scope-init */
    badgeClass?: string;
    /** 底部提示 / 校验错误 */
    hint?: string;
    /** 右侧控件宽度 */
    controlWidth?: string;
    /** 禁用状态，透传给插槽 */
    disabled?: boolean;
  }>(),
  {
    description: "",
    required: false,
    icon: "",
    badge: "",
    badgeClass: "",
    hint: "",
    controlWidth: "min(280px, 46vw)",
    disabled: false,
  },
);

const emit = defineEmits<{
  (e: "update:modelValue", value: T): void;
}>();

const model = computed<T>({
  get: () => props.modelValue as T,
  set: (v) => emit("update:modelValue", v),
});

defineSlots<{
  default(props: { modelValue: T; update: (v: T) => void; disabled: boolean }): any;
  label(props: { label: string; required: boolean; badge: string }): any;
  badge(props: { badge: string }): any;
  hint(props: { hint: string }): any;
}>();
</script>

<template>
  <div class="form-row" :class="{ 'is-invalid': !!hint }">
    <RowItem class="form-row-inner">
      <template #left>
        <slot name="label" :label="label" :required="required" :badge="badge">
          <div class="row-label">
            <Icon v-if="icon" :icon="icon" :size="14" />
            <span class="row-name">{{ label }}</span>
            <span v-if="required" class="required">*</span>

            <slot name="badge" :badge="badge">
              <span v-if="badge" class="badge" :class="badgeClass">{{ badge }}</span>
            </slot>
          </div>
          <p v-if="description" class="row-desc">{{ description }}</p>
        </slot>
      </template>

      <template #right>
        <div class="row-control" :style="{ width: controlWidth }">
          <slot
            :model-value="model"
            :update="(v: T) => (model = v)"
            :disabled="disabled"
          />
        </div>
      </template>
    </RowItem>

    <p v-if="hint" class="row-hint">
      <slot name="hint" :hint="hint">{{ hint }}</slot>
    </p>
  </div>
</template>

<style scoped>
.form-row {
  margin-bottom: 6px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.form-row-inner {
  align-items: center;
}

.row-label {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  text-shadow: 0 2px 4px rgba(0, 0, 0, 0.45);
}

.row-name {
  font-family: var(--font-mono);
}

.required {
  color: #ffd700;
  text-shadow: 0 0 8px rgba(255, 215, 0, 0.6);
}

.badge {
  padding: 1px 7px;
  font-size: 10px;
  font-weight: normal;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.22);
  color: rgba(255, 255, 255, 0.72);
}

.row-desc {
  margin-top: 4px;
  max-width: 260px;
  font-size: 11px;
  line-height: 1.4;
  color: rgba(255, 255, 255, 0.62);
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.5);
}

.row-control {
  display: flex;
  justify-content: flex-end;
}

.row-hint {
  padding: 0 12px 6px;
  font-size: 11px;
  color: #ffb4a8;
  text-align: right;
}
</style>