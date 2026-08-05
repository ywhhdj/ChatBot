<script setup lang="ts">
const props = withDefaults(
  defineProps<{
    src: string
    duration?: number
    objectFit?: string
    position?: string
    className?: string
  }>(),
  {
    duration: 300,
    objectFit: 'contain',
    position: 'center bottom',
  }
)
const currentImageUrl = ref("");
const nextImageUrl = ref("");
const isFadingIn = ref(false);
const isMounted = ref(false);
const topImageRef = ref<HTMLDivElement | null>(null);
let currentImageLoadPromise: Promise<any> | null = null;
const topImageClasses = computed(() => ({
  'opacity-0': isFadingIn.value,
  'opacity-100': !isFadingIn.value
}));

const updateImage = async (url: string) => {
  if (!url || url === currentImageUrl.value) return;
  let resolveLoad!: (value?: void) => void;
  // 新图片加载完成,切换到新图片
  const loadPromise = new Promise((resolve) => {
    resolveLoad = resolve;
  });
  currentImageLoadPromise = loadPromise;
  const img = new Image();
  img.onload = async () => {
    try {
      // 使用 decode() 替代 onload 的回调
      await img.decode().catch(() => { });
    } catch (error) {
      console.error('图片解码失败:', error);
    } finally {
      resolveLoad();
    }
  };
  img.onerror = () => {
    console.error('图片加载失败:', url);
    resolveLoad(); // 确保 Promise 被解决
  };

  img.src = url;
  await loadPromise;
  if (!isMounted.value || currentImageLoadPromise !== loadPromise) return;
  if (currentImageLoadPromise === loadPromise) {
    if (isFadingIn.value) {
      currentImageUrl.value = nextImageUrl.value || currentImageUrl.value;
      isFadingIn.value = false;
    }
    nextImageUrl.value = url;
    await nextTick();
    if (topImageRef.value) {
      //强制触发布局,确保图片加载完成
      topImageRef.value.getBoundingClientRect();
    }
    requestAnimationFrame(() => {
      isFadingIn.value = true;
    });
  }
}

const onTransitionEnd = () => {
  if (isFadingIn.value) {
    currentImageUrl.value = nextImageUrl.value || currentImageUrl.value;
    isFadingIn.value = false; // 切换完成后,重置状态
  }
}

watch(() => props.src, (newSrc) => {
  updateImage(newSrc);
}, { immediate: true });

onMounted(() => {
  isMounted.value = true;
  // 如果已经有 src 且还没加载过，手动触发
  if (props.src && !currentImageUrl.value) {
    updateImage(props.src);
  }
});
// 等待图片加载完成
const waitForLoad = () => {
  if (!isMounted.value) {
    return Promise.reject(new Error('Component is not mounted'));
  }
  return currentImageLoadPromise || Promise.resolve();
}
defineExpose({
  waitForLoad,
})
</script>

<template>
  <div class="image-across-fade">
    <slot></slot>
    <div
      class="image-across-fade-container"
      :style="{
        backgroundImage: `url(${currentImageUrl})`,
        backgroundSize: objectFit,
        backgroundPosition: position,
      }"
    />
    <!--  顶层图片,准备切换-->
    <div
      ref="topImageRef"
      class="image-across-fade-top-image"
      :class="topImageClasses"
      :style="{
        backgroundImage: `url(${nextImageUrl})`,
        backgroundSize: objectFit,
        backgroundPosition: position,
        transition: `opacity ${duration}ms ease-in-out`,
      }"
      @transitionend="onTransitionEnd"
    />
  </div>
</template>

<style>
.image-across-fade-container {
  width: 100%;
  height: 100%;
}

.opacity-0 {
  opacity: 0;
}

.opacity-100 {
  opacity: 1;
}
</style>
