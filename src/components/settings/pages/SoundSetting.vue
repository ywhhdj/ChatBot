<script setup lang="ts">
import { emitMusicPause, emitMusicPlay, emitMusicProgress, emitMusicVolumeChange } from '@/events/event/music';
import { useUserStore } from '@/stores/user';
import notification from '@/utils/notification';
import { useTempStore } from '@/stores/ui';

const userStore = useUserStore();
const uiStore = useTempStore();

const audioFileTypes = ['.mp3', '.wav', '.ogg', '.m4a', '.aac', '.flac', '.webm'];
const currentIndex = ref(0);
const uploadInput = ref<HTMLInputElement | null>(null);
const getAudioFileType = computed(() => audioFileTypes.join(','));
const isMusicPlaying = ref(false)
const playPauseButtonText = computed(() => (isMusicPlaying.value ? '⏸ 暂停' : '▶ 播放'));

const handleStop = () => {
  isMusicPlaying.value = false;
  emitMusicPlay()
};

const handlePlayPause = () => {
  isMusicPlaying.value = !isMusicPlaying.value;
  if (isMusicPlaying.value) {
    emitMusicPlay()
  } else {
    emitMusicPause()
  }
};

const playMusic = (music: UI.Music) => {
  isMusicPlaying.value = true;
  emitMusicPlay(music.url)
}

const updateBackgroundVolume = (volume: number) => {
  userStore.config.bgVolume = volume;
  emitMusicVolumeChange(volume);
};

const updateMusicProgress = (index: number, progress: number) => {
  if (uiStore.musicList[index]) {
    uiStore.musicList[index].progress = progress;
  }
};
const updateBgMusicProgress = (index: number) => {
  if (uiStore.musicList[index]) {
    emitMusicProgress(uiStore.musicList[index].progress);
  }
};

const triggerUpload = () => {
  uploadInput.value?.click();
};

const handleMusicUpload = (event: Event) => {
  const target = event.target as HTMLInputElement;
  const files = Array.from(target.files || []);

  files.forEach((file) => {
    if (!file || !file.type.startsWith('audio/')) {
      return;
    }
    const ext = `.${file.name.split('.').pop()?.toLowerCase() || ''}`;
    if (!audioFileTypes.includes(ext)) {
      return;
    }
    const musicName = file.name.replace(/\.[^.]+$/, '');
    if (uiStore.musicList.some((item) => item.name === musicName)) {
      return;
    }
    uiStore.musicList.push({
      name: musicName,
      url: URL.createObjectURL(file),
      progress: 0,
    });
  });

  if (target) {
    target.value = '';
  }
};

const deleteMusic = (index: number) => {
  if (index < 0 || index >= uiStore.musicList.length || index === 0) {
    notification.showWarning({
      title: '删除失败',
      message: "默认音乐不能删除",
    });
    return;
  };
  const removed = uiStore.musicList.splice(index, 1)[0];
  if (removed?.url?.startsWith('blob:')) {
    URL.revokeObjectURL(removed.url);
  }
  if (currentIndex.value >= uiStore.musicList.length) {
    currentIndex.value = Math.max(0, uiStore.musicList.length - 1);
    emitMusicPlay(uiStore.musicList?.[currentIndex.value]?.url || '');
  }
};


const musicName = computed(() => {
  if (isMusicPlaying.value) {
    return uiStore.musicList[currentIndex.value]?.name;
  }
  return '未选择音乐';
})

</script>

<template>

  <MenuItem
    title="角色音量"
    size="small"
  >
  <Silder>
    <template #left>弱</template>
    <template #right>强</template>
  </Silder>
  </MenuItem>
  <MenuItem
    title="🎶 背景音量"
    size="small"
  >
  <Silder
    :value="userStore.config.bgVolume"
    @change="updateBackgroundVolume"
  >
    <template #left>弱</template>
    <template #right>强</template>
  </Silder>
  </MenuItem>
  <MenuItem
    title="音效音量"
    size="small"
  >
  <Silder>
    <template #left>弱</template>
    <template #right>强</template>
  </Silder>
  </MenuItem>
  <MenuItem title="⚙ 背景音乐设置">
  <div class="music-controls">
    <Button
      type="big"
      @click="handlePlayPause"
      class="left-button"
    >{{ playPauseButtonText }}</Button>
    <Button
      type="big"
      @click="handleStop"
      class="left-button"
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
          @change="(value) => updateMusicProgress(index, value)"
          @input="() => updateBgMusicProgress(index)"
          :max="100"
          :min="0"
          :step="0.1"
        />
      </div>
      <Button
        @click="deleteMusic(index)"
        icon="delete"
        class="action-btn-delete glass-effect"
      />
    </div>
  </div>
  <div class="music-upload">
    <Button
      type="big"
      @click="triggerUpload"
    >➕ 添加音乐</Button>
    <input
      ref="uploadInput"
      type="file"
      :accept="getAudioFileType"
      multiple
      style="display: none"
      @change="handleMusicUpload"
    />
  </div>
  </MenuItem>
  <audio ref="characterTestPlayer"></audio>
  <audio ref="bubbleTestPlayer"></audio>
</template>

<style scoped>
sound-test,
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
  color: var(--accent-color);
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

/* .action-btn-delete {
  flex-shrink: 0;
  margin-left: 10px;
  padding: 4px 8px;
  font-size: 12px;
}

.action-btn-delete.glass-effect {
  background: rgba(255, 0, 0, 0.3);
  transition: all 0.2s ease;
} */

.action-btn-delete {
  padding: 4px 8px;
  color: #ddd;
  cursor: pointer;
  border-radius: 4px;
  transition:
    background-color 0.2s,
    border-color 0.2s;
  white-space: nowrap;
}

.action-btn-delete.glass-effect:hover {
  transform: translateY(-1px);
  background-color:
    color-mix(in oklab, var(--color-red-500) 10%, transparent);
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