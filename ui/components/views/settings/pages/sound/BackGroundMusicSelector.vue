<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue';
import { emitMusicPause, emitMusicPlay, emitMusicProgress } from '@/events/event/music';
import notification from '@/utils/notification';
import { useTempStore } from '@/stores/ui';
import { assetFingerprints, type LoadedAsset } from '@/utils/asset';
import { useObjectUrls } from '@/composables/useObjectUrls';

const uiStore = useTempStore();
const urls = useObjectUrls(false);

const currentIndex = ref(0);
const isMusicPlaying = ref(false);
const playPauseButtonText = computed(() => (isMusicPlaying.value ? '⏸ 暂停' : '▶ 播放'));
const musicName = computed(() => uiStore.musicList[currentIndex.value]?.name || '未选择音乐');
const existing = computed(() => assetFingerprints(uiStore.musicList.map((m) => ({ label: m.name, src: m.url }))));

function clampIndex(next: number): number {
  if (!uiStore.musicList.length) return 0;
  return Math.min(Math.max(next, 0), uiStore.musicList.length - 1);
}

function handleStop() {
  isMusicPlaying.value = false;
  emitMusicPause();
}

function handlePlayPause() {
  isMusicPlaying.value = !isMusicPlaying.value;
  if (!isMusicPlaying.value) {
    emitMusicPause();
    return;
  }
  const music = uiStore.musicList[currentIndex.value] || uiStore.musicList[0];
  if (music?.url) {
    currentIndex.value = uiStore.musicList.findIndex((m) => m.url === music.url);
    emitMusicPlay(music.url);
  } else {
    isMusicPlaying.value = false;
  }
}

function playMusic(music: UI.Music) {
  const index = uiStore.musicList.findIndex((item) => item.url === music.url);
  if (index < 0) return;
  currentIndex.value = index;
  isMusicPlaying.value = true;
  emitMusicPlay(music.url);
}

function updateMusicProgress(index: number, progress: number) {
  if (uiStore.musicList[index]) uiStore.musicList[index].progress = progress;
}

function updateBgMusicProgress(index: number) {
  const music = uiStore.musicList[index];
  if (music) emitMusicProgress(music.progress / 100);
}

function onFiles(assets: LoadedAsset[]) {
  let added = 0;
  for (const asset of assets) {
    if (!asset.file) continue;
    if (uiStore.musicList.some((item) => item.name === asset.label)) continue;
    uiStore.musicList.push({ name: asset.label, url: urls.create(asset.file), progress: 0 });
    added += 1;
  }
  notification.showSuccess({
    title: '背景音乐',
    message: added ? `已添加 ${added} 首音乐` : '所选音乐已存在，未重复添加',
  });
}

function onError(message: string) {
  notification.showError({ title: '音频文件不支持', message });
}

function onWarnings(messages: string[]) {
  notification.showWarning({ title: '部分文件未添加', message: messages.slice(0, 2).join('；') });
}

function deleteMusic(index: number) {
  if (index <= 0 || index >= uiStore.musicList.length) {
    notification.showWarning({ title: '删除失败', message: '默认音乐不能删除' });
    return;
  }
  const removed = uiStore.musicList.splice(index, 1)[0];
  if (removed) urls.revoke(removed.url);

  if (currentIndex.value === index) {
    currentIndex.value = clampIndex(index);
    const next = uiStore.musicList[currentIndex.value];
    // 只在原本播放中才切歌，暂停状态不擅自开始播放
    if (isMusicPlaying.value && next) emitMusicPlay(next.url);
    else if (!next) {
      isMusicPlaying.value = false;
      emitMusicPause();
    }
  } else if (currentIndex.value > index) {
    currentIndex.value = clampIndex(currentIndex.value - 1);
  }
}

onBeforeUnmount(() => {
  urls.prune(uiStore.musicList.map((m) => m.url));
});
</script>

<template>
  <div class="music-controls">
    <Button
      type="big"
      class="left-button"
      @click="handlePlayPause"
    >{{ playPauseButtonText }}</Button>
    <Button
      type="big"
      class="left-button"
      @click="handleStop"
    >■ 停止</Button>
    <span class="music-name">当前: {{ musicName }}</span>
  </div>

  <div class="music-list">
    <div
      v-if="uiStore.musicList.length === 0"
      class="empty-list"
    >暂无音乐，请上传</div>
    <div
      v-for="(music, index) in uiStore.musicList"
      :key="music.url"
      class="music-item"
      @click="playMusic(music)"
    >
      <div class="music-item-name">{{ music.name }}</div>
      <div class="music-item-progress">
        <Silder
          :value="music.progress"
          :max="100"
          :min="0"
          :step="0.1"
          @change="(value) => updateMusicProgress(index, value)"
          @input="() => updateBgMusicProgress(index)"
        />
      </div>
      <button
        type="button"
        class="action-btn-delete glass-effect"
        aria-label="删除音乐"
        @click.stop="deleteMusic(index)"
      ><Icon
        icon="delete"
        :size="14"
      /></button>
    </div>
  </div>

  <div class="music-upload">
    <AssetPicker
      kind="audio"
      label="➕ 添加音乐"
      icon="sound"
      button-type="big"
      :raw-only="true"
      :max-bytes="32 * 1024 * 1024"
      :existing="existing"
      @select="onFiles"
      @error="onError"
      @warnings="onWarnings"
    />
  </div>
</template>

<style scoped>
.music-controls,
.music-upload {
  display: flex;
  justify-content: space-around;
  gap: 20px;
  align-items: center;
}

.music-list {
  max-height: 200px;
  overflow-y: auto;
  margin-top: 15px;
  border: 1px solid #555;
  padding: 5px;
  background-color: rgba(0, 0, 0, 0.2);
  border-radius: 10px;
}

.music-name {
  flex-grow: 1;
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: #eee;
}

.empty-list {
  text-align: center;
  color: #999;
  padding: 20px;
}

.music-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  cursor: pointer;
  border-bottom: 1px solid #444;
  transition: background-color 0.2s;
  border-radius: 8px;
}

.music-item:hover {
  color: var(--primary-color);
  background-color: color-mix(in oklab, var(--color-purple-500) 20%, transparent);
}

.music-item:last-child {
  border-bottom: none;
}

.music-item-name {
  flex-grow: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.action-btn-delete {
  padding: 4px 8px;
  color: #ddd;
  cursor: pointer;
  border-radius: 4px;
  border: 1px solid transparent;
  background: transparent;
  transition: background-color 0.2s, border-color 0.2s;
  white-space: nowrap;
  flex-shrink: 0;
}

.action-btn-delete.glass-effect:hover {
  transform: translateY(-1px);
  background-color: color-mix(in oklab, var(--color-red-500) 10%, transparent);
}

.action-btn-delete:focus-visible {
  outline: 2px solid var(--primary-color);
  outline-offset: 2px;
}

.left-button.big {
  width: 20%;
}

.music-upload {
  margin-top: 15px;
}

@media (max-width: 426px) {
  .music-item-progress {
    display: none;
  }
}
</style>
