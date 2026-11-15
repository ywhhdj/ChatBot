export interface DraggablePoint {
  x: number;
  y: number;
}

export interface UseDraggableOptions {
  /** 拖拽把手（通常是标题栏） */
  handle: Ref<HTMLElement | null>;
  /** 被移动的面板根节点 */
  panel: Ref<HTMLElement | null>;
  /** 初始位置；不传则贴右下角 */
  initial?: DraggablePoint;
  /** 视口安全边距 */
  margin?: number;
  /** 禁用拖拽（例如移动端折叠态） */
  disabled?: Ref<boolean> | (() => boolean);
  onStart?: () => void;
  onEnd?: () => void;
}

const INTERACTIVE_SELECTOR =
  'button, a, input, select, textarea, label, [role="button"], [data-no-drag]';

export function useDraggable(options: UseDraggableOptions) {
  const { handle, panel, initial, margin = 12, disabled, onStart, onEnd } = options;

  const isDragging = shallowRef(false);
  /** 响应式位置：仅供外部读取/展示，拖拽中不会逐帧更新 */
  const position = shallowRef<DraggablePoint>({ x: 0, y: 0 });

  // 内部坐标是普通数值，避免每帧触发依赖收集与组件重渲染
  let x = 0;
  let y = 0;
  let startClientX = 0;
  let startClientY = 0;
  let originX = 0;
  let originY = 0;
  let pendingX = 0;
  let pendingY = 0;
  let rafId = 0;
  let activePointerId: number | null = null;
  let bound = false;

  const isDisabled = () =>
    typeof disabled === 'function' ? disabled() : Boolean(disabled?.value);

  const clamp = (nx: number, ny: number): DraggablePoint => {
    const el = panel.value;
    if (!el || typeof window === 'undefined') return { x: nx, y: ny };
    // offsetWidth/Height 不受 transform 影响，比 getBoundingClientRect 更稳定
    const w = el.offsetWidth;
    const h = el.offsetHeight;
    const maxX = Math.max(margin, window.innerWidth - w - margin);
    const maxY = Math.max(margin, window.innerHeight - h - margin);
    return {
      x: Math.min(Math.max(nx, margin), maxX),
      y: Math.min(Math.max(ny, margin), maxY),
    };
  };

  const apply = () => {
    rafId = 0;
    const el = panel.value;
    if (!el) return;
    // translate3d 触发合成层，避免 layout/paint
    el.style.transform = `translate3d(${pendingX}px, ${pendingY}px, 0)`;
  };

  const scheduleApply = () => {
    if (rafId) return;
    rafId = requestAnimationFrame(apply);
  };

  const syncPosition = () => {
    x = pendingX;
    y = pendingY;
    position.value = { x, y };
  };

  const onPointerMove = (event: PointerEvent) => {
    if (activePointerId !== event.pointerId) return;
    const next = clamp(
      originX + event.clientX - startClientX,
      originY + event.clientY - startClientY
    );
    pendingX = next.x;
    pendingY = next.y;
    scheduleApply();
  };

  function detach() {
    if (!bound) return;
    bound = false;
    window.removeEventListener('pointermove', onPointerMove);
    window.removeEventListener('pointerup', onPointerUp);
    window.removeEventListener('pointercancel', onPointerUp);
  }

  function onPointerUp(event: PointerEvent) {
    if (activePointerId !== null && event.pointerId !== activePointerId) return;
    if (rafId) {
      cancelAnimationFrame(rafId);
      rafId = 0;
    }
    apply();
    syncPosition();
    detach();
    const el = handle.value;
    if (el && activePointerId !== null && el.hasPointerCapture?.(activePointerId)) {
      el.releasePointerCapture(activePointerId);
    }
    activePointerId = null;
    isDragging.value = false;
    onEnd?.();
  }

  const onPointerDown = (event: PointerEvent) => {
    if (isDisabled() || event.button !== 0 || activePointerId !== null) return;
    const target = event.target as HTMLElement | null;
    if (target?.closest(INTERACTIVE_SELECTOR)) return;
    if (!panel.value || !handle.value) return;

    activePointerId = event.pointerId;
    startClientX = event.clientX;
    startClientY = event.clientY;
    originX = x;
    originY = y;
    pendingX = x;
    pendingY = y;
    isDragging.value = true;

    handle.value.setPointerCapture?.(event.pointerId);
    bound = true;
    window.addEventListener('pointermove', onPointerMove, { passive: true });
    window.addEventListener('pointerup', onPointerUp);
    window.addEventListener('pointercancel', onPointerUp);
    onStart?.();
    event.preventDefault();
  };

  const onResize = () => {
    const next = clamp(x, y);
    pendingX = next.x;
    pendingY = next.y;
    apply();
    syncPosition();
  };

  /** 面板尺寸变化（折叠/展开）后重新钳制，避免拖出视口 */
  const clampToViewport = () => {
    onResize();
  };

  const reset = (point?: DraggablePoint) => {
    const el = panel.value;
    const fallback: DraggablePoint = el
      ? {
        x: window.innerWidth - el.offsetWidth - 24,
        y: window.innerHeight - el.offsetHeight - 24,
      }
      : { x: margin, y: margin };
    const target = point || initial || fallback;
    const next = clamp(target.x, target.y);
    pendingX = next.x;
    pendingY = next.y;
    apply();
    syncPosition();
  };

  let started = false;
  const start = () => {
    if (started) return;
    started = true;
    const el = handle.value;
    el?.addEventListener('pointerdown', onPointerDown);
    window.addEventListener('resize', onResize, { passive: true });
    reset();
  };

  const stop = () => {
    if (!started) return;
    started = false;
    handle.value?.removeEventListener('pointerdown', onPointerDown);
    window.removeEventListener('resize', onResize);
    detach();
    if (rafId) {
      cancelAnimationFrame(rafId);
      rafId = 0;
    }
    activePointerId = null;
    isDragging.value = false;
  };

  onScopeDispose(stop);

  return {
    position,
    isDragging,
    start,
    stop,
    reset,
    clampToViewport,
  };
}
