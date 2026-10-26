"""7 级 DOM 蒸馏器：把原始页面压成 LLM 可消费的交互地图。

    原始 HTML (10万 token)
        ▼ 1. 删不可见节点（script/style/display:none/aria-hidden）
        ▼ 2. 删被遮挡元素（z-index + bounds 检测）
        ▼ 3. 只保留可交互元素
        ▼ 4. 折叠冗余容器（无属性纯 div 包装）
        ▼ 5. 去重（同 URL / 高相似文本）
        ▼ 6. 编唯一 ID + 稳定 CSS selector
        ▼ 7. 按视口分块 + 相似度过滤
    精简交互地图 (500~5000 token)
"""

from __future__ import annotations

import hashlib
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from ...runtime import RuntimePath, is_dev_mode
from ...utils.file import read_text
from .models import DistilledDOM, DomChunk, DomElement

INTERACTIVE_TAGS = {
    "a", "button", "input", "select", "textarea",
    "option", "label", "summary", "details",
    "menuitem", "tab", "switch", "checkbox", "radio",
}

NOISE_TAGS = {
    "script", "style", "noscript", "svg", "path",
    "meta", "link", "head", "iframe", "template",
    "picture", "source", "track", "area",
}

INTERACTIVE_ROLES = {
    "button", "link", "menuitem", "tab", "switch",
    "checkbox", "radio", "option",
}

SIMILARITY_WINDOW = 60


class DOMDistiller:
    _DISTILL_JS: Optional[str] = None

    def __init__(
        self,
        max_chunk_size: int = 20,
        similarity_threshold: float = 0.88,
        max_text_length: int = 120,
        keep_semantic_tags: bool = True,
    ):
        self.max_chunk_size = max_chunk_size
        self.similarity_threshold = similarity_threshold
        self.max_text_length = max_text_length
        self.keep_semantic_tags = keep_semantic_tags

    # ═══════════════════════════════════════
    #  入口
    # ═══════════════════════════════════════

    def distill_html(
        self,
        html: str,
        url: str = "",
        title: str = "",
        viewport: Dict[str, int] | None = None,
    ) -> DistilledDOM:
        """从静态 HTML 蒸馏（无浏览器时用）。"""
        from lxml import html as lxml_html

        tree = lxml_html.fromstring(html)
        bodies = tree.findall(".//body")
        body = bodies[0] if bodies else tree

        # S40：过滤注释 / PI 节点 —— 它们的 tag 是函数不是字符串
        all_elements = [e for e in body.iter() if isinstance(e.tag, str)]
        total_original = len(all_elements)

        # ① 删噪声标签
        elements = [e for e in all_elements if e.tag not in NOISE_TAGS]

        # ① 删不可见：aria-hidden + inline style + input[type=hidden]
        elements = [e for e in elements if e.get("aria-hidden") != "true"]
        elements = [e for e in elements if not self.__is_style_hidden(e)]
        elements = [e for e in elements if (e.get("type") or "").lower() != "hidden"]

        # 传播隐藏：祖先隐藏则后代也隐藏
        elements = [e for e in elements if not self.__has_hidden_ancestor(e)]

        # ② 遮挡
        elements = self.__filter_obscured(elements)

        # ③ 只保留可交互
        elements = self.__filter_interactive(elements)

        dom_elements = [self.__element_to_dom(e, i) for i, e in enumerate(elements)]
        return self.__post_process(dom_elements, url, title, total_original)

    async def distill_page(self, page, url: str = "", title: str = "") -> DistilledDOM:
        """在真实页面上执行注入脚本蒸馏（浏览器路径）。"""
        if type(self)._DISTILL_JS is None:
            type(self)._DISTILL_JS = self.__load_script("distiller.js")
        raw = await page.evaluate(type(self)._DISTILL_JS)
        return self.__distill_from_js_result(raw)

    def __load_script(self, name: str) -> str:
        if is_dev_mode():
            js_path = Path(__file__).parent / "scripts" / name
        else:
            js_path = RuntimePath.get_scripts_path(name)

        content = read_text(js_path)
        if content is None:
            raise FileNotFoundError(f"蒸馏脚本缺失: {js_path}")
        return content

    def __distill_from_js_result(self, raw: Dict) -> DistilledDOM:
        url = raw.get("url", "")
        title = raw.get("title", "")
        total_original = raw.get("total_original", 0)
        elements_raw = raw.get("elements", []) or []
        elements = [self.__dict_to_dom(e, i) for i, e in enumerate(elements_raw)]
        return self.__post_process(elements, url, title, total_original)

    # 公开别名（Browser 类调用）
    def distill(self, raw: Dict) -> DistilledDOM:
        return self.__distill_from_js_result(raw)

    # ═══════════════════════════════════════
    #  各级过滤
    # ═══════════════════════════════════════

    def __is_style_hidden(self, el) -> bool:
        """解析 style 属性，检测 display:none / visibility:hidden / opacity:0"""
        style = (el.get("style") or "").lower().replace(" ", "")
        if "display:none" in style:
            return True
        if "visibility:hidden" in style:
            return True
        if "opacity:0" in style:
            return True
        if el.get("hidden") is not None:
            return True
        return False

    def __has_hidden_ancestor(self, el) -> bool:
        """祖先隐藏 → 自己也隐藏（原实现用 id() 集合，遍历重复）"""
        cur = el.getparent()
        while cur is not None:
            if isinstance(cur.tag, str) and (
                self.__is_style_hidden(cur) or cur.get("aria-hidden") == "true"
            ):
                return True
            cur = cur.getparent()
        return False

    def __filter_obscured(self, elements: List[Any]) -> List[Any]:
        """② 遮挡检测：S36 原实现三个分支都 append，等于没过滤。

        有 modal（aria-modal=true 或 <dialog>）时，页面其余部分被遮住，
        只保留 modal 及其后代。
        """
        modal_ids: Set[int] = set()
        for el in elements:
            if el.get("aria-modal") == "true" or el.tag in ("dialog",):
                modal_ids.add(id(el))

        if not modal_ids:
            return elements

        keep = []
        for el in elements:
            cur = el
            while cur is not None:
                if id(cur) in modal_ids:
                    keep.append(el)
                    break
                cur = cur.getparent()
        return keep

    def __filter_interactive(self, elements: List[Any]) -> List[Any]:
        """③ 只保留可交互元素或有语义信息的元素"""
        result = []
        for el in elements:
            tag = el.tag.lower() if isinstance(el.tag, str) else ""
            if tag in INTERACTIVE_TAGS:
                result.append(el)
                continue
            if el.get("onclick"):
                result.append(el)
                continue
            role = el.get("role", "")
            if role and role in INTERACTIVE_ROLES:
                result.append(el)
                continue
            if el.get("aria-label") or el.get("aria-labelledby"):
                result.append(el)
                continue
            tab = el.get("tabindex")
            if tab and tab != "-1":
                result.append(el)
                continue
            if el.get("contenteditable") == "true":
                result.append(el)
                continue
        return result

    # ═══════════════════════════════════════
    #  后处理（④⑤⑥⑦）
    # ═══════════════════════════════════════

    def __post_process(
        self,
        elements: List[DomElement],
        url: str, title: str,
        total_original: int,
    ) -> DistilledDOM:
        # ④ 折叠冗余容器
        elements = self.__collapse_redundant(elements)
        # ⑤ 去重
        elements = self.__deduplicate(elements)
        # ⑥ 唯一 ID + 稳定 selector
        elements = self.__assign_stable_ids(elements)
        # ⑦ 分块
        chunks = self._chunk_elements(elements)

        total_after = len(elements)
        compression = 1 - (total_after / max(total_original, 1))

        stats = {
            "total_original": total_original,
            "after_filter": total_after,
            "chunks": len(chunks),
            "removed": max(total_original - total_after, 0),
        }

        return DistilledDOM(
            url=url,
            title=title,
            total_original_elements=total_original,
            total_after_filter=total_after,
            compression_ratio=round(compression, 4),
            chunks=chunks,
            stats=stats,
        )

    def __collapse_redundant(self, elements: List[DomElement]) -> List[DomElement]:
        """④ 移除无语义的纯包装容器"""
        layout_tags = {"div", "span", "section", "article", "main", "header", "footer"}
        keep = []
        for el in elements:
            has_semantics = bool(
                el.text or el.href or el.aria_label
                or el.placeholder or el.role or el.input_type
            )
            if has_semantics:
                keep.append(el)
            elif el.tag in layout_tags:
                continue
            else:
                keep.append(el)
        return keep

    def __deduplicate(self, elements: List[DomElement]) -> List[DomElement]:
        """⑤ 去重：同指纹 / 高相似文本 / 同 href 路径"""
        seen_hashes: Set[str] = set()
        seen_texts: List[str] = []
        seen_href_paths: Set[str] = set()
        deduped: List[DomElement] = []

        for el in elements:
            # 5a 完全同指纹
            fp = (el.text + "|" + el.href + "|" + el.aria_label)[:200]
            h = hashlib.md5(fp.encode("utf-8", errors="ignore")).hexdigest()[:12]
            if h in seen_hashes:
                continue
            seen_hashes.add(h)

            # 5b 高相似文本（S39：只在最近窗口内比对）
            if el.text and len(el.text) > 2:
                skip = False
                for prev in seen_texts[-SIMILARITY_WINDOW:]:
                    if prev:
                        ratio = SequenceMatcher(None, el.text[:60], prev[:60]).ratio()
                        if ratio > self.similarity_threshold:
                            skip = True
                            break
                if skip:
                    continue

            # 5c 同 href 路径（去查询参数）只留第一个
            if el.href:
                clean_href = el.href.split("?")[0].rstrip("/")
                if clean_href in seen_href_paths:
                    continue
                seen_href_paths.add(clean_href)

            seen_texts.append(el.text)
            deduped.append(el)

        return deduped

    def __assign_stable_ids(self, elements: List[DomElement]) -> List[DomElement]:
        """⑥ 稳定 selector + 唯一 uid"""
        tag_counter: Dict[str, int] = {}
        for i, el in enumerate(elements):
            sel = (el.selector or "").strip()

            if sel.startswith("#") or sel.startswith(".") \
                    or "." in sel or "[" in sel:
                # JS 已经给了可用选择器（#id / tag.cls / 带属性）— 原样保留
                base = sel
            elif el.aria_label:
                base = f'{el.tag}[aria-label="{el.aria_label[:30]}"]'
            elif el.xpath:
                # 有 xpath 时优先用它（Playwright 支持 xpath= 前缀）
                base = f"xpath={el.xpath}"
            else:
                tag_counter[el.tag] = tag_counter.get(el.tag, 0) + 1
                base = f"{el.tag}:nth-of-type({tag_counter[el.tag]})"

            el.selector = base[:200]
            el.uid = f"pw-{i:03d}"
        return elements

    def _chunk_elements(self, elements: List[DomElement]) -> List[DomChunk]:
        """⑦ 视口内优先排序 + 固定大小分块"""
        ordered = sorted(elements, key=lambda e: (not e.in_viewport, e.z_index))
        chunks: List[DomChunk] = []
        for i in range(0, len(ordered), self.max_chunk_size):
            batch = ordered[i:i + self.max_chunk_size]
            est = sum(
                max(1, len(f"{e.text}{e.aria_label}{e.href}{e.selector}") // 4)
                for e in batch
            )
            chunks.append(DomChunk(
                chunk_index=len(chunks),
                total_chunks=0,
                elements=batch,
                total_tokens_estimate=est,
            ))
        for c in chunks:
            c.total_chunks = len(chunks)
        return chunks

    # ═══════════════════════════════════════
    #  元素转换
    # ═══════════════════════════════════════

    def __element_to_dom(self, el, idx: int) -> DomElement:
        tag = el.tag.lower() if isinstance(el.tag, str) else "unknown"
        text = (el.text_content() or "").strip().replace("\n", " ")
        text = re.sub(r"\s+", " ", text)[: self.max_text_length]

        href = el.get("href", "") or ""
        aria = el.get("aria-label", "") or el.get("alt", "") or ""
        placeholder = el.get("placeholder", "") or ""
        input_type = el.get("type", "") or ""
        role = el.get("role", "") or ""

        if el.get("id"):
            selector = f"#{el.get('id')}"
        elif el.get("class"):
            cls = (el.get("class", "") or "").strip().split()[0] if el.get("class") else ""
            selector = f"{tag}.{cls}" if cls else tag
        else:
            selector = tag

        return DomElement(
            uid=f"el_{idx}",
            tag=tag,
            text=text,
            href=href[:200],
            aria_label=aria[:120],
            placeholder=placeholder[:80],
            input_type=input_type,
            role=role,
            selector=selector[:80],
            xpath=self.__build_xpath(el),
            depth=self.__calc_depth(el),
            is_visible=input_type != "hidden",
            is_interactive=(tag in INTERACTIVE_TAGS),
            similarity_hash=f"{text}|{href}|{aria}"[:200],
        )

    def __dict_to_dom(self, raw: Dict, idx: int) -> DomElement:
        return DomElement(
            uid=raw.get("uid", f"el_{idx}"),
            tag=raw.get("tag", ""),
            text=(raw.get("text", "") or "")[: self.max_text_length],
            href=(raw.get("href", "") or "")[:200],
            aria_label=(raw.get("aria_label", "") or "")[:120],
            placeholder=raw.get("placeholder", "") or "",
            input_type=raw.get("input_type", "") or "",
            role=raw.get("role", "") or "",
            selector=(raw.get("selector", "") or "")[:200],
            xpath=raw.get("xpath", "") or "",
            rect=raw.get("rect", {}) or {},
            in_viewport=bool(raw.get("in_viewport", True)),
            z_index=int(raw.get("z_index", 0) or 0),
            is_visible=bool(raw.get("is_visible", True)),
            is_interactive=bool(raw.get("is_interactive", True)),
            similarity_hash=(raw.get("similarity_hash", "") or "")[:200],
        )

    def __build_xpath(self, el) -> str:
        parts: List[str] = []
        cur = el
        while cur is not None and cur.getparent() is not None:
            parent = cur.getparent()
            if parent is None:
                break
            siblings = [s for s in parent if isinstance(s.tag, str) and s.tag == cur.tag]
            try:
                idx = siblings.index(cur) + 1
            except ValueError:
                idx = 1
            parts.append(f"{cur.tag}[{idx}]")
            cur = parent
        return "/" + "/".join(reversed(parts))

    def __calc_depth(self, el) -> int:
        depth = 0
        cur = el
        while cur is not None and cur.getparent() is not None:
            depth += 1
            cur = cur.getparent()
        return depth

    # ═══════════════════════════════════════
    #  输出
    # ═══════════════════════════════════════

    def format_for_llm(self, dom: DistilledDOM, chunk_index: int = 0) -> str:
        """把某个分块渲染成 LLM 可直接读的文本。

        每个元素一行：`uid | tag | 文本/aria | selector`。
        LLM 输出命令时用 uid，执行侧再映射回 selector。
        """
        if not dom.chunks:
            return f"# 页面: {dom.title or dom.url}\n# (无可交互元素)"

        if chunk_index >= len(dom.chunks):
            chunk_index = 0
        chunk = dom.chunks[chunk_index]

        lines = [
            f"# 页面: {dom.title or dom.url}",
            f"# URL: {dom.url}",
            f"# 分块: {chunk.chunk_index + 1}/{chunk.total_chunks}"
            f" (共 {dom.total_after_filter} 个可交互元素,"
            f"压缩率 {dom.compression_ratio * 100:.1f}%)",
            "# 格式: uid | tag | 文本 | selector",
            "",
        ]
        for e in chunk.elements:
            label = e.text or e.aria_label or e.placeholder or e.input_type or e.role
            if not label and e.href:
                label = e.href
            extra = []
            if e.href:
                extra.append(f"href={e.href[:60]}")
            if e.input_type:
                extra.append(f"type={e.input_type}")
            if e.placeholder:
                extra.append(f"ph={e.placeholder[:30]}")
            tail = (" " + " ".join(extra)) if extra else ""
            vp = "" if e.in_viewport else " (视口外)"
            lines.append(f"{e.uid} | {e.tag} | {label}{tail}{vp}")

        return "\n".join(lines)

    def format_all_for_llm(self, dom: DistilledDOM) -> str:
        return "\n\n".join(
            self.format_for_llm(dom, i) for i in range(len(dom.chunks))
        )