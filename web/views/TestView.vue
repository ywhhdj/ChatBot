<script setup lang="ts">
const now = Date.now()

const tools: UI.ToolCallItem[] = [
  {
    id: 't1',
    service: 'obs',
    method: 'switch_scene',
    raw: 'obs switch_scene --name "直播室"',
    status: 'success',
    params: { name: '直播室' },
    result: { scene_uuid: 'abc123', scene_name: '直播室' },
    elapsedMs: 230,
    label: '切换OBS场景 → 直播室',
  },
  {
    id: 't2',
    service: 'obs',
    method: 'start_stream',
    raw: 'obs start_stream',
    status: 'success',
    params: {},
    result: { stream_status: 'live' },
    elapsedMs: 150,
    label: '开始推流',
  },
  {
    id: 't3',
    service: 'skill',
    method: 'run',
    raw: 'skill run --id "greeting"',
    status: 'error',
    params: { id: 'greeting' },
    error: '技能 "greeting" 未找到',
    elapsedMs: 89,
    label: '执行技能 greeting',
  },
]

const longTools: UI.ToolCallItem[] = [
  { id: 'lt1', service: 'search', method: 'web', raw: 'search web --q "今天天气"', status: 'success', params: { q: '今天天气' }, result: { summary: '晴，25°C' }, elapsedMs: 310, label: '网络搜索' },
  { id: 'lt2', service: 'database', method: 'query', raw: 'database query --sql "SELECT * FROM weather"', status: 'success', params: { sql: 'SELECT * FROM weather' }, result: { rows: [{ city: '北京', temp: 26 }] }, elapsedMs: 450, label: '数据库查询' },
  { id: 'lt3', service: 'translate', method: 'en2zh', raw: 'translate en2zh --text "Hello"', status: 'success', params: { text: 'Hello' }, result: { translation: '你好' }, elapsedMs: 200, label: '翻译' },
  { id: 'lt4', service: 'tts', method: 'speak', raw: 'tts speak --text "你好"', status: 'skipped', params: { text: '你好' }, elapsedMs: 0, label: '语音合成' },
]

const mockMessages: UI.ChatMessage[] = [
  {
    id: 'msg1',
    role: 'user',
    content: '帮我准备直播环境，然后说一句欢迎词',
    createdAt: now - 5000,
  },
  {
    id: 'msg2',
    role: 'assistant',
    content: '好的，正在准备直播环境……',
    tools: tools,
    phase: 'done',
    createdAt: now - 3000,
  },
  {
    id: 'msg3',
    role: 'assistant',
    content: `## 今日概要\n\n- 天气：晴 🌤️ 25°C\n- 日程：下午3点会议\n\n更多信息请查看[链接](https://example.com)。`,
    tools: longTools,
    phase: 'done',
    createdAt: now - 1000,
  },
  {
    id: 'msg4',
    role: 'user',
    content: '有哪些待办事项？',
    createdAt: now,
  },
  {
    id: 'msg5',
    role: 'assistant',
    content: '正在思考...',
    tools: [],
    phase: 'thinking',
    createdAt: now + 100,
  },
]
</script>

<template>
  <AgentSidePanel
    visible
    :messages="mockMessages"
  />
</template>