<script setup lang="ts">
/**
 * 模型包导入面板
 *
 * 选一个真实的 Live2D / VTS 模型文件夹 → 解析 → 预览部件清单 → 组装成分层立绘。
 * 不内置任何示例模型，不伪造部件；解析不确定性由 warnings 如实展示。
 */
import { parseModelBundle } from './configs/modelParser';
import type { ParsedModel } from './configs/modelTypes';
import type { LoadedAsset } from '@/utils/asset';

const emit = defineEmits<{
  import: [model: ParsedModel];
  notice: [message: string, kind: 'info' | 'warning' | 'error' | 'success'];
}>();

const model = shallowRef<ParsedModel | null>(null);
const parsing = ref(false);
const error = ref('');

const FORMAT_LABEL: Record<string, string> = {
  cubism2: 'Cubism 2.1（model.json）',
  cubism3: 'Cubism 3/4（.model3.json）',
  vts: 'VTube Studio（.vtube.json + .model3.json）',
  loose: '散落 PNG 目录（兜底）',
};

async function onFiles(assets: LoadedAsset[]) {
  parsing.value = true;
  error.value = '';
  model.value = null;
  try {
    const parsed = await parseModelBundle(assets);
    model.value = parsed;
    emit('notice', `已解析「${parsed.name}」：${parsed.parts.length} 个部件`, parsed.parts.length ? 'success' : 'warning');
  } catch (err) {
    error.value = err instanceof Error ? err.message : '模型包解析失败';
    emit('notice', error.value, 'error');
  } finally {
    parsing.value = false;
  }
}

function onError(message: string) {
  error.value = message;
  emit('notice', message, 'error');
}

function doImport() {
  if (!model.value?.parts.length) return;
  emit('import', model.value);
}
</script>

<template>
  <div class="model-import">
    <p class="mi-intro">
      选择一个 <strong>Live2D / VTS 模型文件夹</strong>，读取其中的
      <code>model.json</code> / <code>.model3.json</code>、
      <code>.cdi3.json</code>、<code>.vtube.json</code> 与纹理 PNG，
      把真实部件组装成分层立绘。
    </p>

    <AssetPicker
      kind="model"
      label="选择模型文件夹"
      icon="box"
      :directory="true"
      :multiple="false"
      :read-text="true"
      :max-bytes="24 * 1024 * 1024"
      :max-files="200"
      :disabled="parsing"
      @select="onFiles"
      @error="onError"
    />

    <p class="mi-limit">
      <Icon
        icon="more"
        :size="12"
      />
      <code>.moc3</code> 是编译二进制，ArtMesh 网格不在 JSON 里；本页不解析它、不引入 Cubism SDK。
      合并图集会按 alpha 连通区域切分，结果不保证与 ArtMesh 一一对应。
    </p>

    <div
      v-if="parsing"
      class="mi-state"
    >正在解析模型包…</div>

    <div
      v-else-if="error"
      class="mi-state is-error"
    >{{ error }}</div>

    <template v-if="model">
      <div class="mi-head">
        <strong>{{ model.name }}</strong>
        <span>{{ FORMAT_LABEL[model.format] || model.format }}</span>
      </div>

      <div class="mi-meta">
        <span>部件 {{ model.parts.length }}</span>
        <span>纹理 {{ model.meta.textureFiles.length }}</span>
        <span v-if="model.meta.hasMoc3">含 moc3</span>
        <span v-if="model.meta.hasVtube">VTS 配置</span>
        <span v-if="model.meta.hasCdi3">含部件名</span>
      </div>

      <ul
        v-if="model.warnings.length"
        class="mi-warnings"
      >
        <li
          v-for="(w, i) in model.warnings"
          :key="i"
        >{{ w }}</li>
      </ul>

      <div
        v-if="model.parts.length"
        class="mi-grid"
      >
        <div
          v-for="part in model.parts.slice(0, 12)"
          :key="part.id"
          class="mi-cell"
          :title="part.note || part.texture"
        >
          <AssetImage
            :src="part.src"
            :alt="part.label"
            hint
          />
          <span>{{ part.label }}</span>
        </div>
        <div
          v-if="model.parts.length > 12"
          class="mi-more"
        >+{{ model.parts.length - 12 }} 个部件</div>
      </div>

      <div class="mi-actions">
        <Button
          type="select"
          :disabled="!model.parts.length"
          @click="doImport"
        >组装为分层立绘</Button>
        <Button
          type="nav"
          @click="model = null"
        >清除</Button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.model-import {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.mi-intro {
  margin: 0;
  font-size: 12px;
  line-height: 1.8;
  opacity: 0.85;
}

.mi-intro code,
.mi-limit code {
  padding: 1px 4px;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.1);
  font-family: ui-monospace, Menlo, monospace;
  font-size: 10px;
}

.mi-limit {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin: 0;
  font-size: 11px;
  line-height: 1.7;
  opacity: 0.68;
}

.mi-state {
  padding: 10px;
  border-radius: 8px;
  border: 1px dashed rgba(255, 255, 255, 0.22);
  font-size: 12px;
  text-align: center;
}

.mi-state.is-error {
  color: #ffcdd2;
  border-color: rgba(244, 67, 54, 0.5);
}

.mi-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  padding-bottom: 6px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.16);
}

.mi-head strong {
  font-family: 'Maoken Assorted Sans', -apple-system, BlinkMacSystemFont, sans-serif;
  font-size: 15px;
}

.mi-head span {
  font-size: 10px;
  opacity: 0.7;
}

.mi-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  font-family: ui-monospace, Menlo, monospace;
  font-size: 10px;
}

.mi-meta span {
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.08);
}

.mi-warnings {
  margin: 0;
  padding: 8px 8px 8px 22px;
  border-radius: 8px;
  background: rgba(251, 191, 36, 0.08);
  border: 1px solid rgba(251, 191, 36, 0.25);
  font-size: 10px;
  line-height: 1.7;
  opacity: 0.85;
}

.mi-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 6px;
}

.mi-cell {
  position: relative;
  aspect-ratio: 1;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(0, 14, 39, 0.45);
  overflow: hidden;
}

.mi-cell span {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  padding: 2px 4px;
  font-size: 9px;
  text-align: center;
  background: rgba(0, 14, 39, 0.8);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.mi-more {
  display: grid;
  place-items: center;
  aspect-ratio: 1;
  border-radius: 8px;
  border: 1px dashed rgba(255, 255, 255, 0.2);
  font-size: 11px;
  opacity: 0.7;
}

.mi-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 8px;
  border-top: 1px dashed rgba(255, 255, 255, 0.18);
}

.mi-actions :deep(button) {
  min-height: 34px;
  font-size: 12px;
}
</style>
