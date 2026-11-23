<script setup lang="ts">
import { requestService } from '@/api/services/request';
import { emitBackgroundChange } from '@/events/event/background';
import { useTempStore } from '@/stores/ui';
import notification from '@/utils/notification';
import { assetFingerprints, type LoadedAsset } from '@/utils/asset';
import { useObjectUrls } from '@/composables/useObjectUrls';

const uiStore = useTempStore();
const urls = useObjectUrls(false);
const selectedUrl = ref(uiStore.bgList[0]?.url || '');

const existing = computed(() => assetFingerprints(uiStore.bgList.map((b) => ({ label: b.name, src: b.url }))));

function isSelected(url: string) {
  return url === selectedUrl.value;
}

function selectBackground(url: string, duration?: number) {
  selectedUrl.value = url;
  emitBackgroundChange(url, duration);
}

function onFiles(assets: LoadedAsset[]) {
  let added = 0;
  for (const asset of assets) {
    if (!asset.file) continue;
    const name = asset.label;
    if (uiStore.bgList.some((item) => item.name === name)) continue;
    uiStore.bgList.push({
      url: urls.create(asset.file),
      name,
      index: uiStore.bgList.length,
      duration: undefined,
    });
    added += 1;
  }
  notification.showSuccess({
    title: '自定义背景',
    message: added ? `已添加 ${added} 张背景` : '所选背景已存在，未重复添加',
  });
}

function onError(message: string) {
  notification.showError({ title: '背景文件不支持', message });
}

function onWarnings(messages: string[]) {
  notification.showWarning({ title: '部分文件未添加', message: messages.slice(0, 2).join('；') });
}

async function openBackgroundFolder() {
  await requestService.openFolder('images');
}

function deleteBackground(index: number) {
  if (index === 0) {
    notification.showWarning({ title: '删除', message: '默认背景不能删除' });
    return;
  }
  const removed = uiStore.bgList.splice(index, 1)[0];
  if (removed) urls.revoke(removed.url);
  if (!uiStore.bgList.some((b) => b.url === selectedUrl.value)) {
    const fallback = uiStore.bgList[Math.min(index, uiStore.bgList.length - 1)];
    if (fallback) selectBackground(fallback.url, fallback.duration);
  }
}

// 全局列表里的 blob 仍可能被其它页面使用：只释放已不再引用的
onBeforeUnmount(() => {
  urls.prune(uiStore.bgList.map((b) => b.url));
});
</script>

<template>
  <BackgroundList>
    <BackgroundCard
      v-for="(background, index) in uiStore.bgList"
      :key="background.url"
      :isSelected="isSelected(background.url)"
    >
      <div class="background-image-container">
        <img
          :src="background.url"
          :alt="background.name"
          class="background-image"
          decoding="async"
          @error="onError('背景图片解码失败，请更换文件')"
        />
      </div>
      <div class="background-title">
        <div>{{ background.name }}</div>
        <div style="display: flex; gap: 8px;">
          <Button
            :class="['background-select-btn', { selected: isSelected(background.url) }]"
            @click="selectBackground(background.url, background.duration)"
          >
            {{ isSelected(background.url) ? '已选中' : '选择' }}
          </Button>
          <Button
            class="background-delete-btn"
            @click="deleteBackground(index)"
          >
            删除
          </Button>
        </div>
      </div>
    </BackgroundCard>
  </BackgroundList>

  <AssetPicker
    kind="image"
    label="上传自定义背景"
    icon="background"
    button-type="big"
    :raw-only="true"
    :max-bytes="8 * 1024 * 1024"
    :existing="existing"
    @select="onFiles"
    @error="onError"
    @warnings="onWarnings"
  />
  <Button
    type="big"
    @click="openBackgroundFolder"
  >打开背景文件夹</Button>
</template>

<style scoped>
.background-image-container::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: linear-gradient(to bottom, transparent 60%, rgba(0, 0, 0, 0.3) 100%);
  z-index: 1;
  pointer-events: none;
}

.background-image-container {
  flex: 1;
  position: relative;
  overflow: hidden;
}

.background-image {
  position: relative;
  width: 100%;
  height: 100%;
  object-fit: cover;
  aspect-ratio: 16/9;
  transition: transform 0.3s ease;
}

.background-title {
  padding: 12px 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: rgba(255, 255, 255, 0.15);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  border-top: 1px solid rgba(255, 255, 255, 0.2);
  position: relative;
  z-index: 2;
}

.background-title::before {
  content: attr(data-title);
  font-weight: 500;
  color: rgba(255, 255, 255, 0.9);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 70%;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
}

.background-delete-btn,
.background-select-btn {
  padding: 6px 12px;
  color: white;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  flex-shrink: 0;
}

.background-select-btn {
  background: #4f46e5;
}

.background-select-btn:hover {
  background: #4338ca;
  transform: translateY(-1px);
}

.background-delete-btn {
  background: #ef4444;
}

.background-delete-btn:hover {
  background: #b91c1c;
  transform: translateY(-1px);
}

.background-select-btn:active {
  transform: translateY(0);
}

.background-select-btn.selected {
  background-color: #10b981 !important;
}

@media (max-width: 768px) {
  .background-title {
    padding: 8px 12px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .background-image,
  .background-delete-btn,
  .background-select-btn {
    transition: none;
  }
}
</style>
