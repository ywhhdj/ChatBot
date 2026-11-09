<template>
  <div class="character-list">
    <slot></slot>
  </div>
</template>

<style scoped>
.character-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
  gap: 20px;
  padding: 15px;
  width: 100%;
  overflow-y: auto;
}

@media (max-width: 768px) {
  .character-list {
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  }
}
</style>