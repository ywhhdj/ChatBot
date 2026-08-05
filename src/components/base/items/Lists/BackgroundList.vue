<template>
  <div class="bg-list">
    <slot></slot>
  </div>
</template>

<style scoped>
.bg-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 20px;
  width: 100%;
  padding: 20px;
  border-radius: 10px;
  box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
  max-width: 1200px;
  margin: 0 auto;
}

@media (max-width: 768px) {
  .bg-list {
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    gap: 16px;
    padding: 12px;
  }
}

@media (max-width: 480px) {
  .bg-list {
    grid-template-columns: 1fr;
  }
}
</style>