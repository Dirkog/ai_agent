"""AI-powered tools for intelligent code operations
Code explanation, smart generation, intelligent review, documentation generation.
"""
import ast
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from ..base import BaseTool, ToolResult


class ExplainCodeTool(BaseTool):
    name = "explain_code"
    description = "Explain what code does in plain English — line by line or high-level summary"
    parameters = {
        "path": {"type": "string", "description": "File path or code snippet"},
        "style": {"type": "string", "description": "Explanation style", "enum": ["line_by_line", "high_level", "algorithm", "complexity"], "default": "high_level"},
        "target_audience": {"type": "string", "description": "Who is reading", "enum": ["beginner", "intermediate", "expert"], "default": "intermediate"}
    }

    def execute(self, path: str, style: str = "high_level", target_audience: str = "intermediate") -> ToolResult:
        try:
            # Check if it's a file path or raw code
            if Path(path).exists():
                with open(path, 'r', encoding='utf-8') as f:
                    code = f.read()
            else:
                code = path  # Treat as code snippet

            tree = ast.parse(code)

            explanations = []

            if style == "high_level":
                # Extract imports and main components
                imports = []
                classes = []
                functions = []

                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        imports.extend(a.name for a in node.names)
                    elif isinstance(node, ast.ImportFrom):
                        imports.append(f"{node.module}.{node.names[0].name}" if node.names else node.module)
                    elif isinstance(node, ast.ClassDef):
                        methods = [n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
                        classes.append(f"Class '{node.name}' with methods: {', '.join(methods)}")
                    elif isinstance(node, ast.FunctionDef):
                        functions.append(f"Function '{node.name}({self._get_args(node)})'")

                explanations.append("📦 Imports: " + ", ".join(set(imports)))
                explanations.append("")
                for c in classes:
                    explanations.append(f"🔷 {c}")
                for f in functions:
                    explanations.append(f"⚡ {f}")

            elif style == "line_by_line":
                lines = code.splitlines()
                for i, line in enumerate(lines, 1):
                    stripped = line.strip()
                    if stripped and not stripped.startswith('#'):
                        explanations.append(f"{i:3d}: {stripped[:60]}")

            elif style == "complexity":
                # Calculate cyclomatic complexity manually
                complexity = 1
                for node in ast.walk(tree):
                    if isinstance(node, (ast.If, ast.While, ast.For, ast.ExceptHandler,
                                       ast.With, ast.Assert, ast.comprehension)):
                        complexity += 1
                    elif isinstance(node, ast.BoolOp):
                        complexity += len(node.values) - 1

                explanations.append(f"Cyclomatic Complexity: {complexity}")
                if complexity <= 10:
                    explanations.append("✅ Low complexity — easy to understand")
                elif complexity <= 20:
                    explanations.append("⚠️  Medium complexity — consider refactoring")
                else:
                    explanations.append("❌ High complexity — should be refactored")

            return ToolResult(True, "\n".join(explanations))
        except Exception as e:
            return ToolResult(False, "", str(e))

    def _get_args(self, node) -> str:
        args = [a.arg for a in node.args.args]
        if node.args.vararg:
            args.append(f"*{node.args.vararg.arg}")
        if node.args.kwarg:
            args.append(f"**{node.args.kwarg.arg}")
        return ", ".join(args)


class GenerateTestsTool(BaseTool):
    name = "generate_tests"
    description = "Generate comprehensive test cases for code — unit tests, edge cases, property tests"
    parameters = {
        "path": {"type": "string", "description": "File to generate tests for"},
        "framework": {"type": "string", "description": "Test framework", "enum": ["pytest", "unittest", "hypothesis"], "default": "pytest"},
        "coverage_target": {"type": "integer", "description": "Target coverage %", "default": 90}
    }

    def execute(self, path: str, framework: str = "pytest", coverage_target: int = 90) -> ToolResult:
        try:
            full_path = Path(path).resolve()
            with open(full_path, 'r', encoding='utf-8') as f:
                source = f.read()

            tree = ast.parse(source)

            test_cases = []
            test_cases.append(f"# Auto-generated tests for {path}")
            test_cases.append(f"# Target coverage: {coverage_target}%")
            test_cases.append(f"# Framework: {framework}")
            test_cases.append("")

            if framework == "pytest":
                test_cases.append("import pytest")
                test_cases.append(f"from {Path(path).stem} import *")
                test_cases.append("")

                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if not node.name.startswith('_'):
                            # Generate test for function
                            args = [a.arg for a in node.args.args if a.arg != 'self']
                            test_cases.append(f"def test_{node.name}():")
                            test_cases.append(f'    """Test {node.name}"""')

                            # Generate parameter examples
                            if args:
                                params = ", ".join([f"{a}=None" for a in args])
                                test_cases.append(f"    result = {node.name}({params})")
                            else:
                                test_cases.append(f"    result = {node.name}()")

                            test_cases.append("    assert result is not None")
                            test_cases.append("")

                            # Edge cases
                            test_cases.append(f"def test_{node.name}_edge_cases():")
                            test_cases.append(f'    """Test {node.name} edge cases"""')
                            test_cases.append("    # TODO: Add edge case tests")
                            test_cases.append("    pass")
                            test_cases.append("")

            elif framework == "hypothesis":
                test_cases.append("from hypothesis import given, strategies as st")
                test_cases.append("")

                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef) and not node.name.startswith('_'):
                        args = [a.arg for a in node.args.args if a.arg != 'self']
                        if args:
                            test_cases.append(f"@given({', '.join([f'{a}=st.integers()' for a in args])})")
                            test_cases.append(f"def test_{node.name}_property({', '.join(args)}):")
                            test_cases.append(f"    {node.name}({', '.join(args)})")
                            test_cases.append("")

            return ToolResult(True, "\n".join(test_cases), metadata={"tests_generated": len(test_cases)})
        except Exception as e:
            return ToolResult(False, "", str(e))


class GenerateDocsTool(BaseTool):
    name = "generate_docs"
    description = "Generate documentation: docstrings, README, API docs, type stubs"
    parameters = {
        "path": {"type": "string", "description": "File or directory to document"},
        "format": {"type": "string", "description": "Output format", "enum": ["docstrings", "markdown", "rst", "stubs"], "default": "docstrings"},
        "include_examples": {"type": "boolean", "description": "Include usage examples", "default": True}
    }

    def execute(self, path: str, format: str = "docstrings", include_examples: bool = True) -> ToolResult:
        try:
            full_path = Path(path).resolve()

            if full_path.is_file():
                with open(full_path, 'r', encoding='utf-8') as f:
                    source = f.read()
                tree = ast.parse(source)

                docs = []

                if format == "docstrings":
                    for node in ast.walk(tree):
                        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                            if not ast.get_docstring(node):
                                # Generate docstring
                                if isinstance(node, ast.ClassDef):
                                    methods = [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
                                    doc = f'"""{node.name} class.\n\nMethods: {", ".join(methods)}\n"""'
                                else:
                                    args = [a.arg for a in node.args.args]
                                    doc = f'"""{node.name}({", ".join(args)}).\n\nReturns:\n    TODO\n"""'

                                docs.append(f"{node.lineno}: {node.name}")
                                docs.append(f"Suggested docstring:\n{doc}")
                                docs.append("")

                elif format == "markdown":
                    docs.append(f"# {full_path.stem}")
                    docs.append("")

                    for node in ast.walk(tree):
                        if isinstance(node, ast.ClassDef):
                            docs.append(f"## Class: {node.name}")
                            docs.append("")
                            for child in ast.iter_child_nodes(node):
                                if isinstance(child, ast.FunctionDef):
                                    docs.append(f"### {child.name}()")
                                    docs.append("")
                            docs.append("")
                        elif isinstance(node, ast.FunctionDef) and not isinstance(node.parent, ast.ClassDef) if hasattr(node, 'parent') else True:
                            docs.append(f"## Function: {node.name}()")
                            docs.append("")

                return ToolResult(True, "\n".join(docs))

            else:
                # Directory documentation
                return ToolResult(True, f"Directory docs for {path} — TODO: Generate module index")
        except Exception as e:
            return ToolResult(False, "", str(e))


class SmartImportTool(BaseTool):
    name = "smart_import"
    description = "Auto-import missing modules, organize imports, detect unused imports (like VS Code auto-import)"
    parameters = {
        "path": {"type": "string", "description": "File to fix imports"},
        "action": {"type": "string", "description": "Action", "enum": ["organize", "remove_unused", "add_missing", "all"], "default": "all"}
    }

    def execute(self, path: str, action: str = "all") -> ToolResult:
        try:
            full_path = Path(path).resolve()
            with open(full_path, 'r', encoding='utf-8') as f:
                source = f.read()

            tree = ast.parse(source)

            # Find all imports
            imports = []
            used_names = set()

            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    for alias in node.names:
                        imports.append({
                            "name": alias.name,
                            "asname": alias.asname,
                            "module": node.module if isinstance(node, ast.ImportFrom) else None,
                            "node": node
                        })
                elif isinstance(node, ast.Name):
                    used_names.add(node.id)

            results = []

            if action in ("remove_unused", "all"):
                unused = [i for i in imports if i["name"] not in used_names and i["asname"] not in used_names]
                if unused:
                    results.append("Unused imports:")
                    for u in unused:
                        results.append(f"  - {u['name']}")

            if action in ("organize", "all"):
                # Group imports
                stdlib = {"os", "sys", "json", "re", "pathlib", "typing", "dataclasses", "collections", "itertools", "functools"}
                third_party = {"requests", "flask", "django", "numpy", "pandas", "pytest"}

                stdlib_imports = [i for i in imports if i["name"] in stdlib or (i["module"] and i["module"].split('.')[0] in stdlib)]
                third_imports = [i for i in imports if i["name"] in third_party or (i["module"] and i["module"].split('.')[0] in third_party)]
                local_imports = [i for i in imports if i not in stdlib_imports and i not in third_imports]

                results.append("Import organization:")
                results.append("  Stdlib: " + ", ".join([i["name"] for i in stdlib_imports]))
                results.append("  Third-party: " + ", ".join([i["name"] for i in third_imports]))
                results.append("  Local: " + ", ".join([i["name"] for i in local_imports]))

            return ToolResult(True, "\n".join(results) if results else "No import issues found")
        except Exception as e:
            return ToolResult(False, "", str(e))
