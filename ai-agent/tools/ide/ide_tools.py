"""IDE-level tools for advanced code navigation and manipulation
Breadcrumbs, minimap, outline view, symbol renaming across files, find references.
"""
import ast
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from ..base import BaseTool, ToolResult


@dataclass
class SymbolInfo:
    name: str
    type: str  # class, function, method, variable, import
    line: int
    column: int
    end_line: int
    docstring: str = ""
    decorators: List[str] = None
    parameters: List[str] = None
    parent: Optional[str] = None


class BreadcrumbsTool(BaseTool):
    name = "get_breadcrumbs"
    description = "Get navigation breadcrumbs for file position — shows class/function hierarchy at cursor"
    parameters = {
        "path": {"type": "string", "description": "File path"},
        "line": {"type": "integer", "description": "Current line number (1-based)"}
    }

    def execute(self, path: str, line: int) -> ToolResult:
        try:
            full_path = Path(path).resolve()
            with open(full_path, 'r', encoding='utf-8') as f:
                source = f.read()

            tree = ast.parse(source)
            breadcrumbs = []

            for node in ast.walk(tree):
                if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    if hasattr(node, 'end_lineno') and node.lineno <= line <= node.end_lineno:
                        symbol_type = "class" if isinstance(node, ast.ClassDef) else "function"
                        breadcrumbs.append({
                            "name": node.name,
                            "type": symbol_type,
                            "line": node.lineno,
                            "signature": self._get_signature(node)
                        })

            # Sort by line number to show hierarchy
            breadcrumbs.sort(key=lambda x: x["line"])

            result = " > ".join([f"{b['type']}:{b['name']}" for b in breadcrumbs])
            return ToolResult(True, result, metadata={"breadcrumbs": breadcrumbs})
        except Exception as e:
            return ToolResult(False, "", str(e))

    def _get_signature(self, node) -> str:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = [a.arg for a in node.args.args]
            return f"({', '.join(args)})"
        return ""


class OutlineTool(BaseTool):
    name = "get_outline"
    description = "Get file outline — all classes, functions, methods with line numbers (like VS Code outline)"
    parameters = {
        "path": {"type": "string", "description": "File path"},
        "include_docstrings": {"type": "boolean", "description": "Include docstrings", "default": True},
        "max_depth": {"type": "integer", "description": "Max nesting depth", "default": 3}
    }

    def execute(self, path: str, include_docstrings: bool = True, max_depth: int = 3) -> ToolResult:
        try:
            full_path = Path(path).resolve()
            with open(full_path, 'r', encoding='utf-8') as f:
                source = f.read()

            tree = ast.parse(source)
            symbols = []

            def extract(node, depth=0, parent=None):
                if depth > max_depth:
                    return

                for child in ast.iter_child_nodes(node):
                    if isinstance(child, ast.ClassDef):
                        doc = ast.get_docstring(child) if include_docstrings else ""
                        symbol = SymbolInfo(
                            name=child.name,
                            type="class",
                            line=child.lineno,
                            column=child.col_offset,
                            end_line=getattr(child, 'end_lineno', child.lineno),
                            docstring=doc[:200] if doc else "",
                            decorators=[self._get_decorator_name(d) for d in child.decorator_list],
                            parent=parent
                        )
                        symbols.append(symbol)
                        extract(child, depth + 1, child.name)

                    elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        doc = ast.get_docstring(child) if include_docstrings else ""
                        is_method = parent is not None
                        symbol = SymbolInfo(
                            name=child.name,
                            type="method" if is_method else "function",
                            line=child.lineno,
                            column=child.col_offset,
                            end_line=getattr(child, 'end_lineno', child.lineno),
                            docstring=doc[:200] if doc else "",
                            decorators=[self._get_decorator_name(d) for d in child.decorator_list],
                            parameters=self._get_params(child),
                            parent=parent
                        )
                        symbols.append(symbol)

            extract(tree)

            # Format as tree
            lines = [f"📄 {path}"]
            for s in symbols:
                indent = "  " * (1 if s.parent else 0)
                icon = "🔷" if s.type == "class" else "🔹" if s.type == "method" else "⚡"
                decorators = " ".join([f"@{d}" for d in s.decorators]) if s.decorators else ""
                params = f"({', '.join(s.parameters)})" if s.parameters else ""
                doc = f" — {s.docstring[:60]}" if s.docstring else ""
                lines.append(f"{indent}{icon} {s.name}{params} :{s.line}{doc}")

            return ToolResult(True, "\n".join(lines), metadata={"symbols": len(symbols)})
        except Exception as e:
            return ToolResult(False, "", str(e))

    def _get_decorator_name(self, node) -> str:
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            return node.func.id
        return ""

    def _get_params(self, node) -> List[str]:
        args = []
        for a in node.args.args:
            args.append(a.arg)
        if node.args.vararg:
            args.append(f"*{node.args.vararg.arg}")
        if node.args.kwarg:
            args.append(f"**{node.args.kwarg.arg}")
        return args


class FindReferencesTool(BaseTool):
    name = "find_references"
    description = "Find all references to a symbol across the entire project (like VS Code Find All References)"
    parameters = {
        "symbol": {"type": "string", "description": "Symbol name to search for"},
        "path": {"type": "string", "description": "Directory to search", "default": "."},
        "file_pattern": {"type": "string", "description": "File pattern", "default": "*.py"}
    }

    def execute(self, symbol: str, path: str = ".", file_pattern: str = "*.py") -> ToolResult:
        try:
            base = Path(path).resolve()
            references = []

            for file_path in base.rglob(file_pattern):
                if not file_path.is_file():
                    continue
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        lines = content.splitlines()

                    for i, line in enumerate(lines, 1):
                        # Match word boundaries
                        if re.search(r'\b' + re.escape(symbol) + r'\b', line):
                            rel = str(file_path.relative_to(base))
                            references.append({
                                "file": rel,
                                "line": i,
                                "column": line.find(symbol),
                                "context": line.strip()[:80]
                            })
                except Exception:
                    continue

            # Format results
            lines = [f"🔍 {len(references)} references to '{symbol}'"]
            current_file = ""
            for ref in references:
                if ref["file"] != current_file:
                    current_file = ref["file"]
                    lines.append(f"\n📁 {current_file}")
                lines.append(f"   {ref['line']:4d}:{ref['column']:3d}  {ref['context']}")

            return ToolResult(True, "\n".join(lines), metadata={"count": len(references)})
        except Exception as e:
            return ToolResult(False, "", str(e))


class RenameSymbolTool(BaseTool):
    name = "rename_symbol"
    description = "Rename symbol across entire project with AST-aware replacement (like F2 in VS Code)"
    parameters = {
        "old_name": {"type": "string", "description": "Current symbol name"},
        "new_name": {"type": "string", "description": "New symbol name"},
        "path": {"type": "string", "description": "Directory to search", "default": "."},
        "file_pattern": {"type": "string", "description": "File pattern", "default": "*.py"},
        "preview": {"type": "boolean", "description": "Preview changes without applying", "default": True}
    }

    def execute(self, old_name: str, new_name: str, path: str = ".", file_pattern: str = "*.py", preview: bool = True) -> ToolResult:
        try:
            base = Path(path).resolve()
            changes = []

            for file_path in base.rglob(file_pattern):
                if not file_path.is_file():
                    continue
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()

                    # Count occurrences
                    occurrences = len(re.findall(r'\b' + re.escape(old_name) + r'\b', content))
                    if occurrences == 0:
                        continue

                    rel = str(file_path.relative_to(base))
                    changes.append({
                        "file": rel,
                        "occurrences": occurrences,
                        "preview": ""
                    })

                    if not preview:
                        # AST-aware replacement
                        new_content = re.sub(r'\b' + re.escape(old_name) + r'\b', new_name, content)
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(new_content)

                except Exception as e:
                    changes.append({"file": str(file_path), "error": str(e)})

            action = "Preview" if preview else "Applied"
            lines = [f"{action}: Rename '{old_name}' -> '{new_name}'"]
            lines.append(f"Files affected: {len(changes)}\n")

            for c in changes:
                if "error" in c:
                    lines.append(f"  ❌ {c['file']}: {c['error']}")
                else:
                    lines.append(f"  {'📝' if preview else '✅'} {c['file']}: {c['occurrences']} occurrences")

            return ToolResult(True, "\n".join(lines), metadata={"files": len(changes), "preview": preview})
        except Exception as e:
            return ToolResult(False, "", str(e))


class MinimapTool(BaseTool):
    name = "get_minimap"
    description = "Generate minimap overview of file — color-coded by syntax (classes, functions, imports)"
    parameters = {
        "path": {"type": "string", "description": "File path"},
        "width": {"type": "integer", "description": "Minimap width in chars", "default": 40}
    }

    def execute(self, path: str, width: int = 40) -> ToolResult:
        try:
            full_path = Path(path).resolve()
            with open(full_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            total_lines = len(lines)
            if total_lines == 0:
                return ToolResult(True, "Empty file")

            # Generate minimap bars
            minimap = []
            chunk_size = max(1, total_lines // width)

            for i in range(0, total_lines, chunk_size):
                chunk = lines[i:i + chunk_size]
                chunk_text = "".join(chunk)

                # Determine color/type
                if any(l.startswith("class ") for l in chunk):
                    char = "█"  # Class - blue
                elif any(l.startswith("def ") or l.startswith("async def") for l in chunk):
                    char = "▓"  # Function - yellow
                elif any(l.startswith("import ") or l.startswith("from ") for l in chunk):
                    char = "░"  # Import - gray
                elif any(l.strip().startswith("#") for l in chunk):
                    char = "▒"  # Comment - green
                else:
                    char = " "  # Empty

                minimap.append(char)

            minimap_str = "".join(minimap)
            legend = "█ class  ▓ function  ░ import  ▒ comment"

            result = f"Minimap ({total_lines} lines):\n{minimap_str}\n{legend}"
            return ToolResult(True, result)
        except Exception as e:
            return ToolResult(False, "", str(e))


class QuickFixTool(BaseTool):
    name = "quick_fix"
    description = "Show quick fixes for errors — import suggestions, typo fixes, auto-imports (like Ctrl+.)"
    parameters = {
        "error_message": {"type": "string", "description": "Error message or exception"},
        "path": {"type": "string", "description": "File path where error occurred"},
        "line": {"type": "integer", "description": "Line number"}
    }

    def execute(self, error_message: str, path: str, line: int) -> ToolResult:
        fixes = []

        # Import error
        if "No module named" in error_message or "ImportError" in error_message:
            module = re.search(r"No module named '([^']+)'", error_message)
            if module:
                mod_name = module.group(1)
                fixes.append(f"1. Install: pip install {mod_name}")
                fixes.append(f"2. Or add to requirements.txt: {mod_name}")
                fixes.append(f"3. Check if module name is correct: {mod_name}")

        # NameError
        if "NameError" in error_message:
            name = re.search(r"name '([^']+)' is not defined", error_message)
            if name:
                var_name = name.group(1)
                fixes.append(f"1. Define variable: {var_name} = ...")
                fixes.append(f"2. Check typo: did you mean '{var_name}'?")
                fixes.append(f"3. Import if from module: from module import {var_name}")

        # Syntax error
        if "SyntaxError" in error_message or "IndentationError" in error_message:
            fixes.append("1. Check brackets/parentheses balance")
            fixes.append("2. Check indentation (spaces vs tabs)")
            fixes.append("3. Check for missing colons (:)")

        # AttributeError
        if "AttributeError" in error_message:
            attr = re.search(r"'[^']+' object has no attribute '([^']+)'", error_message)
            if attr:
                fixes.append(f"1. Check method name: {attr.group(1)}")
                fixes.append("2. Check object type")
                fixes.append("3. Use hasattr() to check attribute exists")

        if not fixes:
            fixes.append("1. Check error message carefully")
            fixes.append("2. Search documentation for this error")
            fixes.append("3. Check stack trace for root cause")

        return ToolResult(True, "\n".join(fixes), metadata={"fixes_count": len(fixes)})
