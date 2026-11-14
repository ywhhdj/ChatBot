<script setup lang="ts">
const props = withDefaults(defineProps<{
  /** 选中态：边框高亮 + 渐变背景 + glow 光带 */
  selected?: boolean;
  /** 禁用：降透明、禁用指针 */
  disabled?: boolean;
  /**
   * 动画开关（默认 true）
   * - true  ：hover 上浮、边框/阴影过渡、选中时 glow 光带扫过
   * - false ：无过渡、无位移、无光带，只有选中态的颜色切换
   */
  animated?: boolean;
}>(), {
  selected: false,
  disabled: false,
  animated: true,
});

const slots = useSlots();
</script>

<template>
  <button
    type="button"
    class="base-card"
    :class="{ 'is-active': selected, 'is-static': !animated }"
    :disabled="disabled"
    :aria-pressed="selected"
  >
    <span v-if="animated" class="card-glow" aria-hidden="true" />

    <span v-if="slots.header" class="card-head">
      <slot name="header" />
    </span>

    <slot />

    <span v-if="slots.footer" class="card-foot">
      <slot name="footer" />
    </span>
  </button>
</template>

<style scoped>
.base-card {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
  min-height: 104px;
  padding: 14px 16px;
  text-align: left;
  color: #fff;
  cursor: pointer;
  border: 1px solid rgba(255, 255, 255, 0.18);
  border-radius: 12px;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.08), rgba(0, 20, 60, 0.18));
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.28), inset 0 1px 0 rgba(255, 255, 255, 0.22);
  text-shadow: 0 2px 4px rgba(0, 0, 0, 0.45);
  transition: transform 0.25s cubic-bezier(0.25, 0.8, 0.25, 1), box-shadow 0.25s, border-color 0.25s;
  overflow: hidden;
}

/* 所有 hover 上浮 */
.base-card:hover:not(:disabled) {
  transform: translateY(-3px);
}

/* 仅非选中态 hover 变白边框（修复原代码：选中卡片 hover 时边框被覆盖成白色） */
.base-card:not(.is-active):hover:not(:disabled) {
  border-color: rgba(255, 255, 255, 0.42);
  box-shadow: 0 10px 26px rgba(0, 0, 0, 0.38), 0 0 16px rgba(121, 217, 255, 0.22);
}

.base-card.is-active {
  border-color: var(--primary-color);
  background: linear-gradient(135deg, rgba(24, 144, 255, 0.24), rgba(255, 255, 255, 0.06));
  box-shadow: 0 0 0 1px rgba(121, 217, 255, 0.45), 0 0 22px rgba(121, 217, 255, 0.32),
              inset 0 1px 0 rgba(255, 255, 255, 0.28);
}

.base-card:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

/* ---------- animated=false：完全静态 ---------- */
.base-card.is-static {
  transition: none;
}

.base-card.is-static:hover:not(:disabled) {
  transform: none;
}

/* 非选中态 hover 恢复基础边框/阴影，选中态保持 is-active 的高亮 */
.base-card.is-static:not(.is-active):hover:not(:disabled) {
  border-color: rgba(255, 255, 255, 0.18);
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.28), inset 0 1px 0 rgba(255, 255, 255, 0.22);
}

/* ---------- glow 光带（仅 animated=true 时渲染） ---------- */
.card-glow {
  position: absolute;
  inset: -40% -60%;
  pointer-events: none;
  opacity: 0;
  background: linear-gradient(115deg, transparent 40%, rgba(255, 255, 255, 0.28) 50%, transparent 60%);
  transform: translateX(-30%);
  transition: opacity 0.3s, transform 0.6s;
}

.base-card.is-active .card-glow {
  opacity: 0.45;
  transform: translateX(30%);
}

/* ---------- 插槽容器布局 ---------- */
.card-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.5px;
}

.card-foot {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: auto;
}
</style>