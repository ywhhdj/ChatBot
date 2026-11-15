export const REGISTRABLE_SERVICE_IDS = [
  'browser',
  'live2d',
  'obs',
  'ppt',
  'qqbot',
  'shell',
] as const;

export type RegistrableServiceId = (typeof REGISTRABLE_SERVICE_IDS)[number];


export const SERVICE_ICON_MAP: Record<string, UI.IconType> = {
  browser: 'url',
  live2d: 'character',
  obs: 'box',
  ppt: 'list',
  qqbot: 'communication',
  shell: 'code',
};

export type ServiceStateTone = 'on' | 'err' | 'off' | 'idle';

const STATE_LABELS: Record<string, string> = {
  running: '运行中',
  stopped: '已停止',
  not_enabled: '未启用',
  error: '异常',
};

export function serviceStateText(state?: string): string {
  if (!state) return '未知';
  return STATE_LABELS[state] || state;
}

export function serviceStateTone(state?: string): ServiceStateTone {
  if (state === 'running') return 'on';
  if (state === 'error') return 'err';
  if (state === 'not_enabled') return 'off';
  return 'idle';
}