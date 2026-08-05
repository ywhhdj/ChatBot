<script lang="ts" setup>
import { useRouter } from 'vue-router';
const router = useRouter();

const menus: UI.MenuItem[] = [
  {
    type: 'nav',
    name: '首页',
    icon: 'home',
    clickAction: () => router.push("/home"),
  },
  {
    type: 'nav',
    name: '菜单',
    icon: 'menu',
    clickAction: () => router.push("/settings"),
  },
  {
    type: 'nav',
    name: '聊天',
    icon: 'chat',
    clickAction: () => router.push("/chat"),
  }
];
</script>

<template>
  <div class="header-nav">
    <MenuBar
      justify="end"
      :is-box-shadow="false"
    >
      <Nav
        :menus="menus"
        :hideText="true"
        direction="row"
      />
    </MenuBar>
  </div>

</template>

<style scoped>
.header-nav {
  border-radius: 8px;
  max-height: 50px;
  top: 10px;
  position: sticky;
}
</style>