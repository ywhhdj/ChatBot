<script setup lang="ts">
const props = defineProps({
  avatar: {
    type: String,
    default: '',
  },
  name: {
    type: String,
    default: '',
  },
  desc: {
    type: String,
    default: '',
  },
  category: {
    type: String,
    default: 'service',
  },
});
</script>

<template>
  <article class="plugin-card">
    <div class="plugin-header">
      <div class="plugin-avatar-container">
        <img v-if="avatar" :src="avatar" :alt="name" class="plugin-avatar" />
        <div v-else class="plugin-avatar-fallback">{{ name.slice(0, 1).toUpperCase() }}</div>
      </div>
      <span class="plugin-tag">{{ category }}</span>
    </div>

    <div class="plugin-content">
      <h5 class="plugin-title">{{ name }}</h5>
      <p class="plugin-description">{{ desc || '暂无描述' }}</p>
      <div class="plugin-actions">
        <slot name="actions"></slot>
      </div>
    </div>
  </article>
</template>

<style scoped>
.plugin-card {
  border: 1px solid rgba(255, 255, 255, 0.16);
  border-radius: 12px;
  padding: 14px;
  background: rgba(12, 22, 40, 0.42);
  color: #fff;
  display: grid;
  gap: 12px;
}

.plugin-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.plugin-avatar-container {
  width: 44px;
  height: 44px;
}

.plugin-avatar,
.plugin-avatar-fallback {
  width: 100%;
  height: 100%;
  border-radius: 10px;
}

.plugin-avatar-fallback {
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.16);
  font-weight: 700;
}

.plugin-tag {
  font-size: 12px;
  opacity: 0.9;
  padding: 3px 8px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.13);
}

.plugin-title {
  margin: 0;
  font-size: 16px;
}

.plugin-description {
  opacity: 0.9;
  margin: 8px 0 10px;
  min-height: 38px;
}

.plugin-actions {
  display: flex;
  justify-content: flex-end;
}
</style>
