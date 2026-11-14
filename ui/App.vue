<script setup lang="ts">
import { useUserStore } from '@/stores/user';
import { useTempStore } from './stores/ui';

const toggleDarkMode = ref(false);
const tempStore = useTempStore();
const useUser = useUserStore();
function init() {
  useUser.loadUIConfig();
}

function destroy() {
  useUser.saveConfig();
  tempStore.clear();
}

watch(toggleDarkMode, (oldVal, newVal) => {
  if (oldVal !== newVal) {
    document.documentElement.classList.toggle('dark', newVal);
  }
});


onMounted(() => init());

onUnmounted(() => destroy());
</script>

<template>
  <div class="bg-group">
    <Notification />
    <BackgroundGroup />
  </div>
  <RouterView class="main-container" />
</template>

<style scoped>
.main-container {
  width: 98%;
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: center;
  overflow: hidden;
}
</style>
