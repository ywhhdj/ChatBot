<script setup lang="ts">
import { emitMusicVolumeChange } from '@/events/event/music';
import { useUserStore } from '@/stores/user';
const userStore = useUserStore();
const updateBackgroundVolume = (volume: number) => {
  userStore.config.bgVolume = volume;
  emitMusicVolumeChange(volume);
};
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
    <BackGroundMusicSelector />
  </MenuItem>
  <audio ref="characterTestPlayer"></audio>
  <audio ref="bubbleTestPlayer"></audio>
</template>