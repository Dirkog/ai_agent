"""Diff-based file editing — preserves formatting and comments"""
import re
import difflib
from pathlib import Path
from typing import List, Tuple, Optional
from .base import BaseTool, ToolResult


class ApplyDiffTool(BaseTool):
    name = "apply_diff"
    description = "Apply a unified diff patch to a file. Preserves surrounding context."
    parameters = {
        "path": {"type": "string", "description": "Path to file"},
        "diff": {"type": "string", "description": "Unified diff text (@@ -start,count +start,count @@ format)"},
        "context_lines": {"type": "integer", "description": "Lines of context", "default": 3}
    }

    def execute(self, path: str, diff: str, context_lines: int = 3) -> ToolResult:
        try:
            full_path = Path(path).resolve()
            if not full_path.exists():
                return ToolResult(False, "", f"File not found: {path}")

            with open(full_path, 'r', encoding='utf-8') as f:
                original_lines = f.readlines()

            # Normalize to list without trailing newlines for processing
            original = [line.rstrip('\n') for line in original_lines]
            # Ensure last line has newline if original did
            ends_with_newline = original_lines and original_lines[-1].endswith('\n')

            new_lines = self._apply_unified_diff(original, diff)
            if new_lines is None:
                return ToolResult(False, "", "Could not apply diff — context mismatch or malformed patch")

            # Restore newlines
            output_lines = [line + '\n' for line in new_lines]
            if not ends_with_newline and output_lines:
                output_lines[-1] = output_lines[-1].rstrip('\n')

            with open(full_path, 'w', encoding='utf-8') as f:
                f.writelines(output_lines)

            return ToolResult(True, f"Patched {path} ({len(original)} -> {len(new_lines)} lines)")
        except Exception as e:
            return ToolResult(False, "", str(e))

    def _apply_unified_diff(self, original: List[str], diff_text: str) -> Optional[List[str]]:
        """Apply unified diff to original lines"""
        lines = original.copy()
        hunks = self._parse_hunks(diff_text)

        # Apply hunks in reverse order (bottom-up) to preserve line numbers
        for hunk in reversed(hunks):
            start, old_count, new_count, hunk_lines = hunk
            # Convert to 0-based
            idx = start - 1

            old_lines = []
            new_lines = []
            for hl in hunk_lines:
                if hl.startswith('-'):
                    old_lines.append(hl[1:])
                elif hl.startswith('+'):
                    new_lines.append(hl[1:])
                elif hl.startswith(' '):
                    old_lines.append(hl[1:])
                    new_lines.append(hl[1:])
                elif hl.startswith('\\'):
                    pass  # No newline marker

            # Verify context matches
            actual_old = lines[idx:idx + old_count]
            if len(actual_old) != len(old_lines):
                return None
            for a, b in zip(actual_old, old_lines):
                if a != b:
                    return None

            # Apply replacement
            lines[idx:idx + old_count] = new_lines

        return lines

    def _parse_hunks(self, diff_text: str) -> List[Tuple[int, int, int, List[str]]]:
        """Parse unified diff into hunks: (start, old_count, new_count, lines)"""
        hunks = []
        lines = diff_text.split('\n')
        i = 0
        while i < len(lines):
            line = lines[i]
            match = re.match(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@', line)
            if match:
                old_start = int(match.group(1))
                old_count = int(match.group(2)) if match.group(2) else 1
                new_start = int(match.group(3))
                new_count = int(match.group(4)) if match.group(4) else 1
                i += 1
                hunk_lines = []
                while i < len(lines) and not lines[i].startswith('@@'):
                    if lines[i]:
                        hunk_lines.append(lines[i])
                    i += 1
                hunks.append((old_start, old_count, new_count, hunk_lines))
            else:
                i += 1
        return hunks


class GenerateDiffTool(BaseTool):
    name = "generate_diff"
    description = "Generate unified diff between original and modified content"
    parameters = {
        "original": {"type": "string", "description": "Original file content"},
        "modified": {"type": "string", "description": "Modified file content"},
        "filename": {"type": "string", "description": "Filename for diff header", "default": "file"}
    }

    def execute(self, original: str, modified: str, filename: str = "file") -> ToolResult:
        try:
            original_lines = original.splitlines(keepends=True)
            modified_lines = modified.splitlines(keepends=True)
            # Ensure both end with newline for clean diff
            if original_lines and not original_lines[-1].endswith('\n'):
                original_lines[-1] += '\n'
            if modified_lines and not modified_lines[-1].endswith('\n'):
                modified_lines[-1] += '\n'

            diff = list(difflib.unified_diff(
                original_lines,
                modified_lines,
                fromfile=f"a/{filename}",
                tofile=f"b/{filename}",
                lineterm='\n'
            ))

            diff_text = ''.join(diff)
            return ToolResult(True, diff_text, metadata={"hunks": diff_text.count('@@')})
        except Exception as e:
            return ToolResult(False, "", str(e))
