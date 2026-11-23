<script setup lang="ts">
/**
 * 单个贴纸
 */
import { useStickerTransform } from '@/composables/useStickerTransform';
import { LIMITS, clamp, type StickerInstance } from '@/components/views/chat/illustration/configs/illustrationTypes';

const props = defineProps<{
  sticker: StickerInstance;
  canvasSize: { width: number; height: number };
  viewportScale: number;
  selected: boolean;
  editing: boolean;
}>();

const emit = defineEmits<{
  select: [id: string];
  update: [id: string, patch: Partial<StickerInstance>];
  remove: [id: string];
  flip: [id: string];
  behind: [id: string];
  layer: [id: string, direction: -1 | 1];
}>();

// root 即定位层：选中框与操作柄都相对它定位，跟随拖拽
const frameRef = ref<HTMLElement | null>(null);
const visualRef = ref<HTMLElement | null>(null);

const size = computed(() => {
  const base = LIMITS.stickerBasePx;
  const ratio = props.sticker.width && props.sticker.height
    ? clamp(props.sticker.height / Math.max(props.sticker.width, 1), 0.1, 6)
    : 1;
  return { width: base, height: base * ratio };
});

/** frame 的基准 transform：容器尺寸变化时由父层 ResizeObserver 驱动，不逐帧读 DOM */
const frameTransform = computed(() => {
  const { width, height } = props.canvasSize;
  if (!width || !height) return 'translate3d(-9999px, -9999px, 0)';
  const px = props.sticker.x * width - size.value.width / 2;
  const py = props.sticker.y * height - size.value.height / 2;
  return `translate3d(${px.toFixed(2)}px, ${py.toFixed(2)}px, 0)`;
});

const visualTransform = computed(() => {
  const s = props.sticker.scale;
  return `scale(${props.sticker.flipX ? -s : s}, ${s}) rotate(${props.sticker.rotation}deg)`;
});

const rootStyle = computed(() => ({
  width: `${size.value.width}px`,
  height: `${size.value.height}px`,
  transform: frameTransform.value,
  zIndex: props.sticker.z,
  opacity: props.sticker.opacity,
}));

const { onPointerDown, onWheel, onKeydown, isInteracting } = useStickerTransform({
  getCanvasSize: () => props.canvasSize,
  frame: frameRef,
  visual: visualRef,
  getSticker: () => props.sticker,
  getSize: () => size.value,
  commit: (patch) => emit('update', props.sticker.id, patch),
  getScale: () => props.viewportScale,
  disabled: () => !props.editing,
});

// ---------- 可见操作柄：缩放 / 旋转 ----------
let handleCleanup: (() => void) | null = null;

function onHandleDown(event: PointerEvent, kind: 'scale' | 'rotate') {
  if (!props.editing || !props.selected) return;
  event.stopPropagation();
  event.preventDefault();
  handleCleanup?.();
  const el = visualRef.value;
  if (!el) return;
  const startX = event.clientX;
  const startY = event.clientY;
  const startScale = props.sticker.scale;
  const startRotation = props.sticker.rotation;
  const rect = el.getBoundingClientRect();
  const cx = rect.left + rect.width / 2;
  const cy = rect.top + rect.height / 2;
  const startAngle = (Math.atan2(startY - cy, startX - cx) * 180) / Math.PI;
  let draft: Partial<StickerInstance> = {};
  let raf = 0;
  let nextTransform = '';

  const apply = () => {
    raf = 0;
    el.style.transform = nextTransform;
  };
  const move = (ev: PointerEvent) => {
    if (kind === 'scale') {
      const delta = (ev.clientX - startX) + (ev.clientY - startY);
      draft = { scale: clamp(startScale * (1 + delta / 160), LIMITS.stickerScaleMin, LIMITS.stickerScaleMax) };
    } else {
      const angle = (Math.atan2(ev.clientY - cy, ev.clientX - cx) * 180) / Math.PI;
      let rotation = startRotation + (angle - startAngle);
      while (rotation > 180) rotation -= 360;
      while (rotation < -180) rotation += 360;
      draft = { rotation: clamp(rotation, LIMITS.rotationMin, LIMITS.rotationMax) };
    }
    const s = draft.scale ?? startScale;
    const r = draft.rotation ?? startRotation;
    nextTransform = `scale(${props.sticker.flipX ? -s : s}, ${s}) rotate(${r}deg)`;
    if (!raf) raf = requestAnimationFrame(apply);
  };
  const up = () => {
    if (raf) cancelAnimationFrame(raf);
    apply();
    if (Object.keys(draft).length) emit('update', props.sticker.id, draft);
    cleanup();
  };
  const onHandleBlur = () => up();
  const cleanup = () => {
    window.removeEventListener('pointermove', move);
    window.removeEventListener('pointerup', up);
    window.removeEventListener('pointercancel', up);
    window.removeEventListener('blur', onHandleBlur);
    handleCleanup = null;
  };
  handleCleanup = cleanup;
  window.addEventListener('pointermove', move, { passive: true });
  window.addEventListener('pointerup', up);
  window.addEventListener('pointercancel', up);
  window.addEventListener('blur', onHandleBlur);
}

onScopeDispose(() => handleCleanup?.());

function onRootPointerDown(event: PointerEvent) {
  if (!props.editing) return;
  // 选中放在 pointerdown 里：部分浏览器在 pointerdown 上 preventDefault 后不再派发 click
  event.stopPropagation();
  emit('select', props.sticker.id);
  onPointerDown(event);
}

function moveLayerUp() {
  emit('layer', props.sticker.id, 1);
}

function moveLayerDown() {
  emit('layer', props.sticker.id, -1);
}

/** 操作柄用具名入口，避免模板字面量被推断成宽泛的 string / number */
function onRotateDown(event: PointerEvent) {
  onHandleDown(event, 'rotate');
}

function onScaleDown(event: PointerEvent) {
  onHandleDown(event, 'scale');
}

/** 工具区容器只做事件拦截，不执行动作 */
const noop = () => {};

function onRootKeydown(event: KeyboardEvent) {
  if (!props.editing) return;
  if (event.key === 'Delete' || event.key === 'Backspace') {
    event.preventDefault();
    emit('remove', props.sticker.id);
    return;
  }
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault();
    emit('select', props.sticker.id);
    return;
  }
  onKeydown(event);
}
</script>

<template>
  <div
    ref="frameRef"
    class="sticker-frame"
    :class="{ 'is-selected': selected, 'is-editing': editing, 'is-interacting': isInteracting }"
    :style="rootStyle"
    :tabindex="editing ? 0 : -1"
    role="button"
    :aria-label="`贴纸 ${sticker.label}${selected ? '（已选中）' : ''}`"
    :aria-pressed="selected"
    @pointerdown="onRootPointerDown"
    @wheel="onWheel"
    @keydown="onRootKeydown"
  >
    <div
      ref="visualRef"
      class="sticker-visual"
      :style="{ transform: visualTransform }"
    >
      <AssetImage
        :src="sticker.src"
        :alt="sticker.label"
      />
    </div>

    <template v-if="editing && selected">
      <span class="sticker-outline"></span>
      <button
        class="sticker-handle handle-rotate"
        type="button"
        data-handle="rotate"
        aria-label="旋转贴纸"
        @pointerdown="onRotateDown"
      ><Icon
        icon="rotate"
        :size="12"
      /></button>
      <button
        class="sticker-handle handle-scale"
        type="button"
        data-handle="scale"
        aria-label="缩放贴纸"
        @pointerdown="onScaleDown"
      ><Icon
        icon="plus"
        :size="12"
      /></button>

      <!-- base Button 的 click 是自定义 emit 且不携带事件对象，这里不能用 .stop 修饰符；
           工具区用原生容器统一拦截指针，避免冒泡到画布误清空选中 -->
      <div
        class="sticker-tools"
        @pointerdown.stop="noop"
        @click.stop="noop"
      >
        <Button
          type="nav"
          aria-label="水平翻转"
          @click="emit('flip', sticker.id)"
        ><Icon
          icon="flip"
          :size="14"
        /></Button>
        <Button
          type="nav"
          aria-label="置于立绘之后"
          @click="emit('behind', sticker.id)"
        ><Icon
          icon="layer"
          :size="14"
        /></Button>
        <Button
          type="nav"
          aria-label="上移一层"
          @click="moveLayerUp"
        >↑</Button>
        <Button
          type="nav"
          aria-label="下移一层"
          @click="moveLayerDown"
        >↓</Button>
        <Button
          type="nav"
          aria-label="删除贴纸"
          @click="emit('remove', sticker.id)"
        ><Icon
          icon="delete"
          :size="14"
        /></Button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.sticker-frame {
  position: absolute;
  left: 0;
  top: 0;
  transform-origin: center;
  will-change: auto;
}

.sticker-frame.is-editing {
  cursor: grab;
}

.sticker-frame.is-interacting {
  cursor: grabbing;
  will-change: transform;
}

.sticker-frame:focus-visible {
  outline: 2px solid var(--primary-color);
  outline-offset: 4px;
  border-radius: 4px;
}

.sticker-visual {
  width: 100%;
  height: 100%;
  transform-origin: center center;
}

.sticker-outline {
  position: absolute;
  inset: -6px;
  border: 1px dashed var(--primary-color);
  border-radius: 6px;
  box-shadow: 0 0 0 1px rgba(0, 14, 39, 0.4);
  pointer-events: none;
}

.sticker-handle {
  position: absolute;
  width: 24px;
  height: 24px;
  padding: 0;
  display: grid;
  place-items: center;
  border-radius: 999px;
  border: 1px solid var(--primary-color);
  background: rgba(0, 14, 39, 0.88);
  color: #fff;
  cursor: pointer;
  z-index: 2;
  /* 视觉 24px，热区靠透明外扩保证可点 */
  box-shadow: 0 0 0 10px transparent;
}

.handle-rotate {
  right: -12px;
  top: -12px;
  cursor: grab;
}

.handle-scale {
  right: -12px;
  bottom: -12px;
  cursor: nwse-resize;
}

.sticker-tools {
  position: absolute;
  left: 50%;
  top: -44px;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 2px 4px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.28);
  background: rgba(0, 14, 39, 0.86);
  backdrop-filter: blur(4px);
  white-space: nowrap;
  z-index: 3;
}

.sticker-tools :deep(button) {
  min-width: 28px;
  min-height: 28px;
  padding: 2px 6px;
  font-size: 12px;
}

@media (prefers-reduced-motion: reduce) {
  .sticker-frame,
  .sticker-visual {
    transition: none !important;
  }
}
</style>
