<script setup lang="ts">
withDefaults(
  defineProps<{
    service: string;
    disabled?: boolean;
  }>(),
  { disabled: false }
);

const emit = defineEmits<{
  applyConfig: [];
  saved: [config: Record<string, any>];
  error: [view: UI.AsyncErrorView];
}>();
</script>

<template>
  <ServiceConfigForm
    :service-id="service"
    :disabled="disabled"
    @saved="(config) => emit('saved', config)"
    @applied="emit('applyConfig')"
    @error="(view) => emit('error', view)"
  />
</template>
