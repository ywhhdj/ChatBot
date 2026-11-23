<script lang="ts" setup>
/**
 * 聊天页顶部导航
 */
import { computed } from 'vue';
import { useRouter } from 'vue-router';
import Button from '@/components/base/Button.vue';
import Icon from '@/components/base/Icon.vue';

const props = defineProps<{
  editing: boolean;
  saving: boolean;
  avatarVisible: boolean;
  dirty: boolean;
}>();

const emit = defineEmits<{
  /** 点击「立绘」：进入编辑模式 */
  toggleEdit: [];
  /** 点击编辑态的「关闭」图标：返回对话 */
  closeEdit: [];
  action: [name: 'save' | 'toggleVisible' | 'exportPng' | 'exportJson' | 'import'];
}>();

const router = useRouter();

function goSettings() {
  router.push('/settings');
}

function enterEdit() {
  emit('toggleEdit');
}

function requestClose() {
  emit('closeEdit');
}

/** Nav 的 menuActionMap 是 computed，menus 动态切换即时生效 */
const menus = computed<UI.MenuItem[]>(() =>
  props.editing
    ? [{ type: 'nav', name: '返回', icon: 'close', clickAction: requestClose }]
    : [{ type: 'nav', name: '设置', icon: 'settings', clickAction: goSettings }]
);

const visibleIcon = computed<UI.IconType>(() => (props.avatarVisible ? 'eye' : 'eyeOff'));

// 用具名入口派发，避免模板里的字符串字面量被推断成宽泛 string
function doSave() { emit('action', 'save'); }
function doToggleVisible() { emit('action', 'toggleVisible'); }
function doExportPng() { emit('action', 'exportPng'); }
function doExportJson() { emit('action', 'exportJson'); }
function doImport() { emit('action', 'import'); }
</script>

<template>
  <div class="header-nav">
    <!-- 初始态唯一入口：点它才进入立绘编辑 -->
    <Button
      v-if="!editing"
      type="nav"
      class="tool-avatar"
      :aria-label="dirty ? '立绘编辑（有未保存的修改）' : '进入立绘编辑'"
      @click="enterEdit"
    >
      <Icon
        icon="character"
        :size="16"
      />立绘
      <span
        v-if="dirty"
        class="dirty-dot"
        aria-label="有未保存的修改"
      />
    </Button>

    <!-- 编辑态才出现的工具组 -->
    <div
      v-if="editing"
      class="avatar-tools"
      role="toolbar"
      aria-label="立绘编辑工具"
    >
      <Button
        type="nav"
        :disabled="saving"
        aria-label="保存装扮到存档"
        @click="doSave"
      ><Icon
        icon="save"
        :size="16"
      />{{ saving ? '保存中…' : '保存' }}</Button>

      <Button
        type="nav"
        :aria-pressed="!avatarVisible"
        :aria-label="avatarVisible ? '隐藏立绘' : '显示立绘'"
        @click="doToggleVisible"
      ><Icon
        :icon="visibleIcon"
        :size="16"
      /></Button>

      <Button
        type="nav"
        aria-label="导出合成图片"
        @click="doExportPng"
      ><Icon
        icon="export"
        :size="16"
      />导出图片</Button>

      <Button
        type="nav"
        aria-label="导出配置备份"
        @click="doExportJson"
      ><Icon
        icon="box"
        :size="16"
      />备份</Button>

      <Button
        type="nav"
        aria-label="导入配置备份"
        @click="doImport"
      ><Icon
        icon="import"
        :size="16"
      />导入</Button>
    </div>

    <MenuBar
      justify="end"
      :is-box-shadow="false"
    >
      <Nav
        :menus="menus"
        :hideText="true"
        direction="row"
      />
    </MenuBar>
  </div>
</template>

<style scoped>
.header-nav {
  border-radius: 8px;
  max-height: 50px;
  top: 10px;
  position: sticky;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
}

/* 初始态「立绘」：与编辑工具组同一套深色玻璃胶囊；
   带父级前缀提高特异性，确保覆盖 base Button 的 nav 默认背景 */
.header-nav .tool-avatar {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 32px;
  margin: 0;
  padding: 4px 12px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.2);
  background: rgba(0, 14, 39, 0.42);
  backdrop-filter: blur(4px);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.28);
  font-size: 12px;
  white-space: nowrap;
}

.avatar-tools {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 3px 6px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.2);
  background: rgba(0, 14, 39, 0.42);
  backdrop-filter: blur(4px);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.28);
}

.avatar-tools :deep(button) {
  min-height: 32px;
  padding: 4px 8px;
  font-size: 12px;
  margin: 0;
  white-space: nowrap;
}

.dirty-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  margin-left: 2px;
  border-radius: 999px;
  background: var(--primary-color);
  box-shadow: 0 0 6px var(--primary-color);
}

@media (max-width: 768px) {
  .avatar-tools :deep(button) {
    padding: 4px 6px;
    font-size: 0;
  }

  .avatar-tools :deep(button svg) {
    font-size: 12px;
  }

  .header-nav .tool-avatar {
    padding: 4px 8px;
  }
}
</style>