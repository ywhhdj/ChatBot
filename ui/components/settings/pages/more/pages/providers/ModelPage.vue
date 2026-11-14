<script setup lang="ts">
import { useModelProvider } from "@/composables/useModelProvider";

const props = defineProps<{
  capability: Model.Capability;
}>();

const {
  preset,
  state,
  pending,
  notice,
  offline,
  providers,
  activeProvider,
  activeModel,
  currentProvider,
  models,
  detail,
  status,
  usage,
  values,
  fields,
  maskedKeys,
  invalidFields,
  warnings,
  missingEnv,
  isLocal,
  installed,
  canApply,
  dirty,
  downloadProgress,
  downloadPhase,
  load,
  refresh,
  refreshIfStale,
  selectProvider,
  selectModel,
  setParam,
  setSecret,
  apply,
  stop,
  download,
  activate,
  deactivate,
} = useModelProvider(props.capability);

/** 首次进入只加载一次；被 KeepAlive 重新激活时按 TTL 决定是否刷新 */
let started = false;
const startOnce = () => {
  if (started) return;
  started = true;
  void load();
};

onMounted(() => {
  startOnce();
  activate();
});
onActivated(() => {
  if (!started) startOnce();
  else refreshIfStale();
  activate();
});
onDeactivated(deactivate);
</script>

<template>
  <div class="model-page">
    <!-- 对话框式抬头：沿用 base/Text 的打字机与 base/Icon 的图标 -->
    <MenuItem
      size="large"
      :title="preset.title"
      :icon="preset.icon"
    >
      <div class="dialog-line">
        <span class="dialog-name">{{ preset.subtitle }}</span>
        <Text
          class="dialog-text"
          :speed="98"
          :min-delay="12"
          :max-delay="55"
          :show-cursor="true"
        >{{ preset.intro }}</Text>
      </div>
      <ModelProviderNav
        :providers="providers"
        :active-name="activeProvider"
        :loading="pending === 'load'"
        :offline="offline"
        :disabled="pending !== null"
        @select="selectProvider"
        @refresh="refresh"
      />
    </MenuItem>

    <MenuItem
      size="small"
      title="模型清单"
      button-text="刷新"
      @click="refresh"
    >
      <StatusMessage v-if="state === 'loading' && !providers.length">
        正在读取模型描述……
      </StatusMessage>
      <StatusMessage v-else-if="!models.length">
        该供应商暂无可用模型
      </StatusMessage>
      <div v-else class="model-grid">
        <ModelCard
          v-for="model in models"
          :key="model.id"
          :model="model"
          :selected="model.id === activeModel"
          :installed="installed && model.id === activeModel"
          :disabled="pending !== null"
          @select="selectModel"
        />
      </div>
      <p class="grid-foot">
        <span class="mono">{{ activeProvider || "—" }}</span>
        <span>{{ models.length }} 个模型 · {{ fields.length }} 项参数</span>
      </p>
    </MenuItem>

    <MenuItem
      size="small"
      title="参数设定"
    >
      <StatusMessage v-if="!fields.length">
        该供应商未声明可配置参数
      </StatusMessage>
      <template v-else>
        <ModelParamGroup
          scope="init"
          :fields="fields"
          :values="values"
          :masked-keys="maskedKeys"
          :disabled="offline || pending !== null"
          @change="setParam"
          @secret="setSecret"
        />
        <ModelParamGroup
          scope="request"
          :fields="fields"
          :values="values"
          :masked-keys="maskedKeys"
          :disabled="offline || pending !== null"
          @change="setParam"
          @secret="setSecret"
        />
        <ModelParamGroup
          scope="unknown"
          :fields="fields"
          :values="values"
          :masked-keys="maskedKeys"
          :disabled="offline || pending !== null"
          @change="setParam"
          @secret="setSecret"
        />
        <p class="param-tip">
          端点与连接字段由服务端配置决定，仅展示不提交；密钥只写不回显。
        </p>
      </template>
    </MenuItem>

    <MenuItem
      size="large"
      title="运行状态"
      button-text="刷新状态"
      @click="refresh"
    >
      <ModelStatusPanel
        :status="status"
        :detail="detail"
        :usage="usage"
        :provider="currentProvider"
        :models="models"
        :warnings="warnings"
        :missing-env="missingEnv"
        :progress="downloadProgress"
        :phase="downloadPhase"
        :offline="offline"
      />
      <ModelActionBar
        :pending="pending"
        :dirty="dirty"
        :can-apply="canApply"
        :can-stop="!offline && !!activeProvider"
        :is-local="isLocal"
        :installed="installed"
        :offline="offline"
        :notice="notice"
        :invalid-count="invalidFields.length"
        @apply="apply"
        @stop="stop"
        @download="download"
        @refresh="refresh"
      />
    </MenuItem>
  </div>
</template>

<style scoped>
.model-page {
  width: 100%;
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 25px;
}

.dialog-line {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-bottom: 14px;
  padding: 10px 16px 8px;
  border-left: 2px solid var(--primary-color);
  border-radius: 12px;
  background: rgba(0, 0, 0, 0.3);
  box-shadow: inset 0 2px 8px rgba(0, 0, 0, 0.25);
  backdrop-filter: blur(8px);
}

.dialog-name {
  font-size: 11px;
  letter-spacing: 1px;
  color: #ffd700;
  text-shadow: 0 0 8px rgba(255, 215, 0, 0.45);
}

.dialog-text {
  font-size: 13px;
  line-height: 1.5;
  color: #f7f8ff;
}

/* base/Text 自带一层终端底框；在对话框里只保留打字机文本 */
.dialog-line :deep(.dialog-text) {
  min-height: 0;
  padding: 2px 0;
  background: transparent;
  border: none;
  box-shadow: none;
  backdrop-filter: none;
}

.model-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
  gap: 12px;
}

.grid-foot {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  margin-top: 10px;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.6);
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.5);
}

.mono {
  font-family: var(--font-mono);
  color: #a9e6ff;
}

.param-tip {
  margin-top: 8px;
  font-size: 11px;
  line-height: 1.5;
  color: rgba(255, 255, 255, 0.55);
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.5);
}

@media (max-width: 768px) {
  .model-page {
    gap: 12px;
  }

  .model-grid {
    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  }
}
</style>
