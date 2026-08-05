() => {
  const getVisibleText = (el) => {
    const t = (el.innerText || el.textContent || '').trim().replace(/\s+/g, ' ');
    return t.length > 120 ? t.slice(0, 120) + '…' : t;
  };
  const isHidden = (el) => {
    const s = getComputedStyle(el);
    if (s.display === 'none' || s.visibility === 'hidden' || s.opacity === '0') return true;
    if (el.getAttribute('aria-hidden') === 'true') return true;
    if (el.type === 'hidden') return true;
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) return true;
    return false;
  };
  const isInteractive = (el) => {
    const tag = el.tagName.toLowerCase();
    if (['button', 'a', 'input', 'select', 'textarea', 'option', 'label'].includes(tag)) return true;
    if (el.hasAttribute('onclick')) return true;
    const role = el.getAttribute('role');
    if (role && ['button', 'link', 'checkbox', 'menuitem', 'tab', 'switch', 'radio'].includes(role)) return true;
    if (el.hasAttribute('aria-label') || el.hasAttribute('aria-labelledby')) return true;
    const tab = el.getAttribute('tabindex');
    if (tab && tab !== '-1') return true;
    if (el.isContentEditable) return true;
    return false;
  };
  const getSelector = (el) => {
    if (el.id) return '#' + CSS.escape(el.id);
    const tag = el.tagName.toLowerCase();
    if (el.className && typeof el.className === 'string') {
      const cls = el.className.trim().split(/\s+/).filter(c => c && !c.startsWith('css-')).slice(0, 2);
      if (cls.length) return tag + '.' + cls.join('.');
    }
    return tag;
  };
  const getXPath = (el) => {
    if (el.id) return `//*[@id="${el.id}"]`;
    const parts = [];
    let cur = el;
    while (cur && cur.nodeType === 1 && cur !== document.body) {
      let idx = 1;
      let sib = cur.previousElementSibling;
      while (sib) { if (sib.tagName === cur.tagName) idx++; sib = sib.previousElementSibling; }
      parts.unshift(cur.tagName.toLowerCase() + '[' + idx + ']');
      cur = cur.parentElement;
    }
    return '//' + parts.join('/');
  };
  const getRect = (el) => {
    const r = el.getBoundingClientRect();
    return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) };
  };
  const inViewport = (r) => r.y < window.innerHeight && r.x < window.innerWidth && r.w > 0 && r.h > 0;
  const getZIndex = (el) => {
    let z = 0, cur = el;
    while (cur && cur !== document.body) {
      const zv = parseInt(getComputedStyle(cur).zIndex);
      if (!isNaN(zv) && zv > z) z = zv;
      cur = cur.parentElement;
    }
    return z;
  };
  const isObscured = (el, rect) => {
    const cx = rect.x + rect.w / 2, cy = rect.y + rect.h / 2;
    if (cx < 0 || cy < 0 || cx > window.innerWidth || cy > window.innerHeight) return true;
    const top = document.elementFromPoint(cx, cy);
    if (!top) return true;
    return !el.contains(top) && el !== top;
  };

  // 收集
  const all = Array.from(document.querySelectorAll('*'));
  const total = all.length;

  // 删噪声 + 不可见
  const noiseTags = new Set(['script', 'style', 'noscript', 'svg', 'path', 'meta', 'link', 'head', 'iframe', 'template', 'picture', 'source']);
  const visible = all.filter(el => {
    if (noiseTags.has(el.tagName.toLowerCase())) return false;
    if (isHidden(el)) return false;
    return true;
  });

  // ③ 可交互
  const interactive = visible.filter(el => isInteractive(el));

  // ② 遮挡 + 采集
  const results = [];
  let uid = 0;
  for (const el of interactive) {
    const rect = getRect(el);
    if (isObscured(el, rect)) continue;

    const tag = el.tagName.toLowerCase();
    const text = getVisibleText(el);
    const href = el.href || '';
    const aria = el.getAttribute('aria-label') || el.getAttribute('alt') || '';
    const placeholder = el.getAttribute('placeholder') || '';
    const inputType = el.type || '';
    const role = el.getAttribute('role') || '';
    const selector = getSelector(el);
    const xpath = getXPath(el);
    const inVp = inViewport(rect);
    const z = getZIndex(el);
    const fp = (text + '|' + href + '|' + aria).slice(0, 200);

    results.push({
      uid: 'el_' + (uid++),
      tag, text, href, aria_label: aria, placeholder,
      input_type: inputType, role, selector, xpath,
      rect, in_viewport: inVp, z_index: z,
      is_visible: true, is_interactive: true,
      similarity_hash: fp,
    });
  }

  return { url: location.href, title: document.title, total_original: total, elements: results };
}