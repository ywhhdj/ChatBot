<script setup lang="ts" generic="T extends Record<string, any>">
import {
  DynamicScroller,
  RecycleScroller,
  DynamicScrollerItem,
} from 'vue-virtual-scroller'
import 'vue-virtual-scroller/dist/vue-virtual-scroller.css'

/**
 * 通用虚拟滚动列表
 * measure = false → RecycleScroller（固定行高，零测量，性能最好）
 * measure = true  → DynamicScroller（动态测高，行高不确定时用）
 *
 * ⚠️ keyField 必须唯一且稳定，重复/缺失会导致位置错乱与反复重测
 */
const props = withDefaults(
  defineProps<{
    items: any[]
    /** 是否动态测量行高 */
    measure?: boolean
    /** measure=false 时为固定行高；measure=true 时为最小行高（估算值，越接近真实值跳动越小） */
    itemSize?: number
    /** 唯一键字段 */
    keyField?: string
    /** measure=true 时生效：内容变化后需要重新测高的依赖（字段数组或取值函数） */
    sizeDependencies?: string[] | ((item: any) => unknown[])
    /** bump 这个值可强制全量重新测量（字体加载完成、主题切换等场景） */
    measureVersion?: number
    /** 上下缓冲像素 */
    buffer?: number
    /** 自动吸底（日志 / 聊天场景） */
    sticky?: boolean
    /** 距底多少 px 内算“在底部”，太小会因高度估算误差误判 */
    stickyThreshold?: number
    /** 容器高度 */
    height?: string
  }>(),
  {
    measure: false,
    itemSize: 30,
    keyField: 'id',
    buffer: 200,
    measureVersion: 0,
    sticky: false,
    stickyThreshold: 48,
    height: '100%',
  }
)

const emit = defineEmits<{
  scroll: [ev: Event]
  'at-bottom-change': [v: boolean]
  'update:startIndex': [v: number]
  'update:endIndex': [v: number]
}>()

const root = ref<any>(null)
const atBottom = ref(true)
let rafId: number | null = null

//根据选项，动态导入组件
const Comp: Component = computed(() => (props.measure ? DynamicScroller : RecycleScroller));

const coreProps = computed(() =>
  props.measure
    ? { minItemSize: props.itemSize, buffer: props.buffer }
    : { itemSize: props.itemSize, buffer: props.buffer }
)

function resolveDeps(item: any): unknown[] {
  const base = !props.sizeDependencies
    ? []
    : typeof props.sizeDependencies === 'function'
      ? props.sizeDependencies(item)
      : props.sizeDependencies.map((k) => item?.[k])
  return [...base, props.measureVersion]
}

function getEl(): HTMLElement | null {
  const c = root.value
  if (!c) return null
  return (c.$el ?? c) as HTMLElement
}

function isNearBottom(): boolean {
  const e = getEl()
  if (!e) return false
  return e.scrollHeight - e.scrollTop - e.clientHeight < props.stickyThreshold
}

// scroll 事件里做 rAF 节流：一帧最多读一次布局，避免 layout thrashing
function onScroll(ev: Event) {
  emit('scroll', ev)
  if (!props.sticky || rafId !== null) return
  rafId = requestAnimationFrame(() => {
    rafId = null
    const bottom = isNearBottom()
    if (bottom !== atBottom.value) emit('at-bottom-change', bottom)
    atBottom.value = bottom
  })
}

// 直接设 scrollTop，比 scrollToItem 便宜一个数量级
function pinBottom(force = false) {
  nextTick(() => {
    if (!force && !props.sticky) return
    const e = getEl()
    if (!e) return
    e.scrollTop = e.scrollHeight
    // 测量模式下总高会在 measure 之后变化，下一帧再校正一次
    if (props.measure) {
      requestAnimationFrame(() => {
        if (!force && !atBottom.value) return
        e.scrollTop = e.scrollHeight
        atBottom.value = true
      })
    } else {
      atBottom.value = true
    }
  })
}

function scrollToItem(index: number) {
  root.value?.scrollToItem?.(index)
}

function scrollToTop() {
  const e = getEl()
  if (e) e.scrollTop = 0
  atBottom.value = props.items.length === 0
}

// 只在“末尾那一项真的变了”时才吸底，避免 filtered 引用变化导致无意义滚动
watch(
  () => [
    props.items.length,
    props.items.length
      ? (props.items[props.items.length - 1] as any)?.[props.keyField]
      : null,
  ],
  () => {
    if (props.sticky && atBottom.value) pinBottom()
  },
  { immediate: true, flush: 'post' }
)

onBeforeUnmount(() => {
  if (rafId !== null) cancelAnimationFrame(rafId)
})

defineExpose({
  scrollToBottom: () => pinBottom(true),
  scrollToItem,
  scrollToTop,
  atBottom,
  getEl,
})
</script>

<template>
  <div
    v-if="!items.length"
    class="vlist vlist-empty"
    :style="{ height }"
  >
    <slot name="empty" />
  </div>

  <component
    v-else
    :is="Comp"
    ref="root"
    class="vlist"
    :style="{ height }"
    :items="items"
    :key-field="keyField"
    v-bind="coreProps"
    @scroll="onScroll"
    @update:start-index="(v: number) => emit('update:startIndex', v)"
    @update:end-index="(v: number) => emit('update:endIndex', v)"
  >
    <template #default="slotProps: {
      item: T;
      index: number;
      active: boolean
    }">
      <!-- 测量模式：每一项需要 DynamicScrollerItem 包裹并上报真实高度 -->
      <DynamicScrollerItem
        v-if="measure"
        :item="slotProps.item"
        :active="slotProps.active"
        :size-dependencies="resolveDeps(slotProps.item)"
      >
        <slot v-bind="slotProps" />
      </DynamicScrollerItem>

      <!-- 固定行高模式：直接渲染，不做任何测量 -->
      <slot
        v-else
        v-bind="slotProps"
      />
    </template>
  </component>
</template>

<style scoped>
.vlist {
  width: 100%;
  /* 关掉滚动锚定，否则会和自动吸底互相打架 */
  overflow-anchor: none;
}

.vlist-empty {
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
