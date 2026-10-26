<script setup lang="ts">
import { getSystemConfig, saveSystemConfig, type SystemConfig } from '@/api/services/config';

const systemConfig = ref<SystemConfig>({
  log_config: {
    level: "INFO",
    dir: "logs"
  },
  network_config: {
    port: 0,
    timeout: 30000
  }
});
const saving = ref(false);
const statusText = ref('');

const loadConfig = async () => {
  try {
    systemConfig.value = await getSystemConfig();
  } catch (error) {
    statusText.value = `加载失败: ${String(error)}`;
  }
};

const saveConfig = async () => {
  saving.value = true;
  statusText.value = '';
  try {
    await saveSystemConfig(systemConfig.value);
    statusText.value = '系统配置保存成功';
  } catch (error) {
    statusText.value = `保存失败: ${String(error)}`;
  } finally {
    saving.value = false;
  }
};

onMounted(loadConfig);
</script>

<template>
  <MenuPage>
    <MenuItem
      title="日志配置"
      button-text="保存"
      @click="saveConfig"
      size="small"
    >
    <div class="field">
      <FormCard title="日志等级">
        <select v-model="systemConfig.log_config.level">
          <option value="INFO">INFO</option>
          <option value="DEBUG">DEBUG</option>
          <option value="WARNING">WARNING</option>
          <option value="ERROR">ERROR</option>
        </select>
      </FormCard>
    </div>
    <div class="field">
      <FormCard title="日志目录">
        <input
          v-model="systemConfig.log_config.dir"
          placeholder="logs"
        />
      </FormCard>
    </div>
    <p class="status">{{ saving ? '保存中...' : statusText }}</p>
    </MenuItem>
    <MenuItem
      title="网络配置"
      button-text="保存"
      @click="saveConfig"
      size="small"
    >
    <div class="field">
      <FormCard title="网络超时(ms)">
        <input
          v-model="systemConfig.network_config.timeout"
          placeholder="30000"
        />
      </FormCard>
    </div>
    <p class="status">{{ saving ? '保存中...' : statusText }}</p>
    </MenuItem>
  </MenuPage>
</template>

<style scoped>
.field {
  display: grid;
  gap: 6px;
  margin-bottom: 10px;
}

input {
  height: 38px;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.2);
  color: #fff;
  background: rgba(0, 0, 0, 0.3);
  padding: 0 12px;
}

.status {
  margin-top: 6px;
  color: #c7ffd5;
  min-height: 22px;
}
</style>
