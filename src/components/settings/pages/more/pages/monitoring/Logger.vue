<script setup lang="ts">
import { LogLevel } from '@/typings/enums'
import logger from '@/composables/LogForwarder'

const scrollerRef = ref<HTMLElement | null>(null)
const atBottom = ref(true)
const levelFilter = ref('')
const levels = ['TRACE', 'DEBUG', 'LOG', 'INFO', 'WARN', 'ERROR']
let ro: ResizeObserver | null = null

// ===== 展开 / 溢出检测 =====
const msgEls = ref<HTMLElement[]>([])            // v-for 字符串 ref，Vue 自动收集成数组
const overflowIds = ref<Record<number, boolean>>({})
const expanded = ref<Set<number>>(new Set())

let checkedEls = new WeakSet<HTMLElement>();      // 已测过的 DOM，避免重复读布局
let checkRaf: number | null = null;
// scroll 里只做 rAF 节流，避免高频读写布局
let rafId: number | null = null;

// all=true 表示全量重测（宽度变化时用）
function scheduleCheck(all = false) {
  if (checkRaf !== null) return
  checkRaf = requestAnimationFrame(() => {
    checkRaf = null
    if (all) checkedEls = new WeakSet()
    const list = msgEls.value
    if (!list.length) return
    const next = { ...overflowIds.value }
    let changed = false
    for (const el of list) {
      if (!all && checkedEls.has(el)) continue   // 只测新增的，几千行也只有几个
      checkedEls.add(el)
      const id = Number(el.dataset.id)
      // nowrap 下 \n 不换行，靠 data-multi 兜住“多行但不太宽”的情况
      const v = el.scrollWidth > el.clientWidth + 1 || el.dataset.multi === '1'
      if (next[id] !== v) { next[id] = v; changed = true }
    }
    if (changed) overflowIds.value = next
  })
}

function toggle(id: number) {
  const el = scrollerRef.value
  const prevH = el?.scrollHeight ?? 0
  const wasBottom = atBottom.value

  const next = new Set(expanded.value)
  next.has(id) ? next.delete(id) : next.add(id)
  expanded.value = next

  nextTick(() => {
    if (!el) return
    if (wasBottom) {                              // 原来在底部 → 继续吸底
      el.scrollTop = el.scrollHeight
      atBottom.value = true
    } else {                                      // 否则补偿高度差，视口不跳动
      el.scrollTop += el.scrollHeight - prevH
    }
  })
}

const levelMap: Record<LogLevel, string> = {
  [LogLevel.TRACE]: 'TRACE',
  [LogLevel.DEBUG]: 'DEBUG',
  [LogLevel.LOG]: 'LOG',
  [LogLevel.INFO]: 'INFO',
  [LogLevel.WARN]: 'WARNING',
  [LogLevel.ERROR]: 'ERROR',
}
const classMap: Record<LogLevel, string> = {
  [LogLevel.TRACE]: 'level-trace',
  [LogLevel.DEBUG]: 'level-debug',
  [LogLevel.LOG]: 'level-log',
  [LogLevel.INFO]: 'level-info',
  [LogLevel.WARN]: 'level-warn',
  [LogLevel.ERROR]: 'level-error',
}

const filtered = computed(() =>
  levelFilter.value
    ? logger.logs.value.filter(
      (l) => l.level === (LogLevel as any)[levelFilter.value]
    )
    : logger.logs.value
)

function onScroll() {
  if (rafId !== null) return
  rafId = requestAnimationFrame(() => {
    rafId = null
    const el = scrollerRef.value
    if (!el) return
    atBottom.value = el.scrollHeight - el.scrollTop - el.clientHeight < 40
  })
}

function pinBottom() {
  nextTick(() => {
    const el = scrollerRef.value
    if (!el) return
    el.scrollTop = el.scrollHeight
    atBottom.value = true
  })
}

// 只在末尾项真的变化时吸底
watch(
  //@ts-ignore
  () => [filtered.value.length, filtered.value.at(-1)?.id],
  () => {
    scheduleCheck()               // ← 新增：只测新挂载的行
    if (atBottom.value) pinBottom()
  },
  { immediate: true, flush: 'post' }
)

function filterChange(value: string) {
  levelFilter.value = value
  pinBottom()
}

function clear() {
  logger.clear()
  expanded.value = new Set()
  overflowIds.value = {}
}

onMounted(() => {
  ro = new ResizeObserver(() => scheduleCheck(true))
  if (scrollerRef.value) ro.observe(scrollerRef.value)
});

onBeforeUnmount(() => {
  ro?.disconnect()
  if (rafId !== null) cancelAnimationFrame(rafId)
  if (checkRaf !== null) cancelAnimationFrame(checkRaf)
});
</script>

<template>
  <div class="logger">
    <div class="log-terminal">
      <div class="toolbar">
        <span class="badge">{{ levelFilter || 'ALL' }}</span>
        <Select
          v-model="levelFilter"
          :options="levels"
          class="filter-select"
          @change="filterChange"
        >
          <option value="">ALL</option>
        </Select>
        <span class="count">{{ filtered.length }} / {{ logger.logs.value.length }}</span>
        <button
          class="btn"
          @click="clear"
        >清空</button>
        <button
          v-show="!atBottom"
          class="btn accent"
          @click="pinBottom"
        >
          ↓ 底部
        </button>
      </div>
      <div
        ref="scrollerRef"
        class="scroller"
        @scroll="onScroll"
      >
        <div
          v-for="log in filtered"
          :key="log.id"
          class="log-line"
          :class="[
            classMap[log.level as LogLevel],
            { 'is-expanded': expanded.has(log.id), 'is-expandable': overflowIds[log.id] }
          ]"
        >
          <span class="log-time">[{{ log.time }}]</span>
          <span class="log-level">[{{ levelMap[log.level as LogLevel] }}]</span>

          <span
            ref="msgEls"
            class="log-message"
            :data-id="log.id"
            :data-multi="log.message.includes('\n') ? '1' : '0'"
            @click="overflowIds[log.id] && toggle(log.id)"
          >{{ log.message }}</span>

          <button
            v-if="overflowIds[log.id]"
            class="toggle-btn"
            :class="{ 'is-open': expanded.has(log.id) }"
            :aria-expanded="expanded.has(log.id)"
            :title="expanded.has(log.id) ? '收起' : '展开全部'"
            @click.stop="toggle(log.id)"
          >
            <svg
              viewBox="0 0 16 16"
              width="12"
              height="12"
              aria-hidden="true"
            >
              <path
                d="M6 4l4 4-4 4"
                fill="none"
                stroke="currentColor"
                stroke-width="1.6"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.logger {
  max-width: 1100px;
  max-height: 500px;
  display: flex;
  flex-direction: column;
  width: 100%;
}

.log-terminal {
  position: relative;
  display: flex;
  flex-direction: column;
  width: 99%;
  height: 100%;
  background: #0d1117;
  border-radius: 8px;
  overflow: hidden;
  font-family: 'Fira Code', 'Consolas', monospace;
  font-size: 13px;
  line-height: 1.5;
  color: #c9d1d9;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  background: #161b22;
  border-bottom: 1px solid #30363d;
  flex-shrink: 0;
}

.badge {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 4px;
  background: #30363d;
  color: #8b949e;
}

.filter-select {
  width: 120px;
  background: #0d1117;
  color: #c9d1d9;
  border: 1px solid #30363d;
  border-radius: 4px;
  font-size: 12px;
  padding: 2px 4px;
}

.count {
  font-size: 12px;
  color: #484f58;
  margin-left: auto;
}

.btn {
  background: transparent;
  border: 1px solid #30363d;
  color: #8b949e;
  padding: 2px 8px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}

.btn:hover {
  background: #21262d;
  color: #c9d1d9;
}

.btn.accent {
  color: #58a6ff;
  border-color: #58a6ff;
}

/* 原生滚动：靠 contain 把重排范围限制在容器内 */
.scroller {
  padding: 8px;
  width: 100%;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  overflow-anchor: none;
  contain: layout paint;
  will-change: scroll-position;
  max-height: 500px;
}

/* 固定行高 + 不换行，是终端性能的关键 */
.log-line {
  min-height: 22px;
  line-height: 22px;
  display: flex;
  align-items: flex-start;
  gap: 8px;
  overflow: hidden;
}

.log-line.is-expanded {
  overflow: visible;
  padding-bottom: 4px;
  background: rgba(255, 255, 255, 0.03);
}

/* 折叠：nowrap + ellipsis。不能用 pre —— \n 会真的换行，把固定行高撑成 44px */
.log-message {
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.log-line.is-expandable .log-message {
  cursor: pointer;
}

/* 展开：还原真实换行 */
.is-expanded .log-message {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  overflow: visible;
  text-overflow: unset;
}

.toggle-btn {
  flex-shrink: 0;
  width: 18px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  background: transparent;
  border: none;
  color: #8b949e;
  cursor: pointer;
  transition: transform 0.15s, color 0.15s;
}

.toggle-btn:hover {
  color: #c9d1d9;
}

.toggle-btn.is-open {
  transform: rotate(90deg);
}

.log-time {
  color: #484f58;
  flex-shrink: 0;
  min-width: 90px;
}

.log-level {
  flex-shrink: 0;
  min-width: 34px;
  font-weight: bold;
}

.log-message {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.level-trace .log-level {
  color: #8b949e;
}

.level-debug .log-level {
  color: #58a6ff;
}

.level-log .log-level {
  color: #c9d1d9;
}

.level-info .log-level {
  color: #3fb950;
}

.level-warn .log-level {
  color: #d29922;
}

.level-error .log-level {
  color: #f85149;
}

.level-error {
  background: rgba(248, 81, 73, 0.04);
}

.level-warn {
  background: rgba(210, 153, 34, 0.03);
}


@media screen and (max-width: 768px) {
  .logger {
    max-width: 320px;
  }
}
</style>
