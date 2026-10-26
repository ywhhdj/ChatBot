<script lang="ts" setup>
import { useRouter } from 'vue-router';
const router = useRouter();

const menus: UI.MenuItem[] = [
  {
    type: 'nav',
    name: '设置',
    icon: 'settings',
    clickAction: () => router.push("/settings"),
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