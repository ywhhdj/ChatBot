<script setup lang="ts">
/**
 * 「贴纸」页
 */
import { computed, ref, watch } from 'vue';
import { useIllustrationStore } from '@/stores/illustration';
import { LIMITS, type StickerAsset } from '@/components/views/chat/illustration/configs/illustrationTypes';
import { assetFingerprints, assetWarnings, type LoadedAsset } from '@/utils/asset';

const emit = defineEmits<{
  notice: [message: string, kind: 'info' | 'warning' | 'error' | 'success'];
}>();

const store = useIllustrationStore();
const page = ref(0);

const existingFingerprints = computed(() => assetFingerprints(store.stickerAssets));

const pageCount = computed(() => Math.max(1, Math.ceil(store.stickerAssets.length / LIMITS.stickerGridSize)));
const paged = computed(() =>
  store.stickerAssets.slice(page.value * LIMITS.stickerGridSize, (page.value + 1) * LIMITS.stickerGridSize)
);

watch(pageCount, (count) => {
  if (page.value > count - 1) page.value = count - 1;
});

function go(direction: -1 | 1) {
  page.value = Math.min(Math.max(page.value + direction, 0), pageCount.value - 1);
}

function goPrev() {
  go(-1);
}

function goNext() {
  go(1);
}

function onFiles(loaded: LoadedAsset[]) {
  const assets: StickerAsset[] = loaded.map((a) => ({
    id: a.id,
    label: a.label,
    src: a.src,
    width: a.width,
    height: a.height,
  }));
  const added = store.addStickerAssets(assets);
  emit('notice', `已添加 ${added} 张贴纸素材`, added ? 'success' : 'warning');
  const warnings = assetWarnings(loaded);
  if (warnings.length) emit('notice', warnings.slice(0, 2).join('；'), 'warning');
  page.value = pageCount.value - 1;
}

function onError(message: string) {
  emit('notice', message, 'error');
}

function place(asset: StickerAsset) {
  const id = store.addSticker(asset);
  if (!id) {
    emit('notice', `画布上最多 ${LIMITS.maxStickerInstances} 张贴纸，请先删除一些`, 'warning');
    return;
  }
  emit('notice', `已放置「${asset.label}」，可在画布上拖动与缩放`, 'info');
}

function removeAsset(asset: StickerAsset) {
  store.removeStickerAsset(asset.id);
  emit('notice', `已移除素材「${asset.label}」及其贴纸`, 'info');
}
</script>

<template>
  <div class="sticker-picker">
    <div class="sp-head">
      <span>素材 {{ store.stickerAssets.length }}/{{ LIMITS.maxStickerAssets }}</span>
      <span>画布 {{ store.stickers.length }}/{{ LIMITS.maxStickerInstances }}</span>
    </div>

    <div
      v-if="!store.stickerAssets.length"
      class="sp-empty"
    >
      <Icon
        icon="box"
        :size="28"
      />
      <strong>还没有贴纸素材</strong>
      <span>点下方「添加图片」从本地选择，之后点格子即可贴到立绘上。</span>
    </div>

    <template v-else>
      <div class="sp-pager">
        <Button
          type="nav"
          :disabled="page <= 0"
          aria-label="上一页贴纸"
          @click="goPrev"
        >‹</Button>
        <span>{{ page + 1 }} / {{ pageCount }}</span>
        <Button
          type="nav"
          :disabled="page >= pageCount - 1"
          aria-label="下一页贴纸"
          @click="goNext"
        >›</Button>
      </div>

      <div class="sp-grid">
        <div
          v-for="asset in paged"
          :key="asset.id"
          class="sp-cell"
        >
          <button
            type="button"
            class="sp-thumb"
            :aria-label="`放置贴纸 ${asset.label}`"
            :title="asset.label"
            @click="place(asset)"
          >
            <AssetImage
              :src="asset.src"
              :alt="asset.label"
              hint
            />
          </button>
          <button
            type="button"
            class="sp-remove"
            :aria-label="`移除素材 ${asset.label}`"
            @click="removeAsset(asset)"
          ><Icon
            icon="close"
            :size="10"
          /></button>
        </div>
      </div>
    </template>

    <div class="sp-foot">
      <AssetPicker
        kind="image"
        label="添加图片"
        icon="plus"
        :max-bytes="LIMITS.maxFileBytes"
        :max-files="LIMITS.maxStickerAssets - store.stickerAssets.length"
        :existing="existingFingerprints"
        :disabled="store.stickerAssets.length >= LIMITS.maxStickerAssets"
        @select="onFiles"
        @error="onError"
      />
      <Button
        type="menu"
        class="sp-confirm"
        @click="store.confirmEdit()"
      >确认</Button>
    </div>

    <p class="sp-tip">
      点击画布中的贴纸可选中；滚轮或右下角手柄缩放，右上角手柄旋转，方向键微调，Delete 删除。
    </p>
  </div>
</template>

<style scoped>
.sticker-picker {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  opacity: 0;
  pointer-events: none;
}

.sp-head {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  opacity: 0.72;
  font-family: ui-monospace, Menlo, monospace;
}

.sp-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 28px 14px;
  border-radius: 10px;
  border: 1px dashed rgba(255, 255, 255, 0.24);
  background: rgba(255, 255, 255, 0.04);
  text-align: center;
  font-size: 12px;
  line-height: 1.7;
}

.sp-empty span {
  opacity: 0.75;
}

.sp-pager {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  font-size: 12px;
}

.sp-pager :deep(button) {
  min-width: 32px;
  min-height: 30px;
  padding: 2px 8px;
}

.sp-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 6px;
}

.sp-cell {
  position: relative;
  aspect-ratio: 1;
}

.sp-thumb {
  width: 100%;
  height: 100%;
  padding: 6px;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  background: rgba(0, 14, 39, 0.5);
  cursor: pointer;
  transition: border-color 0.16s ease-out, background-color 0.16s ease-out;
}

.sp-thumb:hover,
.sp-thumb:focus-visible {
  border-color: var(--primary-color);
  background: rgba(121, 217, 255, 0.14);
  outline: none;
}

.sp-remove {
  position: absolute;
  top: -6px;
  right: -6px;
  width: 20px;
  height: 20px;
  padding: 0;
  display: none;
  place-items: center;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.4);
  background: rgba(0, 14, 39, 0.92);
  color: #fff;
  cursor: pointer;
}

.sp-cell:hover .sp-remove,
.sp-cell:focus-within .sp-remove {
  display: grid;
}

.sp-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding-top: 8px;
  border-top: 1px dashed rgba(255, 255, 255, 0.18);
}

.sp-foot :deep(button) {
  min-height: 34px;
  font-size: 12px;
}

.sp-confirm {
  padding: 6px 18px !important;
  margin: 0 !important;
  font-size: 14px !important;
  border-radius: 999px;
  border: 1px solid var(--primary-color);
  background: rgba(121, 217, 255, 0.18);
}

.sp-tip {
  margin: 0;
  font-size: 10px;
  line-height: 1.7;
  opacity: 0.6;
}
</style>
