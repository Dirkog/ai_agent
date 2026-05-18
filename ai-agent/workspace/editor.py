"""Cursor-like workspace: file tree, tabs, split panes, inline editor
Simulates the full IDE workspace experience.
"""
import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum


class TabState(Enum):
    CLEAN = "clean"
    MODIFIED = "modified"
    UNSAVED = "unsaved"


@dataclass
class EditorTab:
    path: str
    content: str = ""
    cursor_line: int = 0
    cursor_col: int = 0
    scroll_top: int = 0
    state: TabState = TabState.CLEAN
    is_active: bool = False
    language: str = ""


@dataclass
class WorkspaceState:
    root_path: str = "."
    active_tab: Optional[str] = None
    tabs: Dict[str, EditorTab] = field(default_factory=dict)
    open_directories: List[str] = field(default_factory=list)
    sidebar_width: int = 260
    terminal_height: int = 200
    split_ratio: float = 0.5  # 0.5 = 50/50 split

    def to_dict(self) -> dict:
        return {
            "root_path": self.root_path,
            "active_tab": self.active_tab,
            "tabs": {k: {
                "path": v.path,
                "cursor_line": v.cursor_line,
                "cursor_col": v.cursor_col,
                "state": v.state.value,
                "is_active": v.is_active
            } for k, v in self.tabs.items()},
            "open_directories": self.open_directories,
        }


class WorkspaceEditor:
    """Cursor-like workspace manager"""

    def __init__(self, root_path: str = "."):
        self.root = Path(root_path).resolve()
        self.state = WorkspaceState(root_path=str(self.root))
        self._file_cache: Dict[str, str] = {}  # path -> content
        self._history: List[dict] = []  # Undo history

    def open_file(self, path: str) -> EditorTab:
        """Open file in workspace"""
        full_path = self.root / path

        if path in self.state.tabs:
            tab = self.state.tabs[path]
            tab.is_active = True
            self.state.active_tab = path
            self._deactivate_others(path)
            return tab

        content = ""
        if full_path.exists():
            try:
                content = full_path.read_text(encoding='utf-8')
            except Exception:
                pass

        ext = Path(path).suffix.lstrip('.')
        lang_map = {
            'py': 'python', 'js': 'javascript', 'ts': 'typescript',
            'jsx': 'jsx', 'tsx': 'tsx', 'html': 'html', 'css': 'css',
            'json': 'json', 'md': 'markdown', 'yml': 'yaml', 'yaml': 'yaml',
            'rs': 'rust', 'go': 'go', 'java': 'java', 'cpp': 'cpp',
            'c': 'c', 'h': 'c', 'hpp': 'cpp', 'sh': 'shell',
            'dockerfile': 'dockerfile', 'sql': 'sql'
        }

        tab = EditorTab(
            path=path,
            content=content,
            language=lang_map.get(ext, ext or "plaintext"),
            is_active=True
        )

        self.state.tabs[path] = tab
        self.state.active_tab = path
        self._deactivate_others(path)
        self._file_cache[path] = content

        return tab

    def close_file(self, path: str) -> bool:
        """Close tab, prompt if unsaved"""
        if path not in self.state.tabs:
            return False

        tab = self.state.tabs[path]
        if tab.state in (TabState.MODIFIED, TabState.UNSAVED):
            # In real UI would prompt user
            print(f"⚠️  {path} has unsaved changes!")
            return False

        del self.state.tabs[path]
        if self.state.active_tab == path:
            self.state.active_tab = next(iter(self.state.tabs.keys()), None)
            if self.state.active_tab:
                self.state.tabs[self.state.active_tab].is_active = True

        return True

    def edit_file(self, path: str, new_content: str, start_line: int = 0, end_line: Optional[int] = None) -> bool:
        """Edit file content in workspace"""
        if path not in self.state.tabs:
            self.open_file(path)

        tab = self.state.tabs[path]

        # Save to history for undo
        self._history.append({
            "path": path,
            "old_content": tab.content,
            "timestamp": __import__('time').time()
        })

        if end_line is None:
            tab.content = new_content
        else:
            lines = tab.content.splitlines(keepends=True)
            new_lines = new_content.splitlines(keepends=True)
            lines[start_line:end_line] = new_lines
            tab.content = "".join(lines)

        tab.state = TabState.MODIFIED
        return True

    def save_file(self, path: str) -> bool:
        """Save file to disk"""
        if path not in self.state.tabs:
            return False

        tab = self.state.tabs[path]
        full_path = self.root / path

        try:
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(tab.content, encoding='utf-8')
            tab.state = TabState.CLEAN
            self._file_cache[path] = tab.content
            return True
        except Exception as e:
            print(f"❌ Save failed: {e}")
            return False

    def save_all(self) -> Dict[str, bool]:
        """Save all modified tabs"""
        results = {}
        for path, tab in self.state.tabs.items():
            if tab.state != TabState.CLEAN:
                results[path] = self.save_file(path)
        return results

    def get_file_tree(self, path: str = ".", depth: int = 3) -> dict:
        """Get file tree for sidebar"""
        base = self.root / path
        tree = {"name": base.name, "path": str(Path(path)), "type": "directory", "children": []}

        try:
            for item in sorted(base.iterdir()):
                if item.name.startswith('.') and item.name not in ('.env', '.gitignore', '.cursorrules'):
                    continue

                rel = str(item.relative_to(self.root))
                if item.is_dir() and depth > 0:
                    tree["children"].append(self.get_file_tree(rel, depth - 1))
                elif item.is_file():
                    tree["children"].append({
                        "name": item.name,
                        "path": rel,
                        "type": "file",
                        "size": item.stat().st_size,
                        "modified": item.stat().st_mtime
                    })
        except PermissionError:
            pass

        return tree

    def get_active_context(self, max_lines: int = 50) -> str:
        """Get context of active file for LLM"""
        if not self.state.active_tab:
            return ""

        tab = self.state.tabs[self.state.active_tab]
        lines = tab.content.splitlines()

        # Get context around cursor
        start = max(0, tab.cursor_line - max_lines // 2)
        end = min(len(lines), tab.cursor_line + max_lines // 2)

        context_lines = []
        for i in range(start, end):
            prefix = ">>> " if i == tab.cursor_line else "    "
            context_lines.append(f"{prefix}{i+1:4d}: {lines[i]}")

        return f"\n[ACTIVE FILE: {tab.path} | cursor: {tab.cursor_line+1}:{tab.cursor_col+1}]\n" + "\n".join(context_lines)

    def _deactivate_others(self, active_path: str):
        """Deactivate other tabs"""
        for path, tab in self.state.tabs.items():
            if path != active_path:
                tab.is_active = False

    def undo(self) -> Optional[str]:
        """Undo last edit"""
        if not self._history:
            return None

        last = self._history.pop()
        path = last["path"]
        if path in self.state.tabs:
            self.state.tabs[path].content = last["old_content"]
            return path
        return None

    def get_workspace_summary(self) -> str:
        """Summary for LLM context"""
        lines = [
            f"\n[WORKSPACE]",
            f"Root: {self.state.root_path}",
            f"Open tabs: {len(self.state.tabs)}",
            f"Active: {self.state.active_tab or 'none'}",
        ]

        if self.state.tabs:
            lines.append("\nOpen files:")
            for path, tab in self.state.tabs.items():
                marker = "*" if tab.state != TabState.CLEAN else " "
                active = ">" if tab.is_active else " "
                lines.append(f"  {active}{marker} {path} ({tab.language})")

        lines.append("[END WORKSPACE]\n")
        return "\n".join(lines)
