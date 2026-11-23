/**
 * 通用「可变换元素」交互
 *
 * 单指拖拽 / 双指捏合缩放 + 旋转 / 滚轮缩放 / 键盘微调。
 * 与业务无关：任何「绝对定位 + 缩放 + 旋转」的元素都能复用。
 */
import { onScopeDispose, shallowRef, type Ref } from 'vue';
import { LIMITS, clamp, type StickerInstance } from '@/components/views/chat/illustration/configs/illustrationTypes';

export interface UseStickerTransformOptions {
  /** 画布的未变换尺寸（由父层 ResizeObserver 提供，不读 DOM、不触发强制布局） */
  getCanvasSize: () => { width: number; height: number };
  /** 定位层（写 translate3d） */
  frame: Ref<HTMLElement | null>;
  /** 变换层（写 scale / rotate） */
  visual: Ref<HTMLElement | null>;
  /** 当前元素（交互开始时会快照，避免中途被替换） */
  getSticker: () => StickerInstance | null;
  /** 定位层的固定显示尺寸（不含变换） */
  getSize: () => { width: number; height: number };
  /** 松手/滚轮/键盘后一次性提交 */
  commit: (patch: Partial<StickerInstance>) => void;
  /** 外层整体缩放档：把视口像素位移还原成未变换坐标，避免放大后拖拽变慢 */
  getScale?: () => number;
  disabled?: () => boolean;
}

interface PointerPoint {
  x: number;
  y: number;
}

function normalizeRotation(deg: number): number {
  let value = deg;
  while (value > 180) value -= 360;
  while (value < -180) value += 360;
  return clamp(value, LIMITS.rotationMin, LIMITS.rotationMax);
}

export function useStickerTransform(options: UseStickerTransformOptions) {
  const { getCanvasSize, frame, visual, getSticker, getSize, commit, getScale, disabled } = options;
  const isInteracting = shallowRef(false);

  const pointers = new Map<number, PointerPoint>();
  let base: StickerInstance | null = null;
  let mode: 'idle' | 'move' | 'gesture' = 'idle';
  let startX = 0;
  let startY = 0;
  let startDist = 0;
  let startAngle = 0;
  let draft: Partial<StickerInstance> = {};
  let rafId = 0;
  let pendingFrame = '';
  let pendingVisual = '';
  let bound = false;

  const isDisabled = () => (typeof disabled === 'function' ? disabled() : false);

  const applyFrame = () => {
    rafId = 0;
    if (pendingFrame && frame.value) frame.value.style.transform = pendingFrame;
    if (pendingVisual && visual.value) visual.value.style.transform = pendingVisual;
  };

  const scheduleApply = () => {
    if (rafId) return;
    rafId = requestAnimationFrame(applyFrame);
  };

  const writeFrame = (x: number, y: number) => {
    const {
      width: w,
      height: h
    } = getCanvasSize();
    if (!w || !h) return;
    const size = getSize();
    pendingFrame = `translate3d(${(x * w - size.width / 2).toFixed(2)}px, ${(y * h - size.height / 2).toFixed(2)}px, 0)`;
    scheduleApply();
  };

  const writeVisual = (scale: number, rotation: number, flipX: boolean) => {
    pendingVisual = `scale(${flipX ? -scale : scale}, ${scale}) rotate(${rotation}deg)`;
    scheduleApply();
  };

  /** 窗口失焦时按「松手」处理，避免指针永远卡在按下态 */
  const onBlur = () => finish();

  const detach = () => {
    if (!bound) return;
    bound = false;
    window.removeEventListener('pointermove', onPointerMove);
    window.removeEventListener('pointerup', onPointerUp);
    window.removeEventListener('pointercancel', onPointerUp);
    window.removeEventListener('blur', onBlur);
  };

  const finish = () => {
    if (rafId) {
      cancelAnimationFrame(rafId);
      rafId = 0;
    }
    applyFrame();
    if (Object.keys(draft).length) commit(draft);
    draft = {};
    pointers.clear();
    base = null;
    mode = 'idle';
    isInteracting.value = false;
    detach();
  };

  const gestureState = () => {
    const list = Array.from(pointers.values());
    if (list.length < 2) return null;
    const dx = list[1].x - list[0].x;
    const dy = list[1].y - list[0].y;
    return {
      dist: Math.max(Math.hypot(dx, dy), 1),
      angle: (Math.atan2(dy, dx) * 180) / Math.PI,
    };
  };

  function onPointerMove(event: PointerEvent) {
    if (!pointers.has(event.pointerId) || !base) return;
    pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });

    if (mode === 'gesture') {
      const g = gestureState();
      if (!g) return;
      const scale = clamp(base.scale * (g.dist / startDist), LIMITS.stickerScaleMin, LIMITS.stickerScaleMax);
      const rotation = normalizeRotation(base.rotation + (g.angle - startAngle));
      draft = { scale, rotation };
      writeVisual(scale, rotation, base.flipX);
      return;
    }

    // 单指移动：视口像素位移 ÷（未变换尺寸 × 整体缩放档）→ 归一化增量
    const { width: w, height: h } = getCanvasSize();
    if (!w || !h) return;
    const k = Math.max(getScale?.() || 1, 0.01);
    const x = clamp(base.x + (event.clientX - startX) / (w * k), LIMITS.positionMin, LIMITS.positionMax);
    const y = clamp(base.y + (event.clientY - startY) / (h * k), LIMITS.positionMin, LIMITS.positionMax);
    draft = { x, y };
    writeFrame(x, y);
  }

  function onPointerUp(event: PointerEvent) {
    if (!pointers.has(event.pointerId)) return;
    pointers.delete(event.pointerId);
    const el = frame.value;
    if (el?.hasPointerCapture?.(event.pointerId)) el.releasePointerCapture(event.pointerId);
    if (pointers.size === 1 && mode === 'gesture') {
      // 双指变单指：重新以剩余指针为移动起点，避免跳变
      const remain = Array.from(pointers.values())[0];
      const s = base;
      if (s && remain) {
        startX = remain.x;
        startY = remain.y;
        const current = { ...s, ...draft };
        base = current;
        mode = 'move';
        draft = {};
      }
      return;
    }
    if (pointers.size === 0) finish();
  }

  const onPointerDown = (event: PointerEvent) => {
    if (isDisabled() || event.button !== 0) return;
    const target = event.target as HTMLElement | null;
    // 操作柄有自己的逻辑，不参与整体拖拽
    if (target?.closest('[data-handle], button, input')) return;
    const sticker = getSticker();
    if (!sticker || !frame.value) return;

    // 只有第一指按下时快照基准；第二指按下若重置 base 会让捏合从头计算而跳变
    if (pointers.size === 0) base = { ...sticker };
    pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    frame.value.setPointerCapture?.(event.pointerId);

    if (pointers.size >= 2) {
      const g = gestureState();
      startDist = g?.dist || 1;
      startAngle = g?.angle || 0;
      mode = 'gesture';
    } else {
      startX = event.clientX;
      startY = event.clientY;
      mode = 'move';
    }
    isInteracting.value = true;
    if (!bound) {
      bound = true;
      window.addEventListener('pointermove', onPointerMove, { passive: true });
      window.addEventListener('pointerup', onPointerUp);
      window.addEventListener('pointercancel', onPointerUp);
      window.addEventListener('blur', onBlur);
    }
    event.preventDefault();
  };

  const onWheel = (event: WheelEvent) => {
    if (isDisabled()) return;
    const sticker = getSticker();
    if (!sticker) return;
    event.preventDefault();
    const next = clamp(
      sticker.scale * (event.deltaY < 0 ? 1.08 : 1 / 1.08),
      LIMITS.stickerScaleMin,
      LIMITS.stickerScaleMax
    );
    commit({ scale: next });
  };

  const onKeydown = (event: KeyboardEvent) => {
    if (isDisabled()) return;
    const sticker = getSticker();
    if (!sticker) return;
    const step = event.shiftKey ? 0.02 : 0.004;
    let patch: Partial<StickerInstance> | null = null;
    switch (event.key) {
      case 'ArrowLeft': patch = { x: clamp(sticker.x - step, LIMITS.positionMin, LIMITS.positionMax) }; break;
      case 'ArrowRight': patch = { x: clamp(sticker.x + step, LIMITS.positionMin, LIMITS.positionMax) }; break;
      case 'ArrowUp': patch = { y: clamp(sticker.y - step, LIMITS.positionMin, LIMITS.positionMax) }; break;
      case 'ArrowDown': patch = { y: clamp(sticker.y + step, LIMITS.positionMin, LIMITS.positionMax) }; break;
      case '+': case '=': patch = { scale: clamp(sticker.scale * 1.08, LIMITS.stickerScaleMin, LIMITS.stickerScaleMax) }; break;
      case '-': case '_': patch = { scale: clamp(sticker.scale / 1.08, LIMITS.stickerScaleMin, LIMITS.stickerScaleMax) }; break;
      case '[': patch = { rotation: normalizeRotation(sticker.rotation - 5) }; break;
      case ']': patch = { rotation: normalizeRotation(sticker.rotation + 5) }; break;
      default: return;
    }
    event.preventDefault();
    if (patch) commit(patch);
  };

  const cancel = () => finish();

  onScopeDispose(() => {
    detach();
    if (rafId) cancelAnimationFrame(rafId);
    rafId = 0;
    pointers.clear();
    isInteracting.value = false;
  });

  return { onPointerDown, onPointerMove, onPointerUp, onWheel, onKeydown, isInteracting, cancel };
}
