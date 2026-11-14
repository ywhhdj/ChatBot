<script setup lang="ts">
import { tagLabel } from "@/composables/modelPresets";

const props = withDefaults(defineProps<{
  model: Model.ModelItem;
  selected?: boolean;
  installed?: boolean;
  disabled?: boolean;
  animated?: boolean;
}>(), {
  selected: false,
  installed: false,
  disabled: false,
  animated: true,
});

const emit = defineEmits<{
  (e: "select", id: string): void;
}>();

const tags = computed(() => (props.model.tags ?? []).slice(0, 3));
</script>

<template>
  <BaseCard
    class="model-card transparent-glass"
    :selected="selected"
    :disabled="disabled"
    :animated="animated"
    @click="emit('select', model.id)"
  >
    <template #header>
      <Icon icon="chip" :size="18" />
      <span class="card-label">{{ model.label }}</span>
    </template>

    <code class="card-id">{{ model.id }}</code>

    <template #footer>
      <span
        v-for="tag in tags"
        :key="tag"
        class="tag"
        :class="`tag-${tag}`"
      >{{ tagLabel(tag) }}</span>
      <span v-if="installed" class="tag tag-installed">已就绪</span>
      <span v-if="selected" class="selected-mark">✦ 当前</span>
    </template>
  </BaseCard>
</template>

<style scoped>
.card-id {
  font-family: var(--font-mono);
  font-size: 12px;
  color: rgba(255, 255, 255, 0.72);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tag {
  padding: 2px 8px;
  font-size: 11px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.24);
  background: rgba(255, 255, 255, 0.08);
  color: rgba(255, 255, 255, 0.9);
}

.tag-cloud {
  border-color: rgba(121, 217, 255, 0.55);
  color: #a9e6ff;
}

.tag-local,
.tag-free,
.tag-installed {
  border-color: rgba(120, 230, 170, 0.5);
  color: #b8f5d0;
}

.tag-paid {
  border-color: rgba(255, 215, 0, 0.5);
  color: #ffe58a;
}

.selected-mark {
  margin-left: auto;
  color: #ffd700;
  font-size: 12px;
  text-shadow: 0 0 8px rgba(255, 215, 0, 0.7);
}
</style>