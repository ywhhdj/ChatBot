<script setup lang="ts">
/**
 * 「自定义」页
 */
import { useIllustrationStore } from '@/stores/illustration';
import { LIMITS, type PartKey, type PartOption } from './configs/illustrationTypes';
import { assetFingerprints, assetWarnings, type LoadedAsset } from '@/utils/asset';

const emit = defineEmits<{
  notice: [message: string, kind: 'info' | 'warning' | 'error' | 'success'];
  openModel: [];
}>();

const store = useIllustrationStore();
const pickerRef = ref<any>(null);
const targetKey = ref<PartKey>('');
const collapsedGroups = ref<Set<string>>(new Set());

const totalOptions = computed(() => store.layers.reduce((sum, l) => sum + l.options.length, 0));

/** 行数据在 computed 里算一次，模板不再做 map（避免每次渲染重建对象） */
const groups = computed(() =>
  store.layerGroups.map((g) => ({
    label: g.label,
    rows: g.layers.map((layer) => {
      const index = layer.options.findIndex((o) => o.id === layer.activeId);
      return {
        layer,
        index,
        total: layer.options.length,
        current: index >= 0 ? layer.options[index] : null,
      };
    }),
  }))
);
const existingFingerprints = computed(() => {
  const layer = store.layers.find((l) => l.key === targetKey.value);
  return assetFingerprints(layer?.options || []);
});
const sourceLabel = computed(() => {
  const m = store.modelMeta;
  if (!m) return '空白模板（默认 7 组）';
  const map: Record<string, string> = {
    cubism2: 'Cubism 2.1',
    cubism3: 'Cubism 3/4',
    vts: 'VTube Studio',
    loose: '散落 PNG 目录',
  };
  return `${map[m.format] || m.format} · ${m.name} · ${m.partCount} 部件`;
});

function addTo(key: PartKey) {
  targetKey.value = key;
  pickerRef.value?.open?.();
}

function onFiles(assets: LoadedAsset[]) {
  const key = targetKey.value;
  const layer = store.layers.find((l) => l.key === key);
  if (!layer) return;
  let added = 0;
  for (const a of assets) {
    const option: PartOption = { id: a.id, label: a.label, src: a.src, width: a.width, height: a.height };
    if (store.addLayerOption(key, option)) added += 1;
  }
  const warnings = assetWarnings(assets);
  emit('notice', `已添加 ${added} 张「${layer.label}」部件素材`, added ? 'success' : 'warning');
  if (warnings.length) emit('notice', warnings.slice(0, 2).join('；'), 'warning');
}

function onError(message: string) {
  emit('notice', message, 'error');
}

function cyclePrev(key: PartKey) {
  store.cycleLayerOption(key, -1);
}
function cycleNext(key: PartKey) {
  store.cycleLayerOption(key, 1);
}
function onVisibleChange(key: PartKey, value: unknown) {
  store.setLayerVisible(key, Boolean(value));
}
function onOpacityInput(key: PartKey, value: unknown) {
  store.setLayerOpacity(key, Number(value));
}

function removeCurrent(row: { layer: { key: PartKey }; current: PartOption | null }) {
  if (!row.current) return;
  store.removeLayerOption(row.layer.key, row.current.id);
  emit('notice', '已移除当前部件素材', 'info');
}

function toggleGroup(label: string) {
  const next = new Set(collapsedGroups.value);
  if (next.has(label)) next.delete(label);
  else next.add(label);
  collapsedGroups.value = next;
}

function resetTemplate() {
  store.clearModel();
  emit('notice', '已恢复空白模板（默认 7 组）', 'info');
}
</script>

<template>
  <div class="part-selector">
    <!-- 全组件唯一一个文件选择器：所有层共用 -->
    <AssetPicker
      ref="pickerRef"
      kind="image"
      label="添加部件图片"
      :show-trigger="false"
      :max-bytes="LIMITS.maxFileBytes"
      :max-files="LIMITS.maxOptionsPerLayer"
      :existing="existingFingerprints"
      @select="onFiles"
      @error="onError"
    />

    <div class="ps-source">
      <span :title="sourceLabel">来源：{{ sourceLabel }}</span>
      <Button
        type="nav"
        @click="emit('openModel')"
      ><Icon
        icon="box"
        :size="13"
      />导入模型包</Button>
      <Button
        v-if="store.modelMeta"
        type="nav"
        @click="resetTemplate"
      >空白模板</Button>
    </div>

    <p
      v-if="store.modelMeta?.warnings.length"
      class="ps-warnings"
      :title="store.modelMeta.warnings.join('；')"
    >
      解析提示 {{ store.modelMeta.warnings.length }} 条 · {{ store.modelMeta.warnings[0] }}
    </p>

    <div class="ps-head">
      <span>{{ store.layers.length }} 层 · 共 {{ totalOptions }} 张素材</span>
      <span class="ps-hint">按真实 z 顺序叠放</span>
    </div>

    <p
      v-if="!totalOptions"
      class="ps-empty"
    >
      还没有任何部件素材。<br />
      可「导入模型包」从真实 Live2D / VTS 部件组装，或每行点「＋ 添加」选择本地位图。<br />
      <small>SVG 出于安全考虑不接受；单张 ≤2MB，每层最多 12 张。</small>
    </p>

    <div
      v-for="group in groups"
      :key="group.label"
      class="ps-group"
    >
      <button
        type="button"
        class="ps-group-head"
        :aria-expanded="!collapsedGroups.has(group.label)"
        @click="toggleGroup(group.label)"
      >
        <span>{{ group.label }}</span>
        <span>{{ group.layers.length }} 层 {{ collapsedGroups.has(group.label) ? '▸' : '▾' }}</span>
      </button>

      <ul
        v-show="!collapsedGroups.has(group.label)"
        class="ps-list"
      >
        <li
          v-for="row in group.rows"
          :key="row.layer.key"
          class="ps-row"
          :class="{ 'is-off': !row.layer.visible }"
        >
          <div class="ps-line">
            <span
              class="ps-name"
              :title="row.layer.note || row.layer.label"
            >{{ row.layer.label }}</span>

            <Button
              type="nav"
              :disabled="row.total < 2"
              aria-label="上一个部件"
              @click="cyclePrev(row.layer.key)"
            >‹</Button>

            <span
              class="ps-value"
              :title="row.current?.label || ''"
            >
              <template v-if="row.current">
                {{ row.index + 1 }}/{{ row.total }} · {{ row.current.label }}
              </template>
              <template v-else>未添加</template>
            </span>

            <Button
              type="nav"
              :disabled="row.total < 2"
              aria-label="下一个部件"
              @click="cycleNext(row.layer.key)"
            >›</Button>

            <Button
              type="nav"
              class="ps-add"
              :disabled="row.total >= LIMITS.maxOptionsPerLayer"
              :aria-label="`为${row.layer.label}添加图片`"
              @click="addTo(row.layer.key)"
            ><Icon
              icon="plus"
              :size="14"
            />添加</Button>
          </div>

          <div class="ps-sub">
            <label class="ps-check">
              <Checkbox
                :checked="row.layer.visible"
                @click="onVisibleChange(row.layer.key, $event)"
              />
              <span>显示</span>
            </label>
            <Button
              type="nav"
              :disabled="!row.current"
              :aria-pressed="row.layer.flipX"
              aria-label="翻转该层"
              @click="store.setLayerFlip(row.layer.key, !row.layer.flipX)"
            ><Icon
              icon="flip"
              :size="13"
            />翻转</Button>
            <Button
              type="nav"
              :disabled="!row.current"
              aria-label="移除当前部件"
              @click="removeCurrent(row)"
            ><Icon
              icon="delete"
              :size="13"
            />移除</Button>
          </div>

          <div class="ps-opacity">
            <span>透明度</span>
            <Silder
              :value="row.layer.opacity"
              :min="LIMITS.opacityMin"
              :max="LIMITS.opacityMax"
              :step="0.05"
              @input="onOpacityInput(row.layer.key, $event)"
            />
          </div>

          <div
            v-if="row.current"
            class="ps-preview"
          >
            <AssetImage
              :src="row.current.src"
              :alt="row.current.label"
              hint
            />
          </div>
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.part-selector {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.ps-source,
.ps-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  font-size: 11px;
  opacity: 0.78;
}

.ps-source > span {
  flex: 1 1 auto;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ps-source :deep(button) {
  min-height: 28px;
  padding: 3px 6px;
  font-size: 11px;
  white-space: nowrap;
}

.ps-warnings {
  margin: 0;
  padding: 6px 8px;
  border-radius: 8px;
  border: 1px solid rgba(251, 191, 36, 0.25);
  background: rgba(251, 191, 36, 0.08);
  font-size: 10px;
  line-height: 1.6;
  opacity: 0.82;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ps-hint {
  font-family: ui-monospace, Menlo, monospace;
  font-size: 10px;
  letter-spacing: 0.08em;
}

.ps-empty {
  margin: 0;
  padding: 12px;
  border-radius: 10px;
  border: 1px dashed rgba(255, 255, 255, 0.24);
  background: rgba(255, 255, 255, 0.04);
  font-size: 12px;
  line-height: 1.8;
}

.ps-empty small {
  opacity: 0.7;
}

.ps-group-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 4px 8px;
  border-radius: 6px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(255, 255, 255, 0.05);
  color: inherit;
  font-size: 11px;
  cursor: pointer;
}

.ps-group-head:hover {
  border-color: var(--primary-color);
}

.ps-list {
  list-style: none;
  margin: 6px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.ps-row {
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.05);
}

.ps-row.is-off {
  opacity: 0.55;
}

.ps-line {
  display: flex;
  align-items: center;
  gap: 4px;
}

.ps-name {
  flex: 0 0 56px;
  font-family: 'Maoken Assorted Sans', -apple-system, BlinkMacSystemFont, sans-serif;
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ps-value {
  flex: 1 1 auto;
  min-width: 0;
  padding: 2px 8px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.1);
  font-size: 12px;
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ps-line :deep(button),
.ps-sub :deep(button) {
  min-width: 30px;
  min-height: 30px;
  padding: 2px 6px;
  font-size: 13px;
  margin: 0;
}

.ps-sub {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 6px;
}

.ps-check {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  cursor: pointer;
}

.ps-opacity {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
  font-size: 11px;
  opacity: 0.85;
}

.ps-opacity :deep(.slider) {
  flex: 1 1 auto;
  gap: 6px;
}

.ps-opacity :deep(input[type='range']) {
  margin: 2px 0;
}

.ps-preview {
  margin-top: 6px;
  height: 56px;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(0, 14, 39, 0.35);
  overflow: hidden;
}
</style>
