"""Autonomous mode - makes decisions without user input"""
import json
from typing import Dict, Any, List
from dataclasses import dataclass

@dataclass
class Decision:
    action: str
    reasoning: str
    confidence: float
    fallback: str = ""

class AutonomousMode:
    def __init__(self):
        self.decision_log: List[Decision] = []
        self.auto_confirm_rules = {
            "file_read": True,
            "file_write": True,
            "file_edit": True,
            "shell_command": False,  # Require confirmation for destructive commands
            "python_execute": True,
        }

    def should_auto_confirm(self, tool_name: str, parameters: Dict[str, Any]) -> bool:
        """Determine if action can be auto-confirmed"""
        # Check for destructive operations
        if tool_name == "execute_command":
            command = parameters.get("command", "").lower()
            dangerous = ["rm -rf", "dd if", "mkfs", "format", ">/dev/null", "shutdown", "reboot"]
            if any(d in command for d in dangerous):
                return False

            # Auto-confirm safe commands
            safe_prefixes = ["ls", "cat", "echo", "grep", "find", "python", "pip", "npm", "git status", "git log"]
            if any(command.startswith(p) for p in safe_prefixes):
                return True
            return False

        return self.auto_confirm_rules.get(tool_name, False)

    def make_decision(self, context: str, available_actions: List[str]) -> Decision:
        """Simulate decision making (in real implementation, this could use LLM)"""
        # Simple heuristic-based decisions
        if "error" in context.lower() and "fix" in context.lower():
            return Decision(
                action="attempt_fix",
                reasoning="Error detected in previous action, attempting automatic fix",
                confidence=0.7
            )

        if "test" in context.lower():
            return Decision(
                action="run_tests",
                reasoning="Testing phase detected",
                confidence=0.9
            )

        return Decision(
            action=available_actions[0] if available_actions else "continue",
            reasoning="Default continuation",
            confidence=0.5
        )

    def log_decision(self, decision: Decision):
        self.decision_log.append(decision)

    def get_summary(self) -> str:
        """Get summary of all autonomous decisions"""
        summary = "\n=== AUTONOMOUS MODE DECISION LOG ===\n"
        for i, d in enumerate(self.decision_log, 1):
            summary += f"{i}. {d.action} (confidence: {d.confidence:.2f})\n"
            summary += f"   Reason: {d.reasoning}\n"
        return summary
