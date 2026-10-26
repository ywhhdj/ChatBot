<script setup lang="ts">
import { getAdvancedConfig, saveAdvancedConfig } from '@/api/services/config';
import type { AdvancedConfig } from '@/api/services/config';

const defaultConfig: AdvancedConfig = {
  install_components: [],
  code_highlight: {
    enabled: true,
    theme: 'github-dark',
  },
  extra: {},
};

const jsonText = ref(JSON.stringify(defaultConfig, null, 2));
const saving = ref(false);
const statusText = ref('');

const loadConfig = async () => {
  try {
    const data = await getAdvancedConfig();
    jsonText.value = JSON.stringify(data, null, 2);
  } catch (error) {
    statusText.value = `加载失败: ${String(error)}`;
  }
};

const saveConfig = async () => {
  saving.value = true;
  statusText.value = '';
  try {
    const parsed = JSON.parse(jsonText.value) as AdvancedConfig;
    await saveAdvancedConfig(parsed);
    statusText.value = '高级配置保存成功';
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
      title="高级配置 JSON"
      button-text="保存"
      @click="saveConfig"
    >
    <Code
      language="json"
      class="json-editor"
      editable
      :code="jsonText"
    />
    <p class="status">{{ saving ? '保存中...' : statusText }}</p>
    </MenuItem>
  </MenuPage>
</template>

<style scoped>
.tips {
  margin-bottom: 10px;
  opacity: 0.9;
}

.json-editor {
  width: 100%;
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.35);
  color: #f7f8ff;
  padding: 10px 12px;
  font-family: Consolas, Monaco, monospace;
}

.status {
  margin-top: 8px;
  min-height: 22px;
  color: #c7ffd5;
}
</style>
