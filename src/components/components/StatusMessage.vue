

<template>
  <div class="status-message">
    <span><slot></slot></span>
  </div>

</template>
<style scoped>
.status-message {
  display: flex;
  align-items: center;
  justify-content: center;
  color: #f5f5f5;
  padding: 2rem;
  font-size: 24px;
  font-weight: bold;
  height: 100%;
  text-shadow: 0 0 5px rgba(255, 255, 255, 0.5);
}
</style>
