"""
项目文档生成器（增强版）
递归扫描目录，提取所有 .py 文件的代码结构，并可选包含完整源代码，
生成一份清晰的 Markdown 文档，便于 AI 理解项目。

新增：支持「分片输出 (split)」
- 一个索引文件（默认 README.md）：项目统计 + 目录树 + 文件/分片索引表
- 其余内容按字符配额拆分到多个实际分片文件（如 part_01_xxx.md, part_02_xxx.md ...）
- 实现「代码分批上传」，避免单个文件超出 AI 上下文窗口
"""
import os
import ast
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Union
import fnmatch

DEFAULT_OUTPUT_FILE = "PROJECT.md"
DEFAULT_EXCLUDE_PATTERNS = [
    '.git', 
    '.venv', 
    'venv', 
    'env', 
    "tests",
    'node_modules',
    '.idea', 
    '.vscode', 
    'dist',
    'build',
    '*.egg-info', 
    '.pytest_cache', 
    "__pycache__",
    "*.log",
    "resources",
    "database",
    ".mypy_cache",
    ".ruff_cache",
    "test*",
]

from dataclasses import dataclass

@dataclass
class SplitConfig:
    enabled: bool = True
    maxCharsPerFile: int = 80000
    indexFileName: str = 'README.md'

@dataclass
class SplitState:
    part_index: int = 0
    files: Optional[List[Dict[str, str]]] = None

    def __post_init__(self):
        if self.files is None:
            self.files = []

class ProjectDocGenerator:

    def __init__(
        self,
        project_root: Union[str, Path],
        output_file: str = DEFAULT_OUTPUT_FILE,
        exclude_patterns: Optional[List[str]] = None,
        include_tests: bool = False,
        include_source: bool = True,
        split: Optional[SplitConfig] = None,   # 新增：分片配置
    ):
        path_ = Path(__file__).parent.parent
        self.project_root = path_ / project_root
        self.output_file = Path(output_file)
        if not self.output_file.is_absolute():
            self.output_file = path_ / self.output_file

        self.exclude_patterns = exclude_patterns or DEFAULT_EXCLUDE_PATTERNS
        self.include_tests = include_tests
        self.include_source = include_source

        # 分片配置：未传则使用默认（enabled=True）
        self.split = split or SplitConfig()

        self.stats = {
            'total_files': 0,
            'py_files': 0,
            'classes': 0,
            'functions': 0,
            'lines': 0,
            'modules': set(),
        }

    # ------------------------------------------------------------------ 过滤
    def should_exclude(self, path: Path) -> bool:
        """检查是否应该排除该路径"""
        for pattern in self.exclude_patterns:
            if fnmatch.fnmatch(str(path), pattern):
                return True
            for part in path.parts:
                if fnmatch.fnmatch(part, pattern):
                    return True
        return False

    def get_python_files(self) -> List[Path]:
        """递归获取所有 .py 文件"""
        py_files = []
        for root, dirs, files in os.walk(self.project_root):
            root_path = Path(root)
            dirs[:] = [d for d in dirs if not self.should_exclude(root_path / d)]

            for file in files:
                file_path = root_path / file
                if file.endswith('.py') and not self.should_exclude(file_path):
                    if not self.include_tests and file.startswith('test_'):
                        continue
                    py_files.append(file_path)
        return sorted(py_files)

    # ------------------------------------------------------------------ AST
    def extract_code_structure(self, file_path: Path) -> Dict:
        """提取单个文件的代码结构，并保存原始源码。
        若已通过 _structure_cache 预热（分片模式），直接返回缓存，避免重复解析与统计翻倍。
        """
        cache = getattr(self, '_structure_cache', None)
        key = str(file_path)
        if cache is not None and key in cache:
            return cache[key]

        structure = {
            'imports': [],
            'classes': [],
            'functions': [],
            'module_docstring': '',
            'file_size': file_path.stat().st_size,
            'line_count': 0,
            'source_code': '',
            'parse_error': None,
            'read_error': None,
            # 本文件局部计数（不写全局 self.stats，避免多次调用导致翻倍）
            'n_classes': 0,
            'n_functions': 0,
        }

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                structure['source_code'] = content
                structure['line_count'] = len(content.splitlines())

            tree = ast.parse(content)

            if tree.body and isinstance(tree.body[0], ast.Expr) and isinstance(tree.body[0].value, ast.Constant):
                structure['module_docstring'] = tree.body[0].value.s.strip() # type: ignore

            # 仅遍历【模块顶层】节点，避免 ast.walk 递归进入方法体导致重复统计。
            # 类的方法在其 class body 内单独收集。
            for node in tree.body:
                # ---- 导入（顶层）----
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        structure['imports'].append({
                            'type': 'import',
                            'module': alias.name,
                            'alias': alias.asname,
                        })
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ''
                    for alias in node.names:
                        structure['imports'].append({
                            'type': 'from',
                            'module': module,
                            'name': alias.name,
                            'alias': alias.asname,
                        })

                # ---- 类定义 ----
                elif isinstance(node, ast.ClassDef):
                    class_info = {
                        'name': node.name,
                        'bases': [self._get_base_name(base) for base in node.bases],
                        'docstring': ast.get_docstring(node) or '',
                        'methods': [],
                        'decorators': [self._get_decorator_name(d) for d in node.decorator_list],
                    }

                    for item in node.body:
                        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            method_info = {
                                'name': item.name,
                                'is_async': isinstance(item, ast.AsyncFunctionDef),
                                'docstring': ast.get_docstring(item) or '',
                                'args': self._extract_args(item.args),
                                'returns': self._get_annotation(item.returns),
                                'decorators': [self._get_decorator_name(d) for d in item.decorator_list],
                            }
                            class_info['methods'].append(method_info)
                            structure['n_functions'] += 1

                    structure['classes'].append(class_info)
                    structure['n_classes'] += 1

                # ---- 顶层函数 ----
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    func_info = {
                        'name': node.name,
                        'is_async': isinstance(node, ast.AsyncFunctionDef),
                        'docstring': ast.get_docstring(node) or '',
                        'args': self._extract_args(node.args),
                        'returns': self._get_annotation(node.returns),
                        'decorators': [self._get_decorator_name(d) for d in node.decorator_list],
                    }
                    structure['functions'].append(func_info)
                    structure['n_functions'] += 1

        except SyntaxError as e:
            structure['parse_error'] = f"SyntaxError: {e}"
        except Exception as e:
            structure['parse_error'] = f"{type(e).__name__}: {e}"

        return structure

    # ---------------------------------------------------------- 辅助方法
    def _get_base_name(self, base) -> str:
        if isinstance(base, ast.Name):
            return base.id
        if isinstance(base, ast.Attribute):
            return f"{self._get_base_name(base.value)}.{base.attr}"
        if isinstance(base, ast.Call):
            return self._get_base_name(base.func)
        return str(base)

    def _get_decorator_name(self, decorator) -> str:
        if isinstance(decorator, ast.Name):
            return decorator.id
        if isinstance(decorator, ast.Attribute):
            return f"{self._get_base_name(decorator.value)}.{decorator.attr}"
        if isinstance(decorator, ast.Call):
            return self._get_decorator_name(decorator.func)
        return str(decorator)

    def _extract_args(self, args) -> List[Dict]:
        arg_list = []
        for arg in args.args:
            arg_info = {
                'name': arg.arg,
                'annotation': self._get_annotation(arg.annotation),
            }
            arg_list.append(arg_info)

        defaults = [None] * (len(args.args) - len(args.defaults)) + args.defaults
        for i, default in enumerate(defaults):
            if default is not None:
                arg_list[i]['default'] = self._get_default_value(default)

        if args.vararg:
            arg_list.append({
                'name': f"*{args.vararg.arg}",
                'annotation': self._get_annotation(args.vararg.annotation),
            })
        if args.kwarg:
            arg_list.append({
                'name': f"**{args.kwarg.arg}",
                'annotation': self._get_annotation(args.kwarg.annotation),
            })
        return arg_list

    def _get_annotation(self, annotation) -> str:
        if annotation is None:
            return ''
        if isinstance(annotation, ast.Name):
            return annotation.id
        if isinstance(annotation, ast.Attribute):
            return f"{self._get_base_name(annotation.value)}.{annotation.attr}"
        if isinstance(annotation, ast.Subscript):
            return f"{self._get_base_name(annotation.value)}[{self._get_annotation(annotation.slice)}]"
        if isinstance(annotation, ast.Constant):
            return repr(annotation.value)
        return str(annotation)

    def _get_default_value(self, value) -> str:
        if isinstance(value, ast.Constant):
            return repr(value.value)
        if isinstance(value, ast.List):
            return '[]'
        if isinstance(value, ast.Dict):
            return '{}'
        if isinstance(value, ast.Name):
            return value.id
        if isinstance(value, ast.Call):
            return f"{self._get_base_name(value.func)}(...)"
        return str(value)

    # ---------------------------------------------------------- 目录树
    def generate_project_tree(self) -> str:
        lines = []

        def _generate_tree(dir_path: Path, indent: str = "", is_last: bool = True):
            entries = sorted(
                [e for e in dir_path.iterdir() if not self.should_exclude(e)],
                key=lambda x: (not x.is_dir(), x.name),
            )
            for i, entry in enumerate(entries):
                is_last_entry = (i == len(entries) - 1)
                connector = ("└── " if is_last_entry else "├── ")
                if entry.is_dir():
                    lines.append(f"{indent}{connector}{entry.name}/")
                    new_indent = indent + ("    " if is_last_entry else "│   ")
                    _generate_tree(entry, new_indent, is_last_entry)
                else:
                    lines.append(f"{indent}{connector}{entry.name}")

        lines.append(f"📁 {self.project_root.name}/")
        _generate_tree(self.project_root)
        return "\n".join(lines)

    @staticmethod
    def generate_markdown_table(data: Dict[str, List[str]]) -> List[str]:
        keys = list(data.keys())
        header = "| " + " | ".join(keys) + " |"
        separator = "|" + "|".join(["------"] * len(keys)) + "|"
        rows = []
        for row in zip(*data.values()):
            rows.append("| " + " | ".join(str(cell) for cell in row) + " |")
        return [header, separator] + rows

    def _render_file_section(self, file_path: Path) -> List[str]:
        """渲染单个 .py 文件的完整分析区块（便捷入口：先提取再渲染）。"""
        structure = self.extract_code_structure(file_path)
        return self._render_from_structure(structure, file_path)

    def _render_from_structure(self, structure: Dict, file_path: Path) -> List[str]:
        """根据已提取的 structure 渲染该文件的分析区块（不重复解析）。"""
        relative_path = file_path.relative_to(self.project_root)
        out: List[str] = []

        out.append(f"### 📄 `{relative_path}`")
        out.append("")
        out.append(f"- **文件大小**: {structure['file_size'] / 1024:.1f} KB")
        out.append(f"- **代码行数**: {structure['line_count']}")
        out.append("")

        if structure['module_docstring']:
            out.append("#### 模块说明")
            out.append("")
            out.append(f"> {structure['module_docstring']}")
            out.append("")

        if structure['imports']:
            out.append("#### 导入依赖")
            out.append("")
            out.append("```python")
            for imp in structure['imports']:
                if imp['type'] == 'import':
                    line = f"import {imp['module']}"
                    if imp['alias']:
                        line += f" as {imp['alias']}"
                else:
                    line = f"from {imp['module']} import {imp['name']}"
                    if imp['alias']:
                        line += f" as {imp['alias']}"
                out.append(line)
            out.append("```")
            out.append("")

        if structure['classes']:
            out.append("#### 类定义")
            out.append("")
            for cls in structure['classes']:
                bases_str = f"({', '.join(cls['bases'])})" if cls['bases'] else ""
                out.append(f"##### CLASS: `{cls['name']}{bases_str}`")
                if cls['decorators']:
                    out.append("")
                    out.append("@" + ", @".join(cls['decorators']))
                out.append("")
                if cls['docstring']:
                    out.append(f"> {cls['docstring']}")
                    out.append("")

                if cls['methods']:
                    out.append("| 方法 | 类型 | 说明 |")
                    out.append("|------|------|------|")
                    for method in cls['methods']:
                        doc_first_line = method['docstring'].split('\n')[0] if method['docstring'] else ''
                        method_type = "异步" if method['is_async'] else "同步"
                        out.append(f"| `{method['name']}` | {method_type} | {doc_first_line} |")
                    out.append("")

        if structure['functions']:
            out.append("#### 函数定义")
            out.append("")
            out.append("| 函数 | 类型 | 说明 |")
            out.append("|------|------|------|")
            for func in structure['functions']:
                doc_first_line = func['docstring'].split('\n')[0] if func['docstring'] else ''
                func_type = "异步" if func['is_async'] else "同步"
                out.append(f"| `{func['name']}` | {func_type} | {doc_first_line} |")
            out.append("")

        if structure.get('parse_error'):
            out.append("⚠️ **解析错误**:")
            out.append(f"```\n{structure['parse_error']}\n```")
            out.append("")
        if structure.get('read_error'):
            out.append("⚠️ **读取错误**:")
            out.append(f"```\n{structure['read_error']}\n```")
            out.append("")

        # 源代码
        if self.include_source and structure['source_code']:
            out.append("#### 源代码")
            out.append("")
            out.append("```python")
            out.append(structure['source_code'].rstrip())
            out.append("```")
            out.append("")

        return out

    def _part_name(self, n: int, hint: str) -> str:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in hint)[:24].strip("_")
        return f"part_{n:02d}_{safe}.md" if safe else f"part_{n:02d}.md"

    def _finalize_part(self, state: SplitState, part_lines: List[str],
                       out_dir: Path, title: str) -> None:
        """将当前累积的 part_lines 落盘为一个分片文件。"""
        state.part_index += 1
        name = self._part_name(state.part_index, title)
        body = "\n".join(part_lines).rstrip() + "\n"
        (out_dir / name).write_text(body, encoding="utf-8")
        state.files.append({"name": name, "title": title, "chars": len(body)}) #type: ignore
        part_lines.clear()

    def _write_index(self, out_dir: Path, py_files: List[Path], plan: List[List[Path]]) -> None:
        """生成索引文件（默认 README.md）。plan 为真实分片计划，保证映射与产物一致。"""
        idx: List[str] = []

        idx.append(f"# 📚 {self.project_root.name} 项目文档索引")
        idx.append(f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        idx.append(f"> 项目路径：`{self.project_root}`")
        idx.append("> **阅读顺序**：先读本索引（目录树 + 索引表），再按需打开对应分片。")
        idx.append("---")

        # 统计信息
        idx.append("## 📊 项目统计")
        idx.extend(self.generate_markdown_table({
            "指标": ["总文件数", "Python文件", "类数量", "函数数量", "代码行数", "分片文件数"],
            "数值": [
                str(self.stats['total_files']),
                str(self.stats['py_files']),
                str(self.stats['classes']),
                str(self.stats['functions']),
                str(self.stats['lines']),
                str(len(self._split_state.files)), #type: ignore
            ],
        }))
        idx.append("")
        idx.append("---")

        # 目录树
        idx.append("## 🌳 项目目录结构")
        idx.append("")
        idx.append("```text")
        idx.append(self.generate_project_tree())
        idx.append("```")
        idx.append("")
        idx.append("---")

        # 分片索引表
        idx.append("## 🗂️ 分片文件索引")
        idx.append("")
        idx.append(f"按以下顺序阅读各分片（每片 ≤ ~{self.split.maxCharsPerFile:,} 字符）：")
        idx.append("")
        idx.append("| # | 分片文件 | 内容 | 字符数 |")
        idx.append("|---|----------|------|--------|")
        for i, f in enumerate(self._split_state.files, 1): #type: ignore
            idx.append(f"| {i} | [{f['name']}](./{f['name']}) | {f['title']} | {f['chars']:,} |")
        idx.append("")
        idx.append("---")

        # 每个 Python 文件 → 所在分片 映射（直接由真实 plan 推导，无二次解析）
        idx.append("## 📄 Python 文件索引")
        idx.append("")
        idx.append("| 文件 | 行数 | 所在分片 |")
        idx.append("|------|------|----------|")
        for part_no, spans_in_part in enumerate(plan, start=1):
            part_name = self._part_name(part_no, f"files_{part_no}")
            for span in spans_in_part:
                fp = Path(span[0])  # span = (path_str, start_line, end_line) #type: ignore
                rel = str(fp.relative_to(self.project_root))
                line_count = self.extract_code_structure(fp)['line_count']
                idx.append(f"| `{rel}` | {line_count} | [{part_name}](./{part_name}) |")
        idx.append("")
        idx.append("---")

        (out_dir / self.split.indexFileName).write_text("\n".join(idx), encoding="utf-8")

    # ------------------------------------------------------------------
    #  分片粒度：FileSpan = (path, start_line, end_line)（1-based，含端点）
    #  plan 类型：List[List[FileSpan]] —— 一片 = 若干文件的（连续）行区间
    #  一个超大文件会被拆成多个 span，分散到不同片中；切分始终发生在【行边界】，
    #  保证单行代码不被切断；每个 span 自带文件头信息，使分片自包含。
    # ------------------------------------------------------------------
    def _file_spans(self, fp: Path, limit: int) -> List[tuple]:
        """把单个文件拆成若干行区间 span，每个 span 的源码字符数（含文件头）≤ limit。"""
        structure = self.extract_code_structure(fp)
        source = structure['source_code']
        if not source:
            return [(str(fp), 1, max(structure['line_count'], 1))]

        # 文件头开销（模块说明/导入等，每片都带一份，确保自包含）
        header_lines = self._render_file_header(structure, fp)
        header_cost = len("\n".join(header_lines)) + 2

        raw_lines = source.splitlines()
        total = len(raw_lines)

        spans = []
        start = 0
        used = header_cost  # 当前片已用字符（从文件头开始）
        for idx, line in enumerate(raw_lines):
            cost = len(line) + 1  # +1 换行
            # 若加入本行会超配额，且当前片已有内容 → 封片（从 start..idx-1）
            if used + cost > limit and idx > start:
                spans.append((str(fp), start + 1, idx))  # 1-based
                start = idx
                used = header_cost
            used += cost
        # 剩余
        if start < total:
            spans.append((str(fp), start + 1, total))
        elif not spans:
            spans.append((str(fp), 1, max(total, 1)))
        return spans

    def _plan_parts(self, py_files: List[Path]) :
        """预计算分片计划：以「文件行区间」为粒度装箱，每片渲染字符数 ≤ maxCharsPerFile。"""
        limit = self.split.maxCharsPerFile
        plan: List[List[tuple]] = []
        cur: List[tuple] = []
        cur_chars = 0

        for fp in py_files:
            for span in self._file_spans(fp, limit):
                fp_str, lo, hi = span
                # 该 span 的预估字符数（文件头 + 区间源码）
                structure = self.extract_code_structure(Path(fp_str))
                header_cost = len("\n".join(self._render_file_header(structure, Path(fp_str)))) + 2
                span_chars = sum(
                    len(line) + 1
                    for line in structure['source_code'].splitlines()[lo - 1:hi]
                )
                size = header_cost + span_chars

                if cur and cur_chars + size > limit:
                    plan.append(cur)
                    cur = []
                    cur_chars = 0
                cur.append(span)
                cur_chars += size

        if cur:
            plan.append(cur)
        return plan

    def _render_file_header(self, structure: Dict, file_path: Path) -> List[str]:
        """渲染文件级头部（文件名 / 大小 / 模块说明 / 导入）—— 每片自带，保证自包含。"""
        relative_path = file_path.relative_to(self.project_root)
        out: List[str] = []
        out.append(f"### 📄 `{relative_path}`")
        out.append("")
        out.append(f"- **代码行数**: {structure['line_count']}")
        out.append("")

        if structure['module_docstring']:
            out.append("#### 模块说明")
            out.append("")
            out.append(f"> {structure['module_docstring']}")
            out.append("")

        if structure['imports']:
            out.append("#### 导入依赖")
            out.append("")
            out.append("```python")
            for imp in structure['imports']:
                if imp['type'] == 'import':
                    line = f"import {imp['module']}"
                    if imp['alias']:
                        line += f" as {imp['alias']}"
                else:
                    line = f"from {imp['module']} import {imp['name']}"
                    if imp['alias']:
                        line += f" as {imp['alias']}"
                out.append(line)
            out.append("```")
            out.append("")
        return out

    def _render_part_body_cached(self, spans_in_part: List[tuple], part_no: int) -> str:
        """渲染某一片正文（分片模式专用）：按行区间输出，保证每片 ≤ 配额且行完整。"""
        limit = self.split.maxCharsPerFile
        lines = [
            f"# 📦 分片 {part_no}",
            f"> 项目 `{self.project_root.name}` · 单文件配额 ~{limit:,} 字符（AI 分批上传友好）",
            f"> 返回索引：[`{self.split.indexFileName}`](./{self.split.indexFileName})",
            "---",
            "",
        ]
        cache = getattr(self, '_structure_cache', {})
        for span in spans_in_part:
            fp_str, lo, hi = span
            fp = Path(fp_str)
            structure = cache.get(fp_str) or self.extract_code_structure(fp)
            lines.extend(self._render_file_header(structure, fp))

            if self.include_source and structure['source_code']:
                lines.append(f"#### 源代码（第 {lo}–{hi} 行）")
                lines.append("")
                lines.append("```python")
                raw = structure['source_code'].splitlines()
                lines.extend(raw[lo - 1:hi])
                lines.append("```")
                lines.append("")
            lines.append("---")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    def generate_split(self, out_dir: Path) -> None:
        """分片模式：索引文件 + 多个实际分片文件。"""
        out_dir.mkdir(parents=True, exist_ok=True)

        # 重置统计（支持同一 generator 多次调用而不翻倍）
        self.stats['classes'] = self.stats['functions'] = self.stats['lines'] = 0

        py_files = self.get_python_files()
        self.stats['total_files'] = sum(
            1 for _ in self.project_root.rglob('*') if not self.should_exclude(_)
        )
        self.stats['py_files'] = len(py_files)

        # 阶段 A：预提取全部文件结构（单次，结果缓存，供计划/渲染/统计复用，避免重复统计）
        cache: Dict[str, Dict] = {}
        for fp in py_files:
            s = self.extract_code_structure(fp)
            cache[str(fp)] = s
            self.stats['classes'] += s['n_classes']
            self.stats['functions'] += s['n_functions']
            self.stats['lines'] += s['line_count']

        # 让后续 _render_file_section 直接复用缓存，不再重新解析
        self._structure_cache = cache

        # 阶段 B：预计算分片计划（文件 → 片的确定映射）
        plan = self._plan_parts(py_files)

        # 阶段 C：严格按计划渲染落盘
        state = SplitState()
        self._split_state = state
        for i, files_in_part in enumerate(plan, start=1):
            body = self._render_part_body_cached(files_in_part, i)
            name = self._part_name(i, f"files_{i}")
            (out_dir / name).write_text(body, encoding="utf-8")
            titles = []
            for span in files_in_part:
                fp = Path(span[0])
                rel = str(fp.relative_to(self.project_root))
                if rel not in titles:
                    titles.append(rel)
            state.files.append({ # type: ignore
                "name": name,
                "title": f"分片 {i}（{', '.join(titles)}）",
                "chars": len(body), # type: ignore
            })

        # 生成索引文件（依赖 state.files + plan）
        self._write_index(out_dir, py_files, plan) # type: ignore

    def generate_markdown(self) -> str:
        """生成完整的单文件 Markdown 文档"""
        md_lines = []

        # 重置统计（支持同一 generator 多次调用而不翻倍）
        self.stats['classes'] = self.stats['functions'] = self.stats['lines'] = 0

        md_lines.append(f"# 📚 {self.project_root.name} 项目文档")
        md_lines.append(f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        md_lines.append(f"> 项目路径：`{self.project_root}`")
        md_lines.append("---")

        py_files = self.get_python_files()
        self.stats['total_files'] = sum(
            1 for _ in self.project_root.rglob('*') if not self.should_exclude(_)
        )
        self.stats['py_files'] = len(py_files)

        md_lines.append("## 📊 项目统计")
        md_lines.extend(self.generate_markdown_table({
            "指标": ["总文件数", "Python文件", "类数量", "函数数量", "代码行数"],
            "数值": [
                str(self.stats['total_files']),
                str(self.stats['py_files']),
                str(self.stats['classes']),
                str(self.stats['functions']),
                str(self.stats['lines']),
            ],
        }))
        md_lines.append("")
        md_lines.append("---")

        md_lines.append("## 🌳 项目目录结构")
        md_lines.append("")
        md_lines.append("```text")
        md_lines.append(self.generate_project_tree())
        md_lines.append("```")
        md_lines.append("")
        md_lines.append("---")

        md_lines.append("## 📄 Python文件详细分析")
        md_lines.append("")
        for file_path in py_files:
            structure = self.extract_code_structure(file_path)
            self.stats['classes'] += structure['n_classes']
            self.stats['functions'] += structure['n_functions']
            self.stats['lines'] += structure['line_count']
            md_lines.extend(self._render_from_structure(structure, file_path))
            md_lines.append("---")
            md_lines.append("")
        return "\n".join(md_lines)

    def save_documentation(self):
        """保存文档。split.enabled=True 时分片输出到目录，否则输出单文件。"""
        if self.split.enabled:
            out_dir = self.output_file
            # 若用户给的 output_file 形如 xxx.md，取其父目录
            if out_dir.suffix == '.md':
                out_dir = out_dir.parent if out_dir.parent != Path('') else Path('.')
            self.generate_split(out_dir.resolve())

            print(f"\n✅ 分片文档已生成: {out_dir}/")
            print(f"   📑 索引文件: {self.split.indexFileName}")
            print(f"   📦 分片数量: {len(self._split_state.files)}") # type: ignore
            for f in self._split_state.files: # type: ignore
                print(f"      - {f['name']}  ({f['chars']:,} 字符)")
            print(f"   📊 统计: {self.stats['py_files']} py 文件 / "
                  f"{self.stats['classes']} 类 / {self.stats['functions']} 函数 / "
                  f"{self.stats['lines']} 行")
        else:
            markdown_content = self.generate_markdown()
            self.output_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.output_file, 'w', encoding='utf-8') as f:
                f.write(markdown_content)

            print(f"\n✅ 文档已生成: {self.output_file}")
            print(f"📊 统计信息:")
            print(f"   - 扫描了 {self.stats['py_files']} 个 Python 文件")
            print(f"   - 发现 {self.stats['classes']} 个类")
            print(f"   - 发现 {self.stats['functions']} 个函数")
            print(f"   - 总计 {self.stats['lines']} 行代码")
            if self.include_source:
                print("   - 源代码已包含在文档中")


# ===========================================================================
# CLI
# ===========================================================================
def main():
    parser = argparse.ArgumentParser(
        description='生成项目文档（支持分片，便于 AI 分批理解）'
    )
    parser.add_argument('path', nargs='?', default='.',
                        help='项目根目录路径 (默认: 当前目录)')
    parser.add_argument('-o', '--output', default='docs/PROJECT',
                        help='输出：分片模式为目录 (默认: docs/PROJECT)，单文件模式为 .md 路径')
    parser.add_argument('-e', '--exclude', action='append', default=[],
                        help='排除模式 (可多次使用)')
    parser.add_argument('-t', '--include-tests', action='store_true',
                        help='包含测试文件')
    parser.add_argument('--no-source', action='store_true',
                        help='不包含源代码（只包含结构信息）')
    parser.add_argument('--no-split', action='store_true',
                        help='关闭分片，输出为单个 Markdown 文件')
    parser.add_argument('--max-chars', type=int, default=80000,
                        help='每个分片的最大字符数 (默认: 80000)')
    parser.add_argument('--index-name', default='README.md',
                        help='索引文件名 (默认: README.md)')
    args = parser.parse_args()

    exclude_patterns = DEFAULT_EXCLUDE_PATTERNS.copy()
    if args.exclude:
        exclude_patterns.extend(args.exclude)

    split = SplitConfig(
        enabled=not args.no_split,
        maxCharsPerFile=args.max_chars,
        indexFileName=args.index_name,
    )

    generator = ProjectDocGenerator(
        project_root=args.path,
        output_file=args.output,
        exclude_patterns=exclude_patterns,
        include_tests=args.include_tests,
        include_source=not args.no_source,
        split=split,
    )
    generator.save_documentation()


def _run_example():
    generator = ProjectDocGenerator(
        project_root="src_py",              
        output_file="docs/chatbot_project",    # 输出目录（split 模式下为目录）
        exclude_patterns=DEFAULT_EXCLUDE_PATTERNS,
        include_source=True,
        split=SplitConfig(
            enabled=True,
            maxCharsPerFile=80000,        # 每个分片最大字符数（保守留余量）
            indexFileName='README.md',    # 索引文件名
        )
    )
    generator.save_documentation()


if __name__ == "__main__":
    import sys
    # 有命令行参数 → 走 CLI；无参数 → 运行上方示例
    if len(sys.argv) > 1:
        main()
    else:
        _run_example()
