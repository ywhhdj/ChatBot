<script setup lang="ts">
import { CONFIG } from '@/config';
import { useSaveSlots } from '@/stores/user'
import {
  SECTIONS, INDEX_SECTIONS, SECTION_LABELS,
  type SectionName, type SlotInfo,
} from '@/stores/user'

const emit = defineEmits<{
  (e: 'switch', slot: SlotInfo): void
  (e: 'saved', slot: SlotInfo): void
  (e: 'deleted', id: string): void
  (e: 'create', slot: SlotInfo): void
}>()

const {
  slots, currentId, loading, busyId, error,
  create, remove, toggle, save, load,
} = useSaveSlots()

const showCreate = ref(false)
const newName = ref('')
const newId = ref('')
const confirmingId = ref<string | null>(null)
const toast = ref('')

/** 空位卡数量：始终让列表末尾保持一个空位，视觉上像"格子" */
const MIN_SLOTS = CONFIG.save.MIN_SLOTS
const emptyCount = computed(() => Math.max(0, MIN_SLOTS - slots.value.length))

function notify(msg: string) {
  toast.value = msg
  setTimeout(() => (toast.value = ''), 2000)
}

async function onSubmitCreate() {
  const name = newName.value.trim()
  if (!name) return
  const info = await create(name, newId.value)
  if (info) {
    emit('create', info)
    notify(`已创建「${info.name}」`)
    showCreate.value = false
    newName.value = ''
    newId.value = ''
  }
}

/** 点整张卡 = 切换；点具体按钮由按钮自己 stopPropagation */
async function onCardTap(slot: SlotInfo) {
  if (slot.id === currentId.value) return
  await toggle(slot.id)
  emit('switch', slot)
  notify(`已切换到「${slot.name}」`)
}

async function onSwitch(e: Event, slot: SlotInfo) {
  e.stopPropagation()
  await onCardTap(slot)
}

async function onSave(e: Event, slot: SlotInfo) {
  e.stopPropagation()
  await save(slot.id)
  emit('saved', slot)
  notify(`「${slot.name}」已保存`)
}

async function onLoad(e: Event, slot: SlotInfo) {
  e.stopPropagation()
  await load(slot.id)
  notify(`「${slot.name}」已加载`)
}

async function onDelete(e: Event, id: string) {
  e.stopPropagation()
  if (confirmingId.value !== id) {
    confirmingId.value = id
    setTimeout(() => {
      if (confirmingId.value === id) confirmingId.value = null
    }, 3000)
    return
  }
  if (slots.value.length === 1) {
    notify('不能删除最后一个存档')
    return
  }
  confirmingId.value = null
  await remove(id)
  emit('deleted', id)
  notify('存档已删除')
}

function fmtTime(t: string): string {
  if (!t) return '—'
  try {
    const d = new Date(t)
    return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  } catch {
    return t
  }
}

function sectionKind(name: string): 'index' | 'content' | 'mixed' {
  if (name === 'chat_history') return 'mixed'
  return (INDEX_SECTIONS as string[]).includes(name) ? 'index' : 'content'
}
</script>

<template>
  <header class="panel-head">
    <h3>存档</h3>
    <button
      class="btn btn-primary"
      @click="showCreate = true"
    >
      <span class="btn-plus">+</span> 新建
    </button>
  </header>
  <div class="save-panel">

    <div
      v-if="loading && !slots.length"
      class="hint"
    >加载中…</div>

    <div class="slot-grid">
      <!-- 已有存档 -->
      <SaveCard
        v-for="(slot, idx) in slots"
        :key="slot.id"
        :save-id="String(idx + 1).padStart(2, '0')"
        :active="slot.id === currentId"
        :busy="busyId === slot.id"
        @tap="onCardTap(slot)"
      >
        <template #header>
          <div class="title-wrap">
            <span class="name">{{ slot.name || slot.id }}</span>
            <div class="meta">
              <span class="meta-item">
                <i class="dot create" />{{ fmtTime(slot.meta.create_time) }}
              </span>
              <span class="meta-item">
                <i class="dot update" />{{ fmtTime(slot.meta.update_time) }}
              </span>
            </div>
            <span
              v-if="slot.id === currentId"
              class="badge"
            >当前</span>
          </div>
          <div class="actions">
            <button
              class="mini"
              :disabled="busyId === slot.id"
              @click="onLoad($event, slot)"
            >载入</button>
            <button
              class="mini"
              :disabled="busyId === slot.id"
              @click="onSave($event, slot)"
            >保存</button>
            <button
              class="mini danger"
              :disabled="busyId === slot.id"
              @click="onDelete($event, slot.id)"
            >{{ confirmingId === slot.id ? '确认?' : '删除' }}</button>
          </div>
        </template>

        <template #body>
          <!-- <div class="meta">
            <span class="meta-item">
              <i class="dot create" />{{ fmtTime(slot.meta.create_time) }}
            </span>
            <span class="meta-item">
              <i class="dot update" />{{ fmtTime(slot.meta.update_time) }}
            </span>
          </div> -->
        </template>

        <template #preview>
          <div class="chips">
            <span
              v-for="name in SECTIONS"
              :key="name"
              class="chip"
              :class="[
                `chip-${sectionKind(name)}`,
                { on: slot.sections.includes(name) },
              ]"
            >{{ SECTION_LABELS[name as SectionName] }}</span>
          </div>
        </template>
      </SaveCard>

      <!-- 空位 -->
      <SaveCard
        v-for="n in emptyCount"
        :key="`empty-${n}`"
        :save-id="String(slots.length + n).padStart(2, '0')"
        is-empty
        @tap="showCreate = true"
      />
    </div>

    <!-- 新建对话框 -->
    <div
      v-if="showCreate"
      class="modal-mask"
      @click.self="showCreate = false"
    >
      <div class="modal">
        <h4>新建存档</h4>
        <label>
          名称
          <input
            v-model="newName"
            placeholder="例如：一周目"
            @keyup.enter="onSubmitCreate"
          />
        </label>
        <label>
          槽位 ID（可选）
          <input
            v-model="newId"
            placeholder="留空自动生成"
          />
        </label>
        <div class="modal-actions">
          <button
            class="btn"
            @click="showCreate = false"
          >取消</button>
          <button
            class="btn btn-primary"
            :disabled="!newName.trim()"
            @click="onSubmitCreate"
          >创建</button>
        </div>
      </div>
    </div>

    <transition name="fade">
      <div
        v-if="toast"
        class="toast"
      >{{ toast }}</div>
    </transition>
  </div>
</template>

<style scoped>
.save-panel {
  --ink: #6b4f42;
  --ink-soft: #8b6b5a;
  --ink-faint: #b58776;
  --line: rgba(180, 120, 100, 0.18);
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 14px;
  color: var(--ink);
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 2px;
}

.panel-head h3 {
  margin: 0;
  font-size: 16px;
  color: var(--ink);
  letter-spacing: 1px;
}

.slot-grid {
  display: flex;
  flex-direction: column;
}

.hint {
  padding: 24px;
  text-align: center;
  color: var(--ink-faint);
}

/* ───────── 头部插槽内容 ───────── */
.title-wrap {
  display: flex;
  align-items: baseline;
  gap: 8px;
  min-width: 0;
}

.title-wrap .name {
  font-weight: 600;
  color: #5c4033;
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.badge {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 6px;
  background: rgba(196, 149, 111, 0.28);
  color: #8b5a3c;
  font-weight: 500;
}

.actions {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}

/* ───────── 主体插槽内容 ───────── */
.meta {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: var(--ink-soft);
  flex-wrap: wrap;
}

.meta-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  display: inline-block;
}

.dot.create {
  background: #d4a08c;
}

.dot.update {
  background: #a8b78c;
}

/* ───────── 预览插槽内容 ───────── */
.chips {
  display: flex;
  gap: 5px;
  flex-wrap: wrap;
}

.chip {
  font-size: 11px;
  padding: 2px 7px;
  border-radius: 999px;
  border: 1px solid var(--line);
  color: #b8a094;
  background: rgba(255, 255, 255, 0.35);
  user-select: none;
}

.chip.on {
  color: #5c4033;
  font-weight: 500;
}

.chip-index.on {
  background: rgba(230, 190, 120, 0.35);
  border-color: rgba(200, 150, 80, 0.4);
}

.chip-mixed.on {
  background: rgba(150, 190, 220, 0.35);
  border-color: rgba(120, 160, 200, 0.4);
}

.chip-content.on {
  background: rgba(160, 200, 150, 0.35);
  border-color: rgba(120, 170, 110, 0.4);
}

/* ───────── 按钮 ───────── */
.btn {
  border: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.6);
  color: var(--ink);
  padding: 5px 12px;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  font-family: inherit;
  transition: all 0.15s;
}

.btn:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.95);
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-primary {
  background: linear-gradient(135deg, #c4956f, #b58776);
  color: #fff;
  border-color: transparent;
  box-shadow: 0 2px 8px rgba(180, 120, 100, 0.25);
}

.btn-primary:hover:not(:disabled) {
  background: linear-gradient(135deg, #b8875f, #a57663);
}

.btn-plus {
  font-size: 15px;
  line-height: 1;
  margin-right: 2px;
  vertical-align: -1px;
}

.mini {
  border: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.55);
  color: var(--ink-soft);
  padding: 3px 8px;
  border-radius: 5px;
  font-size: 11px;
  cursor: pointer;
  font-family: inherit;
  transition: all 0.15s;
}

.mini:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.95);
  color: var(--ink);
}

.mini:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.mini.danger {
  color: #b85545;
  border-color: rgba(184, 85, 69, 0.28);
}

.mini.danger:hover:not(:disabled) {
  background: rgba(255, 240, 235, 0.9);
}

/* ───────── 错误 / 弹窗 / toast ───────── */

.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(90, 60, 45, 0.28);
  backdrop-filter: blur(2px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 50;
}

.modal {
  background: linear-gradient(180deg, #fbf4e6, #f2e5cd);
  border-radius: 12px;
  padding: 20px;
  width: 320px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  box-shadow: 0 12px 40px rgba(120, 80, 60, 0.25);
  border: 1px solid rgba(255, 255, 255, 0.7);
}

.modal h4 {
  margin: 0;
  font-size: 15px;
  color: #5c4033;
}

.modal label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: var(--ink-soft);
}

.modal input {
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 6px 10px;
  font-size: 14px;
  color: #5c4033;
  font-family: inherit;
  background: rgba(255, 255, 255, 0.7);
  outline: none;
}

.modal input:focus {
  border-color: rgba(196, 149, 111, 0.6);
  background: #fff;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.toast {
  position: fixed;
  left: 50%;
  bottom: 32px;
  transform: translateX(-50%);
  background: rgba(92, 64, 51, 0.92);
  color: #fff;
  padding: 8px 14px;
  border-radius: 8px;
  font-size: 13px;
  z-index: 60;
  box-shadow: 0 6px 20px rgba(90, 60, 45, 0.3);
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>