/* ChatBot DevTools —— 纯静态、零依赖、仅开发态。
 *
 * 约定：
 *  - 只调用现有契约端点，不新增后端路由、不改业务数据。
 *  - 默认只做只读请求；写操作必须用户手动触发（冒烟面板有显式勾选）。
 *  - 同时兼容统一信封 {ok,code,data,...} 与原生协议裸对象（compat.*）。
 */
'use strict';

const $ = (id) => document.getElementById(id);
const fmt = (v) => JSON.stringify(v, null, 2);
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => (
  { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]
));

const state = {
  base: '/api',
  wsBase: '',
  catalog: [],
  groups: {},
  recent: [],
  perfStop: false,
  ws: null,
};

function apiPath(p) {
  const base = ($('apiBase').value || '/api').replace(/\/$/, '');
  const path = p.startsWith('/') ? p : `/${p}`;
  return `${base}${path}`;
}

function wsURL() {
  if ($('wsBase').value.trim()) return $('wsBase').value.trim();
  const h = location.hostname || 'localhost';
  const port = location.port && location.port !== '8000' ? ':8000' : (location.port ? `:${location.port}` : '');
  return `ws://${h}${port}/`;
}

function parseJSON(text, fallback) {
  try { return JSON.parse(text); } catch { return fallback; }
}

function markBadge(text, kind) {
  const b = $('connBadge');
  b.textContent = text;
  b.className = `badge badge-${kind}`;
}

function logRecent(entry) {
  state.recent.unshift(entry);
  state.recent = state.recent.slice(0, 12);
  const rows = state.recent.map((r) => `<tr>
    <td class="mono">${esc(r.method)}</td><td class="mono">${esc(r.path)}</td>
    <td class="${r.ok ? 'st-ok' : 'st-err'}">${r.status}</td>
    <td class="mono">${r.ms.toFixed(1)} ms</td>
    <td class="mono">${esc(r.rid || '—')}</td></tr>`).join('');
  $('ovRecent').innerHTML = `<thead><tr><th>方法</th><th>路径</th><th>状态</th><th>耗时</th><th>X-Request-ID</th></tr></thead><tbody>${rows || '<tr><td colspan="5" class="muted">暂无请求</td></tr>'}</tbody>`;
}

/** 统一的单次请求：计时 + 关联 ID + 兼容裸响应。 */
async function req(method, path, { query = null, body = null, signal = null } = {}) {
  let url = apiPath(path);
  if (query && typeof query === 'object') {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(query)) {
      if (v !== undefined && v !== null && v !== '') qs.set(k, typeof v === 'object' ? JSON.stringify(v) : String(v));
    }
    const s = qs.toString();
    if (s) url += (url.includes('?') ? '&' : '?') + s;
  }
  const init = { method, headers: { 'Accept': 'application/json' }, signal };
  if (body !== null && method !== 'GET') {
    init.headers['Content-Type'] = 'application/json';
    init.body = typeof body === 'string' ? body : JSON.stringify(body);
  }
  const t0 = performance.now();
  try {
    const res = await fetch(url, init);
    const ms = performance.now() - t0;
    const text = await res.text();
    const parsed = parseJSON(text, text);
    const out = {
      ok: res.ok, status: res.status, ms,
      rid: res.headers.get('X-Request-ID') || '',
      body: parsed,
      data: (parsed && typeof parsed === 'object' && 'data' in parsed) ? parsed.data : parsed,
      error: null,
      raw: text,
    };
    logRecent({ method, path, ok: res.ok, status: res.status, ms, rid: out.rid });
    return out;
  } catch (e) {
    const ms = performance.now() - t0;
    logRecent({ method, path, ok: false, status: 'ERR', ms, rid: '' });
    return { ok: false, status: 0, ms, rid: '', body: null, data: null, error: String(e), raw: '' };
  }
}

function cards(target, items) {
  $(target).innerHTML = items.map((it) => `
    <div class="card"><div class="k">${esc(it.k)}</div>
      <div class="v ${it.cls || ''}">${esc(it.v)}</div>
      <div class="s">${esc(it.s || '')}</div></div>`).join('');
}

function percentile(sorted, p) {
  if (!sorted.length) return 0;
  const i = Math.min(sorted.length - 1, Math.ceil((p / 100) * sorted.length) - 1);
  return sorted[Math.max(0, i)];
}

/* ───────────────────────── 概览 ───────────────────────── */
async function loadCatalog() {
  const r = await req('GET', '/catalog');
  if (!r.ok || !r.body || !Array.isArray(r.body.endpoints)) {
    markBadge(`连接失败 ${r.status || 'ERR'}`, 'err');
    $('ovCards').innerHTML = '';
    cards('ovCards', [{ k: '状态', v: '不可达', cls: 'err', s: r.error || '检查 API Base 与后端是否启动' }]);
    return false;
  }
  state.catalog = r.body.endpoints;
  state.groups = r.body.groups || {};
  markBadge(`已连接 · ${r.body.total} 端点`, 'ok');
  renderOverview();
  renderEndpointTable();
  fillGroups();
  return true;
}

function renderOverview() {
  const eps = state.catalog;
  const byMethod = {};
  eps.forEach((e) => { const m = (e.http?.method || '?').toUpperCase(); byMethod[m] = (byMethod[m] || 0) + 1; });
  cards('ovCards', [
    { k: '契约端点', v: eps.length, cls: 'ok', s: '来自 /api/catalog' },
    { k: '能力域', v: Object.keys(state.groups).length, s: 'groups.json 同源' },
    { k: 'GET / 写操作', v: `${byMethod.GET || 0} / ${eps.length - (byMethod.GET || 0)}`, s: '按方法统计' },
    { k: 'desktop bridge', v: eps.filter((e) => e.desktop).length, s: '其余仅 HTTP' },
  ]);
  const chips = Object.entries(state.groups).map(([k, g]) => {
    const n = eps.filter((e) => (e.tags || []).includes(k)).length;
    return `<span class="chip">${esc(g.label || k)} <b>${n}</b></span>`;
  }).join('');
  $('ovGroups').innerHTML = chips || '<span class="muted">无分组数据</span>';
}

/* ───────────────────────── 端点浏览器 ───────────────────────── */
function fillGroups() {
  const sel = $('epGroup');
  const cur = sel.value;
  sel.innerHTML = '<option value="">全部分组</option>' +
    Object.entries(state.groups).map(([k, g]) => `<option value="${esc(k)}">${esc(g.label || k)}</option>`).join('');
  sel.value = cur;
}

function renderEndpointTable() {
  const q = ($('epFilter').value || '').toLowerCase();
  const grp = $('epGroup').value;
  const mth = $('epMethod').value;
  const list = state.catalog.filter((e) => {
    const method = (e.http?.method || '').toUpperCase();
    const path = e.http?.path || '';
    const hay = `${e.op} ${path} ${e.http?.summary || ''} ${e.meta?.label || ''}`.toLowerCase();
    if (q && !hay.includes(q)) return false;
    if (grp && !(e.tags || []).includes(grp)) return false;
    if (mth && method !== mth) return false;
    return true;
  });
  $('epCount').textContent = `${list.length} / ${state.catalog.length}`;
  const rows = list.map((e) => {
    const method = (e.http?.method || 'GET').toLowerCase();
    const path = e.http?.path || '—';
    return `<tr data-method="${esc(method.toUpperCase())}" data-path="${esc(path)}">
      <td class="mono">${esc(e.op)}</td>
      <td><span class="tag ${esc(method)}">${esc(method.toUpperCase())}</span></td>
      <td class="mono">${esc(path)}</td>
      <td>${esc((e.tags || []).join(', '))}</td>
      <td>${esc(e.http?.summary || e.meta?.label || '')}</td>
      <td class="mono">${e.desktop ? '✓' : '—'}</td></tr>`;
  }).join('');
  $('epTable').innerHTML = `<thead><tr><th>op</th><th>方法</th><th>路径</th><th>分组</th><th>说明</th><th>Bridge</th></tr></thead><tbody>${rows || '<tr><td colspan="6" class="muted">无匹配端点</td></tr>'}</tbody>`;
  $('epTable').querySelectorAll('tbody tr[data-path]').forEach((tr) => {
    tr.addEventListener('click', () => {
      $('rqMethod').value = tr.dataset.method;
      $('rqPath').value = tr.dataset.path;
      switchTab('request');
      $('rqOut').textContent = `已填入 ${tr.dataset.method} ${tr.dataset.path}\n\n点击「发送」执行。`;
    });
  });
}

/* ───────────────────────── 请求调试 ───────────────────────── */
async function sendRequest() {
  const method = $('rqMethod').value;
  const path = $('rqPath').value.trim() || '/';
  const query = parseJSON($('rqQuery').value, null);
  const bodyText = $('rqBody').value.trim();
  const body = method === 'GET' ? null : (bodyText ? parseJSON(bodyText, bodyText) : null);
  const r = await req(method, path, { query, body });
  $('rqMeta').textContent = `${r.status} · ${r.ms.toFixed(1)} ms · rid=${r.rid || '—'}`;
  $('rqOut').textContent = r.error
    ? `请求异常: ${r.error}`
    : (typeof r.body === 'string' ? r.body : fmt(r.body));
  $('rqOut').style.color = r.ok ? '' : 'var(--err)';
}

/* ───────────────────────── 性能压测 ───────────────────────── */
async function runPerf() {
  const path = $('pfPath').value.trim() || '/system/ping';
  const conc = Math.max(1, Math.min(64, Number($('pfConc').value) || 8));
  const total = Math.max(1, Math.min(2000, Number($('pfTotal').value) || 100));
  const method = $('pfMethod').value;
  const body = parseJSON($('pfBody').value, {});
  state.perfStop = false;
  $('pfRun').disabled = true; $('pfStop').disabled = false;

  const times = [], errors = {};
  let done = 0, success = 0;
  const t0 = performance.now();
  let cursor = 0;

  async function worker() {
    while (!state.perfStop && cursor < total) {
      cursor += 1;
      const r = await req(method, path, { body: method === 'GET' ? null : body });
      times.push(r.ms);
      if (r.ok && r.status < 400) success += 1;
      else {
        const key = `${r.status} ${r.error || (r.body?.message || r.body?.error?.message || 'failed')}`;
        errors[key] = (errors[key] || 0) + 1;
      }
      done += 1;
      if (done % Math.max(1, Math.floor(total / 40)) === 0 || done === total) {
        $('pfBar').style.width = `${(done / total * 100).toFixed(1)}%`;
      }
    }
  }
  await Promise.all(Array.from({ length: conc }, worker));
  const wall = (performance.now() - t0) / 1000;
  const sorted = [...times].sort((a, b) => a - b);
  const avg = times.reduce((a, b) => a + b, 0) / (times.length || 1);
  const successRate = times.length ? (success / times.length * 100) : 0;

  cards('pfCards', [
    { k: '请求数', v: times.length, s: `并发 ${conc} · 墙钟 ${wall.toFixed(2)}s` },
    { k: '成功率', v: `${successRate.toFixed(1)}%`, cls: successRate > 99 ? 'ok' : successRate > 90 ? 'warn' : 'err', s: `${success} / ${times.length}` },
    { k: '吞吐', v: `${(times.length / (wall || 1)).toFixed(1)}`, s: 'req/s' },
    { k: '平均延迟', v: `${avg.toFixed(1)} ms`, s: `max ${sorted.at(-1)?.toFixed(1) || 0} ms` },
  ]);
  $('pfTable').innerHTML = `<thead><tr><th>分位</th><th>延迟 (ms)</th></tr></thead><tbody>${
    [50, 75, 90, 95, 99].map((p) => `<tr><td>p${p}</td><td class="mono">${percentile(sorted, p).toFixed(1)}</td></tr>`).join('')
  }</tbody>`;
  $('pfErrors').textContent = Object.keys(errors).length
    ? Object.entries(errors).sort((a, b) => b[1] - a[1]).map(([k, v]) => `${v}×  ${k}`).join('\n')
    : '无错误';
  $('pfRun').disabled = false; $('pfStop').disabled = true;
}

/* ───────────────────────── 功能冒烟 ───────────────────────── */
const SMOKE_DENY = /service\.(start|stop|register)|provider\.(switch|stop|download)|system\.(shutdown|restart|gc)|skill\.reload|save\.(delete|create|load|toggle)|memory\.(clear|delete)|config\.(save|update|apply)|hotkeys\./;

async function runSmoke() {
  const includeWrites = $('smIncludeWrites').checked;
  const eps = state.catalog.filter((e) => {
    const path = e.http?.path || '';
    if (path.includes('{')) return false;
    const method = (e.http?.method || '').toUpperCase();
    if (method === 'GET') return true;
    return includeWrites && !SMOKE_DENY.test(e.op) && ['POST', 'PUT', 'PATCH'].includes(method);
  });
  $('smRun').disabled = true;
  const results = [];
  for (let i = 0; i < eps.length; i += 1) {
    const e = eps[i];
    $('smProgress').textContent = `${i + 1} / ${eps.length} · ${e.op}`;
    const r = await req(e.http.method.toUpperCase(), e.http.path, { body: null });
    results.push({ op: e.op, method: e.http.method.toUpperCase(), path: e.http.path, ...r });
  }
  $('smProgress').textContent = `完成 ${eps.length} 项`;
  const okN = results.filter((r) => r.ok && r.status < 400).length;
  cards('smCards', [
    { k: '执行端点', v: eps.length, s: `只读 ${eps.filter((e) => e.http.method.toUpperCase() === 'GET').length}` },
    { k: '通过', v: okN, cls: 'ok', s: 'HTTP < 400' },
    { k: '失败', v: eps.length - okN, cls: eps.length - okN ? 'err' : 'ok', s: '见下表' },
    { k: 'p95', v: `${percentile(results.map((r) => r.ms).sort((a, b) => a - b), 95).toFixed(1)} ms`, s: '全量耗时' },
  ]);
  $('smTable').innerHTML = `<thead><tr><th>op</th><th>方法</th><th>路径</th><th>状态</th><th>耗时</th><th>说明</th></tr></thead><tbody>${
    results.map((r) => `<tr>
      <td class="mono">${esc(r.op)}</td><td>${esc(r.method)}</td><td class="mono">${esc(r.path)}</td>
      <td class="${r.ok && r.status < 400 ? 'st-ok' : 'st-err'}">${r.status}</td>
      <td class="mono">${r.ms.toFixed(1)} ms</td>
      <td>${esc(r.error || r.body?.message || (r.ok && r.status < 400 ? 'ok' : 'failed'))}</td></tr>`).join('')
  }</tbody>`;
  $('smRun').disabled = false;
}

/* ───────────────────────── 服务配置三态 ───────────────────────── */
function cfLog(line, obj) {
  const pre = $('cfLog');
  const stamp = new Date().toLocaleTimeString('zh-CN', { hour12: false });
  const text = `[${stamp}] ${line}${obj !== undefined ? '\n' + fmt(obj) : ''}`;
  pre.textContent = pre.textContent === '—' ? text : `${text}\n\n${pre.textContent}`;
}

function renderCfState(d) {
  const box = $('cfState');
  if (!d) { box.textContent = '读取失败'; box.className = 'state-box'; return; }
  box.className = `state-box ${d.pending ? 'pending' : 'clean'}`;
  box.textContent = [
    `service      : ${d.id}`,
    `source       : ${d.source} (slot=${d.slot_id || '—'})`,
    `state        : ${d.state}`,
    `pending      : ${d.pending}`,
    `applied      : ${d.applied}`,
    `restarted    : ${d.restarted}`,
    `masked       : ${d.credentials_masked}`,
    ``,
    `saved.config.port  = ${d.config?.port ?? '—'}`,
    `active_config.port = ${d.active_config?.port ?? '—'}`,
  ].join('\n');
}

async function cfGet(tag) {
  const id = $('cfService').value;
  const r = await req('GET', `/service/${id}/config`);
  const d = r.data;
  renderCfState(d);
  cfLog(`${tag} GET /service/${id}/config → ${r.status} (${r.ms.toFixed(1)} ms)`, d);
  return d;
}

async function cfSave() {
  const id = $('cfService').value;
  const body = parseJSON($('cfBody').value, {});
  const r = await req('PUT', `/service/${id}/config`, { body: { config: body } });
  renderCfState(r.data);
  cfLog(`② update_config → ${r.status}（只保存，运行态不应变化）`, r.data);
}

async function cfApply() {
  const id = $('cfService').value;
  const r = await req('PUT', `/service/${id}/config/apply`, { body: { restart: false } });
  renderCfState(r.data);
  cfLog(`③ apply_config → ${r.status}（restart=false，避免调试时重启真实服务）`, r.data);
}

/* ───────────────────────── SSE / WS ───────────────────────── */
async function runSSE() {
  const path = $('ssPath').value.trim() || '/chat/stream';
  const body = parseJSON($('ssBody').value, {});
  const out = $('ssOut');
  out.textContent = '';
  const t0 = performance.now();
  let first = null, frames = 0;
  try {
    const res = await fetch(apiPath(path), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Accept': 'text/event-stream' },
      body: JSON.stringify(body),
    });
    if (!res.ok || !res.body) {
      out.textContent = `HTTP ${res.status}\n${await res.text()}`;
      return;
    }
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = '';
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const blocks = buf.split('\n\n');
      buf = blocks.pop() || '';
      for (const block of blocks) {
        if (!block.trim()) continue;
        frames += 1;
        if (first === null) first = performance.now() - t0;
        out.textContent += `${block.trim()}\n\n`;
        out.scrollTop = out.scrollHeight;
      }
    }
    $('ssMeta').textContent = `HTTP ${res.status} · 首帧 ${first?.toFixed(1) ?? '—'} ms · ${frames} 帧 · 总 ${(performance.now() - t0).toFixed(1)} ms`;
  } catch (e) {
    out.textContent += `\n[异常] ${e}`;
  }
}

function wsWrite(line) {
  const out = $('wsOut');
  out.textContent = (out.textContent === '—' ? '' : out.textContent) + line + '\n';
  out.scrollTop = out.scrollHeight;
}

function wsConnect() {
  if (state.ws && state.ws.readyState === WebSocket.OPEN) { wsWrite('[已连接]'); return; }
  const url = wsURL();
  $('wsBase').value = url;
  const t0 = performance.now();
  const ws = new WebSocket(url);
  state.ws = ws;
  $('wsMeta').textContent = '连接中…';
  ws.onopen = () => {
    $('wsMeta').textContent = `已连接 · ${(performance.now() - t0).toFixed(1)} ms · ${url}`;
    wsWrite(`[open] ${url}`);
  };
  ws.onmessage = (ev) => wsWrite(`[recv] ${ev.data}`);
  ws.onerror = () => wsWrite('[error] 连接失败（后端 WS 路由为 /）');
  ws.onclose = (ev) => {
    $('wsMeta').textContent = `已断开 (${ev.code})`;
    wsWrite(`[close] code=${ev.code} reason=${ev.reason || '—'}`);
  };
}

function wsSend(text) {
  if (!state.ws || state.ws.readyState !== WebSocket.OPEN) { wsWrite('[send] 未连接'); return; }
  state.ws.send(text);
  wsWrite(`[send] ${text}`);
}

/* ───────────────────────── 初始化 ───────────────────────── */
function switchTab(name) {
  document.querySelectorAll('.tab').forEach((t) => t.classList.toggle('active', t.dataset.tab === name));
  document.querySelectorAll('.panel').forEach((p) => p.classList.toggle('active', p.id === `panel-${name}`));
}

function bind() {
  document.querySelectorAll('.tab').forEach((t) => t.addEventListener('click', () => switchTab(t.dataset.tab)));
  $('btnPing').addEventListener('click', loadCatalog);
  ['epFilter', 'epGroup', 'epMethod'].forEach((id) => $(id).addEventListener('input', renderEndpointTable));
  $('rqSend').addEventListener('click', sendRequest);
  $('pfRun').addEventListener('click', runPerf);
  $('pfStop').addEventListener('click', () => { state.perfStop = true; });
  $('smRun').addEventListener('click', runSmoke);
  $('cfGet').addEventListener('click', () => cfGet('①'));
  $('cfSave').addEventListener('click', cfSave);
  $('cfApply').addEventListener('click', cfApply);
  $('cfReset').addEventListener('click', () => { $('cfLog').textContent = '—'; $('cfState').textContent = '未读取'; $('cfState').className = 'state-box'; });
  $('ssRun').addEventListener('click', runSSE);
  $('wsConnect').addEventListener('click', wsConnect);
  $('wsPing').addEventListener('click', () => wsSend(JSON.stringify({ type: 'websocket.heartbeat', ts: Date.now() / 1000 })));
  $('wsClose').addEventListener('click', () => { if (state.ws) state.ws.close(); });
  $('wsBody').addEventListener('keydown', (e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) wsSend($('wsBody').value); });
}

bind();
$('wsBase').value = wsURL();
loadCatalog();
