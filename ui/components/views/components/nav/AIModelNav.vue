<script lang="ts" setup>
const props = defineProps<{
  models: UI.MenuItem[]
}>()
</script>

<template>
  <MenuBar
    direction="column"
    class="ai-model-nav"
  >
    <Nav :menus="models" />
  </MenuBar>
</template>

<style scoped>
.ai-model-nav {
  min-width: 100px;
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  flex: 1;
  max-width: 200px;
  border-radius: 10px;
}

@media screen and (max-width: 768px) {
  .ai-model-nav {
    width: 100%;
  }
}
</style>
