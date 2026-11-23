<script setup lang="ts">
/**
 * 通用文件选择器
 *
 * 全站只此一个 `<input type="file">` 实现：背景、音乐、立绘部件、贴纸、
 * 模型包目录、配置导入都复用它。校验/去重/读取统一交给 `utils/assetFile`，
 */
import { ref } from 'vue';
import {
  acceptString,
  loadAssets,
  type AssetKind,
  type LoadedAsset,
  type LoadOptions,
} from '@/utils/asset';
import Button from '@/components/base/Button.vue';
import Icon from '@/components/base/Icon.vue';

const props = withDefaults(
  defineProps<{
    kind: AssetKind;
    label?: string;
    icon?: UI.IconType;
    multiple?: boolean;
    /** 目录模式（选 Live2D/VTS 模型包文件夹） */
    directory?: boolean;
    disabled?: boolean;
    accept?: string;
    maxBytes?: number;
    maxFiles?: number;
    existing?: ReadonlySet<string>;
    /** 文本类读取内容（模型包 / JSON） */
    readText?: boolean;
    /** 只校验并保留 File，不读内容（配合 useObjectUrls 用 blob URL） */
    rawOnly?: boolean;
    /** 是否显示内置触发按钮；false 时由父级用 slot 自定义触发器 */
    showTrigger?: boolean;
    buttonType?: UI.ButtonType;
  }>(),
  {
    label: '选择文件',
    icon: 'plus',
    multiple: true,
    directory: false,
    disabled: false,
    accept: '',
    maxBytes: 8 * 1024 * 1024,
    maxFiles: 60,
    readText: false,
    rawOnly: false,
    showTrigger: true,
    buttonType: 'nav',
  }
);

const emit = defineEmits<{
  select: [assets: LoadedAsset[]];
  error: [message: string];
  warnings: [messages: string[]];
}>();

const inputRef = ref<HTMLInputElement | null>(null);
const busy = ref(false);

function open() {
  if (props.disabled || busy.value) return;
  inputRef.value?.click();
}

async function onChange(event: Event) {
  const input = event.target as HTMLInputElement;
  const files = input.files;
  // 立刻清空，允许连续选同一个文件
  input.value = '';
  if (!files?.length) return;
  busy.value = true;
  try {
    const options: LoadOptions = {
      maxBytes: props.maxBytes,
      maxFiles: props.maxFiles,
      existing: props.existing,
      readText: props.readText,
      rawOnly: props.rawOnly,
      looseMime: props.kind === 'model',
    };
    const assets = await loadAssets(files, props.kind, options);
    emit('select', assets);
    const warns = (assets as LoadedAsset[] & { warnings?: string[] }).warnings;
    if (warns?.length) emit('warnings', warns);
  } catch (err) {
    emit('error', err instanceof Error ? err.message : '文件读取失败');
  } finally {
    busy.value = false;
  }
}

defineExpose({ open });
</script>

<template>
  <span class="asset-picker">
    <input
      ref="inputRef"
      class="hidden"
      type="file"
      :accept="accept || acceptString(kind)"
      :multiple="multiple && !directory"
      v-bind="directory ? { webkitdirectory: '', directory: '' } : {}"
      :aria-label="label"
      @change="onChange"
    />
    <Button
      v-if="showTrigger"
      :type="buttonType"
      :disabled="disabled || busy"
      :aria-label="label"
      @click="open"
    >
      <Icon
        :icon="icon"
        :size="14"
      />
      {{ busy ? '读取中…' : label }}
    </Button>
    <slot
      v-else
      :open="open"
      :busy="busy"
    />
  </span>
</template>

<style scoped>
.asset-picker {
  display: inline-flex;
  align-items: center;
}
</style>
