<script lang="ts" setup>
defineProps({
  header: {
    type: Array as PropType<string[]>,
    default: () => [],
  },
  data: {
    type: Array as PropType<any[]>,
    default: () => [],
  },
  emptyText: {
    type: String,
    default: '暂无数据',
  },
  loading: {
    type: Boolean,
    default: false,
  },
});
</script>

<template>
  <table class="table">
    <tr class="header">
      <th v-for="item in header" :key="item">{{ item }}</th>
    </tr>
    <tr v-if="loading" class="loading">
      <td colspan="100%" class="loading-text">加载中...</td>
    </tr>
    <tr v-else-if="data.length === 0" class="empty">
      <td colspan="100%" class="empty-text">{{ emptyText }}</td>
    </tr>
    <tr v-else class="row" v-for="(row, index) in data" :key="index">
      <slot :name="index" :row="row" :index="index"></slot>
    </tr>
  </table>
</template>

<style scoped>
.table {
  border-collapse: collapse;
  width: 100%;
  border: 1px solid rgba(255, 255, 255, 0.16);
  border-radius: 8px;
  overflow: hidden;
}

.header {
  height: 44px;
  background: rgba(255, 255, 255, 0.08);
  border-top: none;
  font-weight: 700;
}

.row {
  border: 1px solid rgba(255, 255, 255, 0.16);
  padding: 12px;
}

.loading {
  padding: 14px;
  opacity: 0.85;
}
</style>
