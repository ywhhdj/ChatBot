<script setup lang="ts">
const props = withDefaults(
  defineProps<{
    menus: UI.MenuItem[]
    direction?: 'column' | 'row'
    hideText?: boolean
    depth?: number
    fontFamily?: 'maokenAssorted' | ''
    scaleAnimation?: boolean
  }>(),
  {
    menus: () => [],
    direction: 'column',
    hideText: false,
    depth: 0,
    fontFamily: '',
  },
);

const expandedMap = ref<Record<string, boolean>>({});
const rootRef = ref<HTMLElement | null>(null);

const keyOf = (index: number) => {
  return `${props.depth}-${index}`;
};

const menuActionMap = computed(() => {
  const map: Record<string, UI.MenuItem> = {};
  props.menus.forEach((menu, index) => {
    map[keyOf(index)] = menu;
  });
  return map;
});

const onDelegatedClick = (event: MouseEvent) => {
  const root = rootRef.value;
  if (!root) {
    return;
  }
  const target = event.target as HTMLElement | null;
  if (!target) {
    return;
  }
  const trigger = target.closest('[data-menu-key]') as HTMLElement | null;
  if (!trigger || !root.contains(trigger)) {
    return;
  }
  const menuKey = trigger.dataset.menuKey;
  if (!menuKey) {
    return;
  }
  const menu = menuActionMap.value[menuKey];
  if (!menu) {
    return;
  }
  if (menu.children && menu.children.length > 0) {
    expandedMap.value[menuKey] = !expandedMap.value[menuKey];
  }
  menu.clickAction?.();
};
const spanClass = computed(() => {
  return props.hideText ? 'hide' : '';
});

const isExpanded = (index: number) => {
  return !!expandedMap.value[keyOf(index)];
};

const isExpandedIcon = computed(() => (index: number) => {
  return isExpanded(index) ? '▾' : '▸';
})

</script>

<template>
  <div
    ref="rootRef"
    class="nav-tree"
    :class="[`direction-${direction}`, `depth-${depth}`]"
    @click="onDelegatedClick"
  >
    <div
      v-for="(menu, index) in menus"
      :key="keyOf(index)"
      class="menu-node"
    >
      <Button
        :type="menu.type"
        :icon="menu.icon"
        class="menu-trigger"
        :class="['menu-trigger', props.fontFamily, { 'expandable': !!menu.children?.length }, { 'scale-animation': props.scaleAnimation }]"
        :data-menu-key="keyOf(index)"
      >
        <span :class="spanClass">{{ menu.name }}</span>
        <span
          v-if="menu.children?.length"
          class="expand-indicator"
        >
          {{ isExpandedIcon(index) }}
        </span>
      </Button>

      <div
        v-if="menu.children?.length"
        v-show="isExpanded(index)"
        class="submenu-wrap"
      >
        <Nav
          :menus="menu.children || []"
          :direction="direction"
          :hide-text="hideText"
          :depth="depth + 1"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.nav-tree {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.direction-row {
  flex-direction: row;
}

.menu-trigger {
  width: 100%;
  cursor: pointer;
}

.menu-trigger.maokenAssorted {
  font-family: 'Maoken Assorted Sans',
    -apple-system,
    BlinkMacSystemFont,
    Segoe UI,
    Roboto,
    Helvetica Neue,
    Arial,
    sans-serif;
}

.menu-trigger.expandable {
  cursor: pointer;
}

.menu-trigger.scale-animation:hover {
  transform: translateY(-8px) scale(1.05);
}

.expand-indicator {
  opacity: 0.8;
  font-size: 12px;
}

.submenu-wrap {
  margin-top: 4px;
  margin-left: 14px;
  padding-left: 10px;
  border-left: 1px solid rgba(255, 255, 255, 0.2);
}

.depth-1 :deep(.nav) {
  font-size: 14px;
  font-weight: 600;
  opacity: 0.95;
}

.depth-2 :deep(.nav) {
  font-size: 13px;
  font-weight: 500;
  opacity: 0.9;
}

@media screen and (max-width: 768px) {
  .hide {
    display: none;
  }
}
</style>
