<script setup lang="ts">

withDefaults(defineProps<{
  title: string;
  icon?: UI.IconType;
  size?: 'small' | 'large';
  buttonText?: string;
}>(), {
  icon: "none",
  size: 'large',
  buttonText: "",
});
const emit = defineEmits(['click']);
</script>

<template>
  <section :class="['menu-item', size]">
    <RowItem class="menu-item-title">
      <template #left>
        <div
          class="flex gap-0.5"
          style="margin-right: 8px;"
        >
          <Icon
            v-if="icon"
            :icon="icon"
          />
          <div class="title-text">
            {{ title }}
          </div>
        </div>
      </template>
      <template #right>
        <div
          v-if="buttonText"
          style="justify-self: flex-end;width: max-content;height: min-content;"
        >
          <Button
            type="big"
            @click="$emit('click')"
          >{{ buttonText }}</Button>
        </div>
      </template>
    </RowItem>
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
  height: 100%;
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
  border-bottom: 2px solid var(--primary-color);
  padding-bottom: 8px;
  margin-bottom: 15px;
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

@media (max-width: 768px) {
  .menu-item.small {
    width: 100%;
  }
}

.menu-item-content {
  flex: 1;
  padding: 0 15px;
  overflow: hidden;
}
</style>
