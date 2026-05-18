"""Core AI Agent — Full Cursor-like IDE with 30+ tools
Complete workspace: file tree, tabs, breadcrumbs, minimap, terminal, AI chat panel.
"""
import json
import re
import time
from typing import List, Dict, Any, Optional, Generator
from dataclasses import dataclass, field
from provider_manager import ProviderManager
from tools import (
    # File operations (6)
    ReadFileTool, WriteFileTool, ListFilesTool, SearchFilesTool,
    ApplyDiffTool, GenerateDiffTool,
    # Shell & Python (2)
    ShellTool, PythonTool,
    # Git (4)
    GitCheckpointTool, GitRollbackTool, GitStatusTool, GitLogTool,
    # Advanced (8)
    DatabaseTool, BrowserTool, APITestTool, ImageAnalysisTool,
    CodeAnalysisTool, RefactorTool, DockerTool, TestRunnerTool,
    # IDE (6)
    BreadcrumbsTool, OutlineTool, FindReferencesTool,
    RenameSymbolTool, MinimapTool, QuickFixTool,
    # AI-powered (4)
    ExplainCodeTool, GenerateTestsTool, GenerateDocsTool, SmartImportTool,
    ToolResult
)
from modes import InteractiveMode, AutonomousMode
from validator import ProjectValidator
from context_manager import ContextWindow
from metrics.cost_tracker import CostTracker
from memory.vector_store import ProjectIndex
from memory.persistent.session_memory import PersistentMemory
from swarm.orchestrator import Orchestrator
from composer.batch_editor import BatchEditor
from lsp.client import LSPClient
from workspace.editor import WorkspaceEditor
from security.guardian import SecurityGuardian
from config import CONFIG


@dataclass
class AgentState:
    iteration: int = 0
    task_completed: bool = False
    context: Dict[str, Any] = field(default_factory=dict)
    last_checkpoint: Optional[str] = None


class Agent:
    def __init__(self, mode: str = "interactive"):
        self.provider_manager = ProviderManager()
        self.mode = mode
        self.interactive = InteractiveMode()
        self.autonomous = AutonomousMode()
        self.state = AgentState()
        self.context_window = ContextWindow()
        self.cost_tracker = CostTracker()
        self.vector_index: Optional[ProjectIndex] = None
        self.memory = PersistentMemory(CONFIG.working_directory)
        self.composer = BatchEditor(CONFIG.working_directory)
        self.workspace = WorkspaceEditor(CONFIG.working_directory)
        self.guardian = SecurityGuardian(mode)
        self.lsp: Optional[LSPClient] = None
        self.orchestrator: Optional[Orchestrator] = None

        # ALL 30 tools
        self.tools = {
            # 📁 FILE OPERATIONS (6)
            "read_file": ReadFileTool(),
            "write_file": WriteFileTool(),
            "list_files": ListFilesTool(),
            "search_files": SearchFilesTool(),
            "apply_diff": ApplyDiffTool(),
            "generate_diff": GenerateDiffTool(),

            # 💻 EXECUTION (2)
            "execute_command": ShellTool(),
            "execute_python": PythonTool(),

            # 🔀 GIT (4)
            "git_checkpoint": GitCheckpointTool(),
            "git_rollback": GitRollbackTool(),
            "git_status": GitStatusTool(),
            "git_log": GitLogTool(),

            # 🚀 ADVANCED (8)
            "query_database": DatabaseTool(),
            "browse_web": BrowserTool(),
            "test_api": APITestTool(),
            "analyze_image": ImageAnalysisTool(),
            "analyze_code": CodeAnalysisTool(),
            "refactor_code": RefactorTool(),
            "docker_command": DockerTool(),
            "run_tests": TestRunnerTool(),

            # 🏗️ IDE FEATURES (6)
            "get_breadcrumbs": BreadcrumbsTool(),
            "get_outline": OutlineTool(),
            "find_references": FindReferencesTool(),
            "rename_symbol": RenameSymbolTool(),
            "get_minimap": MinimapTool(),
            "quick_fix": QuickFixTool(),

            # 🤖 AI-POWERED (4)
            "explain_code": ExplainCodeTool(),
            "generate_tests": GenerateTestsTool(),
            "generate_docs": GenerateDocsTool(),
            "smart_import": SmartImportTool(),
        }

        self.messages: List[Dict[str, str]] = []
        self.system_prompt = self._build_system_prompt()

        # Init subsystems
        try:
            self.vector_index = ProjectIndex(CONFIG.working_directory)
            self.vector_index.index_files("*.py")
        except Exception as e:
            print(f"[VectorStore] {e}")

        try:
            self.lsp = LSPClient(project_path=CONFIG.working_directory)
            if self.lsp.start():
                print("[LSP] Connected")
        except Exception as e:
            print(f"[LSP] {e}")

    def _build_system_prompt(self) -> str:
        cursorrules = self.memory.load_cursorrules()
        learned = self.memory.get_project_summary()
        workspace_summary = self.workspace.get_workspace_summary()

        base = f"""You are an AI coding agent with a full Cursor-like IDE.

WORKSPACE:
{workspace_summary}

📁 FILE OPERATIONS (6):
- read_file(path, offset, limit) — Read with pagination
- write_file(path, content, append) — Write/create
- list_files(path, pattern, recursive) — Directory listing
- search_files(query, path, file_pattern) — Grep search
- apply_diff(path, diff) — Apply unified diff (PREFERRED)
- generate_diff(original, modified) — Generate diff

💻 EXECUTION (2):
- execute_command(command, timeout) — Shell (SAFE auto-approved, DANGEROUS blocked)
- execute_python(code) — Run Python code

🔀 GIT (4):
- git_checkpoint(message) — Commit before changes
- git_rollback(steps, hard) — Revert changes
- git_status() — Repository status
- git_log(n) — Commit history

🚀 ADVANCED (8):
- query_database(connection_string, query) — SQL queries
- browse_web(url, selector) — Fetch web pages
- test_api(method, url, headers, body) — API testing
- analyze_image(image_path, prompt) — Vision analysis
- analyze_code(path, analysis_type) — Complexity/security/types scan
- refactor_code(path, operation, target, new_name) — Automated refactoring
- docker_command(command) — Docker (BLOCKED: rm, prune)
- run_tests(framework, path, coverage) — Test suites

🏗️ IDE FEATURES (6):
- get_breadcrumbs(path, line) — Navigation hierarchy at cursor
- get_outline(path, include_docstrings) — File outline (classes, functions)
- find_references(symbol, path, file_pattern) — Find all references
- rename_symbol(old_name, new_name, path) — Rename across project
- get_minimap(path, width) — Visual file overview
- quick_fix(error_message, path, line) — Suggest fixes for errors

🤖 AI-POWERED (4):
- explain_code(path, style, target_audience) — Explain in plain English
- generate_tests(path, framework, coverage_target) — Auto-generate tests
- generate_docs(path, format, include_examples) — Generate documentation
- smart_import(path, action) — Organize/fix imports

@-MENTIONS:
- @file:path.py — Include file content
- @dir:path/ — Include directory listing
- @symbol:Name — Reference symbol definition

COMPOSER: Use ```file path blocks for batch multi-file editing.

SECURITY: Guardian blocks dangerous ops. HIGH/CRITICAL tools require your approval.

End with [TASK_COMPLETE].
"""

        if cursorrules:
            base += f"\n[.cursorrules]:\n{cursorrules}\n"
        base += learned
        return base

    def _resolve_mentions(self, text: str) -> str:
        for match in re.finditer(r'@file:([\w./-]+)', text):
            path = match.group(1)
            result = self.tools["read_file"].execute(path=path)
            if result.success:
                self.workspace.open_file(path)
                replacement = f"\n[FILE: {path}]\n```\n{result.content[:3000]}\n```\n"
                text = text.replace(match.group(0), replacement)

        for match in re.finditer(r'@dir:([\w./-]+)', text):
            path = match.group(1)
            result = self.tools["list_files"].execute(path=path)
            if result.success:
                text = text.replace(match.group(0), f"\n[DIR: {path}]\n{result.content[:1000]}\n")

        for match in re.finditer(r'@symbol:([\w.]+)', text):
            symbol = match.group(1)
            result = self.tools["search_files"].execute(query=f"(class|def) {symbol.split('.')[-1]}")
            if result.success:
                text = text.replace(match.group(0), f"\n[SYMBOL: {symbol}]\n{result.content[:2000]}\n")

        return text

    def _build_tool_schemas(self) -> List[Dict]:
        return [tool.get_schema() for tool in self.tools.values()]

    def _parse_tool_calls(self, response: str) -> List[Dict[str, Any]]:
        tool_calls = []
        pattern = r'```tool\s*\n(\w+)\s*\n(.*?)\s*```'
        for tool_name, params_str in re.findall(pattern, response, re.DOTALL):
            try:
                params = json.loads(params_str.strip())
                tool_calls.append({"tool": tool_name, "params": params})
            except:
                try:
                    params = json.loads(params_str.strip().replace("'", '"'))
                    tool_calls.append({"tool": tool_name, "params": params})
                except:
                    continue
        return tool_calls

    def _execute_tool(self, tool_name: str, params: Dict, context: str = "") -> str:
        if tool_name not in self.tools:
            return f"[ERROR] Unknown tool: {tool_name}"

        allowed, reason = self.guardian.check_permission(tool_name, params, context)
        if not allowed:
            if "REQUIRES APPROVAL" in reason:
                approved = self.guardian.request_approval(tool_name, params, context)
                if not approved:
                    return "[DENIED] User declined operation"
            else:
                return f"[BLOCKED] {reason}"

        tool = self.tools[tool_name]
        print(f"[Executing] {tool_name}({json.dumps(params, ensure_ascii=False)})")

        result = tool.execute(**params)

        icon = "✅" if result.success else "❌"
        status = "SUCCESS" if result.success else "FAILED"

        output = f"[{status}] {tool_name}\n"
        if result.content:
            output += f"Output:\n{result.content[:2000]}\n"
        if result.error:
            output += f"Error: {result.error}\n"

        print(f"{icon} {tool_name}: {status}")

        if tool_name in ("write_file", "apply_diff") and "path" in params:
            self.workspace.open_file(params["path"])
            if tool_name == "write_file":
                self.workspace.edit_file(params["path"], params.get("content", ""))
            self.workspace.save_file(params["path"])

        return output

    def _auto_fix_file(self, path: str, error_msg: str) -> bool:
        print(f"\n🔧 Auto-fix: {path}: {error_msg[:100]}")
        fix_prompt = f"""Fix syntax error in {path}:
{error_msg}
Use apply_diff or write_file. Only fix the error."""

        fix_messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": fix_prompt}
        ]

        try:
            response_parts = []
            for chunk in self.provider_manager.chat(fix_messages, tools=self._build_tool_schemas()):
                response_parts.append(chunk)

            for tc in self._parse_tool_calls("".join(response_parts)):
                self._execute_tool(tc["tool"], tc["params"])

            import ast
            with open(path, 'r') as f:
                ast.parse(f.read())
            print(f"✅ Fixed {path}")
            return True
        except Exception as e:
            print(f"❌ Fix failed: {e}")
            return False

    def _run_validation_with_autofix(self):
        print("\n🔍 Validation + auto-fix...")
        validator = ProjectValidator(CONFIG.working_directory)
        validator.validate_all()

        syntax = next((r for r in validator.results if r.category == "Python Syntax"), None)
        if syntax and not syntax.passed:
            for detail in syntax.details:
                match = re.match(r"(.+?):(\d+):\s*(.+)", detail)
                if match:
                    self._auto_fix_file(match.group(1), match.group(3))

        print(validator.get_summary())
        return not validator.has_critical_errors()

    def run(self, task: str) -> Generator[str, None, None]:
        task = self._resolve_mentions(task)

        self.messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Task: {task}\n\nStart working. Use tools as needed."}
        ]

        print(f"\n🚀 Task: {task[:100]}...")
        print(f"Mode: {self.mode.upper()} | Tools: {len(self.tools)}")
        print(f"Workspace: {len(self.workspace.state.tabs)} tabs")
        print("=" * 60)

        cp = self.tools["git_checkpoint"].execute(message="agent start")
        if cp.success:
            self.state.last_checkpoint = cp.metadata.get("commit") if cp.metadata else None

        while self.state.iteration < CONFIG.max_iterations:
            self.state.iteration += 1
            print(f"\n--- Iteration {self.state.iteration} ---")

            self.messages = self.context_window.trim(self.messages, keep_recent=12)

            if self.state.iteration == 1 and self.vector_index:
                ctx = self.vector_index.get_context_for_query(task, max_chars=2000)
                if ctx:
                    self.messages.insert(1, {
                        "role": "user", "content": f"[PROJECT CONTEXT]\n{ctx}\n[END CONTEXT]"
                    })

            active_ctx = self.workspace.get_active_context(max_lines=30)
            if active_ctx:
                self.messages.insert(1, {"role": "user", "content": active_ctx})

            start = time.time()
            response_parts = []
            for chunk in self.provider_manager.chat(self.messages, tools=self._build_tool_schemas()):
                response_parts.append(chunk)
                yield chunk

            latency = int((time.time() - start) * 1000)
            response = "".join(response_parts)

            self.cost_tracker.log_request(
                provider="unknown", model="unknown",
                input_tokens=self.context_window.estimate_tokens(self.messages),
                output_tokens=len(response) // 4, latency_ms=latency
            )

            # Check Composer
            from composer.batch_editor import ComposerPlan
            composer_plan = self.composer.generate_plan_from_llm(response)
            if composer_plan and composer_plan.total_files > 0:
                print(f"\n📝 Composer: {composer_plan.total_files} files")
                self.state.current_plan = composer_plan

                if self.mode == "interactive":
                    print(self.composer.preview_diff())
                    confirm = input("\nApply? [Y/n/review]: ").strip().lower()
                    if confirm == "review":
                        s, f = self.composer.apply_all(auto_approve=False)
                    elif confirm and confirm not in ('y', 'yes'):
                        print("Cancelled")
                        s, f = 0, 0
                    else:
                        s, f = self.composer.apply_all(auto_approve=True)
                else:
                    s, f = self.composer.apply_all(auto_approve=True)

                self.messages.append({"role": "assistant", "content": response})
                self.messages.append({
                    "role": "user",
                    "content": f"Composer: {s} applied, {f} failed."
                })
                continue

            # Interactive questions
            if self.mode == "interactive":
                q = self.interactive.should_ask_question(response)
                if q:
                    answer = self.interactive.ask_user(q)
                    self.messages.append({"role": "assistant", "content": response})
                    self.messages.append({"role": "user", "content": self.interactive.format_answer_for_agent(q, answer)})
                    continue

            if "[TASK_COMPLETE]" in response:
                self.state.task_completed = True
                break

            tool_calls = self._parse_tool_calls(response)

            if tool_calls:
                self.messages.append({"role": "assistant", "content": response})

                results = []
                for tc in tool_calls:
                    results.append(self._execute_tool(tc["tool"], tc["params"], context=task))

                self.messages.append({
                    "role": "user",
                    "content": f"Tool results:\n{'\n\n'.join(results)}\n\nContinue."
                })
            else:
                self.messages.append({"role": "assistant", "content": response})

                if self.mode == "interactive":
                    ui = input("\nContinue? [Enter=yes/stop/feedback]: ").strip()
                    if ui.lower() == 'stop':
                        break
                    if ui:
                        self.messages.append({"role": "user", "content": ui})
                        continue
                else:
                    self.messages.append({"role": "user", "content": "Continue working."})

        self._run_validation_with_autofix()

        files = [c.path for c in (self.state.current_plan.changes if hasattr(self.state, 'current_plan') and self.state.current_plan else [])]
        self.memory.record_session(task, self.state.task_completed, self.state.iteration, files)

        print(self.cost_tracker.get_summary())
        print(f"\n🏁 Done: {self.state.iteration} iterations")

    def run_swarm(self, task: str) -> Generator[str, None, None]:
        self.orchestrator = Orchestrator(self.provider_manager)
        for chunk in self.orchestrator.run_workflow(task):
            yield chunk

    def chat(self, message: str) -> Generator[str, None, None]:
        message = self._resolve_mentions(message)
        self.messages.append({"role": "user", "content": message})
        for chunk in self.provider_manager.chat(self.messages):
            yield chunk

    def inline_complete(self, file_path: str, cursor_line: int, cursor_col: int) -> Generator[str, None, None]:
        result = self.tools["read_file"].execute(path=file_path)
        if not result.success:
            yield "[ERROR] Cannot read file"
            return

        lines = result.content.splitlines()
        before = "\n".join(lines[max(0, cursor_line-10):cursor_line])
        current = lines[cursor_line] if cursor_line < len(lines) else ""
        after = "\n".join(lines[cursor_line+1:cursor_line+5])

        prompt = f"Complete code at cursor:\n```\n{before}\n{current[:cursor_col]}[CURSOR]{current[cursor_col:]}\n{after}\n```\nProvide ONLY completion text."

        msgs = [
            {"role": "system", "content": "Code completion engine. Output only completion text."},
            {"role": "user", "content": prompt}
        ]

        for chunk in self.provider_manager.chat(msgs):
            yield chunk
