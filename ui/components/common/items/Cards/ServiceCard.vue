<template>
  <div class="transparent-glass service-card">
    <slot></slot>
  </div>
</template>

<style scoped>
.service-card {
  backdrop-filter: blur(1px);
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
</style>