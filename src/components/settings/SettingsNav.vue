<script setup lang="ts">
import { defaultUIStore } from '@/stores/ui';
import { useRouter } from 'vue-router';
const router = useRouter();
const uiStore = defaultUIStore();
const menus: UI.MenuItem[] = [
  {
    type: 'nav',
    name: '通用',
    icon: 'advance',
    clickAction: () => uiStore.setCurrentSettingsTab('general'),
  },
  {
    type: 'nav',
    name: '背景',
    icon: 'background',
    clickAction: () => uiStore.setCurrentSettingsTab('background'),
  },
  {
    type: 'nav',
    name: '对话历史',
    icon: 'history',
    clickAction: () => uiStore.setCurrentSettingsTab('history'),
  },
  {
    type: 'nav',
    name: '角色',
    icon: 'character',
    clickAction: () => uiStore.setCurrentSettingsTab('character'),
  },

  {
    type: 'nav',
    name: '声音',
    icon: 'sound',
    clickAction: () => uiStore.setCurrentSettingsTab('sound'),
  },
  {
    type: 'nav',
    name: '存档',
    icon: 'save',
    clickAction: () => uiStore.setCurrentSettingsTab('save'),
  },
  {
    type: 'nav',
    name: '其它',
    icon: 'more',
    clickAction: () => uiStore.setCurrentSettingsTab('more'),
  },
];
</script>

<template>
  <div class="logo"></div>
  <MenuBar
    justify="center"
    class="nav-container"
    :is-box-shadow="false"
  >
    <Nav
      :menus="menus"
      :hideText="true"
      direction="row"
    />
  </MenuBar>
  <div class="close-container">
    <Icon
      @click="router.back()"
      icon="close"
      :icon-size="24"
    />
  </div>
</template>

<style scoped>
.nav-container {
  display: flex;
  align-items: center;
  flex-direction: column;
}

.close-container {
  --tw-duration: 300ms;
  transition-duration: 300ms;
  color: white;
  cursor: pointer;
  display: flex;
  justify-items: center;
  align-items: center;
  transition-property: all;
  --tw-ease: var(--ease-in-out);
  transition-timing-function: var(--ease-in-out);
  padding: calc(var(--spacing) * 1.5);
  background-color: transparent;
  border-radius: calc(infinity * 1px);

  &:hover {
    transform: rotate(90deg);
    color: var(--primary-color);
  }
}

@media screen and (max-width: 768px) {
  .logo {
    display: none;
  }
}
</style>
