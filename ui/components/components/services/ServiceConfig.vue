<script setup lang="ts">
import { useUserStore } from "@/stores/user";

const userStore = useUserStore();

const props = defineProps<{
  service: API.ServiceId;
}>();

const emit = defineEmits(["applyConfig"]);

const fields = computed(() => userStore.serviceConfig[props.service]?.fields ?? []);

/** options 兼容 [{value,label}] / [{id,label}] / 原始值 */
function selectOptions(item: any) {
  return (item.options ?? []).map((o: any) =>
    typeof o === "object" && o !== null
      ? { id: o.value ?? o.id, label: o.label ?? String(o.value ?? o.id) }
      : { id: o, label: String(o) },
  );
}

/** 统一回写 store；number 做一次安全转换 */
function setField(index: number, value: unknown) {
  const item = userStore.serviceConfig[props.service]?.fields?.[index];
  if (!item) return;
  if (item.type === "number") {
    const n = Number(value);
    item.default = Number.isFinite(n) ? n : item.default;
    return;
  }
  item.default = value;
}

onMounted(async () => {
  ui=await serviceService.serviceUi(props.service);
  if (!userStore.serviceConfig[props.service]) {
    await userStore.getServiceConfig(props.service);
  }
});

const notFoundText = computed(
  () => `未查询到 ${props.service.toUpperCase()} 服务配置信息`,
);

const saveConfig = async () => {
  let config={}
  userStore.serviceConfig[props.service]?.fields.map((field: any) => (config[field.key]=field.default));
  await userStore.saveServiceConfig(props.service, config:{config});
};


const applyConfig = async () => {
  await serviceService.applyServiceConfig(props.service);
};
</script>

<template>
  <div v-if="userStore.serviceConfig[props.service]?.fields" class="w-full h-full">
    <div class="service-config">
      <FormRow
        v-for="(item, index) in fields"
        :key="item.key"
        :label="item.label"
        :description="item.description || ''"
        :model-value="item.default"
        @update:model-value="(v) => setField(index, v)"
      >
        <template #default="{ update }">
          <!-- 布尔：Checkbox 用 checked 事件，不要用 click -->
          <Checkbox
            v-if="item.type === 'boolean'"
            :checked="Boolean(item.default)"
            @checked="(v: boolean) => update(v)"
          />

          <!-- 枚举 -->
          <Select
            v-else-if="item.type === 'select'"
            :model-value="String(item.default ?? '')"
            :options="selectOptions(item)"
            @change="(v: string) => update(v)"
          />

          <!-- 数字：只在这里用 numeric 键盘 -->
          <Input
            v-else-if="item.type === 'number'"
            :model-value="String(item.default ?? '')"
            inputmode="decimal"
            @change="(v: string) => update(v)"
            @enter="(v: string) => update(v)"
          />

          <!-- 密码 -->
          <Input
            v-else-if="item.type === 'password'"
            type="password"
            :model-value="String(item.default ?? '')"
            @change="(v: string) => update(v)"
            @enter="(v: string) => update(v)"
          />

          <!-- 字符串（路径、尺寸等），不要 inputmode="numeric" -->
          <Input
            v-else
            :model-value="String(item.default ?? '')"
            @change="(v: string) => update(v)"
            @enter="(v: string) => update(v)"
          />
        </template>
      </FormRow>
    </div>

    <div class="config-btn">
      <Button type="big" style="width: 79%;" @click="saveConfig">保存</Button>
      <Button type="big" style="width: 20%;" @click="emit('applyConfig')">应用</Button>
    </div>
  </div>

  <StatusMessage v-else message="请先保存服务配置">
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

.config-btn {
  align-self: flex-end;
  display: flex;
  gap: 10px;
}
</style>