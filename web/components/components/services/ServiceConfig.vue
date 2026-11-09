<script setup lang="ts">
import { useUserStore } from '@/stores/user';
const userStore = useUserStore();

const props = defineProps<{
  service: API.ServiceId;
}>();

const emit = defineEmits(['updateConfig', 'saveConfig', 'applyConfig'])

function updateConfig(index: number, newValue: boolean | string | number | null) {
  emit('updateConfig', index, newValue)
}


onMounted(async () => {
  if (!userStore.serviceConfig[props.service]) {
    await userStore.getServiceConfig(props.service);
  }
});

const notFoundText = computed(() => {
  return `未查询到 ${props.service.toUpperCase()} 服务配置信息`
});

const saveConfig = async () => {
  //@ts-ignore
  const config = userStore.serviceConfig[props.service]?.fields.map((field) => ({
    [field.key]: field.default
  }))
  await userStore.saveServiceConfig(props.service, config);
}

</script>

<template>
  <div
    class="w-full h-full"
    v-if="userStore.serviceConfig[props.service]?.fields"
  >
    <div class="service-config">
      <RowItem
        v-for="(configItem, index) in userStore.serviceConfig[props.service]?.fields"
        :key="configItem.key"
        class="config-row"
      >
        <!-- 左侧：标签 + 描述 -->
        <template #left>
          <div class="config-label">
            <span class="config-title">{{ configItem.label }}</span>

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
            @checked="(val: boolean) => updateConfig(index, val)"
            :checked="configItem.default as boolean"
          />
          <Select
            v-model="configItem.default as string"
            class="config-select"
            :options="configItem.options!"
            v-else-if="configItem.type === 'select'"
            @change="(val: string) => updateConfig(index, val)"
          />
          <Input
            v-else-if="configItem.type === 'string'"
            class="config-input"
            @input="(val: string) => updateConfig(index, val)"
            v-model="configItem.default as string"
          />
          <Input
            v-else-if="configItem.type === 'number'"
            class="config-input"
            @input="(val: number) => updateConfig(index, val)"
            v-model.number="configItem.default as number"
          />
          <Input
            v-else-if="configItem.type === 'password'"
            class="config-input"
            @input="(val: string) => updateConfig(index, val)"
            v-model="configItem.default as string"
            type="password"
          />
        </template>
      </RowItem>
    </div>

    <div class="config-btn">
      <Button
        type="big"
        style="width: 79%;"
        @click="saveConfig"
      >保存</Button>
      <Button
        type="big"
        style="width: 20%;"
        @click="$emit('applyConfig')"
      >应用</Button>
    </div>
  </div>
  <StatusMessage
    v-else
    message="请先保存服务配置"
  >
    {{ notFoundText }}
  </StatusMessage>
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
