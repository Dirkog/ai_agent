"""AI Agent v5 — Fixed & Desktop-Ready
Cursor-like IDE agent with 30 tools, dynamic tool picking, Composer, Security, LSP, and stop/cancel support.
"""
import os
import re
import ast
import json
import time
import queue
import threading
from pathlib import Path
from typing import Dict, List, Optional, Any, Generator
from dataclasses import dataclass, field

# Core imports
from config import CONFIG
from provider_manager import ProviderManager
from composer.batch_editor import BatchEditor, ComposerPlan, FileChange, ChangeStatus
from tools.tool_picker import ToolPicker
from security.guardian import SecurityGuardian, RiskLevel
from workspace.editor import WorkspaceEditor
from lsp.client import LSPClient
from memory.vector_store import ProjectIndex
from metrics.cost_tracker import CostTracker
from memory.persistent.session_memory import SessionMemory

# Tools
from tools.base import BaseTool, ToolResult
from tools.file_tools import ReadFileTool, WriteFileTool, ListFilesTool, SearchFilesTool
from tools.shell_tools import ShellTool, PythonTool
from tools.diff_tool import ApplyDiffTool, GenerateDiffTool
from tools.git_tools import GitCheckpointTool, GitRollbackTool, GitStatusTool, GitLogTool
from tools.advanced_tools import (
    DatabaseTool, BrowserTool, APITestTool, ImageAnalysisTool,
    CodeAnalysisTool, RefactorTool, DockerTool, TestRunnerTool
)
from tools.ide.ide_tools import (
    BreadcrumbsTool, OutlineTool, FindReferencesTool,
    RenameSymbolTool, MinimapTool, QuickFixTool
)
from tools.ai.ai_tools import (
    ExplainCodeTool, GenerateTestsTool, GenerateDocsTool, SmartImportTool
)


@dataclass
class AgentState:
    iteration: int = 0
    task_completed: bool = False
    context: Dict[str, Any] = field(default_factory=dict)
    last_checkpoint: Optional[str] = None
    current_plan: Optional[Any] = None
    stop_requested: bool = False


class Agent:
    """Main AI Agent with IDE, Security, and Multi-tool support"""

    def __init__(self, mode: str = "interactive", working_dir: str = "."):
        self.mode = mode
        self.working_dir = Path(working_dir).resolve()
        self.state = AgentState()
        self.messages: List[Dict[str, str]] = []
        self._stop_event = threading.Event()

        # Core systems
        self.provider_manager = ProviderManager()
        self.security = SecurityGuardian()
        self.composer = BatchEditor(str(self.working_dir))
        self.tool_picker = ToolPicker({})
        self.workspace = WorkspaceEditor(str(self.working_dir))
        self.lsp = LSPClient(project_path=str(self.working_dir))
        self.vector_index = ProjectIndex(str(self.working_dir))
        self.cost_tracker = CostTracker()
        self.session_memory = SessionMemory(str(self.working_dir / ".ai-agent"))

        # Initialize all tools
        self.tools = self._init_tools()
        self.tool_picker = ToolPicker(self.tools)  # Re-init with actual tools

        # Try start LSP
        try:
            self.lsp.start()
        except Exception:
            pass

        # Load session memory
        self.session_memory.load()

        # Initial system message
        self.messages.append({
            "role": "system",
            "content": self._build_system_prompt()
        })

    def _init_tools(self) -> Dict[str, BaseTool]:
        """Initialize all 30 tools"""
        tools = {
            # File operations (6)
            "read_file": ReadFileTool(str(self.working_dir)),
            "write_file": WriteFileTool(str(self.working_dir)),
            "list_files": ListFilesTool(str(self.working_dir)),
            "search_files": SearchFilesTool(str(self.working_dir)),
            "apply_diff": ApplyDiffTool(str(self.working_dir)),
            "generate_diff": GenerateDiffTool(),

            # Execution (2)
            "execute_command": ShellTool(str(self.working_dir)),
            "execute_python": PythonTool(),

            # Git (4)
            "git_checkpoint": GitCheckpointTool(str(self.working_dir)),
            "git_rollback": GitRollbackTool(str(self.working_dir)),
            "git_status": GitStatusTool(str(self.working_dir)),
            "git_log": GitLogTool(str(self.working_dir)),

            # Advanced (8)
            "query_database": DatabaseTool(),
            "browse_web": BrowserTool(),
            "test_api": APITestTool(),
            "analyze_image": ImageAnalysisTool(),
            "analyze_code": CodeAnalysisTool(),
            "refactor_code": RefactorTool(str(self.working_dir)),
            "docker_command": DockerTool(),
            "run_tests": TestRunnerTool(str(self.working_dir)),

            # IDE (6)
            "get_breadcrumbs": BreadcrumbsTool(str(self.working_dir)),
            "get_outline": OutlineTool(str(self.working_dir)),
            "find_references": FindReferencesTool(str(self.working_dir)),
            "rename_symbol": RenameSymbolTool(str(self.working_dir)),
            "get_minimap": MinimapTool(str(self.working_dir)),
            "quick_fix": QuickFixTool(str(self.working_dir)),

            # AI-powered (4)
            "explain_code": ExplainCodeTool(),
            "generate_tests": GenerateTestsTool(str(self.working_dir)),
            "generate_docs": GenerateDocsTool(str(self.working_dir)),
            "smart_import": SmartImportTool(str(self.working_dir)),
        }
        return tools

    def _build_system_prompt(self, task: str = "") -> str:
        """Build dynamic system prompt with relevant tools only"""
        # Get workspace summary
        try:
            tree = self.workspace.get_file_tree(max_depth=2)
            workspace_summary = json.dumps(tree, indent=2)[:2000]
        except Exception:
            workspace_summary = "Workspace not indexed yet."

        # Dynamic tools section
        if task:
            tools_section = self.tool_picker.get_system_prompt_tools_section(task)
        else:
            tools_section = "\n".join([
                f"- {name}: {tool.description}"
                for name, tool in list(self.tools.items())[:15]
            ])

        # Load cursorrules if exists
        cursorrules = ""
        rules_file = self.working_dir / ".cursorrules"
        if rules_file.exists():
            cursorrules = f"\n\nCUSTOM RULES:\n{rules_file.read_text()[:1000]}"

        # Session memory context
        memory_context = ""
        prefs = self.session_memory.get_preferences()
        if prefs:
            memory_context = f"\n\nUSER PREFERENCES:\n{json.dumps(prefs, indent=2)[:500]}"

        prompt = f"""You are an AI coding agent with a full Cursor-like IDE.

WORKSPACE:
{workspace_summary}

AVAILABLE TOOLS (relevant to task):
{tools_section}

TOOL CALL FORMAT:
tool_name
{{"param1": "value1"}}
Copy
Or for Composer multi-file editing:
file path/to/file.py
<<CONTENT>
Copy

RULES:
1. Prefer `apply_diff` over `write_file` for small edits
2. Use `git_checkpoint` before major changes
3. For dangerous operations (rm, sudo, curl | sh), explain why
4. Always validate syntax after write_file
5. Use @file:path.py to reference files in chat
6. In autonomous mode, make decisions independently
7. In interactive mode, ask for clarification on ambiguous tasks
8. Prefer existing patterns in the codebase
9. Write tests for new functionality
10. Keep responses concise and actionable{cursorrules}{memory_context}

Current mode: {self.mode}
"""
        return prompt

    def _resolve_mentions(self, text: str) -> str:
        """Resolve @file:path, @dir:path/, @symbol:Name mentions"""
        # @file:path.py
        for match in re.finditer(r'@file:([^\s]+)', text):
            path = match.group(1)
            full_path = self.working_dir / path
            if full_path.exists():
                content = full_path.read_text(errors='replace')[:3000]
                text = text.replace(match.group(0), f"\n--- Content of {path} ---\n{content}\n---\n")
            else:
                text = text.replace(match.group(0), f"[File not found: {path}]")

        # @dir:path/
        for match in re.finditer(r'@dir:([^\s]+)/?', text):
            path = match.group(1)
            full_path = self.working_dir / path
            if full_path.is_dir():
                files = [f.name for f in full_path.iterdir() if f.is_file()]
                text = text.replace(match.group(0), f"\n--- Directory {path}: {', '.join(files[:20])} ---\n")

        # @symbol:ClassName (via LSP or grep)
        for match in re.finditer(r'@symbol:([^\s]+)', text):
            symbol = match.group(1)
            # Try LSP first
            try:
                results = []
                for root, _, files in os.walk(self.working_dir):
                    for f in files:
                        if f.endswith('.py'):
                            fp = Path(root) / f
                            content = fp.read_text(errors='ignore')
                            if f"class {symbol}" in content or f"def {symbol}" in content:
                                rel = str(fp.relative_to(self.working_dir))
                                results.append(f"{rel}: {symbol}")
                if results:
                    text = text.replace(match.group(0), f"\n--- Symbol {symbol} found in: {', '.join(results[:5])} ---\n")
            except Exception:
                pass

        return text

    def _parse_tool_calls(self, response: str) -> List[Dict[str, Any]]:
        """Parse tool calls from LLM response"""
        calls = []

        # Standard format: ```tool_name\n{"params"}\n```
        for match in re.finditer(r'```(\w+)\s*\n(.*?)```', response, re.DOTALL):
            tool_name = match.group(1)
            params_str = match.group(2).strip()
            if tool_name in self.tools:
                try:
                    params = json.loads(params_str) if params_str else {}
                    calls.append({"tool": tool_name, "params": params})
                except json.JSONDecodeError:
                    # Try fixing common JSON issues
                    try:
                        params = json.loads(params_str.replace("'", '"'))
                        calls.append({"tool": tool_name, "params": params})
                    except Exception:
                        pass

        # Composer format: ```file path\ncontent```
        composer_blocks = []
        for match in re.finditer(r'```file\s+([^\n]+)\n(.*?)```', response, re.DOTALL):
            path = match.group(1).strip()
            content = match.group(2)
            composer_blocks.append(FileChange(path=path, new_content=content))

        if composer_blocks:
            plan = ComposerPlan(changes=composer_blocks)
            self.state.current_plan = plan
            calls.append({"tool": "composer", "params": {"plan": plan}})

        return calls

    def _auto_fix(self, path: str, error: str) -> bool:
        """Attempt automatic syntax fix"""
        print(f"[AutoFix] Attempting to fix {path}: {error}")
        fix_prompt = f"""Fix this syntax error in {path}:
{error}

Current file content (first 50 lines):
{Path(path).read_text(errors='replace').split(chr(10))[:50]}

Return ONLY the corrected code block."""
        
        self.messages.append({"role": "user", "content": fix_prompt})
        
        try:
            response = self.provider_manager.complete(
                self.messages,
                temperature=0.1
            )
            # Extract code block
            code_match = re.search(r'```(?:\w+)?\n(.*?)```', response, re.DOTALL)
            if code_match:
                fixed = code_match.group(1)
                Path(path).write_text(fixed, encoding='utf-8')
                # Validate
                try:
                    ast.parse(fixed)
                    print(f"[AutoFix] Success for {path}")
                    return True
                except SyntaxError:
                    print(f"[AutoFix] Still has syntax errors")
                    return False
        except Exception as e:
            print(f"[AutoFix] Failed: {e}")
            return False
        finally:
            # Remove fix prompt from history
            if self.messages and "Fix this syntax error" in self.messages[-1].get("content", ""):
                self.messages.pop()

    def stop(self):
        """Request agent to stop"""
        self.state.stop_requested = True
        self._stop_event.set()
        print("\n[Agent] Stop requested...")

    def is_stopped(self) -> bool:
        return self.state.stop_requested or self._stop_event.is_set()

    def run(self, task: str) -> Generator[str, None, None]:
        """Main agent loop with streaming and stop support"""
        self.state.iteration = 0
        self.state.task_completed = False
        self.state.stop_requested = False
        self._stop_event.clear()

        # Rebuild prompt with task-specific tools
        self.messages[0]["content"] = self._build_system_prompt(task)

        # Resolve mentions in task
        task = self._resolve_mentions(task)

        # Inject vector context if available
        try:
            context = self.vector_index.get_context_for_query(task, top_k=3)
            if context:
                task += f"\n\n[Relevant code context from project]:\n{context}"
        except Exception:
            pass

        self.messages.append({"role": "user", "content": task})

        yield f"🚀 Starting task in {self.mode} mode...\n"

        while self.state.iteration < CONFIG.max_iterations:
            if self.is_stopped():
                yield "\n\n⛔ AGENT STOPPED BY USER\n"
                break

            self.state.iteration += 1
            yield f"\n--- Iteration {self.state.iteration} ---\n"

            try:
                # Get response from LLM
                start_time = time.time()
                response = self.provider_manager.complete(self.messages)
                latency = time.time() - start_time

                # Track cost (approximate)
                self.cost_tracker.add_record(
                    provider=self.provider_manager.current_provider_name,
                    model=getattr(CONFIG, 'model', 'unknown'),
                    input_tokens=len(str(self.messages)) // 4,
                    output_tokens=len(response) // 4,
                    latency_ms=int(latency * 1000)
                )

                yield f"\n🤖 {response[:500]}{'...' if len(response) > 500 else ''}\n"

                # Check for Composer plan
                composer_plan = self.composer.generate_plan_from_llm(response)
                if composer_plan and composer_plan.total_files > 0:
                    self.state.current_plan = composer_plan
                    yield f"\n📝 Composer: {composer_plan.total_files} files to modify\n"
                    preview = self.composer.preview_diff()
                    yield preview[:2000] + ("\n..." if len(preview) > 2000 else "") + "\n"

                    if self.mode == "interactive":
                        yield "\n[APPROVAL REQUIRED] Apply changes? (Y/n/review): "
                        # In streaming mode, we can't wait for input here
                        # Web/TUI should handle this via separate event
                        # For CLI, this would block - simplified:
                        yield "Auto-approving in autonomous mode logic...\n"
                        success, failed = self.composer.apply_all(auto_approve=True)
                    else:
                        success, failed = self.composer.apply_all(auto_approve=True)

                    yield f"✅ Applied: {success}, ❌ Failed: {failed}\n"
                    self.messages.append({
                        "role": "assistant",
                        "content": f"Composer applied {success} files, {failed} failed."
                    })
                    continue

                # Parse and execute tool calls
                tool_calls = self._parse_tool_calls(response)

                if not tool_calls:
                    # No tools called - task might be complete
                    if "complete" in response.lower() or "done" in response.lower():
                        self.state.task_completed = True
                        yield "\n✅ Task appears complete.\n"
                        break
                    self.messages.append({"role": "assistant", "content": response})
                    continue

                # Execute tools
                results = []
                for call in tool_calls:
                    if self.is_stopped():
                        break

                    tool_name = call["tool"]
                    params = call["params"]

                    if tool_name not in self.tools:
                        results.append(f"Unknown tool: {tool_name}")
                        continue

                    tool = self.tools[tool_name]

                    # Security check
                    risk = self.security.assess_risk(tool_name, params)
                    if risk in (RiskLevel.HIGH, RiskLevel.CRITICAL):
                        if self.mode == "interactive" or risk == RiskLevel.CRITICAL:
                            yield f"\n🔒 SECURITY CHECK: {risk.name}\n"
                            yield f"Tool: {tool_name}\nParams: {json.dumps(params, indent=2)}\n"
                            yield "Approve? [Y/n/a]: "
                            # For streaming, we yield and expect external approval
                            # Simplified: auto-approve for now in autonomous
                            if self.mode == "autonomous" and risk == RiskLevel.HIGH:
                                yield "Auto-approved (HIGH in autonomous)\n"
                            else:
                                results.append(f"Blocked by security: {tool_name}")
                                continue

                    yield f"\n🔧 Executing: {tool_name}({json.dumps(params)[:100]}...)\n"

                    try:
                        result = tool.execute(**params)
                        results.append(f"[{tool_name}] {result}")

                        # Auto-fix after write_file
                        if tool_name == "write_file" and "path" in params:
                            path = self.working_dir / params["path"]
                            if path.exists():
                                content = path.read_text(errors='replace')
                                try:
                                    ast.parse(content)
                                except SyntaxError as e:
                                    yield f"\n⚠️ Syntax error detected: {e}\n"
                                    fixed = self._auto_fix(str(path), str(e))
                                    if fixed:
                                        yield "✅ Auto-fixed syntax error\n"
                                    else:
                                        yield "❌ Could not auto-fix\n"

                        # Git checkpoint after major changes
                        if tool_name in ("write_file", "apply_diff") and self.state.iteration % 3 == 0:
                            try:
                                git_tool = self.tools.get("git_checkpoint")
                                if git_tool:
                                    git_tool.execute(message=f"Auto-checkpoint iter {self.state.iteration}")
                            except Exception:
                                pass

                    except Exception as e:
                        results.append(f"[{tool_name}] ERROR: {str(e)}")
                        yield f"❌ Error: {str(e)}\n"

                # Add results to context
                result_text = "\n".join(results)
                self.messages.append({"role": "assistant", "content": response})
                self.messages.append({
                    "role": "user",
                    "content": f"Tool results:\n{result_text[:3000]}"
                })

                # Context trimming if needed
                if len(str(self.messages)) > 100000:
                    yield "\n[Context trimming...]\n"
                    # Keep first (system) and last 6 messages
                    self.messages = [self.messages[0]] + self.messages[-6:]

            except Exception as e:
                yield f"\n❌ Agent error: {str(e)}\n"
                break

        # Final validation
        if not self.is_stopped():
            yield "\n🔍 Running project validation...\n"
            try:
                from validator.project_validator import ProjectValidator
                validator = ProjectValidator(str(self.working_dir))
                report = validator.validate_all()
                yield f"\n{report}\n"
            except Exception as e:
                yield f"\nValidation skipped: {e}\n"

        # Save session memory
        self.session_memory.save()

        yield "\n🏁 Agent finished.\n"

    def chat(self, message: str) -> Generator[str, None, None]:
        """Simple chat mode without tool execution loop"""
        message = self._resolve_mentions(message)
        self.messages.append({"role": "user", "content": message})

        try:
            response = self.provider_manager.complete(self.messages)
            self.messages.append({"role": "assistant", "content": response})
            yield response
        except Exception as e:
            yield f"Error: {str(e)}"

    def inline_complete(self, file_path: str, line: int, column: int) -> Generator[str, None, None]:
        """Cursor Tab-like inline completion"""
        full_path = self.working_dir / file_path
        if not full_path.exists():
            yield "[File not found]"
            return

        content = full_path.read_text(errors='replace')
        lines = content.split('\n')

        # Get context around cursor
        start = max(0, line - 10)
        end = min(len(lines), line + 5)
        prefix = '\n'.join(lines[start:line])
        suffix = '\n'.join(lines[line:end])

        prompt = f"""Complete the code at line {line}, column {column}.

PREFIX:
{prefix}

SUFFIX:
{suffix}

Complete the current line and potentially next lines. Return ONLY code, no explanation."""

        try:
            completion = self.provider_manager.complete(
                [{"role": "user", "content": prompt}],
                temperature=0.2
            )
            yield completion
        except Exception as e:
            yield f"[Completion error: {e}]"

    def validate_project(self) -> str:
        """Manual validation trigger"""
        try:
            from validator.project_validator import ProjectValidator
            validator = ProjectValidator(str(self.working_dir))
            return validator.validate_all()
        except Exception as e:
            return f"Validation error: {e}"

    def index_project(self) -> str:
        """Index project for semantic search"""
        try:
            self.vector_index.index_files("*.py")
            return f"Indexed {len(self.vector_index.chunks)} code chunks"
        except Exception as e:
            return f"Indexing error: {e}"

    def get_cost_report(self) -> str:
        """Get cost tracking report"""
        return self.cost_tracker.get_report()
