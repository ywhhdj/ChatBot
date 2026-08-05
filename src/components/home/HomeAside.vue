<script setup lang="ts">
import { defaultUIStore } from '@/stores/ui';

const uiStore = defaultUIStore();
const isCollapsed = ref(true)

const menus: UI.MenuItem[] = [
  {
    type: 'nav',
    name: '模型供应商',
    icon: 'box',
    clickAction: () => uiStore.setCurrentHomeTab('modelprovider'),
  },
  {
    type: 'nav',
    name: '监控',
    icon: 'schedule',
    clickAction: () => uiStore.setCurrentHomeTab('monitor'),
  },
  {
    type: 'nav',
    name: '服务',
    clickAction: () => uiStore.setCurrentHomeTab('services'),
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
    class="home-aside"
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
    <div class="nav-item">
      <!-- 底部区域（如用户信息） -->
      <a
        target="_blank"
        class="github-link"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          aria-hidden="true"
          focusable="false"
          viewBox="0 0 24 24"
        >
          <path
            d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12"
          ></path>
        </svg>
      </a>
    </div>
  </aside>
</template>

<style scoped>
.home-aside {
  border-radius: 8px;
  display: grid;
  grid-template-rows: 1fr 200px;
  left: 0;
  top: 0;
  width: 180px;
  height: 100vh;
  z-index: 900;
  transition: width 0.3s ease, transform 0.3s ease;
  overflow: hidden;
  gap: 10px;
  position: sticky;
}

/* 响应式：小屏收起（可改为隐藏或缩小为图标） */
@media screen and (max-width: 768px) {
  .home-aside {
    width: 60px;
    transform: translateX(-100%);
  }

  .home-aside.collapsed {
    transform: translateX(-100%);
  }
}

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