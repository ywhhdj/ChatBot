<script setup lang="ts">
/**
 * 右侧「自定义立绘」面板 
 */
import {
  useIllustrationStore,
  type IllustrationEditorTab,
} from '@/stores/illustration';
import type { ParsedModel } from './configs/illustrationTypes';
import type { DraggablePoint } from '@/composables/useDraggable';

type NoticeKind = 'info' | 'warning' | 'error' | 'success';

const emit = defineEmits<{
  notice: [message: string, kind: NoticeKind];
  /** 关闭前若 dirty，由页面层做确认 */
  requestClose: [];
}>();

const store = useIllustrationStore();

const TABS: ReadonlyArray<UI.TabItem> = [
  {
    id: 'parts',
    label: '自定义'
  },
  {
    id: 'stickers',
    label: '贴纸'
  },
  {
    id: 'model',
    label: '模型',
    icon: 'box'
  },
];

function forwardNotice(message: string, kind: NoticeKind) {
  emit('notice', message, kind);
}

function requestClose() {
  emit('requestClose');
}

/** TabBar emit 的是 string，这里按白名单收窄成联合类型 */
function onTabChange(id: string) {
  const allowed: IllustrationEditorTab[] = ['parts', 'stickers', 'model'];
  if (allowed.includes(id as IllustrationEditorTab)) store.setTab(id as IllustrationEditorTab);
}

function openModelTab() {
  store.setTab('model');
}

function onModelImport(model: ParsedModel) {
  store.applyModel(model);
  store.setTab('parts');
  emit('notice', `已用「${model.name}」的 ${model.parts.length} 个真实部件组装分层立绘`, 'success');
}

const PANEL_WIDTH = 360;
const initial: DraggablePoint = typeof window === 'undefined'
  ? { x: 24, y: 72 }
  : { x: Math.max(12, window.innerWidth - PANEL_WIDTH - 24), y: 72 };
</script>

<template>
  <Float
    title="自定义立绘"
    icon="character"
    :width="`${PANEL_WIDTH}px`"
    :initial="initial"
    :draggable="false"
    :collapsible="false"
    :z-index="40"
  >
    <template #badge>{{ store.layers.filter((l) => l.activeId).length }}/{{ store.layers.length }} 层 · {{ store.stickers.length }} 贴纸</template>

    <template #actions>
      <Button
        type="nav"
        aria-label="关闭自定义面板"
        @click="requestClose"
      ><Icon
        icon="close"
        :size="14"
      /></Button>
    </template>

    <template #default>
      <TabBar
        :tabs="TABS"
        :model-value="store.editorTab"
        aria-label="立绘编辑页签"
        @update:model-value="onTabChange"
      />

      <IllustrationPartSelector
        v-if="store.editorTab === 'parts'"
        @notice="forwardNotice"
        @open-model="openModelTab"
      />
      <IllustrationStickerPicker
        v-else-if="store.editorTab === 'stickers'"
        @notice="forwardNotice"
      />
      <ModelImportPanel
        v-else
        @notice="forwardNotice"
        @import="onModelImport"
      />
    </template>

    <template #footer>
      <p class="ae-foot">
        素材来自真实模型包或你选择的本地位图。「保存」整段写入后端存档的 ui 分区；「备份 / 导入」用于完整往返。
      </p>
    </template>
  </Float>
</template>

<style scoped>
.ae-foot {
  margin: 0;
  font-size: 10px;
  line-height: 1.6;
  opacity: 0.6;
  text-align: left;
}
</style>
