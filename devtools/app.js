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
  const r = await req('PUT', `/service/${id}/config/apply`, { body: { restart: true } });
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

/* ───────────────────────── 插件（AIRI Registry View） ───────────────────────── */
function pgLog(line, obj) {
  const pre = $('pgLog');
  const stamp = new Date().toLocaleTimeString('zh-CN', { hour12: false });
  const text = `[${stamp}] ${line}${obj !== undefined ? '\n' + fmt(obj) : ''}`;
  pre.textContent = pre.textContent === '—' ? text : `${text}\n\n${pre.textContent}`;
}

async function loadPlugins() {
  const r = await req('GET', '/plugin');
  if (!r.ok || !r.data || !Array.isArray(r.data.plugins)) {
    $('pgCards').innerHTML = '';
    cards('pgCards', [{ k: '插件', v: '不可达', cls: 'err', s: r.error || `HTTP ${r.status}` }]);
    return;
  }
  const list = r.data.plugins;
  $('pgCount').textContent = `${list.length} 个插件`;
  cards('pgCards', [
    { k: '插件总数', v: list.length, s: `内置 ${list.filter((x) => x.source === 'builtin').length}` },
    { k: '已启用', v: list.filter((x) => x.enabled).length, cls: 'ok', s: 'enabled=true' },
    { k: '已激活', v: list.filter((x) => x.loaded).length, cls: 'ok', s: 'state=active' },
    { k: '等待依赖', v: list.filter((x) => x.state === 'pending').length,
      cls: list.some((x) => x.state === 'pending') ? 'warn' : '', s: 'pending / missing' },
  ]);

  const rows = list.map((p) => {
    const st = p.state === 'active' ? 'st-ok' : p.state === 'pending' ? 'st-warn' : p.error ? 'st-err' : '';
    const ops = [
      ['enable', '启用'], ['disable', '停用'], ['reload', '重载'],
    ].map(([a, label]) => `<button class="btn pg-act" data-act="${a}" data-id="${esc(p.id)}">${label}</button>`).join(' ')
      + (p.removable ? ` <button class="btn pg-act pg-del" data-act="uninstall" data-id="${esc(p.id)}">卸载</button>` : '');
    return `<tr>
      <td class="mono"><b>${esc(p.id)}</b></td>
      <td class="mono">${esc(p.version)}</td>
      <td>${esc(p.source)}</td>
      <td class="${st}">${esc(p.state)}</td>
      <td>${p.enabled ? '✓' : '—'}</td>
      <td>${p.loaded ? '✓' : '—'}</td>
      <td class="mono">${esc((p.inject || []).join(', ') || '—')}</td>
      <td class="mono">${esc((p.services || []).join(', ') || '—')}</td>
      <td class="mono">${esc((p.missing || []).join(', ') || '—')}</td>
      <td class="mono">${esc(p.path || '—')}</td>
      <td>${ops}</td></tr>`;
  }).join('');
  $('pgTable').innerHTML = `<thead><tr><th>id</th><th>版本</th><th>来源</th><th>状态</th><th>启用</th><th>激活</th><th>inject</th><th>services</th><th>missing</th><th>路径</th><th>操作</th></tr></thead><tbody>${rows || '<tr><td colspan="11" class="muted">无插件</td></tr>'}</tbody>`;
  $('pgTable').querySelectorAll('.pg-act').forEach((b) => {
    b.addEventListener('click', () => pgAction(b.dataset.act, b.dataset.id));
  });

  const cap = await req('GET', '/plugin/capabilities');
  const svcs = cap.data?.services || [];
  const capRows = svcs.map((s) => `<tr>
    <td class="mono">${esc(s.name)}</td>
    <td class="${s.ready ? 'st-ok' : 'st-warn'}">${s.ready ? 'ready' : 'not ready'}</td>
    <td class="mono">${esc((s.providers || []).join(', ') || '—')}</td>
    <td class="mono">${esc(s.value_type || '—')}</td></tr>`).join('');
  $('pgCaps').innerHTML = `<thead><tr><th>服务名</th><th>状态</th><th>提供者</th><th>值类型</th></tr></thead><tbody>${capRows || '<tr><td colspan="4" class="muted">无能力</td></tr>'}</tbody>`;
}

async function pgAction(action, id) {
  let r;
  if (action === 'uninstall') r = await req('DELETE', `/plugin/${encodeURIComponent(id)}`);
  else r = await req('POST', `/plugin/${encodeURIComponent(id)}/${action}`);
  pgLog(`${action} ${id} → ${r.status}`, r.data || r.body);
  await loadPlugins();
}

async function pgInstall() {
  const source = $('pgSource').value.trim();
  if (!source) { pgLog('安装失败：source 为空'); return; }
  const enable = $('pgEnable').checked;
  const r = await req('POST', '/plugin/install', { body: { source, enable } });
  pgLog(`install ${source}（enable=${enable}）→ ${r.status}`, r.data || r.body);
  await loadPlugins();
}

/* ───────────────────────── Live2D / Galgame ───────────────────────── */
function l2dLog(line, obj) {
  const pre = $('l2dTestOut');
  const stamp = new Date().toLocaleTimeString('zh-CN', { hour12: false });
  const text = `[${stamp}] ${line}${obj !== undefined ? '\n' + fmt(obj) : ''}`;
  pre.textContent = pre.textContent === '—' ? text : `${text}\n\n${pre.textContent}`;
}

function l2dBadge(text, kind) {
  const b = $('l2dBadge');
  b.textContent = text;
  b.className = `badge badge-${kind}`;
}

async function loadLive2DStatus() {
  const r = await req('GET', '/live2d/status');
  const d = r.data || {};
  $('l2dStatusOut').textContent = fmt(r.ok ? d : { error: r.error || `HTTP ${r.status}` });
  const running = !!d.running, loaded = !!d.model_loaded;
  l2dBadge(loaded ? '模型已加载' : running ? '服务运行中（模型待载）' : '服务未启动',
           loaded ? 'ok' : running ? 'idle' : 'err');
  cards('l2dCards', [
    { k: '模型 / 服务', v: loaded ? 'READY' : running ? 'RUNNING' : 'OFF',
      cls: loaded ? 'ok' : running ? 'warn' : 'err',
      s: d.model_path ? d.model_path.split(/[\\/]/).slice(-2).join('/') : '—' },
    { k: 'FPS / p95', v: (d.fps || 0).toFixed(1),
      s: `avg ${(d.avg_ms || 0).toFixed(1)}ms · p95 ${(d.p95_ms || 0).toFixed(1)}ms` },
    { k: '视线来源', v: d.gaze_source || 'center',
      cls: d.gaze_source === 'face' ? 'warn' : d.gaze_source === 'mouse' ? 'ok' : '',
      s: `动捕 ${d.face_active ? '活跃' : '无数据'} · 跟随鼠标 ${d.gaze_when_no_face ? '开' : '关'}` },
    { k: '待机 / 说话', v: d.idle ? 'IDLE' : d.speaking ? 'SPEAK' : 'ACTIVE',
      cls: d.idle ? 'warn' : '', s: `表情 ${(d.expressions || []).length} · 动作组 ${Object.keys(d.motion_groups || {}).length}` },
    { k: '渲染 / 内存', v: `${d.render_scale || 1}×`,
      s: `${d.render_width || 0}×${d.render_height || 0} · RSS ${(d.process_rss_mb || 0).toFixed(0)} MB` },
  ]);
  return d;
}

function drawGazeChart(frames) {
  const cv = $('l2dGazeCanvas');
  const ctx = cv.getContext('2d');
  const W = cv.width, H = cv.height, pad = 26;
  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = '#0a0e15'; ctx.fillRect(0, 0, W, H);
  // 网格与 ±1 / 0 基准
  ctx.strokeStyle = '#202838'; ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = pad + (H - 2 * pad) * i / 4;
    ctx.beginPath(); ctx.moveTo(pad, y); ctx.lineTo(W - pad, y); ctx.stroke();
  }
  const mid = H / 2;
  ctx.strokeStyle = '#3a4658'; ctx.setLineDash([4, 4]);
  ctx.beginPath(); ctx.moveTo(pad, mid); ctx.lineTo(W - pad, mid); ctx.stroke();
  ctx.setLineDash([]);
  ctx.fillStyle = '#7d8aa0'; ctx.font = '11px ui-monospace, monospace';
  ctx.fillText('+1', 4, pad + 4); ctx.fillText('0', 8, mid + 4); ctx.fillText('-1', 4, H - pad + 4);

  const plot = (key, color) => {
    ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.beginPath();
    frames.forEach((f, i) => {
      const x = pad + (W - 2 * pad) * (frames.length === 1 ? 0.5 : i / (frames.length - 1));
      const y = mid - Math.max(-1, Math.min(1, Number(f[key]) || 0)) * (H / 2 - pad);
      i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    });
    ctx.stroke();
    ctx.fillStyle = color;
    frames.forEach((f, i) => {
      const x = pad + (W - 2 * pad) * (frames.length === 1 ? 0.5 : i / (frames.length - 1));
      const y = mid - Math.max(-1, Math.min(1, Number(f[key]) || 0)) * (H / 2 - pad);
      ctx.beginPath(); ctx.arc(x, y, 2.5, 0, Math.PI * 2); ctx.fill();
    });
  };
  plot('angle_x', '#4ea1ff');
  plot('eyeball_x', '#f0b357');
  ctx.fillStyle = '#4ea1ff'; ctx.fillText('■ ParamAngleX（头）', W - 250, 18);
  ctx.fillStyle = '#f0b357'; ctx.fillText('■ ParamEyeBallX（眼球）', W - 250, 34);
}

async function l2dGaze() {
  let points;
  try { points = JSON.parse($('l2dGazePoints').value || '[]'); }
  catch (e) { l2dLog('视线轨迹 JSON 解析失败', String(e)); return; }
  const r = await req('POST', '/live2d/test/gaze', { body: { points } });
  if (!r.ok || !r.data) { l2dLog('视线曲线请求失败', r.body || r.error); return; }
  drawGazeChart(r.data.frames || []);
  $('l2dGazeInfo').textContent =
    `${r.data.points} 个采样点 · 灵敏度 ${r.data.config_used?.gaze_sensitivity} · ` +
    `眼球强度 ${r.data.config_used?.gaze_eyeball}`;
  // 同时把最后一个点注入真实模型（服务没启动也不影响曲线）
  const last = points[points.length - 1] || [0, 0];
  const g = await req('POST', '/live2d/gaze', { body: { nx: last[0], ny: last[1] } });
  l2dLog(`视线曲线完成，末点注入模型 ${g.ok ? '已提交' : '服务未启动（仅曲线）'}`,
         r.data.config_used);
}

async function l2dAction(label, method, path, body) {
  const r = await req(method, path, body === undefined ? {} : { body });
  $('l2dActionInfo').textContent =
    `${label} → ${r.status} ${r.ok ? '✓' : '×'} ${r.data?.note || ''}`;
  l2dLog(label, r.data || r.body || r.error);
  return r;
}

async function loadDialogue() {
  const s = await req('GET', '/live2d/dialogue');
  $('l2dDialogueState').textContent = fmt(s.ok ? s.data : { error: s.error });
  const b = await req('GET', '/live2d/backlog', { query: { limit: 20, offset: 0 } });
  const rows = (b.data?.entries || []).map((e, i) => `<tr>
    <td class="mono">${i + 1}</td><td class="mono">${esc(e.speaker || '—')}</td>
    <td>${esc(e.text || '')}</td><td>${e.read ? '已读' : '—'}</td></tr>`).join('');
  $('l2dBacklog').innerHTML =
    `<thead><tr><th>#</th><th>说话人</th><th>台词</th><th>状态</th></tr></thead><tbody>${rows || '<tr><td colspan="4" class="muted">暂无回看</td></tr>'}</tbody>`;
}

async function l2dPush() {
  const choices = ($('l2dChoices').value || '').split(',').map(s => s.trim()).filter(Boolean);
  const text = $('l2dText').value.replace(/\\n/g, '\n');
  const r = await l2dAction('推送台词', 'PUT', '/live2d/dialogue', {
    text, speaker: $('l2dSpeaker').value, emotion: $('l2dEmo').value,
    instant: $('l2dInstant').checked, choices,
  });
  await loadDialogue();
  return r;
}

async function l2dCfgState() {
  const r = await req('GET', '/service/live2d/config');
  $('l2dCfgState').textContent = fmt(r.ok ? r.data : { error: r.error || `HTTP ${r.status}` });
  return r;
}

function l2dCfgPatch() {
  return {
    gaze_when_no_face: $('l2dCfgGaze').checked,
    idle_enabled: $('l2dCfgIdle').checked,
    is_face_detected: $('l2dCfgFace').checked,
    dialogue_typing_cps: Number($('l2dCfgCps').value || 30),
    fps: Number($('l2dCfgFps').value || 60),
    opacity: Number($('l2dCfgOpacity').value || 1),
  };
}

async function l2dCfgSave() {
  const r = await req('PUT', '/service/live2d/config',
                      { body: { config: l2dCfgPatch() } });
  l2dLog('① 只保存配置（pending 应变为 true，运行态不变）', r.data || r.body);
  await l2dCfgState();
  await loadLive2DStatus();
}

async function l2dCfgApply() {
  const r = await req('PUT', '/service/live2d/config/apply',
                      { body: { restart: false } });
  l2dLog('② 显式应用（on_config_change 增量热应用，不重启）', r.data || r.body);
  await l2dCfgState();
  await loadLive2DStatus();
}

async function l2dSuite() {
  const r = await req('POST', '/live2d/test/suite');
  const d = r.data || {};
  l2dLog(`离线自检 ${d.passed}/${d.total} 通过（${d.elapsed_ms}ms，${d.environment}）`, d.cases);
  l2dBadge(`自检 ${d.passed}/${d.total}`, d.ok ? 'ok' : 'err');
  $('l2dTestOut').textContent =
    `${d.passed}/${d.total} 通过 · ${d.elapsed_ms}ms\n\n` +
    (d.cases || []).map(c => `[${c.ok ? 'PASS' : 'FAIL'}] ${c.name} (${c.ms}ms) ${typeof c.detail === 'string' ? c.detail : JSON.stringify(c.detail)}`).join('\n')
    + '\n\n' + (r.ok ? '' : fmt(r.body));
}

async function l2dSmoke() {
  const r = await req('POST', '/live2d/test/smoke', { body: {} });
  const d = r.data || {};
  l2dLog(`真实服务冒烟 ${d.passed}/${d.total} 通过`, d.steps);
  await loadDialogue();
  await loadLive2DStatus();
}

/* ───────────────────────── 初始化 ───────────────────────── */
function switchTab(name) {
  document.querySelectorAll('.tab').forEach((t) => t.classList.toggle('active', t.dataset.tab === name));
  document.querySelectorAll('.panel').forEach((p) => p.classList.toggle('active', p.id === `panel-${name}`));
  if (name === 'plugins' && !$('pgTable').innerHTML) loadPlugins();
  if (name === 'live2d' && !$('l2dCards').innerHTML) {
    loadLive2DStatus();
    loadDialogue();
    l2dCfgState();
  }
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
  $('pgInstall').addEventListener('click', pgInstall);
  $('pgRefresh').addEventListener('click', loadPlugins);
  $('pgSource').addEventListener('keydown', (e) => { if (e.key === 'Enter') pgInstall(); });

  // Live2D / Galgame 面板
  const bind = (id, fn) => { const el = $(id); if (el) el.addEventListener('click', fn); };
  bind('l2dRefresh', loadLive2DStatus);
  bind('l2dStart', () => l2dAction('启动服务', 'POST', '/service/live2d/start', {}).then(loadLive2DStatus));
  bind('l2dStop', () => l2dAction('停止服务', 'POST', '/service/live2d/stop', {}).then(loadLive2DStatus));
  bind('l2dSuite', l2dSuite);
  bind('l2dSmoke', l2dSmoke);
  bind('l2dGazeDraw', l2dGaze);
  bind('l2dGazeHome', () => l2dAction('视线回中', 'POST', '/live2d/gaze', { nx: 0, ny: 0 }));
  bind('l2dExprBtn', () => l2dAction('切表情', 'POST', '/live2d/expression',
    { expression: $('l2dExpr').value.trim() }));
  bind('l2dMotionBtn', () => l2dAction('播动作', 'POST', '/live2d/motion',
    { group: $('l2dMotion').value.trim() || 'Idle', index: 0, priority: 2 }));
  bind('l2dEmotionBtn', () => l2dAction('按情绪切', 'POST', '/live2d/emotion',
    { emotion: $('l2dEmotion').value.trim() }));
  bind('l2dSpeakOn', () => l2dAction('说话开始', 'POST', '/live2d/speaking', { on: true }));
  bind('l2dSpeakOff', () => l2dAction('说话结束', 'POST', '/live2d/speaking', { on: false }));
  bind('l2dBlink', () => l2dAction('眨眼', 'POST', '/live2d/blink', {}));
  bind('l2dReset', () => l2dAction('复位', 'POST', '/live2d/reset', { target: 'all' }));
  bind('l2dPush', l2dPush);
  bind('l2dSkip', () => l2dAction('跳过打字机', 'POST', '/live2d/dialogue/skip', {}).then(loadDialogue));
  bind('l2dAdvance', () => l2dAction('推进台词', 'POST', '/live2d/dialogue/advance', {}).then(loadDialogue));
  bind('l2dClear', () => l2dAction('清空对话', 'POST', '/live2d/dialogue/clear', {}).then(loadDialogue));
  bind('l2dCfgSave', l2dCfgSave);
  bind('l2dCfgApply', l2dCfgApply);
  $('l2dGazePoints').addEventListener('keydown', (e) => { if (e.key === 'Enter') l2dGaze(); });
  $('l2dText').addEventListener('keydown', (e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) l2dPush(); });
}

bind();
$('wsBase').value = wsURL();
loadCatalog();
