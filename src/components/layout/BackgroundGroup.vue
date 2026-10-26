<script setup lang="ts">
import { CONFIG } from '@/config';
import {
  onMusicPause, onMusicPlay, onMusicProgress
  , offMusicPlay, offMusicPause, offMusicProgress,
  onMusicVolumeChange
} from '@/events/event/music';
import { onBackgroundChange } from '@/events/event/background';
import { useUserStore } from '@/stores/user';

const user = useUserStore();

const audioRef = ref<HTMLAudioElement | null>(null);

const backgroundUrl = ref(CONFIG.background.url);
const backgroundDuration = ref(CONFIG.background.duration);
function registerEvent() {
  onMusicPlay(async (url?: string) => {
    if (!audioRef.value) return;
    if (url) audioRef.value.src = url;
    await audioRef.value?.play();
  })
  onMusicPause(() => {
    audioRef.value?.pause();
  });
  onMusicProgress((progress: number, url?: string) => {
    if (!audioRef.value) return;
    if (url) audioRef.value.src = url;
    const currentTime = progress * audioRef.value?.duration;
    audioRef.value.currentTime = currentTime;
  });
  onMusicVolumeChange((volume: number) => {
    if (!audioRef.value) return;
    audioRef.value.volume = volume / 100;
  });
  onBackgroundChange((url: string, duration?: number) => {
    backgroundUrl.value = url;
    if (duration) backgroundDuration.value = duration;
  });
}

function unregisterEvent() {
  offMusicPlay();
  offMusicPause();
  offMusicProgress();
}

onMounted(async () => {
  registerEvent();
})
onUnmounted(() => unregisterEvent())
</script>

<template>
  <ImageAcrossFade
    class="background-image"
    :src="backgroundUrl"
    position="center center"
    object-fit="cover"
    :duration="backgroundDuration"
  >
    <SnowFlakes v-if="user.config.animations.snowFlakes" />
  </ImageAcrossFade>
  <audio
    class="hidden"
    ref="audioRef"
    controls
    autoplay
    loop
    :src="CONFIG.sound.audio.url"
  />
</template>

<style scoped>
.background-image {
  position: fixed;
  left: 0;
  top: 0;
  width: 100%;
  height: 100%;
  background-size: cover;
  background-position: center center;
  background-attachment: fixed;
  background-repeat: no-repeat;
  z-index: -2;
}
</style>