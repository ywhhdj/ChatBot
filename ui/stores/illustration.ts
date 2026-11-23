/**
 * 分层立绘编辑态（Step 9.1）
 *
 * 单一状态源：所有组件只读写这里，避免 props 层层透传与多份真相。
 * 素材、贴纸实例、整体缩放档都有硬上限；任何增删都同步修正选中态与索引，
 * 防止「删掉当前项后操作柄指向空对象」这类边界 bug。
 */
import { defineStore } from 'pinia';
import {
  LIMITS,
  SCALE_STEPS,
  clamp,
  createDefaultGlobal,
  createEmptyLayers,
  createLayersFromModel,
  sortedLayers,
  uid,
  type IllustrationGlobalState,
  type IllustrationSnapshot,
  type ModelMetaLite,
  type PartKey,
  type PartLayer,
  type PartOption,
  type StickerAsset,
  type StickerInstance,
} from '@/components/views/chat/illustration/configs/illustrationTypes';
import type { ParsedModel } from '@/components/views/chat/illustration/configs/modelTypes';

export type IllustrationEditorTab = 'parts' | 'stickers' | 'model';

interface IllustrationState {
  layers: PartLayer[];
  stickerAssets: StickerAsset[];
  stickers: StickerInstance[];
  global: IllustrationGlobalState;
  selectedStickerId: string | null;
  editorTab: IllustrationEditorTab;
  editVisible: boolean;
  dirty: boolean;
  saving: boolean;
  /** 模型来源元信息：只记录可解析事实，不含 moc3 二进制 */
  modelMeta: ModelMetaLite | null;
}

export const useIllustrationStore = defineStore('avatar', {
  state: (): IllustrationState => ({
    layers: createEmptyLayers(),
    stickerAssets: [],
    stickers: [],
    global: createDefaultGlobal(),
    selectedStickerId: null,
    editorTab: 'parts',
    editVisible: false,
    dirty: false,
    saving: false,
    modelMeta: null,
  }),

  getters: {
    selectedSticker(state): StickerInstance | null {
      return state.stickers.find((s) => s.id === state.selectedStickerId) || null;
    },
    activeOption: (state) => (key: PartKey): PartOption | null => {
      const layer = state.layers.find((l) => l.key === key);
      return layer?.options.find((o) => o.id === layer.activeId) || null;
    },
    maxStickerZ(state): number {
      return state.stickers.reduce((max, s) => Math.max(max, s.z), 10);
    },
    /** 舞台与面板共用的稳定排序，避免同 z 层顺序抖动 */
    orderedLayers(state): PartLayer[] {
      return sortedLayers(state.layers);
    },
    /** 面板分组：动态层按 group 归类，空白模板归「默认分组」 */
    layerGroups(state): Array<{ label: string; layers: PartLayer[] }> {
      const map = new Map<string, PartLayer[]>();
      for (const layer of sortedLayers(state.layers)) {
        const key = layer.group || '其他';
        const list = map.get(key) || [];
        list.push(layer);
        map.set(key, list);
      }
      return Array.from(map, ([label, layers]) => ({ label, layers }));
    },
  },

  actions: {
    markDirty() {
      this.dirty = true;
    },
    markClean() {
      this.dirty = false;
    },
    setTab(tab: IllustrationEditorTab) {
      this.editorTab = tab;
    },
    setEditVisible(visible: boolean) {
      this.editVisible = visible;
      if (!visible) this.selectedStickerId = null;
    },
    toggleEditVisible() {
      this.setEditVisible(!this.editVisible);
    },
    selectSticker(id: string | null) {
      this.selectedStickerId = id && this.stickers.some((s) => s.id === id) ? id : null;
    },
    confirmEdit() {
      this.selectedStickerId = null;
      this.editVisible = false;
    },
    setSaving(value: boolean) {
      this.saving = value;
    },

    // ---------- 部件层 ----------
    addLayerOption(key: PartKey, option: PartOption) {
      const layer = this.layers.find((l) => l.key === key);
      if (!layer || layer.options.length >= LIMITS.maxOptionsPerLayer) return false;
      if (layer.options.some((o) => o.id === option.id)) return false;
      layer.options.push(option);
      // 第一个素材自动选中，避免出现「有素材但什么都不显示」
      if (!layer.activeId) layer.activeId = option.id;
      this.markDirty();
      return true;
    },
    removeLayerOption(key: PartKey, id: string) {
      const layer = this.layers.find((l) => l.key === key);
      if (!layer) return;
      const index = layer.options.findIndex((o) => o.id === id);
      if (index < 0) return;
      layer.options.splice(index, 1);
      if (layer.activeId === id) {
        // 删掉当前项后回退到相邻项，索引不会越界
        layer.activeId = layer.options[Math.min(index, layer.options.length - 1)]?.id || null;
      }
      this.markDirty();
    },
    cycleLayerOption(key: PartKey, direction: -1 | 1) {
      const layer = this.layers.find((l) => l.key === key);
      if (!layer || layer.options.length < 2) return;
      const current = layer.options.findIndex((o) => o.id === layer.activeId);
      const next = (current + direction + layer.options.length) % layer.options.length;
      if (layer.options[next]) {
        layer.activeId = layer.options[next].id;
      }
      this.markDirty();
    },
    setLayerVisible(key: PartKey, value: boolean) {
      const layer = this.layers.find((l) => l.key === key);
      if (!layer) return;
      layer.visible = value;
      this.markDirty();
    },
    setLayerFlip(key: PartKey, value: boolean) {
      const layer = this.layers.find((l) => l.key === key);
      if (!layer) return;
      layer.flipX = value;
      this.markDirty();
    },
    setLayerOpacity(key: PartKey, value: number) {
      const layer = this.layers.find((l) => l.key === key);
      if (!layer) return;
      layer.opacity = clamp(value, LIMITS.opacityMin, LIMITS.opacityMax);
      this.markDirty();
    },

    // ---------- 贴纸库与实例 ----------
    addStickerAssets(assets: StickerAsset[]) {
      const room = LIMITS.maxStickerAssets - this.stickerAssets.length;
      if (room <= 0) return 0;
      let added = 0;
      for (const asset of assets.slice(0, room)) {
        if (this.stickerAssets.some((a) => a.id === asset.id)) continue;
        this.stickerAssets.push(asset);
        added += 1;
      }
      if (added) this.markDirty();
      return added;
    },
    removeStickerAsset(id: string) {
      const index = this.stickerAssets.findIndex((a) => a.id === id);
      if (index < 0) return;
      this.stickerAssets.splice(index, 1);
      // 库条目被移除时，已摆放的实例一并清理，避免留下无来源的孤立项
      this.stickers = this.stickers.filter((s) => s.assetId !== id);
      if (!this.stickers.some((s) => s.id === this.selectedStickerId)) this.selectedStickerId = null;
      this.markDirty();
    },
    addSticker(asset: StickerAsset): string | null {
      if (this.stickers.length >= LIMITS.maxStickerInstances) return null;
      const id = uid('sticker');
      this.stickers.push({
        id,
        assetId: asset.id,
        src: asset.src,
        label: asset.label,
        // 默认落在立绘中部偏上，不压住对话框
        x: 0.5,
        y: 0.42,
        scale: 1,
        rotation: 0,
        flipX: false,
        opacity: 1,
        z: this.maxStickerZ + 1,
        behind: false,
        width: asset.width,
        height: asset.height,
      });
      this.selectedStickerId = id;
      this.markDirty();
      return id;
    },
    updateSticker(id: string, patch: Partial<StickerInstance>) {
      const target = this.stickers.find((s) => s.id === id);
      if (!target) return;
      if (patch.x !== undefined) patch.x = clamp(patch.x, LIMITS.positionMin, LIMITS.positionMax);
      if (patch.y !== undefined) patch.y = clamp(patch.y, LIMITS.positionMin, LIMITS.positionMax);
      if (patch.scale !== undefined) patch.scale = clamp(patch.scale, LIMITS.stickerScaleMin, LIMITS.stickerScaleMax);
      if (patch.rotation !== undefined) patch.rotation = clamp(patch.rotation, LIMITS.rotationMin, LIMITS.rotationMax);
      if (patch.opacity !== undefined) patch.opacity = clamp(patch.opacity, LIMITS.opacityMin, LIMITS.opacityMax);
      Object.assign(target, patch);
      this.markDirty();
    },
    removeSticker(id: string) {
      const index = this.stickers.findIndex((s) => s.id === id);
      if (index < 0) return;
      this.stickers.splice(index, 1);
      // 删除后立刻清选中，操作柄不会指向空对象
      if (this.selectedStickerId === id) this.selectedStickerId = null;
      this.markDirty();
    },
    toggleStickerFlip(id: string) {
      const target = this.stickers.find((s) => s.id === id);
      if (!target) return;
      target.flipX = !target.flipX;
      this.markDirty();
    },
    toggleStickerBehind(id: string) {
      const target = this.stickers.find((s) => s.id === id);
      if (!target) return;
      target.behind = !target.behind;
      target.z = target.behind ? -1 : this.maxStickerZ + 1;
      this.markDirty();
    },
    moveStickerLayer(id: string, direction: -1 | 1) {
      const target = this.stickers.find((s) => s.id === id);
      if (!target || target.behind) return;
      target.z = clamp(target.z + direction, 10, 1000);
      this.markDirty();
    },

    // ---------- 整体 ----------
    setScale(value: number) {
      this.global.scale = SCALE_STEPS.includes(value) ? value : 1;
      this.markDirty();
    },
    toggleGlobalFlip() {
      this.global.flipX = !this.global.flipX;
      this.markDirty();
    },
    toggleVisible() {
      this.global.visible = !this.global.visible;
      this.markDirty();
    },
    /** 用真实解析出的模型部件替换默认层；不改动贴纸与整体缩放 */
    applyModel(model: ParsedModel) {
      this.layers = createLayersFromModel(model);
      this.modelMeta = {
        format: model.format,
        name: model.name,
        partCount: model.parts.length,
        textureFiles: model.meta.textureFiles.slice(0, 60),
        warnings: model.warnings.slice(0, 20),
        hasMoc3: model.meta.hasMoc3,
        hasVtube: model.meta.hasVtube,
        hasCdi3: model.meta.hasCdi3,
        importedAt: Date.now(),
      };
      this.selectedStickerId = null;
      this.markDirty();
    },
    clearModel() {
      this.modelMeta = null;
      this.layers = createEmptyLayers();
      this.markDirty();
    },
    reset() {
      this.layers = createEmptyLayers();
      this.stickerAssets = [];
      this.stickers = [];
      this.global = createDefaultGlobal();
      this.selectedStickerId = null;
      this.modelMeta = null;
      this.markDirty();
    },

    // ---------- 往返 ----------
    hydrate(snapshot: IllustrationSnapshot) {
      this.layers = snapshot.layers;
      this.stickerAssets = snapshot.stickerAssets;
      this.stickers = snapshot.stickers;
      this.global = snapshot.global;
      this.modelMeta = snapshot.modelMeta || null;
      this.selectedStickerId = null;
      this.markClean();
    },
    snapshot(): IllustrationSnapshot {
      return JSON.parse(JSON.stringify({
        version: 2,
        layers: this.layers,
        stickerAssets: this.stickerAssets,
        stickers: this.stickers,
        global: this.global,
        modelMeta: this.modelMeta,
      })) as IllustrationSnapshot;
    },
  },
});
