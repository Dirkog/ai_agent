"""Persistent session memory — learns from past edits and user preferences
Like Cursor: remembers project context, coding style, frequently used patterns.
"""
import json
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime


@dataclass
class UserPreference:
    key: str
    value: Any
    context: str = ""  # e.g., "python", "javascript", "testing"
    confidence: float = 1.0  # How sure we are about this preference
    last_used: str = field(default_factory=lambda: datetime.now().isoformat())
    use_count: int = 1


@dataclass
class EditPattern:
    """Learned pattern from past edits"""
    file_pattern: str  # e.g., "*.py", "models/*.py"
    before_pattern: str  # Regex or snippet of what was changed
    after_pattern: str  # What it became
    description: str  # Human-readable description
    success_rate: float = 1.0  # How often this pattern worked
    use_count: int = 1


@dataclass
class ProjectContext:
    """Persistent context about the project"""
    tech_stack: List[str] = field(default_factory=list)
    architecture_notes: str = ""
    api_endpoints: List[Dict] = field(default_factory=list)
    database_schema: Dict = field(default_factory=dict)
    important_files: List[str] = field(default_factory=list)
    custom_rules: str = ""  # Like .cursorrules


class PersistentMemory:
    """Persistent memory store for AI agent"""

    def __init__(self, project_path: str = "."):
        self.project_path = Path(project_path).resolve()
        self.memory_dir = self.project_path / ".ai-agent" / "memory"
        self.memory_dir.mkdir(parents=True, exist_ok=True)

        self.preferences_file = self.memory_dir / "preferences.json"
        self.patterns_file = self.memory_dir / "patterns.json"
        self.context_file = self.memory_dir / "project_context.json"
        self.sessions_file = self.memory_dir / "sessions.json"

        self.preferences: Dict[str, UserPreference] = {}
        self.patterns: List[EditPattern] = []
        self.project_context = ProjectContext()
        self.sessions: List[Dict] = []

        self._load_all()

    def _load_all(self):
        """Load all persistent data"""
        if self.preferences_file.exists():
            try:
                data = json.loads(self.preferences_file.read_text())
                self.preferences = {k: UserPreference(**v) for k, v in data.items()}
            except Exception:
                pass

        if self.patterns_file.exists():
            try:
                data = json.loads(self.patterns_file.read_text())
                self.patterns = [EditPattern(**p) for p in data]
            except Exception:
                pass

        if self.context_file.exists():
            try:
                data = json.loads(self.context_file.read_text())
                self.project_context = ProjectContext(**data)
            except Exception:
                pass

        if self.sessions_file.exists():
            try:
                self.sessions = json.loads(self.sessions_file.read_text())
            except Exception:
                pass

    def _save_all(self):
        """Save all persistent data"""
        self.preferences_file.write_text(json.dumps(
            {k: asdict(v) for k, v in self.preferences.items()}, indent=2
        ))
        self.patterns_file.write_text(json.dumps(
            [asdict(p) for p in self.patterns], indent=2
        ))
        self.context_file.write_text(json.dumps(
            asdict(self.project_context), indent=2
        ))
        self.sessions_file.write_text(json.dumps(self.sessions, indent=2))

    def record_preference(self, key: str, value: Any, context: str = ""):
        """Record a user preference (e.g., 'prefer_fastapi_over_flask': True)"""
        pref_key = f"{context}:{key}" if context else key

        if pref_key in self.preferences:
            existing = self.preferences[pref_key]
            existing.value = value
            existing.use_count += 1
            existing.confidence = min(1.0, existing.confidence + 0.1)
            existing.last_used = datetime.now().isoformat()
        else:
            self.preferences[pref_key] = UserPreference(
                key=key, value=value, context=context
            )

        self._save_all()

    def get_preference(self, key: str, context: str = "", default: Any = None) -> Any:
        """Get a learned preference"""
        pref_key = f"{context}:{key}" if context else key
        if pref_key in self.preferences:
            return self.preferences[pref_key].value
        return default

    def record_pattern(self, file_pattern: str, before: str, after: str, description: str):
        """Record a successful edit pattern"""
        # Check if similar pattern exists
        for p in self.patterns:
            if p.file_pattern == file_pattern and p.before_pattern == before:
                p.success_rate = (p.success_rate * p.use_count + 1) / (p.use_count + 1)
                p.use_count += 1
                p.after_pattern = after  # Update to latest
                self._save_all()
                return

        self.patterns.append(EditPattern(
            file_pattern=file_pattern,
            before_pattern=before,
            after_pattern=after,
            description=description
        ))
        self._save_all()

    def find_patterns_for_file(self, path: str) -> List[EditPattern]:
        """Find relevant patterns for a file"""
        from fnmatch import fnmatch
        return [p for p in self.patterns if fnmatch(path, p.file_pattern)]

    def update_project_context(self, **kwargs):
        """Update project context (tech stack, architecture, etc.)"""
        for key, value in kwargs.items():
            if hasattr(self.project_context, key):
                setattr(self.project_context, key, value)
        self._save_all()

    def record_session(self, task: str, success: bool, iterations: int, files_modified: List[str]):
        """Record session outcome for learning"""
        self.sessions.append({
            "timestamp": datetime.now().isoformat(),
            "task": task,
            "success": success,
            "iterations": iterations,
            "files_modified": files_modified
        })
        # Keep only last 100 sessions
        self.sessions = self.sessions[-100:]
        self._save_all()

    def get_project_summary(self) -> str:
        """Get summary of learned project context for LLM prompt"""
        lines = ["\n[LEARNED PROJECT CONTEXT]"]

        if self.project_context.tech_stack:
            lines.append(f"Tech stack: {', '.join(self.project_context.tech_stack)}")

        if self.project_context.architecture_notes:
            lines.append(f"Architecture: {self.project_context.architecture_notes}")

        if self.project_context.important_files:
            lines.append(f"Key files: {', '.join(self.project_context.important_files)}")

        # Top preferences
        top_prefs = sorted(
            self.preferences.values(),
            key=lambda p: p.use_count * p.confidence,
            reverse=True
        )[:10]
        if top_prefs:
            lines.append("\nLearned preferences:")
            for p in top_prefs:
                lines.append(f"  - {p.key}: {p.value} (confidence: {p.confidence:.2f})")

        lines.append("[END CONTEXT]\n")
        return "\n".join(lines)

    def load_cursorrules(self) -> str:
        """Load .cursorrules file if exists"""
        rules_file = self.project_path / ".cursorrules"
        if rules_file.exists():
            return rules_file.read_text()
        return ""

    def save_cursorrules(self, content: str):
        """Save .cursorrules file"""
        rules_file = self.project_path / ".cursorrules"
        rules_file.write_text(content)
