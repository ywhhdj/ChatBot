<script setup lang="ts">
interface Props {
  /** 槽位编号，用于空位标签 "存档 #01 · 空位" */
  saveId: string | number
  /** 空位态：只显示加号 + 标签 */
  isEmpty?: boolean
  /** 当前选中：外圈高亮（原 WXSS 没有，但列表场景需要） */
  active?: boolean
  /** 忙碌：半透明禁用，避免连点 */
  busy?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  isEmpty: false,
  active: false,
  busy: false,
})

const emit = defineEmits<{
  (e: 'tap'): void
}>()

function onTap() {
  if (props.busy) return
  emit('tap')
}
</script>

<template>
  <div
    class="archive-card"
    :class="{ empty: isEmpty, active, busy }"
    @click="onTap"
  >
    <template v-if="isEmpty">
      <div class="empty-content">
        <span class="plus">+</span>
        <span class="label">存档 #{{ saveId }} · 空位</span>
      </div>
    </template>

    <template v-else>
      <div class="card-header">
        <slot name="header" />
      </div>
      <div class="card-body">
        <slot name="body" />
      </div>
      <div class="card-preview">
        <slot name="preview" />
      </div>
    </template>
  </div>
</template>

<style scoped>
/* ───────── 卡片基底 ───────── */
.archive-card {
  background: linear-gradient(180deg, #f7ebd5 0%, #efdfbf 40%, #ead5aa 100%);
  backdrop-filter: blur(12px);
  border-radius: 8px;
  padding: 16px 18px 14px;
  box-shadow:
    0 4px 20px rgba(150, 100, 80, 0.10),
    0 0 0 1px rgba(255, 255, 255, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.3);
  transition: all 0.25s ease;
  flex-shrink: 0;
  margin-top: 15px;
  cursor: pointer;
  position: relative;
}

.archive-card:active {
  transform: scale(0.97);
  background: rgba(255, 255, 255, 0.9);
}

.archive-card.active {
  border-color: rgba(180, 120, 100, 0.55);
  box-shadow:
    0 6px 24px rgba(150, 100, 80, 0.18),
    0 0 0 2px rgba(196, 149, 111, 0.35);
}

.archive-card.busy {
  opacity: 0.55;
  pointer-events: none;
}

/* ───────── 空位态 ───────── */
.archive-card.empty {
  background: rgb(199 215 251 / 34%);
  backdrop-filter: blur(6px);
  border: 2px dashed rgba(180, 120, 100, 0.25);
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 86px;
  transition: all 0.3s ease;
}

.archive-card.empty:active {
  transform: scale(0.97);
  background: rgba(255, 255, 255, 0.45);
  border-color: rgba(180, 120, 100, 0.4);
}

.empty-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  color: #b58776;
}

.empty-content .plus {
  font-size: 32px;
  font-weight: 300;
  line-height: 1;
  color: #d4a08c;
}

.empty-content .label {
  font-size: 14px;
  font-weight: 500;
  letter-spacing: 1px;
  color: #b58776;
}

/* ───────── 三段结构 ───────── */
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.card-body {
  display: flex;
  align-items: stretch;
  gap: 12px;
  margin-top: 2px;
}

.card-preview {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed rgba(180, 120, 100, 0.15);
  font-size: 13px;
  color: #8b6b5a;
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
</style>