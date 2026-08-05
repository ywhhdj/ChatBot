<script lang="ts" setup>
const providerList = ref<UI.MenuItem[]>([
  {
    type: 'nav',
    name: 'deepseek',
    icon: 'deepseek',
    // clickAction: () => uiStore.currentModelProvider = value as UI.ModelProviderTab
  },
  {
    type: 'nav',
    name: 'chatgpt',
    icon: 'chatgpt',
    // clickAction: () => uiStore.currentModelProvider = value as UI.ModelProviderTab
  },
]);
</script>

<template>
  <!-- <AIModelNav :models="providerList" /> -->
  <MenuItem
    size="large"
    title="API模型"
  >

  </MenuItem>
  <MenuItem
    size="large"
    title="本地模型"
  >

  </MenuItem>
  <!-- <MenuItem
    size="small"
    title="通用设置"
  >
  <template #left>
    主动感知
  </template>
<template #right>
    <Select
      :value="uiStore.activeModelProvider"
      :options="providerList"
      @change="uiStore.activeModelProvider = $event"
    />
  </template>
<RowItem>
</RowItem>
</MenuItem> -->
</template>

<style scoped>
.model-list {
  display: flex;
  flex-direction: column;
}
</style>