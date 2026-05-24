"""AI Agent v6 — Editor Feature Module
Handles file editing, diff management, and Composer batch operations.
"""
import re
import json
import difflib
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field

@dataclass
class EditOperation:
    """Single edit operation"""
    file_path: str
    old_text: str
    new_text: str
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    description: str = ""
    applied: bool = False
    error: Optional[str] = None

@dataclass
class FileVersion:
    """Version of a file for undo/redo"""
    content: str
    timestamp: float
    operation_id: str
    description: str

class EditorManager:
    """Manages file editing with undo/redo and Composer support"""

    def __init__(self, working_dir: str = "."):
        self.working_dir = Path(working_dir).resolve()
        self.undo_stack: Dict[str, List[FileVersion]] = {}  # file -> versions
        self.redo_stack: Dict[str, List[FileVersion]] = {}
        self.pending_edits: List[EditOperation] = []
        self.max_undo_depth = 50

    def read_file(self, path: str, offset: int = 0, lines: int = None) -> Tuple[str, int]:
        """Read file content with optional offset/lines"""
        full_path = self._resolve_path(path)
        if not full_path.exists():
            return "", 0

        content = full_path.read_text(encoding='utf-8', errors='replace')
        total_lines = content.count('\n') + 1

        if offset > 0 or lines is not None:
            all_lines = content.split('\n')
            start = offset
            end = offset + lines if lines else len(all_lines)
            content = '\n'.join(all_lines[start:end])

        return content, total_lines

    def write_file(self, path: str, content: str, create_dirs: bool = True) -> bool:
        """Write file content, creating directories if needed"""
        full_path = self._resolve_path(path)

        if create_dirs:
            full_path.parent.mkdir(parents=True, exist_ok=True)

        # Save current version for undo
        if full_path.exists():
            old_content = full_path.read_text(encoding='utf-8', errors='replace')
            self._push_undo(path, old_content, f"Before write: {path}")

        full_path.write_text(content, encoding='utf-8')
        return True

    def apply_diff(self, path: str, diff_text: str) -> Tuple[bool, str]:
        """Apply unified diff to a file"""
        full_path = self._resolve_path(path)

        if not full_path.exists():
            return False, f"File not found: {path}"

        old_content = full_path.read_text(encoding='utf-8', errors='replace')

        try:
            # Parse unified diff
            new_content = self._parse_and_apply_diff(old_content, diff_text)

            # Save undo
            self._push_undo(path, old_content, f"Diff apply: {path}")

            full_path.write_text(new_content, encoding='utf-8')
            return True, "Diff applied successfully"
        except Exception as e:
            return False, f"Failed to apply diff: {str(e)}"

    def _parse_and_apply_diff(self, original: str, diff_text: str) -> str:
        """Parse unified diff and apply to content"""
        lines = original.split('\n')
        diff_lines = diff_text.split('\n')

        result = []
        i = 0
        in_hunk = False
        hunk_start = 0
        hunk_len = 0

        for dline in diff_lines:
            if dline.startswith('@@'):
                # Parse hunk header: @@ -start,len +start,len @@
                match = re.match(r'@@ -(\d+),?(\d*) \+(\d+),?(\d*) @@', dline)
                if match:
                    hunk_start = int(match.group(1)) - 1  # 0-based
                    hunk_len = int(match.group(2) or 1)
                    in_hunk = True
                    # Add lines before hunk
                    while i < hunk_start and i < len(lines):
                        result.append(lines[i])
                        i += 1
            elif in_hunk:
                if dline.startswith('+'):
                    result.append(dline[1:])
                elif dline.startswith('-'):
                    i += 1  # Skip this line from original
                elif dline.startswith('\'):
                    pass  # No newline marker
                else:
                    # Context line
                    if i < len(lines):
                        result.append(lines[i])
                        i += 1

        # Add remaining lines
        while i < len(lines):
            result.append(lines[i])
            i += 1

        return '\n'.join(result)

    def generate_diff(self, path: str, new_content: str) -> str:
        """Generate unified diff between current and new content"""
        full_path = self._resolve_path(path)

        if not full_path.exists():
            return ""

        old_content = full_path.read_text(encoding='utf-8', errors='replace')
        old_lines = old_content.split('\n')
        new_lines = new_content.split('\n')

        diff = difflib.unified_diff(
            old_lines, new_lines,
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm=''
        )

        return '\n'.join(diff)

    def search_and_replace(self, path: str, old_text: str, new_text: str, 
                          count: int = 0) -> Tuple[int, str]:
        """Search and replace in file"""
        full_path = self._resolve_path(path)

        if not full_path.exists():
            return 0, f"File not found: {path}"

        content = full_path.read_text(encoding='utf-8', errors='replace')
        old_content = content

        if count == 0:
            new_content = content.replace(old_text, new_text)
            replacements = content.count(old_text)
        else:
            new_content = content.replace(old_text, new_text, count)
            replacements = count if old_text in content else 0

        if new_content == old_content:
            return 0, "No replacements made"

        self._push_undo(path, old_content, f"Search/replace: {path}")
        full_path.write_text(new_content, encoding='utf-8')

        return replacements, f"Made {replacements} replacement(s)"

    def insert_at_line(self, path: str, line: int, text: str) -> bool:
        """Insert text at specific line"""
        full_path = self._resolve_path(path)

        if not full_path.exists():
            return False

        content = full_path.read_text(encoding='utf-8', errors='replace')
        lines = content.split('\n')

        if line < 0:
            line = len(lines) + line + 1

        if line > len(lines):
            lines.extend([''] * (line - len(lines)))

        lines.insert(line, text)

        self._push_undo(path, content, f"Insert at line {line}: {path}")
        full_path.write_text('\n'.join(lines), encoding='utf-8')
        return True

    def delete_lines(self, path: str, start: int, end: int) -> bool:
        """Delete lines from start to end (inclusive, 0-based)"""
        full_path = self._resolve_path(path)

        if not full_path.exists():
            return False

        content = full_path.read_text(encoding='utf-8', errors='replace')
        lines = content.split('\n')

        if start < 0 or end >= len(lines) or start > end:
            return False

        del lines[start:end+1]

        self._push_undo(path, content, f"Delete lines {start}-{end}: {path}")
        full_path.write_text('\n'.join(lines), encoding='utf-8')
        return True

    def undo(self, path: str) -> Tuple[bool, str]:
        """Undo last change to file"""
        stack = self.undo_stack.get(path, [])
        if not stack:
            return False, "No undo history"

        version = stack.pop()
        full_path = self._resolve_path(path)

        # Save current to redo
        if full_path.exists():
            current = full_path.read_text(encoding='utf-8', errors='replace')
            redo_stack = self.redo_stack.setdefault(path, [])
            redo_stack.append(FileVersion(
                content=current,
                timestamp=__import__('time').time(),
                operation_id="redo",
                description=f"Before undo: {version.description}"
            ))

        full_path.write_text(version.content, encoding='utf-8')
        return True, f"Undone: {version.description}"

    def redo(self, path: str) -> Tuple[bool, str]:
        """Redo last undone change"""
        stack = self.redo_stack.get(path, [])
        if not stack:
            return False, "No redo history"

        version = stack.pop()
        full_path = self._resolve_path(path)

        # Save current back to undo
        if full_path.exists():
            current = full_path.read_text(encoding='utf-8', errors='replace')
            undo_stack = self.undo_stack.setdefault(path, [])
            undo_stack.append(FileVersion(
                content=current,
                timestamp=__import__('time').time(),
                operation_id="undo",
                description=f"Before redo"
            ))

        full_path.write_text(version.content, encoding='utf-8')
        return True, f"Redone: {version.description}"

    def get_file_info(self, path: str) -> Dict:
        """Get file metadata"""
        full_path = self._resolve_path(path)

        if not full_path.exists():
            return {"exists": False}

        stat = full_path.stat()
        content = full_path.read_text(encoding='utf-8', errors='replace')

        return {
            "exists": True,
            "path": path,
            "size": stat.st_size,
            "lines": content.count('\n') + 1,
            "modified": stat.st_mtime,
            "language": self._detect_language(path),
            "undo_count": len(self.undo_stack.get(path, [])),
            "redo_count": len(self.redo_stack.get(path, []))
        }

    def _resolve_path(self, path: str) -> Path:
        """Resolve path relative to working directory"""
        full = (self.working_dir / path).resolve()
        if not str(full).startswith(str(self.working_dir)):
            raise ValueError("Path traversal attempt detected")
        return full

    def _push_undo(self, path: str, content: str, description: str):
        """Push version to undo stack"""
        import time
        stack = self.undo_stack.setdefault(path, [])
        stack.append(FileVersion(
            content=content,
            timestamp=time.time(),
            operation_id=f"edit_{len(stack)}",
            description=description
        ))
        # Trim to max depth
        if len(stack) > self.max_undo_depth:
            stack.pop(0)
        # Clear redo on new edit
        self.redo_stack[path] = []

    def _detect_language(self, path: str) -> str:
        """Detect programming language from extension"""
        ext = Path(path).suffix.lower()
        mapping = {
            '.py': 'python', '.js': 'javascript', '.ts': 'typescript',
            '.jsx': 'jsx', '.tsx': 'tsx', '.html': 'html', '.css': 'css',
            '.json': 'json', '.md': 'markdown', '.yml': 'yaml', '.yaml': 'yaml',
            '.rs': 'rust', '.go': 'go', '.java': 'java', '.cpp': 'cpp',
            '.c': 'c', '.h': 'c', '.hpp': 'cpp', '.sh': 'shell',
            '.sql': 'sql', '.toml': 'toml', '.txt': 'plaintext'
        }
        return mapping.get(ext, ext.lstrip('.') or 'plaintext')

    def batch_apply(self, operations: List[EditOperation]) -> Dict[str, Any]:
        """Apply multiple edit operations atomically"""
        results = {
            "success": [],
            "failed": [],
            "total": len(operations)
        }

        # Validate all operations first
        for op in operations:
            full_path = self._resolve_path(op.file_path)
            if not full_path.exists() and op.old_text:
                results["failed"].append({
                    "path": op.file_path,
                    "error": "File does not exist"
                })
                continue

        # Apply valid operations
        for op in operations:
            if any(f["path"] == op.file_path for f in results["failed"]):
                continue

            try:
                if op.old_text and op.new_text:
                    count, msg = self.search_and_replace(
                        op.file_path, op.old_text, op.new_text
                    )
                    if count > 0:
                        op.applied = True
                        results["success"].append({
                            "path": op.file_path,
                            "description": op.description or msg
                        })
                    else:
                        results["failed"].append({
                            "path": op.file_path,
                            "error": msg
                        })
                else:
                    # Full file write
                    self.write_file(op.file_path, op.new_text)
                    op.applied = True
                    results["success"].append({
                        "path": op.file_path,
                        "description": op.description or "File written"
                    })
            except Exception as e:
                results["failed"].append({
                    "path": op.file_path,
                    "error": str(e)
                })

        return results

# Singleton
_editor_manager: Optional[EditorManager] = None

def get_editor_manager(working_dir: str = ".") -> EditorManager:
    global _editor_manager
    if _editor_manager is None:
        _editor_manager = EditorManager(working_dir)
    return _editor_manager
