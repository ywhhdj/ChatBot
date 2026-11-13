<template>
  <div class="music-list">
    <slot></slot>
  </div>
</template>

<style scoped>
.music-list {
  max-height: 200px;
  overflow-y: auto;
  margin-top: 15px;
  border: 1px solid #555;
  padding: 5px;
  background-color: rgba(0, 0, 0, 0.2);
  border-radius: 10px;
}
</style>