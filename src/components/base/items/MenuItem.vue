<script setup lang="ts">
defineProps({
  icon: {
    type: String as () => UI.IconType,
    default: '',
  },
  title: {
    type: String,
    default: '默认标题',
  },
  size: {
    type: String as () => 'small' | 'large',
    default: 'large',
    validator: (value: string) => ['small', 'large'].includes(value),
  },
  buttonText: {
    type: String,
    required: false
  }
});
const emit = defineEmits(['click']);
</script>

<template>
  <section :class="['menu-item', size]">
    <div style="display: flex;">
      <div class="menu-item-title">
        <div class="title-left">
          <div
            v-if="icon"
            style="margin-right: 8px;"
          >
            <Icon :icon="icon" />
          </div>
          <div class="title-text">
            {{ title }}
          </div>
        </div>
        <div
          v-if="buttonText"
          style="justify-self: flex-end;width: max-content;height: min-content;"
        >
          <Button
            type="big"
            @click="$emit('click')"
          >{{ buttonText }}</Button>
        </div>
      </div>
    </div>
    <div class="menu-item-content">
      <slot></slot>
    </div>
  </section>
</template>

<style scoped>
section {
  box-shadow: 0 0 10px rgba(0, 0, 0, 0.8);
  background: var(--accent-bg);
  border-radius: 12px;
  padding: 15px;
}

.menu-item.large {
  width: 100%;
}

.menu-item.small {
  width: calc(50% - 12.5px);
  /* 减去一半的margin */
}

.menu-item-title {
  width: 100%;
  display: flex;
  align-items: center;
  border-bottom: 2px solid var(--accent-color);
  padding-bottom: 8px;
  margin-bottom: 15px;
  justify-content: space-between;
}

h4 {
  margin: 0;
  font-size: 18px;
  color: #fff;
  font-weight: 600;
  text-shadow: 0 0 2px rgba(0, 0, 0, 0.5);
}

.title-text {
  font-weight: 600;
}

slot {
  display: flex;
}

.title-left {
  display: flex;
  align-items: center;
  justify-self: flex-start;
}

/* 响应式设计 - 在小屏幕上让small菜单项变为全宽 */
@media (max-width: 768px) {
  section.small {
    width: 100%;
    max-width: 900px;
  }
}
</style>
