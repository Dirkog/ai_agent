"""Composer — batch multi-file editing with atomic transactions and topological sort
Like Cursor Composer: plans changes across multiple files, shows unified diff, applies atomically.
v6 update: Fixed _sort_by_dependencies to use Kahn's algorithm, improved diff preview
"""
import json
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict, deque


class ChangeStatus(Enum):
    PLANNED = "planned"
    APPROVED = "approved"
    APPLIED = "applied"
    FAILED = "failed"
    REVERTED = "reverted"


@dataclass
class FileChange:
    path: str
    original_content: str = ""
    new_content: str = ""
    diff: str = ""
    status: ChangeStatus = ChangeStatus.PLANNED
    reason: str = ""  # Why this change was made
    dependencies: List[str] = field(default_factory=list)  # Other files this depends on


@dataclass
class ComposerPlan:
    task: str = ""
    changes: List[FileChange] = field(default_factory=list)
    checkpoint_commit: Optional[str] = None
    total_files: int = 0
    estimated_tokens: int = 0


class BatchEditor:
    """Batch file editor with atomic apply/revert and topological sorting"""

    def __init__(self, working_dir: str = "."):
        self.working_dir = Path(working_dir).resolve()
        self.current_plan: Optional[ComposerPlan] = None
        self._backup: Dict[str, str] = {}  # path -> original content

    def create_plan(self, task: str, file_changes: List[Dict[str, Any]]) -> ComposerPlan:
        """Create a batch editing plan from LLM output"""
        plan = ComposerPlan(task=task)

        for change_data in file_changes:
            path = change_data.get("path", "")
            full_path = self.working_dir / path

            # Read original if exists
            original = ""
            if full_path.exists():
                try:
                    original = full_path.read_text(encoding='utf-8')
                except Exception:
                    pass

            fc = FileChange(
                path=path,
                original_content=original,
                new_content=change_data.get("content", ""),
                reason=change_data.get("reason", ""),
                dependencies=change_data.get("dependencies", [])
            )
            plan.changes.append(fc)

        plan.total_files = len(plan.changes)
        plan.estimated_tokens = sum(len(c.new_content) // 4 for c in plan.changes)
        self.current_plan = plan
        return plan

    def generate_plan_from_llm(self, llm_response: str) -> ComposerPlan:
        """Parse LLM response with multiple file edits into a plan"""
        # Parse ```file blocks
        pattern = r'```file\s+([\w./-]+)\s*\n([\s\S]*?)```'
        matches = re.findall(pattern, llm_response)

        changes = []
        for filepath, content in matches:
            changes.append({
                "path": filepath,
                "content": content,
                "reason": "LLM generated edit"
            })

        return self.create_plan("Batch edit", changes)

    def preview_diff(self) -> str:
        """Generate unified diff preview of all changes"""
        if not self.current_plan:
            return "No plan available"

        lines = [
            "=" * 70,
            f"📝 COMPOSER PLAN: {self.current_plan.task}",
            f"Files: {len(self.current_plan.changes)} | Est. tokens: {self.current_plan.estimated_tokens}",
            "=" * 70,
        ]

        for i, change in enumerate(self.current_plan.changes, 1):
            lines.append(f"\n--- [{i}/{len(self.current_plan.changes)}] {change.path} ---")
            lines.append(f"Reason: {change.reason}")

            if change.dependencies:
                lines.append(f"Dependencies: {', '.join(change.dependencies)}")

            if change.original_content and change.new_content:
                # Generate unified diff
                diff_lines = self._generate_unified_diff(
                    change.original_content, change.new_content, change.path
                )
                lines.append("\nDiff:")
                lines.extend(diff_lines[:30])  # Show first 30 lines of diff
                if len(diff_lines) > 30:
                    lines.append(f"... ({len(diff_lines) - 30} more lines)")
            elif not change.original_content:
                lines.append("[NEW FILE]")
                preview = change.new_content[:200].replace('\n', ' ')
                lines.append(f" {preview}...")

            lines.append(f"Status: {change.status.value}")
            lines.append("\n" + "-" * 70)

        return "\n".join(lines)

    def _generate_unified_diff(self, original: str, new: str, path: str, context: int = 3) -> List[str]:
        """Generate unified diff between original and new content"""
        orig_lines = original.splitlines()
        new_lines = new.splitlines()

        # Simple line-by-line diff
        import difflib
        diff = list(difflib.unified_diff(
            orig_lines, new_lines,
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm="",
            n=context
        ))
        return diff

    def approve_all(self) -> None:
        """Mark all changes as approved"""
        if self.current_plan:
            for change in self.current_plan.changes:
                change.status = ChangeStatus.APPROVED

    def apply_all(self, auto_approve: bool = False) -> Tuple[int, int]:
        """Apply all approved changes atomically. Returns (success, failed)"""
        if not self.current_plan:
            return 0, 0

        if not auto_approve:
            # Interactive approval
            print(self.preview_diff())
            confirm = input("\nApply all changes? [Y/n/review]: ").strip().lower()
            if confirm == "review":
                return self._interactive_apply()
            if confirm and confirm not in ('y', 'yes'):
                print("Cancelled")
                return 0, 0

        success = 0
        failed = 0

        # Backup all files first
        for change in self.current_plan.changes:
            full_path = self.working_dir / change.path
            if full_path.exists():
                self._backup[change.path] = full_path.read_text(encoding='utf-8')

        # FIX: Apply in topological order (dependencies first)
        sorted_changes = self._sort_by_dependencies(self.current_plan.changes)

        for change in sorted_changes:
            try:
                full_path = self.working_dir / change.path
                full_path.parent.mkdir(parents=True, exist_ok=True)
                full_path.write_text(change.new_content, encoding='utf-8')
                change.status = ChangeStatus.APPLIED
                success += 1
                print(f" ✅ {change.path}")
            except Exception as e:
                change.status = ChangeStatus.FAILED
                change.reason += f" | Error: {e}"
                failed += 1
                print(f" ❌ {change.path}: {e}")

        if failed > 0 and not auto_approve:
            revert = input(f"\n{failed} failed. Revert all? [Y/n]: ").strip().lower()
            if not revert or revert in ('y', 'yes'):
                self.revert_all()

        return success, failed

    def _interactive_apply(self) -> Tuple[int, int]:
        """Apply changes one by one with user confirmation"""
        success = 0
        failed = 0

        for change in self.current_plan.changes:
            print(f"\n--- {change.path} ---")
            print(f"Reason: {change.reason}")

            # Show mini diff
            if change.original_content:
                print("Original (first 5 lines):")
                for line in change.original_content.splitlines()[:5]:
                    print(f" {line}")

            print("New (first 5 lines):")
            for line in change.new_content.splitlines()[:5]:
                print(f" {line}")

            action = input("[a]pply, [s]kip, [r]eview full, [q]uit: ").strip().lower()

            if action == 'q':
                break
            elif action == 's':
                continue
            elif action == 'r':
                print("\nFull new content:")
                print(change.new_content)
                inner = input("Apply? [Y/n]: ").strip().lower()
                if inner and inner not in ('y', 'yes'):
                    continue

            try:
                full_path = self.working_dir / change.path
                full_path.parent.mkdir(parents=True, exist_ok=True)
                if full_path.exists():
                    self._backup[change.path] = full_path.read_text(encoding='utf-8')
                full_path.write_text(change.new_content, encoding='utf-8')
                change.status = ChangeStatus.APPLIED
                success += 1
            except Exception as e:
                change.status = ChangeStatus.FAILED
                failed += 1
                print(f"Error: {e}")

        return success, failed

    def revert_all(self) -> None:
        """Revert all changes to original state"""
        if not self.current_plan:
            return

        for change in self.current_plan.changes:
            if change.path in self._backup:
                full_path = self.working_dir / change.path
                full_path.write_text(self._backup[change.path], encoding='utf-8')
                change.status = ChangeStatus.REVERTED

        print("🔄 All changes reverted")

    def _sort_by_dependencies(self, changes: List[FileChange]) -> List[FileChange]:
        """FIX: Topological sort using Kahn's algorithm"""
        # Build dependency graph
        path_to_change = {c.path: c for c in changes}
        in_degree = {c.path: 0 for c in changes}
        graph = defaultdict(list)

        for change in changes:
            for dep in change.dependencies:
                if dep in path_to_change:
                    graph[dep].append(change.path)
                    in_degree[change.path] += 1

        # Kahn's algorithm
        queue = deque([p for p, d in in_degree.items() if d == 0])
        sorted_paths = []

        while queue:
            path = queue.popleft()
            sorted_paths.append(path)
            for neighbor in graph[path]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # Check for cycles
        if len(sorted_paths) != len(changes):
            # Cycle detected — return original order as fallback
            print("⚠️ Dependency cycle detected, using original order")
            return changes

        return [path_to_change[p] for p in sorted_paths]

    def get_summary(self) -> str:
        """Get execution summary"""
        if not self.current_plan:
            return "No plan executed"

        applied = sum(1 for c in self.current_plan.changes if c.status == ChangeStatus.APPLIED)
        failed = sum(1 for c in self.current_plan.changes if c.status == ChangeStatus.FAILED)
        planned = len(self.current_plan.changes)

        return f"Composer: {applied}/{planned} applied, {failed} failed"
