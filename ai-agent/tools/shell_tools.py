"""Shell execution tools with smart approval levels"""
import re
import subprocess
import shlex
from pathlib import Path
from typing import Dict, Any
from .base import BaseTool, ToolResult


# Command safety classification
SAFE_COMMANDS = [
    r"^ls\b", r"^cat\b", r"^echo\b", r"^grep\b", r"^find\b",
    r"^python\s+-c\b", r"^python\s+--version\b", r"^pip\s+list\b",
    r"^npm\s+list\b", r"^git\s+status\b", r"^git\s+log\b",
    r"^git\s+diff\b", r"^git\s+show\b", r"^head\b", r"^tail\b",
    r"^wc\b", r"^pwd\b", r"^which\b", r"^mkdir\s+-p\b",
]

DANGEROUS_PATTERNS = [
    r"rm\s+-rf", r"rm\s+.*/\s*", r"sudo\b", r"curl.*\|\s*sh",
    r"curl.*\|\s*bash", r">?\s*/dev/(null|zero|random)",
    r"mkfs\.", r"dd\s+if=", r"format\b", r"shutdown\b",
    r"reboot\b", r"halt\b", r"init\s+0", r"killall\b",
    r"chmod\s+777", r"chown\s+-R", r"mv\s+/\s+",
    r"wget.*\|\s*sh", r"eval\s*\(", r"exec\s*\(",
    r"\brm\b.*\*/", r"\brm\b.*\*\.",
]


def classify_command(command: str) -> tuple:
    """Returns (level, reason) where level: 1=safe, 2=confirm, 3=block"""
    cmd_lower = command.strip().lower()

    # Check blocked first
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, cmd_lower):
            return 3, f"BLOCKED: matches dangerous pattern '{pattern}'"

    # Check safe
    for pattern in SAFE_COMMANDS:
        if re.search(pattern, cmd_lower):
            return 1, "SAFE: matches safe pattern"

    # Everything else needs confirmation
    return 2, "REQUIRES CONFIRMATION: unknown command"


class ShellTool(BaseTool):
    name = "execute_command"
    description = "Execute shell command. Dangerous commands are blocked. Safe commands auto-approve. Others require confirmation."
    parameters = {
        "command": {"type": "string", "description": "Command to execute"},
        "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 30},
        "force": {"type": "boolean", "description": "Skip confirmation (autonomous mode only)", "default": False}
    }

    def execute(self, command: str, timeout: int = 30, force: bool = False) -> ToolResult:
        level, reason = classify_command(command)

        if level == 3:
            return ToolResult(False, "", f"COMMAND BLOCKED: {reason}\nCommand: {command}")

        if level == 2 and not force:
            print(f"\n⚠️  SHELL COMMAND REQUIRES APPROVAL")
            print(f"   Command: {command}")
            print(f"   Reason: {reason}")
            confirm = input("   Approve? [y/N]: ").strip().lower()
            if confirm not in ('y', 'yes'):
                return ToolResult(False, "", "User declined command execution")

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=Path.cwd()
            )

            output = result.stdout
            if result.stderr:
                output += f"\n[STDERR]:\n{result.stderr}"

            return ToolResult(
                result.returncode == 0,
                output,
                metadata={"returncode": result.returncode, "safety_level": level}
            )
        except subprocess.TimeoutExpired:
            return ToolResult(False, "", f"Command timed out after {timeout}s")
        except Exception as e:
            return ToolResult(False, "", str(e))


class PythonTool(BaseTool):
    name = "execute_python"
    description = "Execute Python code and return result. Safe to auto-run."
    parameters = {
        "code": {"type": "string", "description": "Python code to execute"}
    }

    def execute(self, code: str) -> ToolResult:
        try:
            import io
            import sys

            # Security: block dangerous builtins
            blocked = ['__import__', 'open', 'eval', 'exec', 'compile']
            for b in blocked:
                if re.search(rf'\b{b}\s*\(', code):
                    return ToolResult(False, "", f"Blocked builtin: {b}() is not allowed")

            old_stdout = sys.stdout
            sys.stdout = buffer = io.StringIO()

            exec_globals = {"__name__": "__agent__", "__builtins__": __builtins__}
            exec(code, exec_globals)

            sys.stdout = old_stdout
            output = buffer.getvalue()

            return ToolResult(True, output or "Code executed successfully")
        except Exception as e:
            import traceback
            return ToolResult(False, "", f"{str(e)}\n{traceback.format_exc()}")
