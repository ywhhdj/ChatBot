<script setup lang="ts">
/**
 * 聊天页外壳
 *
 * 保留顶部导航与底部对话框；中间是「真实模型部件分层拼装 + 贴纸画布」，
 * 右上角编辑图标切换右侧「自定义 / 贴纸 / 模型」面板。
 */
import { onBeforeRouteLeave } from 'vue-router';
import { useIllustrationStore } from '@/stores/Illustration';
import { errorView, toApiClientError } from '@/api/decoder';
import notification from '@/utils/notification';
import {
  exportJson,
  exportPng,
  parseSnapshotText,
  resolveSaveTarget,
  saveToBackend,
} from '@/components/views/chat/illustration/configs/persistence';
import type { LoadedAsset } from '@/utils/asset';

type ActionName = 'save' | 'toggleVisible' | 'exportPng' | 'exportJson' | 'import';
type NoticeKind = 'info' | 'warning' | 'error' | 'success';

interface PendingConfirm {
  spec: UI.ConfirmSpec;
  onConfirm: () => void;
  onCancel?: () => void;
}

const store = useIllustrationStore();
const importPicker = ref<any>(null);
const pending = ref<PendingConfirm | null>(null);
const confirmSpec = ref<UI.ConfirmSpec | null>(null);

let actionToken = 0;

function onNotice(message: string, kind: NoticeKind) {
  const payload = { title: '自定义立绘', message };
  if (kind === 'error') notification.showError(payload);
  else if (kind === 'warning') notification.showWarning(payload);
  else if (kind === 'success') notification.showSuccess(payload);
  else notification.showInfo(payload);
}

function openConfirm(item: PendingConfirm) {
  pending.value = item;
  confirmSpec.value = item.spec;
}

function acceptConfirm() {
  const item = pending.value;
  pending.value = null;
  confirmSpec.value = null;
  item?.onConfirm();
}

function cancelConfirm() {
  const item = pending.value;
  pending.value = null;
  confirmSpec.value = null;
  item?.onCancel?.();
}

/** Esc 单一入口：确认框优先取消，其次才请求关闭编辑面板 */
function onGlobalKeydown(event: KeyboardEvent) {
  if (event.key !== 'Escape') return;
  if (confirmSpec.value) {
    event.preventDefault();
    cancelConfirm();
    return;
  }
  if (store.editVisible) {
    event.preventDefault();
    onRequestClose();
  }
}

onMounted(() => document.addEventListener('keydown', onGlobalKeydown));
onBeforeUnmount(() => document.removeEventListener('keydown', onGlobalKeydown));

// ---------- 顶部工具动作 ----------

async function onSave() {
  if (store.saving) return;
  const token = ++actionToken;
  store.setSaving(true);
  try {
    const target = await resolveSaveTarget();
    if (token !== actionToken) return;
    if (!target) {
      notification.showWarning({
        title: '未找到存档槽',
        message: '请先在「设置 → 存档」创建存档槽，或点「备份」导出配置文件',
      });
      return;
    }
    await saveToBackend(target.slotId, store.snapshot());
    if (token !== actionToken) return;
    store.markClean();
    notification.showSuccess({
      title: '已保存',
      message: `装扮已整段写入存档「${target.slotName}」的 ui 分区；完整备份请用「备份」`,
    });
  } catch (err) {
    if (token !== actionToken) return;
    const view = errorView(toApiClientError(err));
    const fallback = err instanceof Error ? err.message : '请稍后重试';
    notification.showError({
      title: view?.title || '保存失败',
      message: view?.message || fallback.slice(0, 200),
    });
  } finally {
    if (token === actionToken) store.setSaving(false);
  }
}

async function onExportPng() {
  try {
    await exportPng(store.snapshot());
    notification.showSuccess({ title: '已导出', message: '合成图片已开始下载' });
  } catch (err) {
    notification.showError({
      title: '导出图片失败',
      message: err instanceof Error ? err.message : '请改用「备份」导出配置',
    });
  }
}

function onExportJson() {
  try {
    exportJson(store.snapshot());
    notification.showSuccess({ title: '已备份', message: '配置文件已开始下载，可用「导入」恢复' });
  } catch (err) {
    notification.showError({ title: '备份失败', message: err instanceof Error ? err.message : '请稍后重试' });
  }
}

function onImportClick() {
  const apply = () => importPicker.value?.open?.();
  if (!store.dirty) {
    apply();
    return;
  }
  openConfirm({
    spec: {
      title: '导入会覆盖当前编辑',
      message: '当前有未保存的修改，导入配置文件会替换它们。建议先「保存」或「备份」。',
      confirmText: '仍要导入',
      cancelText: '继续编辑',
      danger: true,
    },
    onConfirm: apply,
  });
}

function onImportFiles(assets: LoadedAsset[]) {
  const first = assets[0];
  if (!first?.text) {
    notification.showError({ title: '导入失败', message: '配置文件内容为空' });
    return;
  }
  try {
    const snapshot = parseSnapshotText(first.text);
    store.hydrate(snapshot);
    notification.showSuccess({
      title: '导入成功',
      message: snapshot.modelMeta
        ? `已恢复「${snapshot.modelMeta.name}」的 ${snapshot.layers.length} 层装扮`
        : '装扮配置已恢复',
    });
  } catch (err) {
    notification.showError({
      title: '导入失败',
      message: err instanceof Error ? err.message : '配置文件不受支持',
    });
  }
}

function onImportError(message: string) {
  notification.showError({ title: '读取配置失败', message });
}

function onAction(name: ActionName) {
  switch (name) {
    case 'save': void onSave(); break;
    case 'toggleVisible': store.toggleVisible(); break;
    case 'exportPng': void onExportPng(); break;
    case 'exportJson': onExportJson(); break;
    case 'import': onImportClick(); break;
  }
}

// ---------- 关闭 / 重置 / 离开：未保存确认 ----------

function onRequestClose() {
  if (!store.dirty) {
    store.confirmEdit();
    return;
  }
  openConfirm({
    spec: {
      title: '有未保存的装扮修改',
      message: '关闭面板不会丢弃当前编辑，但修改尚未写入存档。建议先「保存」或「备份」。',
      confirmText: '仍要关闭',
      cancelText: '继续编辑',
    },
    onConfirm: () => store.confirmEdit(),
  });
}

function onToggleEdit() {
  store.setEditVisible(true);
}

function onResetRequest() {
  openConfirm({
    spec: {
      title: '重置全部装扮',
      message: '会清空模型部件层、贴纸与贴纸实例，且不可撤销。建议先「备份」。',
      confirmText: '确认重置',
      cancelText: '取消',
      danger: true,
    },
    onConfirm: () => {
      store.reset();
      onNotice('已重置为空白模板', 'info');
    },
  });
}

onBeforeRouteLeave((_to, _from, next) => {
  if (!store.dirty) {
    next();
    return;
  }
  openConfirm({
    spec: {
      title: '有未保存的装扮修改',
      message: '离开后本次编辑不会写入存档。建议先「保存」或「备份」。',
      confirmText: '仍要离开',
      cancelText: '继续编辑',
      danger: true,
    },
    onConfirm: () => {
      store.markClean();
      next();
    },
    onCancel: () => next(false),
  });
});
</script>

<template>
  <header style="margin: 10px;">
    <ChatNav
      :editing="store.editVisible"
      :saving="store.saving"
      :avatar-visible="store.global.visible"
      :dirty="store.dirty"
      @toggle-edit="onToggleEdit"
      @close-edit="onRequestClose"
      @action="onAction"
    />
  </header>

  <main class="chat-main">
    <IllustrationStage
      :editing="store.editVisible"
      @reset="onResetRequest"
    />
    <ChatStage :avatar-editing="store.editVisible" />
  </main>

  <IllustrationEditorPanel
    v-if="store.editVisible"
    @notice="onNotice"
    @request-close="onRequestClose"
  />

  <!-- 配置导入统一走全站 AssetPicker，不再手写 input / FileReader -->
  <AssetPicker
    ref="importPicker"
    kind="json"
    label="选择装扮配置文件"
    :show-trigger="false"
    :multiple="false"
    :read-text="true"
    :max-bytes="8 * 1024 * 1024"
    :max-files="1"
    @select="onImportFiles"
    @error="onImportError"
  />

  <ConfirmDialog
    :spec="confirmSpec"
    @confirm="acceptConfirm"
    @cancel="cancelConfirm"
  />
</template>

<style scoped>
.chat-main {
  position: relative;
  flex: 1 1 auto;
  width: 100%;
  min-height: 0;
}
</style>

