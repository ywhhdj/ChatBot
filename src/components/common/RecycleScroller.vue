<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'

const props = withDefaults(defineProps<{
  minHeight?: number
  items: any[]
  itemHeight?: number
  overscan?: number
  getKey?: (item: any) => string | number | undefined
}>(), {
  minHeight: 150,
  itemHeight: 22,
  overscan: 30,
})

const emit = defineEmits<{
  (e: 'scroll', payload: { scrollTop: number; atBottom: boolean }): void
}>()

const viewport = ref<HTMLDivElement>()
const scrollTop = ref(0)

const totalHeight = computed(() => props.items.length * props.itemHeight)

const visibleStart = computed(() => {
  const s = Math.floor(scrollTop.value / props.itemHeight)
  return Math.max(0, s - props.overscan)
})

const visibleEnd = computed(() => {
  if (!viewport.value) return 0
  const containerHeight = viewport.value.clientHeight
  const visibleCount = Math.ceil(containerHeight / props.itemHeight)
  return Math.min(props.items.length, Math.floor(scrollTop.value / props.itemHeight) + visibleCount + props.overscan)
})

const visibleItems = computed(() =>
  props.items.slice(visibleStart.value, visibleEnd.value)
)

const offset = computed(() => visibleStart.value * props.itemHeight)

function onScroll() {
  const el = viewport.value
  if (!el) return
  scrollTop.value = el.scrollTop
  const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 2
  emit('scroll', { scrollTop: scrollTop.value, atBottom })
}

/** 外部调用滚动到底部 */
function scrollToBottom() {
  nextTick(() => {
    const el = viewport.value
    if (!el) return
    el.scrollTop = el.scrollHeight
  })
}

defineExpose({ scrollToBottom, viewport })
</script>

<template>
  <div
    ref="viewport"
    class="virtual-list-viewport"
    @scroll="onScroll"
  >
    <div :style="{ minHeight: minHeight + 'px', height: totalHeight + 'px', position: 'relative' }">
      <div :style="{ transform: `translateY(${offset}px)` }">
        <div
          v-for="(item, idx) in visibleItems"
          :key="getKey ? getKey(item) : idx"
          class="virtual-list-item"
          :style="{ height: itemHeight + 'px' }"
        >
          <slot
            name="item"
            :item="item"
            :index="visibleStart + idx"
          />
        </div>
      </div>
    </div>
  </div>
</template>


<style scoped>
.virtual-list-viewport {
  height: 100%;
  flex: 1;
  overflow-y: auto;
  width: 100%;
  /* 确保视口占满宽度 */
  box-sizing: border-box;
}

.virtual-list-item {
  contain: layout style;
  height: v-bind(itemHeight + 'px');
  width: 100%;
  /* 关键：限制单条宽度为100% */
  box-sizing: border-box;
  padding: 0 12px;
  /* 增加左右内边距，防止文字贴边 */
  overflow: hidden;
  /* 配合 flex 布局 */
  display: flex;
  /* 关键：让内部 slot 内容垂直排布 */
  align-items: center;
  /* 垂直居中 */
}

:deep(.virtual-scroll-wrapper) {
  min-height: v-bind(minHeight + 'px');
  /* 使用 JS 传入的最小高度 */
  height: v-bind(totalHeight + 'px');
  position: relative;
  width: 100%;
}

/* 偏移层：负责 translateY 移动 */
:deep(.virtual-scroll-offset) {
  transform: translateY(v-bind(offset + 'px'));
  width: 100%;
  height: 100%;
  flex: 1;
}
</style>