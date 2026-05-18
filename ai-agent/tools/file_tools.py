"""File system tools"""
import os
import glob
from pathlib import Path
from .base import BaseTool, ToolResult

class ReadFileTool(BaseTool):
    name = "read_file"
    description = "Read contents of a file. Use relative paths from working directory."
    parameters = {
        "path": {"type": "string", "description": "Path to file"},
        "offset": {"type": "integer", "description": "Line offset (optional)", "default": 0},
        "limit": {"type": "integer", "description": "Max lines to read (optional)", "default": 100}
    }

    def execute(self, path: str, offset: int = 0, limit: int = 100) -> ToolResult:
        try:
            full_path = Path(path).resolve()
            if not full_path.exists():
                return ToolResult(False, "", f"File not found: {path}")

            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                start = max(0, offset)
                end = min(len(lines), start + limit)
                content = "".join(lines[start:end])

            return ToolResult(True, content, metadata={"total_lines": len(lines), "shown": f"{start}-{end}"})
        except Exception as e:
            return ToolResult(False, "", str(e))

class WriteFileTool(BaseTool):
    name = "write_file"
    description = "Write content to a file. Creates directories if needed."
    parameters = {
        "path": {"type": "string", "description": "Path to file"},
        "content": {"type": "string", "description": "Content to write"},
        "append": {"type": "boolean", "description": "Append instead of overwrite", "default": False}
    }

    def execute(self, path: str, content: str, append: bool = False) -> ToolResult:
        try:
            full_path = Path(path).resolve()
            full_path.parent.mkdir(parents=True, exist_ok=True)

            mode = 'a' if append else 'w'
            with open(full_path, mode, encoding='utf-8') as f:
                f.write(content)

            return ToolResult(True, f"File {'appended' if append else 'written'}: {path}")
        except Exception as e:
            return ToolResult(False, "", str(e))

class ListFilesTool(BaseTool):
    name = "list_files"
    description = "List files in directory with optional pattern matching"
    parameters = {
        "path": {"type": "string", "description": "Directory path", "default": "."},
        "pattern": {"type": "string", "description": "Glob pattern", "default": "*"},
        "recursive": {"type": "boolean", "description": "Recursive listing", "default": False}
    }

    def execute(self, path: str = ".", pattern: str = "*", recursive: bool = False) -> ToolResult:
        try:
            base = Path(path).resolve()
            if not base.exists():
                return ToolResult(False, "", f"Directory not found: {path}")

            if recursive:
                files = list(base.rglob(pattern))
            else:
                files = list(base.glob(pattern))

            files_str = "\n".join([str(f.relative_to(base)) for f in files])
            return ToolResult(True, files_str, metadata={"count": len(files)})
        except Exception as e:
            return ToolResult(False, "", str(e))

class SearchFilesTool(BaseTool):
    name = "search_files"
    description = "Search for text in files using grep-like functionality"
    parameters = {
        "query": {"type": "string", "description": "Search text or regex"},
        "path": {"type": "string", "description": "Directory to search", "default": "."},
        "file_pattern": {"type": "string", "description": "File pattern", "default": "*"}
    }

    def execute(self, query: str, path: str = ".", file_pattern: str = "*") -> ToolResult:
        try:
            import re
            base = Path(path).resolve()
            results = []

            for file_path in base.rglob(file_pattern):
                if file_path.is_file():
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            for i, line in enumerate(f, 1):
                                if re.search(query, line):
                                    rel_path = file_path.relative_to(base)
                                    results.append(f"{rel_path}:{i}: {line.strip()}")
                    except Exception:
                        continue

            return ToolResult(True, "\n".join(results[:100]), metadata={"matches": len(results)})
        except Exception as e:
            return ToolResult(False, "", str(e))
