from dataclasses import asdict
from difflib import SequenceMatcher
import hashlib
import json
import re
from typing import Any, Dict, List, Optional
from lxml import html as lxml_html

from ...utils.file import read_text
from ...runtime import RuntimePath
from .models import DistilledDOM,DomElement,DomChunk

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

class DOMDistiller:
    _DISTILL_JS=None
    print(RuntimePath.get_scripts_path("./distiller.js"))
    """
    7 级 DOM 蒸馏器

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

    def distill_html(
        self,
        html: str,
        url: str = "",
        title: str = "",
        viewport: Dict[str, int]|None = None,
    ) -> DistilledDOM:
        tree = lxml_html.fromstring(html)
        bodies = tree.findall(".//body")
        if len(bodies) > 0:
            body = bodies[0]
        else:
            body = tree

        all_elements = list(body.iter())
        total_original = len(all_elements)

        # 删噪声标签
        elements=[]
        for e in all_elements:
            if e.tag not in NOISE_TAGS:
                elements.append(e)

        # 删不可见：aria-hidden + CSS display:none/visibility:hidden + input[type=hidden]
        elements = [e for e in elements if e.get("aria-hidden") != "true"]
        elements = [e for e in elements if not self.__is_style_hidden(e)]
        elements = [e for e in elements if (e.get("type") or "").lower() != "hidden"]

        # 传播隐藏：父元素有 display:none / aria-hidden 时子元素也视为隐藏
        hidden_ancestors = set()
        for el in elements:
            parent = el.getparent()
            while parent is not None:
                if id(parent) in hidden_ancestors:
                    hidden_ancestors.add(id(el))
                    break
                if self.__is_style_hidden(parent) or parent.get("aria-hidden") == "true":
                    hidden_ancestors.add(id(el))
                    break
                parent = parent.getparent()
        elements = [e for e in elements if id(e) not in hidden_ancestors]

        # 模拟 z-index 遮挡检测（简化版：基于 DOM 顺序 + aria-modal）
        elements = self.__filter_obscured(elements)

        # 只保留可交互
        elements = self.__filter_interactive(elements)

        # 转 DomElement
        dom_elements=[]
        for idx,e in enumerate(elements):
            dom_elements.append(self.__element_to_dom(e,idx))
        # 后处理
        return self.__post_process(dom_elements, url, title, total_original)

    def __is_style_hidden(self, el) -> bool:
        """解析 style 属性，检测 display:none / visibility:hidden / opacity:0"""
        style = (el.get("style") or "").lower().replace(" ", "")
        if "display:none" in style:
            return True
        if "visibility:hidden" in style:
            return True
        if "opacity:0" in style:
            return True
        # hidden 属性
        if el.get("hidden") is not None:
            return True
        return False

    async def distill_page(self, page, url: str = "", title: str = "") -> DistilledDOM:
        if self._DISTILL_JS is None:
            self._DISTILL_JS = read_text(RuntimePath.get_scripts_path("distiller.js"))
        raw = await page.evaluate(self._DISTILL_JS)
        return self.__distill_from_js_result(raw)

    def __distill_from_js_result(self, raw: Dict) -> DistilledDOM:
        url = raw.get("url", "")
        title = raw.get("title", "")
        total_original = raw.get("total_original", 0)
        elements_raw = raw.get("elements", [])
        elements=[]
        for idx,e in enumerate(elements_raw):
            elements.append(self.__dict_to_dom(e,idx))
        return self.__post_process(elements, url, title, total_original)

    # 公开别名（Browser 类调用）
    def distill(self, raw: Dict) -> DistilledDOM:
        return self.__distill_from_js_result(raw)

    # ═══════════════════════════════════════
    #  各级过滤
    # ═══════════════════════════════════════

    def __filter_obscured(self, elements: List[Any]) -> List[Any]:
        """② 遮挡检测：有 aria-modal=true 的弹窗出现时，屏蔽其后的同级元素"""
        filtered = []
        in_modal = False
        for el in elements:
            # 检测 modal 开始
            if el.get("aria-modal") == "true" or el.tag in ("dialog",):
                in_modal = True
                filtered.append(el)
                continue
            # modal 内的元素保留
            if in_modal:
                # 简化的 modal 结束检测：遇到 body 直接子元素且不是 dialog
                parent = el.getparent()
                if parent is not None and parent.tag == "body" and el.tag != "dialog":
                    in_modal = False
                    filtered.append(el)
                else:
                    filtered.append(el)
                continue
            filtered.append(el)
        return filtered

    def __filter_interactive(self, elements: List[Any]) -> List[Any]:
        """只保留可交互元素或有语义信息的元素"""
        result = []
        for el in elements:
            tag = el.tag.lower() if isinstance(el.tag, str) else ""
            if tag in INTERACTIVE_TAGS:
                result.append(el)
                continue
            # 有 onclick
            if el.get("onclick"):
                result.append(el)
                continue
            # 有 aria 角色
            role = el.get("role", "")
            if role and role in {"button", "link", "menuitem", "tab", "switch", "checkbox", "radio", "option"}:
                result.append(el)
                continue
            # 有 aria-label 或 aria-labelledby
            if el.get("aria-label") or el.get("aria-labelledby"):
                result.append(el)
                continue
            # 有 tabindex
            tab = el.get("tabindex")
            if tab and tab != "-1":
                result.append(el)
                continue
            # contenteditable
            if el.get("contenteditable") == "true":
                result.append(el)
                continue
        return result

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
            "removed_by_noise": total_original - len(elements),
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
        """移除无语义的纯包装 div/span/section/article"""
        keep = []
        for el in elements:
            has_semantics = bool(
                el.text or el.href or el.aria_label
                or el.placeholder or el.role or el.input_type
            )
            if has_semantics:
                keep.append(el)
            elif el.tag in ("div", "span", "section", "article", "main", "header", "footer"):
                # 纯布局容器，丢弃
                continue
            else:
                keep.append(el)
        return keep

    def __deduplicate(self, elements: List[DomElement]) -> List[DomElement]:
        seen_hashes: set[str] = set()
        seen_texts: List[str] = []
        # 按 href 前缀去重（同一搜索页多个链接）
        seen_href_prefixes: set[str] = set()
        deduped = []

        for el in elements:
            # 5a: 完全同指纹（同文本+同href+同aria）
            fp = (el.text + "|" + el.href + "|" + el.aria_label)[:200]
            h = hashlib.md5(fp.encode("utf-8", errors="ignore")).hexdigest()[:12]
            if h in seen_hashes:
                continue
            seen_hashes.add(h)

            # 5b: 高相似文本（如 "加入购物车" vs "立即购买" 同商品）
            skip = False
            for prev in seen_texts:
                if prev and el.text and len(el.text) > 2:
                    ratio = SequenceMatcher(None, el.text[:60], prev[:60]).ratio()
                    if ratio > self.similarity_threshold:
                        skip = True
                        break
            if skip:
                continue

            # 5c: 同 href 前缀去重（/search?q=手机 vs /search?q=手机）
            if el.href:
                # 去掉查询参数后比较
                clean_href = el.href.split("?")[0].rstrip("/")
                if clean_href in seen_href_prefixes:
                    # 同路径只留第一个
                    continue
                seen_href_prefixes.add(clean_href)

            seen_texts.append(el.text)
            deduped.append(el)

        return deduped

    def __assign_stable_ids(self, elements: List[DomElement]) -> List[DomElement]:
        seen_selectors: Dict[str, int] = {}
        for i, el in enumerate(elements):
            # selector 生成
            if el.selector.startswith("#"):
                base = el.selector[1:]
            elif el.aria_label:
                base = f'{el.tag}[aria-label="{el.aria_label[:30]}"]'
            else:
                # nth-of-type 兜底
                tag = el.tag
                seen_selectors[tag] = seen_selectors.get(tag, 0) + 1
                base = f"{tag}:nth-of-type({seen_selectors[tag]})"

            el.selector = base[:80]
            el.uid = f"pw-{i:03d}"
        return elements

    def _chunk_elements(self, elements: List[DomElement]) -> List[DomChunk]:
        # 视口内优先排序
        ordered = sorted(elements, key=lambda e: (not e.in_viewport, e.z_index))
        chunks = []
        for i in range(0, len(ordered), self.max_chunk_size):
            batch = ordered[i:i + self.max_chunk_size]
            est = sum(max(1, len(f"{e.text}{e.aria_label}{e.href}{e.selector}") // 4) for e in batch)
            chunks.append(DomChunk(
                chunk_index=len(chunks),
                total_chunks=0,
                elements=batch,
                total_tokens_estimate=est,
            ))
        for c in chunks:
            c.total_chunks = len(chunks)
        return chunks


    def __element_to_dom(self, el, idx: int) -> DomElement:
        tag = el.tag.lower() if isinstance(el.tag, str) else "unknown"
        text = (el.text_content() or "").strip().replace("\n", " ")[: self.max_text_length]
        # 去多余空格
        text = re.sub(r"\s+", " ", text)

        href = el.get("href", "") or ""
        aria = el.get("aria-label", "") or el.get("alt", "") or ""
        placeholder = el.get("placeholder", "") or ""
        input_type = el.get("type", "") or ""
        role = el.get("role", "") or ""

        # CSS selector 构建
        if el.get("id"):
            selector = f"#{el.get('id')}"
        elif el.get("class"):
            cls = el.get("class", "").strip().split()[0]
            selector = f"{tag}.{cls}" if cls else tag
        else:
            selector = tag

        # XPath
        xpath = self.__build_xpath(el)

        # 指纹
        fp = f"{text}|{href}|{aria}"

        # 深度
        depth = self.__calc_depth(el)

        # 可见性（input type=hidden 视为不可见）
        is_visible = True
        if input_type == "hidden":
            is_visible = False

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
            xpath=xpath,
            depth=depth,
            is_visible=is_visible,
            is_interactive=(tag in INTERACTIVE_TAGS),
            similarity_hash=fp[:200],
        )

    def __dict_to_dom(self, raw: Dict, idx: int) -> DomElement:
        return DomElement(
            uid=raw.get("uid", f"el_{idx}"),
            tag=raw.get("tag", ""),
            text=raw.get("text", "")[: self.max_text_length],
            href=raw.get("href", "")[:200],
            aria_label=raw.get("aria_label", "")[:120],
            placeholder=raw.get("placeholder", ""),
            input_type=raw.get("input_type", ""),
            role=raw.get("role", ""),
            selector=raw.get("selector", "")[:80],
            xpath=raw.get("xpath", ""),
            rect=raw.get("rect", {}),
            in_viewport=raw.get("in_viewport", True),
            z_index=raw.get("z_index", 0),
            is_visible=raw.get("is_visible", True),
            is_interactive=raw.get("is_interactive", True),
            similarity_hash=raw.get("similarity_hash", "")[:200],
        )

    def __build_xpath(self, el) -> str:
        parts = []
        cur: Optional[Any] = el
        while cur is not None and cur.getparent() is not None:
            parent = cur.getparent()
            if parent is None:
                break
            siblings = [s for s in parent if s.tag == cur.tag]  # type: ignore
            idx = siblings.index(cur) + 1 if siblings else 1
            parts.append(f"{cur.tag}[{idx}]")
            cur = parent
        return "/" + "/".join(reversed(parts))

    def __calc_depth(self, el) -> int:
        depth = 0
        cur = el
        while cur.getparent() is not None:
            depth += 1
            cur = cur.getparent()  # type: ignore
        return depth

    def format_for_llm(self, dom: DistilledDOM, chunk_index: int = 0) -> str:
        if chunk_index >= len(dom.chunks):
            chunk_index = 0
        chunk = dom.chunks[chunk_index]
        lines = [
            f"# 页面: {dom.title or dom.url}",
            f"# URL: {dom.url}",
            f"# 区块 {chunk.chunk_index+1}/{chunk.total_chunks} (~{chunk.total_tokens_estimate} tokens)",
            "",
            "可用元素：",
        ]
        for el in chunk.elements:
            parts = [f"[{el.uid}]", f"<{el.tag}>"]
            if el.text:
                parts.append(f'text="{el.text}"')
            if el.aria_label:
                parts.append(f'aria="{el.aria_label}"')
            if el.placeholder:
                parts.append(f'placeholder="{el.placeholder}"')
            if el.href:
                parts.append(f'href="{el.href[:80]}"')
            if el.input_type:
                parts.append(f'type="{el.input_type}"')
            parts.append(f"sel={el.selector}")
            lines.append("  " + " ".join(parts))

        # 其他区块摘要
        if len(dom.chunks) > 1:
            lines.append("")
            lines.append("[其他区块摘要]")
            for c in dom.chunks:
                if c.chunk_index != chunk_index:
                    tags = [e.tag for e in c.elements[:5]]
                    lines.append(f"  区块 {c.chunk_index+1}: {len(c.elements)} 元素 ({', '.join(tags)}…)")
        return "\n".join(lines)

    def to_json(self, dom: DistilledDOM) -> str:
        return json.dumps(asdict(dom), ensure_ascii=False, indent=2)



