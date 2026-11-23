/**
 * 设置页组件映射（模块级单例）
 */
import { defineAsyncComponent, type Component } from 'vue';

function named(name: string, loader: () => Promise<any>): Component {
  const comp = defineAsyncComponent(loader) as Component & { name?: string; __name?: string };
  comp.name = name;
  comp.__name = name;
  return comp;
}

export const SETTINGS_TABS: UI.SettingsTab[] = [
  'general',
  'history',
  'character',
  'background',
  'sound',
  'save',
  'more',
];
export const MORE_TABS: UI.MoreTab[] = [
  'modelprovider',
  'monitor',
  'services'
];

export const SETTINGS_PAGE_MAP: Record<UI.SettingsTab, Component> = {
  general: named('general', () => import('@/components/views/settings/pages/GeneralSetting.vue')),
  history: named('history', () => import('@/components/views/settings/pages/HistorySetting.vue')),
  character: named('character', () => import('@/components/views/settings/pages/CharacterSetting.vue')),
  background: named('background', () => import('@/components/views/settings/pages/BackgroundSetting.vue')),
  sound: named('sound', () => import('@/components/views/settings/pages/SoundSetting.vue')),
  save: named('save', () => import('@/components/views/settings/pages/SaveSetting.vue')),
  more: named('more', () => import('@/components/views/settings/pages/MoreSetting.vue')),
};

export const MORE_PAGE_MAP: Record<UI.MoreTab, Component> = {
  modelprovider: named('modelprovider', () => import('@/components/views/settings/pages/more/pages/ModelProviderSetting.vue')),
  monitor: named('monitor', () => import('@/components/views/settings/pages/more/pages/MonitorSetting.vue')),
  services: named('services', () => import('@/components/views/settings/pages/more/pages/ServicesSetting.vue')),
};

export const SETTINGS_PAGE_NAMES = Object.keys(SETTINGS_PAGE_MAP).join(',');
export const MORE_PAGE_NAMES = Object.keys(MORE_PAGE_MAP).join(',');
