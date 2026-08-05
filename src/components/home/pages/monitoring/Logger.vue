<script setup lang="ts">
import { ref, inject, computed, nextTick, watch, onBeforeUnmount } from 'vue'
import { LogLevel } from '@/typings/enums'
import type { LogRecord } from '@/api/logger'

const logs = inject<LogRecord[]>('loggerLogs')!
const virtualListRef = ref()
const atBottom = ref(true)

// 格式化时间（只显示时分秒毫秒）
function formatTime(iso: string) {
  const d = new Date(iso)
  return d.toLocaleTimeString('zh-CN', { hour12: false })
}

// 级别标签
function levelLabel(level: LogLevel): string {
  const map: Record<LogLevel, string> = {
    [LogLevel.TRACE]: 'TRACE',
    [LogLevel.DEBUG]: 'DEBUG',
    [LogLevel.LOG]: 'LOG',
    [LogLevel.INFO]: 'INFO',
    [LogLevel.WARN]: 'WARNING',
    [LogLevel.ERROR]: 'ERROR',
  }
  return map[level] || '???'
}

// 级别对应 CSS class
function getLevelClass(level: LogLevel): string {
  const classMap: Record<LogLevel, string> = {
    [LogLevel.TRACE]: 'level-trace',
    [LogLevel.DEBUG]: 'level-debug',
    [LogLevel.LOG]: 'level-log',
    [LogLevel.INFO]: 'level-info',
    [LogLevel.WARN]: 'level-warn',
    [LogLevel.ERROR]: 'level-error',
  }
  return classMap[level] || ''
}

// 级别列表
const levels = ['TRACE', 'DEBUG', 'LOG', 'INFO', 'WARN', 'ERROR']

// 筛选
const levelFilter = ref('')
const filtered = computed(() =>
  levelFilter.value
    ? logs.filter(l => l.level === (LogLevel as any)[levelFilter.value])
    : logs
)

function onVirtualScroll(payload: { atBottom: boolean }) {
  atBottom.value = payload.atBottom
}

function filterChange(value: string) {
  levelFilter.value = value
}

function scrollToBottom() {
  virtualListRef.value?.scrollToBottom()
}

watch(filtered, () => {
  if (atBottom.value) {
    scrollToBottom()
  }
})



function clear() {
  logs.splice(0, logs.length)
}
</script>

<template>
  <div class="logger">
    <div
      class="log-terminal"
      ref="terminalRef"
    >
      <!-- 工具栏 -->
      <div class="toolbar">
        <span class="badge">{{ levelFilter || 'ALL' }}</span>
        <Select
          :options="levels"
          @change="filterChange"
          :value="levelFilter"
          class="filter-select"
        >
          <option value="">ALL</option>
        </Select>
        <span class="count">{{ filtered.length }} / {{ logs.length }}</span>
        <button
          class="btn"
          @click="clear"
        >清空</button>
        <button
          v-if="!atBottom"
          class="btn accent"
          @click="scrollToBottom"
        >↓ 底部</button>
      </div>

      <!-- 虚拟滚动容器 -->
      <RecycleScroller
        ref="virtualListRef"
        :items="filtered"
        :item-height="22"
        :get-key="(item: LogRecord) => item.timestamp"
        @scroll="onVirtualScroll"
      >
        <template #item="{ item }">
          <div
            class="log-line"
            :class="getLevelClass(item.level)"
          >
            <span class="log-time">[{{ formatTime(item.timestamp) }}]</span>
            <span class="log-level">[{{ levelLabel(item.level) }}]</span>
            <span class="log-message">{{ item.message }}</span>
          </div>
        </template>
      </RecycleScroller>
    </div>
  </div>

</template>

<style scoped>
.logger {
  display: flex;
  flex-direction: column;
  height: 100%;
  width: 100%;
}

.log-terminal {
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

.scroller {
  flex: 1;
  overflow-y: auto;
  padding: 4px 0;
}

.log-line {
  display: flex;
  align-items: flex-start;
  /* 顶部对齐 */
  gap: 8px;
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
  word-break: break-word;
  white-space: pre-wrap;
}

/* 级别颜色 */
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

/* 整行背景微色（可选） */
.level-error {
  background: rgba(248, 81, 73, 0.04);
}

.level-warn {
  background: rgba(210, 153, 34, 0.03);
}
</style>