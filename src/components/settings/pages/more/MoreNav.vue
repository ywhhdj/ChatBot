<script setup lang="ts">
import { defaultUIStore } from '@/stores/ui';

const uiStore = defaultUIStore();
const isCollapsed = ref(true)

const menus: UI.MenuItem[] = [
  {
    type: 'nav',
    name: '模型供应商',
    icon: 'box',
    clickAction: () => uiStore.setCurrentMoreTab('modelprovider'),
  },
  {
    type: 'nav',
    name: '监控',
    icon: 'schedule',
    clickAction: () => uiStore.setCurrentMoreTab('monitor'),
  },
  {
    type: 'nav',
    name: '服务',
    clickAction: () => uiStore.setCurrentMoreTab('services'),
  },
  {
    type: 'nav',
    name: '插件',
    icon: 'plugin',
  },
  // {
  //   type: 'nav',
  //   name: '配置',
  //   icon: 'advance',
  //   children: [
  //     {
  //       type: 'nav',
  //       name: '高级配置',
  //       clickAction: () => router.push('configs'),
  //     },
  //     {
  //       type: 'nav',
  //       name: '系统配置',
  //       clickAction: () => router.push('/configs/system'),
  //     }
  //   ],
  // },
];
</script>

<template>
  <aside
    class="nav"
    :class="{ collapsed: isCollapsed }"
  >
    <div class="nav-item menu-wrapper">
      <MenuBar
        direction="column"
        justify="center"
        is-top-right="false"
        :is-box-shadow="false"
      >
        <Nav :menus="menus" />
      </MenuBar>
    </div>
  </aside>
</template>

<style scoped>
.nav {
  border-radius: 8px;
  left: 0;
  top: 0;
  width: 180px;
  height: 100%;
  z-index: 900;
  gap: 10px;
  position: sticky;
}

/* 
@media screen and (max-width: 768px) {
  .nav {
    width: 60px;
    transform: translateX(-100%);
  }

  .nav.collapsed {
    transform: translateX(-100%);
  } 
}*/

.nav-item {
  border-radius: 10px;
  background: var(--accent-bg);
  box-shadow: 0 0 10px rgba(0, 0, 0, 0.8);
  overflow: hidden;
  border-radius: 10px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 12px 8px;
  flex: 1;
  min-height: 0;
}

.menu-wrapper {
  flex: 1;
  overflow-y: auto;
  padding-bottom: 12px;
}
</style>