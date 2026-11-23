<script setup lang="ts">
/**
 * 通用图片 + 加载失败回退 —— Step 9.1
 *
 * 沿用 AppIcon.vue 的思路：素材来自用户文件或真实 URL，解码失败时
 * 回退到 base Icon，不出现破图、不把异常抛到页面。
 * 只渲染 <img> + v-text，绝不使用 v-html（素材不可信）。
 */
import { ref, watch } from 'vue';
import Icon from '@/components/base/Icon.vue';

const props = withDefaults(
  defineProps<{
    src: string;
    alt?: string;
    /** 失败时是否显示说明文字 */
    hint?: boolean;
  }>(),
  { alt: '', hint: false }
);

const failed = ref(false);
watch(
  () => props.src,
  () => {
    failed.value = false;
  }
);
</script>

<template>
  <img
    v-if="!failed && src"
    class="asset-image"
    :src="src"
    :alt="alt"
    draggable="false"
    decoding="async"
    @error="failed = true"
  />
  <span
    v-else
    class="asset-fallback"
    role="img"
    :aria-label="alt || '图片加载失败'"
  >
    <Icon
      icon="box"
      :size="20"
    />
    <span v-if="hint">素材不可用</span>
  </span>
</template>

<style scoped>
.asset-image {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
  pointer-events: none;
  user-select: none;
  -webkit-user-drag: none;
}

.asset-fallback {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  width: 100%;
  height: 100%;
  font-size: 11px;
  opacity: 0.55;
  color: var(--text-color);
}
</style>
