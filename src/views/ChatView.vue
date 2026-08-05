<template>
  <div class="game-image"></div>
  <div class="game-dialog">
    <GameDialog />
  </div>
</template>

<style scoped>
.game-image {
  position: absolute;
}

.game-dialog {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: 2;
}
</style>
