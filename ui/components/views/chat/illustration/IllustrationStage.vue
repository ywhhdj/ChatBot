<script setup lang="ts">
/**
 * 分层拼接立绘舞台
 *
 * 中间是 Live2D 各部件 PNG 按固定层级叠放的合成立绘（不是 moc3 实时模型），
 * 贴纸铺在同一坐标系上，可任意摆放、拖动、缩放、旋转。
 */
import { useIllustrationStore } from '@/stores/illustration';
import { LIMITS, SCALE_STEPS, type StickerInstance } from './configs/illustrationTypes';

const props = defineProps<{
  editing: boolean;
}>();

const emit = defineEmits<{
  /** 请求重置（由页面层做 dirty 确认，组件不自行破坏编辑态） */
  reset: [];
}>();

const store = useIllustrationStore();
const canvasRef = ref<HTMLElement | null>(null);
const canvasSize = shallowRef({ width: 0, height: 0 });
let observer: ResizeObserver | null = null;
let resizeFallback: (() => void) | null = null;

onMounted(() => {
  const el = canvasRef.value;
  if (!el) return;
  const measure = () => {
    // offset 不受 transform 影响，与拖拽换算同源
    canvasSize.value = { width: el.offsetWidth, height: el.offsetHeight };
  };
  measure();
  if (typeof ResizeObserver !== 'undefined') {
    observer = new ResizeObserver(measure);
    observer.observe(el);
  } else {
    window.addEventListener('resize', measure, { passive: true });
    resizeFallback = measure;
  }
});

onBeforeUnmount(() => {
  observer?.disconnect();
  if (resizeFallback) window.removeEventListener('resize', resizeFallback);
});

interface VisibleLayer {
  key: string;
  label: string;
  z: number;
  opacity: number;
  flipX: boolean;
  src: string;
  optionLabel: string;
}

const visibleLayers = computed<VisibleLayer[]>(() => {
  const result: VisibleLayer[] = [];
  // 动态层按 z 稳定排序，避免模型部件层序抖动
  for (const layer of store.orderedLayers) {
    if (!layer.visible || !layer.activeId) continue;
    const option = layer.options.find((o) => o.id === layer.activeId);
    if (!option) continue;
    result.push({
      key: layer.key,
      label: layer.label,
      z: layer.z,
      opacity: layer.opacity,
      flipX: layer.flipX,
      src: option.src,
      optionLabel: option.label,
    });
  }
  return result;
});

const hasContent = computed(() => visibleLayers.value.length > 0 || store.stickers.length > 0);

const figureStyle = computed(() => {
  const s = store.global.scale;
  return {
    transform: `scale(${store.global.flipX ? -s : s}, ${s})`,
    transformOrigin: 'center bottom',
  };
});

const canvasHeight = '100%';

function clearSelection(event: PointerEvent) {
  if (!props.editing) return;
  const target = event.target as HTMLElement | null;
  // 点在贴纸、工具条、缩放档或操作柄上时不取消选中；
  // 其余（画布空白 / 立绘图层）都视为「点击空白处」，清空选中态
  if (target?.closest('.sticker-frame, .stage-tools, .stage-scales, [data-handle]')) return;
  store.selectSticker(null);
}

function onStickerUpdate(id: string, patch: Partial<StickerInstance>) {
  store.updateSticker(id, patch);
}

function removeSelected() {
  const current = store.selectedSticker;
  if (current) store.removeSticker(current.id);
}
</script>

<template>
  <div
    v-show="store.global.visible"
    class="avatar-stage"
    :class="{ 'is-editing': editing }"
  >
    <div
      ref="canvasRef"
      class="avatar-canvas"
      :style="{ height: canvasHeight }"
      @pointerdown="clearSelection"
    >
      <div
        class="avatar-figure"
        :style="figureStyle"
      >
        <!-- 部件层：固定 z 顺序，逐层叠放 -->
        <div
          v-for="entry in visibleLayers"
          :key="entry.key"
          class="part-layer"
          :style="{
            zIndex: entry.z,
            opacity: entry.opacity,
            transform: entry.flipX ? 'scaleX(-1)' : 'none',
          }"
        >
          <AssetImage
            :src="entry.src"
            :alt="`${entry.label} · ${entry.optionLabel}`"
          />
        </div>

        <IllustrationStickerItem
          v-for="sticker in store.stickers"
          :key="sticker.id"
          :sticker="sticker"
          :canvas-size="canvasSize"
          :viewport-scale="store.global.scale"
          :selected="store.selectedStickerId === sticker.id"
          :editing="editing"
          @select="store.selectSticker"
          @update="onStickerUpdate"
          @remove="store.removeSticker"
          @flip="store.toggleStickerFlip"
          @behind="store.toggleStickerBehind"
          @layer="store.moveStickerLayer"
        />
      </div>

      <!-- 初始对话画面保持干净；只有进入立绘编辑模式才给引导 -->
      <p
        v-if="!hasContent && editing"
        class="avatar-empty"
      >
        尚未添加部件素材<br />
        <small>从右侧「自定义 / 贴纸 / 模型」添加本地素材，或导入真实 Live2D / VTS 模型包</small>
      </p>

      <!-- 左侧竖排工具：仅在编辑态出现，避免遮挡正常对话 -->
      <div
        v-if="editing"
        class="stage-tools"
        data-no-drag
      >
        <Button
          type="nav"
          @click="emit('reset')"
        >
          <Icon
            icon="update"
            :size="14"
          />重置
        </Button>
        <Button
          type="nav"
          :disabled="!store.selectedSticker"
          @click="removeSelected"
        >
          <Icon
            icon="delete"
            :size="14"
          />删除
        </Button>
        <Button
          type="nav"
          @click="store.toggleGlobalFlip"
        >
          <Icon
            icon="flip"
            :size="14"
          />水平翻转
        </Button>
      </div>

      <!-- 左下整体缩放档 -->
      <div
        v-if="editing"
        class="stage-scales"
        data-no-drag
      >
        <Button
          v-for="step in SCALE_STEPS"
          :key="step"
          type="nav"
          :class="{ 'is-active': store.global.scale === step }"
          :aria-pressed="store.global.scale === step"
          @click="store.setScale(step)"
        >×{{ step }}</Button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.avatar-stage {
  position: absolute;
  inset: 0;
  z-index: 10;
  pointer-events: none;
}

.avatar-canvas {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  /* 画布高度由模板 :style 统一给 100%：立绘延伸到屏幕底，
     由 z 更高的半透明对话框覆盖下半身；此处不重复定义 height */
  pointer-events: none;
}

.avatar-stage.is-editing .avatar-canvas {
  pointer-events: auto;
  border-radius: 12px;
  border: 1px dashed rgba(121, 217, 255, 0.35);
  background: rgba(0, 14, 39, 0.08);
}

.avatar-figure {
  position: absolute;
  inset: 0;
  /* 立绘脚底对齐，放大时向上长而不是向下穿进对话框 */
  transform-origin: center bottom;
}

.part-layer {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.part-layer :deep(.asset-image) {
  object-fit: contain;
  object-position: center bottom;
}

.avatar-empty {
  position: absolute;
  left: 50%;
  top: 46%;
  transform: translate(-50%, -50%);
  margin: 0;
  text-align: center;
  font-family: 'Maoken Assorted Sans', -apple-system, BlinkMacSystemFont, sans-serif;
  font-size: 15px;
  line-height: 1.8;
  color: var(--text-color);
  opacity: 0.62;
  text-shadow: 0 2px 4px rgba(0, 0, 0, 0.6);
  pointer-events: none;
  max-width: 60%;
}

.avatar-empty small {
  font-family: -apple-system, BlinkMacSystemFont, 'Microsoft YaHei', sans-serif;
  font-size: 11px;
  opacity: 0.8;
}

.stage-tools {
  position: absolute;
  left: 16px;
  top: 18%;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.22);
  background: rgba(0, 14, 39, 0.55);
  backdrop-filter: blur(4px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
}

.stage-tools :deep(button) {
  justify-content: flex-start;
  min-height: 36px;
  font-size: 13px;
  white-space: nowrap;
}

.stage-scales {
  position: absolute;
  left: 16px;
  bottom: 12px;
  display: flex;
  gap: 6px;
  padding: 4px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.22);
  background: rgba(0, 14, 39, 0.55);
  backdrop-filter: blur(4px);
}

.stage-scales :deep(button) {
  min-width: 44px;
  min-height: 32px;
  padding: 4px 8px;
  font-size: 12px;
  border-radius: 999px;
}

.stage-scales :deep(.is-active) {
  background: rgba(121, 217, 255, 0.22);
  color: var(--primary-color);
}

@media (max-width: 768px) {
  .stage-tools {
    top: 10%;
    left: 8px;
  }

  .avatar-empty {
    max-width: 80%;
    font-size: 13px;
  }
}

@media (prefers-reduced-motion: reduce) {

  .avatar-stage,
  .avatar-figure {
    transition: none !important;
  }
}
</style>
