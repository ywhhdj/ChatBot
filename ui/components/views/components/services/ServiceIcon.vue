<script setup lang="ts">
import { computed } from 'vue';
import { SERVICE_ICON_MAP } from '@/components/configs/serviceConfig';

const props = withDefaults(
  defineProps<{
    serviceId: string;
    size?: number;
  }>(),
  { size: 22 }
);

const icon = computed<UI.IconType>(
  () => SERVICE_ICON_MAP[props.serviceId] || 'plugin'
);
</script>

<template>
  <span
    class="service-icon"
    :aria-label="`${serviceId} 服务图标`"
  >
    <Icon
      :icon="icon"
      :size="size"
    />
  </span>
</template>

<style scoped>
.service-icon {
  display: inline-grid;
  place-items: center;
  flex: 0 0 auto;
  width: 34px;
  height: 34px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.18);
  background: rgba(255, 255, 255, 0.07);
  color: #fff;
  text-shadow: 0 2px 4px rgba(0, 0, 0, 0.4);
}
</style>
