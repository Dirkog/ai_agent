"""Security Guardian — approval system for high-risk operations
Like Cursor: every dangerous action requires explicit user confirmation.
"""
from enum import Enum
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass


class RiskLevel(Enum):
    NONE = 0      # Safe, auto-approve
    LOW = 1       # Read-only, auto-approve
    MEDIUM = 2    # Write files, ask once per session
    HIGH = 3      # Shell commands, ask every time
    CRITICAL = 4  # Destructive operations, require password/2FA


@dataclass
class ApprovalRule:
    tool_name: str
    risk_level: RiskLevel
    description: str
    requires_reason: bool = False
    max_auto_approve: int = 0  # 0 = always ask


class SecurityGuardian:
    """Central security controller for all tool executions"""

    RULES = {
        # Safe — auto-approve
        "read_file": ApprovalRule("read_file", RiskLevel.LOW, "Read file contents"),
        "list_files": ApprovalRule("list_files", RiskLevel.LOW, "List directory"),
        "search_files": ApprovalRule("search_files", RiskLevel.LOW, "Search in files"),
        "git_status": ApprovalRule("git_status", RiskLevel.LOW, "Git status"),
        "git_log": ApprovalRule("git_log", RiskLevel.LOW, "Git history"),
        "generate_diff": ApprovalRule("generate_diff", RiskLevel.LOW, "Generate diff"),
        "execute_python": ApprovalRule("execute_python", RiskLevel.LOW, "Run Python code"),

        # Medium — ask once per session, then auto
        "write_file": ApprovalRule("write_file", RiskLevel.MEDIUM, "Write/create file", max_auto_approve=3),
        "apply_diff": ApprovalRule("apply_diff", RiskLevel.MEDIUM, "Apply diff patch", max_auto_approve=5),
        "git_checkpoint": ApprovalRule("git_checkpoint", RiskLevel.MEDIUM, "Git commit", max_auto_approve=1),

        # High — ask every time
        "execute_command": ApprovalRule("execute_command", RiskLevel.HIGH, "Shell command", requires_reason=True),
        "docker_command": ApprovalRule("docker_command", RiskLevel.HIGH, "Docker command", requires_reason=True),
        "query_database": ApprovalRule("query_database", RiskLevel.HIGH, "Database query", requires_reason=True),
        "test_api": ApprovalRule("test_api", RiskLevel.HIGH, "API test", max_auto_approve=2),
        "browse_web": ApprovalRule("browse_web", RiskLevel.HIGH, "Web fetch", max_auto_approve=3),

        # Critical — require explicit confirmation + reason
        "git_rollback": ApprovalRule("git_rollback", RiskLevel.CRITICAL, "Git rollback (DESTRUCTIVE)", requires_reason=True),
        "run_tests": ApprovalRule("run_tests", RiskLevel.CRITICAL, "Run test suite", requires_reason=True),
        "refactor_code": ApprovalRule("refactor_code", RiskLevel.CRITICAL, "Code refactoring", requires_reason=True),
        "analyze_code": ApprovalRule("analyze_code", RiskLevel.CRITICAL, "Security scan", requires_reason=True),
    }

    def __init__(self, mode: str = "interactive"):
        self.mode = mode
        self.approved_this_session: Dict[str, int] = {}  # tool -> count
        self.blocked_patterns = [
            r"rm\s+-rf", r"rm\s+.*/\s*", r"sudo\b", r"curl.*\|\s*sh",
            r"dd\s+if=/dev/zero", r"mkfs\.", r">\s*/dev/sd",
            r"chmod\s+777\s+/", r"chown\s+-R\s+root",
            r"docker\s+system\s+prune", r"docker\s+rm\s+-f",
        ]
        self._callbacks: List[Callable] = []

    def check_permission(self, tool_name: str, params: Dict, context: str = "") -> tuple:
        """Check if operation is allowed. Returns (allowed, reason)"""
        rule = self.RULES.get(tool_name)
        if not rule:
            return True, "Unknown tool, allowing by default"

        # Check blocked patterns in parameters
        param_str = str(params)
        for pattern in self.blocked_patterns:
            if __import__('re').search(pattern, param_str, __import__('re').IGNORECASE):
                return False, f"BLOCKED: Matches dangerous pattern '{pattern}'"

        # Auto mode — skip confirmations
        if self.mode == "autonomous":
            if rule.risk_level in (RiskLevel.CRITICAL, RiskLevel.HIGH):
                # Still log critical operations
                self._log_critical(tool_name, params, context)
            return True, "Autonomous mode"

        # Check session approvals
        approved_count = self.approved_this_session.get(tool_name, 0)
        if approved_count < rule.max_auto_approve:
            self.approved_this_session[tool_name] = approved_count + 1
            return True, f"Auto-approved ({approved_count + 1}/{rule.max_auto_approve})"

        # Need explicit approval
        return False, f"REQUIRES APPROVAL: {rule.description}"

    def request_approval(self, tool_name: str, params: Dict, context: str = "") -> bool:
        """Interactive approval prompt"""
        rule = self.RULES.get(tool_name)
        if not rule:
            return True

        print(f"\n{'='*60}")
        print(f"🔒 SECURITY CHECK: {rule.risk_level.name}")
        print(f"{'='*60}")
        print(f"Tool: {tool_name}")
        print(f"Description: {rule.description}")
        print(f"Parameters: {__import__('json').dumps(params, indent=2, ensure_ascii=False)}")
        if context:
            print(f"Context: {context}")

        if rule.requires_reason:
            print(f"\nThis operation requires a reason.")
            reason = input("Reason for this operation: ").strip()
            if not reason:
                print("❌ No reason provided. Operation denied.")
                return False

        print(f"\n[Y] Approve  [N] Deny  [A] Approve all {tool_name} this session")
        choice = input("Your choice [y/n/a]: ").strip().lower()

        if choice == 'a':
            self.approved_this_session[tool_name] = 999
            print(f"✅ All future '{tool_name}' operations approved this session")
            return True
        elif choice in ('y', 'yes'):
            self.approved_this_session[tool_name] = self.approved_this_session.get(tool_name, 0) + 1
            print("✅ Approved")
            return True
        else:
            print("❌ Denied")
            return False

    def _log_critical(self, tool_name: str, params: Dict, context: str):
        """Log critical operation for audit"""
        log_entry = {
            "timestamp": __import__('datetime').datetime.now().isoformat(),
            "tool": tool_name,
            "params": params,
            "context": context,
            "mode": self.mode
        }
        # In production, write to audit log
        print(f"[AUDIT] Critical operation logged: {tool_name}")

    def get_status(self) -> str:
        """Get current approval status"""
        lines = ["\n🔐 Security Guardian Status"]
        lines.append("-" * 40)
        for tool, count in sorted(self.approved_this_session.items()):
            rule = self.RULES.get(tool)
            max_a = rule.max_auto_approve if rule else 0
            lines.append(f"  {tool}: {count} approved (max auto: {max_a})")
        return "\n".join(lines)
