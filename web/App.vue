<script setup lang="ts">
import { useUserStore } from '@/stores/user';
import { useTempStore } from './stores/ui';


const toggleDarkMode = ref(false);
const tempStore = useTempStore();
const useUser = useUserStore();

watch(toggleDarkMode, (oldVal, newVal) => {
  if (oldVal !== newVal) {
    document.documentElement.classList.toggle('dark', newVal);
  }
});


onMounted(() => {
  useUser.loadUIConfig();
  //再开一个页面测试markdown
  // window.open('/markdown', '_blank');
});

onUnmounted(() => {
  useUser.saveConfig();
  tempStore.clear();
});
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
