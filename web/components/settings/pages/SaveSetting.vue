

<template>
  <MenuPage width="100%">
    <p
      v-if="error"
      class="error"
    >{{ error }}</p>
    <MenuItem
      size="large"
      icon="list"
      title="存档列表"
      style="max-height: 500px;"
    >
    <SaveSlotsPanel />
    </MenuItem>
  </MenuPage>
</template>
<style scoped>
.error {
  margin: 6px 0;
  padding: 8px 10px;
  border-radius: 6px;
  background: rgba(255, 235, 230, 0.85);
  color: #b85545;
  font-size: 13px;
}
</style>