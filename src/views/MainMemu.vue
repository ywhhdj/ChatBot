<script setup lang="ts">
</script>

<template>
  <div class="main-page">
    <GameNav />
  </div>
</template>

<style scoped>
.main-page {
  display: flex;
  flex-direction: row;
  width: 80%;
}

@media screen and (max-width: 768px) {
  .main-page {
    width: 95%;
  }
}
</style>
