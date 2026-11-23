<script lang="ts" setup>
import { computed } from 'vue';
import { defaultUIStore } from '@/stores/ui';
import { MORE_PAGE_MAP, MORE_PAGE_NAMES } from '@/components/views/settings/settingsPages';

const uiStore = defaultUIStore();
const currentComponent = computed(() => MORE_PAGE_MAP[uiStore.currentTab.more] || null);
const keepAliveInclude = MORE_PAGE_NAMES;
</script>

<template>
  <div class="flex flex-row h-full w-full ">
    <aside>
      <MoreNav />
    </aside>
    <div class="flex-1">
      <KeepAlive
        :include="keepAliveInclude"
        :max="6"
      >
        <component :is="currentComponent" />
      </KeepAlive>
    </div>
  </div>
</template>
