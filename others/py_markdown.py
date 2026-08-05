"""
项目文档生成器
递归扫描目录，提取所有 .py 文件的代码结构，生成一份清晰的 Markdown 文档
"""
import os
import ast
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import fnmatch

DEFAULT_OUTPUT_FILE = "PROJECT.md"
DEFAULT_EXCLUDE_PATTERNS = [
    '__pycache__', '.git', '.venv', 'venv', 'env',"tests",
    'node_modules', '.idea', '.vscode', 'dist', 'build',
    '*.egg-info', '.pytest_cache', '__pycache__',"*.log","resources",
    "database",
]


class ProjectDocGenerator:
    """
    项目文档生成器
    """
    
    def __init__(
            self, 
            project_root: str,
            output_file: str = DEFAULT_OUTPUT_FILE,
            exclude_patterns: Optional[List[str]] = None,
            include_tests: bool = False
        ):
        self.project_root = Path(project_root).resolve()
        self.output_file = get_project_root() + output_file
        self.exclude_patterns = exclude_patterns or DEFAULT_EXCLUDE_PATTERNS
        self.include_tests = include_tests
        self.stats = {
            'total_files': 0,
            'py_files': 0,
            'classes': 0,
            'functions': 0,
            'lines': 0,
            'modules': set()
        }

    def should_exclude(self, path: Path) -> bool:
        """检查是否应该排除该路径"""
        for pattern in self.exclude_patterns:
            if fnmatch.fnmatch(str(path), pattern) or \
               any(fnmatch.fnmatch(part, pattern) for part in path.parts):
                return True
        return False

    def get_python_files(self) -> List[Path]:
        """递归获取所有 .py 文件"""
        py_files = []
        for root, dirs, files in os.walk(self.project_root):
            # 排除不需要的目录
            dirs[:] = [d for d in dirs if not self.should_exclude(Path(root) / d)]
            
            for file in files:
                file_path = Path(root) / file
                if file.endswith('.py') and not self.should_exclude(file_path):
                    # 跳过测试文件（除非指定包含）
                    if not self.include_tests and file.startswith('test_'):
                        continue
                    py_files.append(file_path)
                    
        return sorted(py_files)

    def extract_code_structure(self, file_path: Path) -> Dict:
        """提取单个文件的代码结构"""
        structure = {
            'imports': [],
            'classes': [],
            'functions': [],
            'module_docstring': '',
            'file_size': file_path.stat().st_size,
            'line_count': 0
        }
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                structure['line_count'] = len(content.splitlines())
                self.stats['lines'] += structure['line_count']
                
            tree = ast.parse(content)
            
            # 提取模块文档字符串
            if isinstance(tree.body[0], ast.Expr) and isinstance(tree.body[0].value, ast.Constant):
                structure['module_docstring'] = tree.body[0].value.s.strip() # type: ignore
            
            for node in ast.walk(tree):
                # 提取导入
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        structure['imports'].append({
                            'type': 'import',
                            'module': alias.name,
                            'alias': alias.asname
                        })
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ''
                    for alias in node.names:
                        structure['imports'].append({
                            'type': 'from',
                            'module': module,
                            'name': alias.name,
                            'alias': alias.asname
                        })
                
                # 提取类定义
                elif isinstance(node, ast.ClassDef):
                    class_info = {
                        'name': node.name,
                        'bases': [self._get_base_name(base) for base in node.bases],
                        'docstring': ast.get_docstring(node) or '',
                        'methods': [],
                        'decorators': [self._get_decorator_name(d) for d in node.decorator_list]
                    }
                    
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef) or isinstance(item, ast.AsyncFunctionDef):
                            method_info = {
                                'name': item.name,
                                'is_async': isinstance(item, ast.AsyncFunctionDef),
                                'docstring': ast.get_docstring(item) or '',
                                'args': self._extract_args(item.args),
                                'returns': self._get_return_annotation(item.returns),
                                'decorators': [self._get_decorator_name(d) for d in item.decorator_list]
                            }
                            class_info['methods'].append(method_info)
                            self.stats['functions'] += 1
                    
                    structure['classes'].append(class_info)
                    self.stats['classes'] += 1
                
                # 提取函数定义（不在类中的）
                elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                    # 检查是否在类中
                    parent = getattr(node, 'parent', None)
                    if not isinstance(parent, ast.ClassDef):
                        func_info = {
                            'name': node.name,
                            'is_async': isinstance(node, ast.AsyncFunctionDef),
                            'docstring': ast.get_docstring(node) or '',
                            'args': self._extract_args(node.args),
                            'returns': self._get_return_annotation(node.returns),
                            'decorators': [self._get_decorator_name(d) for d in node.decorator_list]
                        }
                        structure['functions'].append(func_info)
                        self.stats['functions'] += 1
                        
        except SyntaxError as e:
            structure['parse_error'] = str(e)
        except Exception as e:
            structure['read_error'] = str(e)
            
        return structure

    def _get_base_name(self, base) -> str:
        """获取基类名称"""
        if isinstance(base, ast.Name):
            return base.id
        elif isinstance(base, ast.Attribute):
            return f"{self._get_base_name(base.value)}.{base.attr}"
        elif isinstance(base, ast.Call):
            return self._get_base_name(base.func)
        return str(base)

    def _get_decorator_name(self, decorator) -> str:
        """获取装饰器名称"""
        if isinstance(decorator, ast.Name):
            return decorator.id
        elif isinstance(decorator, ast.Attribute):
            return f"{self._get_base_name(decorator.value)}.{decorator.attr}"
        elif isinstance(decorator, ast.Call):
            return self._get_decorator_name(decorator.func)
        return str(decorator)

    def _extract_args(self, args) -> List[Dict]:
        """提取函数参数"""
        arg_list = []
        for arg in args.args:
            arg_info = {
                'name': arg.arg,
                'annotation': self._get_annotation(arg.annotation)
            }
            arg_list.append(arg_info)
        
        # 处理默认值
        defaults = [None] * (len(args.args) - len(args.defaults)) + args.defaults
        for i, default in enumerate(defaults):
            if default is not None:
                arg_list[i]['default'] = self._get_default_value(default)
                
        return arg_list

    def _get_annotation(self, annotation) -> str:
        """获取类型注解"""
        if annotation is None:
            return ''
        if isinstance(annotation, ast.Name):
            return annotation.id
        elif isinstance(annotation, ast.Attribute):
            return f"{self._get_base_name(annotation.value)}.{annotation.attr}"
        elif isinstance(annotation, ast.Subscript):
            return f"{self._get_base_name(annotation.value)}[{self._get_annotation(annotation.slice)}]"
        return str(annotation)

    def _get_return_annotation(self, returns) -> str:
        """获取返回值注解"""
        return self._get_annotation(returns)

    def _get_default_value(self, value) -> str:
        """获取默认值表示"""
        if isinstance(value, ast.Constant):
            return repr(value.value)
        elif isinstance(value, ast.List):
            return '[]'
        elif isinstance(value, ast.Dict):
            return '{}'
        elif isinstance(value, ast.Name):
            return value.id
        return str(value)

    def generate_project_tree(self) -> str:
        """生成项目目录树"""
        lines = []
        prefix = "│   "
        last_prefix = "└── "
        
        def _generate_tree(dir_path: Path, indent: str = "", is_last: bool = True):
            entries = sorted([e for e in dir_path.iterdir() 
                            if not self.should_exclude(e)], 
                           key=lambda x: (not x.is_dir(), x.name))
            
            for i, entry in enumerate(entries):
                is_last_entry = i == len(entries) - 1
                connector = last_prefix if is_last_entry else "├── "
                
                if entry.is_dir():
                    lines.append(f"{indent}{connector}{entry.name}/")
                    new_indent = indent + ("    " if is_last_entry else "│   ")
                    _generate_tree(entry, new_indent, is_last_entry)
                else:
                    lines.append(f"{indent}{connector}{entry.name}")
        
        lines.append(f"📁 {self.project_root.name}/")
        _generate_tree(self.project_root)
        return "\n".join(lines)

    def get_project_base_info(self):
        """获取项目基本信息"""
        return [
            f"# 📚 {self.project_root.name} 项目文档",
            f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"> 项目路径：`{self.project_root}`",
            "---",
            "## 📋 项目概览",
            "",
        ]

    def generate_markdown_table(self,data:dict[str,list[str]]):
        keys = list(data.keys())
        first_row = "|".join(keys)
        second_row = "|".join(["------"] * len(keys))
        rows = [
            "|".join(row)
            for row in zip(*data.values())
        ]
        return [
            f"| {first_row} |",
            f"| {second_row} |",
            *rows
        ]

    def markdown_title(self,title:str,level:int=1) -> str:
        return f"{'#'*level} {title}"

    def generate_markdown(self) -> str:
        """生成完整的 Markdown 文档"""
        md_lines = []
        
        # 标题和基本信息
        md_lines.extend(self.get_project_base_info())
        
        # 统计信息
        py_files = self.get_python_files()
        self.stats['total_files'] = len(list(self.project_root.rglob('*')))
        self.stats['py_files'] = len(py_files)
        
        md_lines.extend([
            "## 📊 项目统计",
            *self.generate_markdown_table({
                "指标": ["总文件数", "Python文件", "类数量", "函数数量", "代码行数"],
                "数值": [
                    str(self.stats['total_files']),
                    str(self.stats['py_files']),
                    str(self.stats['classes']),
                    str(self.stats['functions']),
                    str(self.stats['lines']),
                ]
            }),
            "",
            "---",
            "",
            self.markdown_title("🌳 项目目录结构",2),
            "",
            "```text",
            self.generate_project_tree(),
            "```",
            "",
            "---",
            "",
            self.markdown_title("📄 Python文件详细分析",2),
            "",
        ])
        
        # 分析每个文件
        for file_path in py_files:
            relative_path = file_path.relative_to(self.project_root)
            structure = self.extract_code_structure(file_path)
            
            md_lines.extend([
                self.markdown_title(f"📄 {relative_path}",3),
                "",
                f"- **文件大小**: {structure['file_size'] / 1024:.1f} KB",
                f"- **代码行数**: {structure['line_count']}",
                "",
            ])
            
            # 模块文档字符串
            if structure['module_docstring']:
                md_lines.extend([
                    self.markdown_title("模块说明",4),
                    "",
                    f"> {structure['module_docstring']}",
                    "",
                ])
            
            # 导入语句
            if structure['imports']:
                md_lines.extend([
                    self.markdown_title("导入依赖",4),
                    "",
                    "```python",
                ])
                for imp in structure['imports'][:20]:  # 限制显示前20个
                    if imp['type'] == 'import':
                        line = f"import {imp['module']}"
                        if imp['alias']:
                            line += f" as {imp['alias']}"
                    else:
                        line = f"from {imp['module']} import {imp['name']}"
                        if imp['alias']:
                            line += f" as {imp['alias']}"
                    md_lines.append(line)
                
                if len(structure['imports']) > 20:
                    md_lines.append(f"# ... 还有 {len(structure['imports']) - 20} 个导入")
                md_lines.extend(["```", ""])
            
            # 类定义
            if structure['classes']:
                md_lines.extend([
                    self.markdown_title("类定义",4),
                    "",
                ])
                for cls in structure['classes']:
                    decorators_str = ""
                    if cls['decorators']:
                        decorators_str = "@" + ", @".join(cls['decorators'])
                    
                    bases_str = ""
                    if cls['bases']:
                        bases_str = f"({', '.join(cls['bases'])})"
                    
                    md_lines.extend([
                        self.markdown_title(f"CLASS: {cls['name']}{bases_str}",5),
                        "",
                    ])
                    
                    if cls['docstring']:
                        md_lines.extend([
                            f"> {cls['docstring']}",
                            "",
                        ])
                    
                    if cls['methods']:
                        md_lines.append("| 方法 | 类型 | 说明 |")
                        md_lines.append("|------|------|------|")
                        for method in cls['methods']:
                            decorators = ""
                            if method['decorators']:
                                decorators = ", ".join(method['decorators'])
                            
                            doc_first_line = method['docstring'].split('\n')[0] if method['docstring'] else ''
                            method_type = "异步" if method['is_async'] else "同步"
                            
                            md_lines.append(
                                f"| `{method['name']}` | {method_type} | {doc_first_line} |"
                            )
                        md_lines.append("")
            
            # 函数定义
            if structure['functions']:
                md_lines.extend([
                    self.markdown_title("函数定义",4),
                    "",
                    "| 函数 | 类型 | 说明 |",
                    "|------|------|------|",
                ])
                for func in structure['functions']:
                    doc_first_line = func['docstring'].split('\n')[0] if func['docstring'] else ''
                    func_type = "异步" if func['is_async'] else "同步"
                    md_lines.append(f"| `{func['name']}` | {func_type} | {doc_first_line} |")
                md_lines.append("")
            
            # 解析错误
            if 'parse_error' in structure:
                md_lines.extend([
                    "⚠️ **语法错误**:",
                    f"```\n{structure['parse_error']}\n```",
                    "",
                ])
            
            md_lines.append("---")
            md_lines.append("")
        
        # 底部信息
        md_lines.extend([
            self.markdown_title("🔗 相关链接",2),
            "",
            "- [项目主页](#)",
            "- [API文档](#)",
            "- [开发指南](#)",
            "",
            "---",
            "",
            "*此文档由 ProjectDocGenerator 自动生成*",
            "",
        ])
        
        return "\n".join(md_lines)


    def markdown(self):
        return self.generate_markdown()

    def save_documentation(self):
        """保存文档到文件"""
        markdown_content = self.generate_markdown()
        
        output_path = Path(self.output_file)
        if not output_path.is_absolute():
            output_path = self.project_root / output_path
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(markdown_content)
        
        print(f"\n✅ 文档已生成: {output_path}")
        print(f"📊 统计信息:")
        print(f"   - 扫描了 {self.stats['py_files']} 个 Python 文件")
        print(f"   - 发现 {self.stats['classes']} 个类")
        print(f"   - 发现 {self.stats['functions']} 个函数")
        print(f"   - 总计 {self.stats['lines']} 行代码")


def main():
    print("""
        Usage: python project_markdown.py [options]
        Options:
          -h, --help  显示帮助信息
          -o, --output OUTPUT  输出文件名 (默认: PROJECT.md)
          -e, --exclude EXCLUDE  排除模式 (可多次使用)
          -t, --include-tests  包含测试文件
    """)

    parser = argparse.ArgumentParser(description='生成项目文档')
    parser.add_argument('path', nargs='?', default='.', 
                       help='项目根目录路径 (默认: 当前目录)')
    parser.add_argument('-o', '--output', default='PROJECT.md',
                       help='输出文件名 (默认: PROJECT.md)')
    parser.add_argument('-e', '--exclude', action='append', default=[],
                       help='排除模式 (可多次使用)')
    parser.add_argument('-t', '--include-tests', action='store_true',
                       help='包含测试文件')
    
    args = parser.parse_args()
    
    generator = ProjectDocGenerator(
        project_root=args.path,
        output_file=args.output,
        exclude_patterns=args.exclude or None,
        include_tests=args.include_tests
    )
    
    generator.save_documentation()

def get_project_root(target_dir:str="") -> str:
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), target_dir)

if __name__ == "__main__":
    generator = ProjectDocGenerator(
        project_root=get_project_root("src_py"),
        output_file="others/docs/chatbot.md",
    )
    #Run the generator
    generator.save_documentation()
