<script setup lang="ts">
import { useRouter } from 'vue-router';

const router = useRouter()
const gameNav: UI.MenuItem[] = [
  {
    type: 'menu',
    name: '开始游戏',
    clickAction: () => router.push('/chat')
  },
  {
    type: 'menu',
    name: '继续游戏',
    clickAction: () => router.push('/settings')
  },
  {
    type: 'menu',
    name: '游戏设置',
    clickAction: () => router.push('/settings')
  },
  {
    type: 'menu',
    name: '退出游戏',
    clickAction: () => window.close(),
  },
]
</script>

<template>
  <div class="game-nav">
    <Nav
      class="menu-item"
      :menus="gameNav"
      font-family="maokenAssorted"
      :scale-animation="true"
    />
  </div>
</template>

<style scoped>
.game-nav {
  display: flex;
  flex-direction: column;
}

@media screen and (max-width: 768px) {
  .game-nav {
    flex-direction: row;
  }
}
</style>