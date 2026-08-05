<script setup lang="ts">
defineProps<{
  config: UI.ServiceConfigItem[];
}>()

const emit = defineEmits(['updateConfig', 'saveConfig', 'applyConfig'])

function updateConfig(index: number, newValue: boolean | string) {
  emit('updateConfig', index, newValue)
}
</script>

<template>
  <div class="service-config">
    <RowItem
      v-for="(configItem, index) in config"
      :key="configItem.name"
      class="config-row"
    >
      <!-- 左侧：标签 + 描述 -->
      <template #left>
        <div class="config-label">
          <span class="config-title">{{ configItem.name }}</span>

        </div>
        <span
          v-if="configItem.description"
          class="config-desc"
        >{{ configItem.description }}</span>
      </template>

      <!-- 右侧：根据类型渲染控件 -->
      <template
        #right
        class="config-control"
      >
        <Checkbox
          v-if="configItem.type === 'boolean'"
          :checked="configItem.value as boolean"
          @checked="(val: boolean) => updateConfig(index, val)"
        />
        <Select
          :options="configItem.options!"
          v-else-if="configItem.type === 'select'"
          :value="configItem.value as string"
          @change="(val: string) => updateConfig(index, val)"
        />
        <Input
          v-else-if="configItem.type === 'string'"
          class="config-input"
          :value="configItem.value as string"
          @input="(val: string | boolean) => updateConfig(index, val)"
        />
      </template>
    </RowItem>
  </div>

  <div class="config-btn">
    <Button
      type="big"
      style="width: 79%;"
      @click="$emit('saveConfig')"
    >保存</Button>
    <Button
      type="big"
      style="width: 20%;"
      @click="$emit('applyConfig')"
    >应用</Button>
  </div>
</template>

<style scoped>
.service-config {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.config-desc {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.45);
}

.config-btn {
  align-self: flex-end;
  display: flex;
  gap: 10px;
}
</style>
