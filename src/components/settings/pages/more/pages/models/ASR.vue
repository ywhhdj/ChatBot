<script setup lang="ts">
//供应商
const provider: UI.MenuItem[] = [{
  name: "whisper",
  clickAction: () => {
    console.log("whisper");
  },
}];
</script>
<template>
  <MenuItem
    title="本地模型"
    size="large"
  >
  
  </MenuItem>
</template>