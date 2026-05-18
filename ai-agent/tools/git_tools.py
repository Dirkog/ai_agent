"""Git integration — checkpoints and rollback"""
import subprocess
from pathlib import Path
from typing import Optional
from .base import BaseTool, ToolResult


def _git_available() -> bool:
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
        return True
    except Exception:
        return False


class GitCheckpointTool(BaseTool):
    name = "git_checkpoint"
    description = "Create a git checkpoint (commit) before modifications. Returns commit hash."
    parameters = {
        "message": {"type": "string", "description": "Commit message", "default": "agent checkpoint"},
        "allow_empty": {"type": "boolean", "description": "Allow empty commit", "default": True}
    }

    def execute(self, message: str = "agent checkpoint", allow_empty: bool = True) -> ToolResult:
        if not _git_available():
            return ToolResult(False, "", "Git not available")
        try:
            cwd = Path.cwd()
            # Check if inside git repo
            result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                cwd=cwd, capture_output=True, text=True
            )
            if result.returncode != 0:
                return ToolResult(False, "", "Not a git repository")

            # Stage all changes
            subprocess.run(["git", "add", "-A"], cwd=cwd, check=True)

            # Commit
            cmd = ["git", "commit", "-m", message]
            if allow_empty:
                cmd.append("--allow-empty")
            result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)

            if result.returncode != 0 and "nothing to commit" not in result.stderr:
                return ToolResult(False, "", f"Git commit failed: {result.stderr}")

            # Get commit hash
            hash_res = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=cwd, capture_output=True, text=True, check=True
            )
            commit_hash = hash_res.stdout.strip()

            return ToolResult(True, f"Checkpoint created: {commit_hash}", metadata={"commit": commit_hash})
        except Exception as e:
            return ToolResult(False, "", str(e))


class GitRollbackTool(BaseTool):
    name = "git_rollback"
    description = "Rollback to previous checkpoint (HEAD~1). DESTRUCTIVE."
    parameters = {
        "steps": {"type": "integer", "description": "How many commits to go back", "default": 1},
        "hard": {"type": "boolean", "description": "Hard reset (discard changes)", "default": True}
    }

    def execute(self, steps: int = 1, hard: bool = True) -> ToolResult:
        if not _git_available():
            return ToolResult(False, "", "Git not available")
        try:
            cwd = Path.cwd()
            cmd = ["git", "reset", "--hard" if hard else "--soft", f"HEAD~{steps}"]
            result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
            if result.returncode != 0:
                return ToolResult(False, "", f"Rollback failed: {result.stderr}")
            return ToolResult(True, f"Rolled back {steps} commit(s)")
        except Exception as e:
            return ToolResult(False, "", str(e))


class GitStatusTool(BaseTool):
    name = "git_status"
    description = "Show git status — modified, staged, untracked files"
    parameters = {}

    def execute(self) -> ToolResult:
        if not _git_available():
            return ToolResult(False, "", "Git not available")
        try:
            cwd = Path.cwd()
            result = subprocess.run(
                ["git", "status", "-sb"],
                cwd=cwd, capture_output=True, text=True, check=True
            )
            return ToolResult(True, result.stdout)
        except Exception as e:
            return ToolResult(False, "", str(e))


class GitLogTool(BaseTool):
    name = "git_log"
    description = "Show recent commit history"
    parameters = {
        "n": {"type": "integer", "description": "Number of commits", "default": 10}
    }

    def execute(self, n: int = 10) -> ToolResult:
        if not _git_available():
            return ToolResult(False, "", "Git not available")
        try:
            cwd = Path.cwd()
            result = subprocess.run(
                ["git", "log", "--oneline", "-n", str(n)],
                cwd=cwd, capture_output=True, text=True, check=True
            )
            return ToolResult(True, result.stdout)
        except Exception as e:
            return ToolResult(False, "", str(e))
