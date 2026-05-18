"""Additional tools for Cursor-like experience"""
import os
import re
import json
import time
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List
from urllib.parse import urlparse
import urllib.request

try:
    import httpx
except ImportError:
    httpx = None

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

from tools.base import BaseTool, ToolResult


class WebSearchTool(BaseTool):
    """Search the web for information — @Web equivalent"""
    name = "web_search"
    description = "Search the internet for documentation, examples, latest info"

    def execute(self, query: str, num_results: int = 5) -> ToolResult:
        try:
            # Use DuckDuckGo HTML or searx instance
            search_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"

            req = urllib.request.Request(
                search_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            )

            with urllib.request.urlopen(req, timeout=10) as response:
                html = response.read().decode("utf-8", errors="ignore")

            # Parse results (simple regex)
            results = []
            links = re.findall(r'<a rel="nofollow" class="result__a" href="([^"]+)">([^<]+)</a>', html)
            snippets = re.findall(r'<a class="result__snippet"[^>]*>([^<]+)</a>', html)

            for i, (url, title) in enumerate(links[:num_results]):
                snippet = snippets[i] if i < len(snippets) else ""
                results.append(f"{i+1}. {title}\n   {url}\n   {snippet}\n")

            return ToolResult(
                success=True,
                output="\n".join(results) if results else "No results found",
                data={"query": query, "results_count": len(results)}
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class FetchDocsTool(BaseTool):
    """Fetch documentation from URL — @Docs equivalent"""
    name = "fetch_docs"
    description = "Fetch and parse documentation from a URL (MDN, Python docs, etc.)"

    def execute(self, url: str, max_length: int = 10000) -> ToolResult:
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; AI-Agent/1.0)"}
            )

            with urllib.request.urlopen(req, timeout=15) as response:
                html = response.read().decode("utf-8", errors="ignore")

            # Simple HTML to text
            text = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
            text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
            text = re.sub(r'<[^>]+>', ' ', text)
            text = re.sub(r'\s+', ' ', text).strip()

            return ToolResult(
                success=True,
                output=text[:max_length],
                data={"url": url, "full_length": len(text)}
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class NotepadTool(BaseTool):
    """Notepad for context — @Notepads equivalent"""
    name = "notepad"
    description = "Save notes, context, requirements for the session"

    def __init__(self, working_dir: str = "."):
        super().__init__()
        self.notepad_path = Path(working_dir) / ".ai-agent" / "notepad.md"
        self.notepad_path.parent.mkdir(parents=True, exist_ok=True)

    def execute(self, action: str = "read", content: str = "", section: str = "") -> ToolResult:
        try:
            if action == "read":
                if self.notepad_path.exists():
                    text = self.notepad_path.read_text(encoding="utf-8")
                    return ToolResult(success=True, output=text)
                return ToolResult(success=True, output="Notepad is empty")

            elif action == "write":
                if section:
                    # Append to section
                    existing = ""
                    if self.notepad_path.exists():
                        existing = self.notepad_path.read_text(encoding="utf-8")

                    section_header = f"\n## {section}\n"
                    if section_header in existing:
                        existing = existing.replace(section_header, f"{section_header}{content}\n")
                    else:
                        existing += f"\n{section_header}{content}\n"

                    self.notepad_path.write_text(existing, encoding="utf-8")
                else:
                    self.notepad_path.write_text(content, encoding="utf-8")

                return ToolResult(success=True, output=f"Saved to notepad")

            elif action == "append":
                existing = ""
                if self.notepad_path.exists():
                    existing = self.notepad_path.read_text(encoding="utf-8")
                self.notepad_path.write_text(existing + "\n" + content, encoding="utf-8")
                return ToolResult(success=True, output="Appended to notepad")

            elif action == "clear":
                self.notepad_path.write_text("", encoding="utf-8")
                return ToolResult(success=True, output="Notepad cleared")

            else:
                return ToolResult(success=False, error=f"Unknown action: {action}")

        except Exception as e:
            return ToolResult(success=False, error=str(e))


class GitDiffTool(BaseTool):
    """Show recent git changes — @Recent Changes equivalent"""
    name = "git_recent_changes"
    description = "Show recent git changes, diffs, commit history"

    def __init__(self, working_dir: str = "."):
        super().__init__()
        self.working_dir = Path(working_dir)

    def execute(self, commits: int = 5, file: str = "") -> ToolResult:
        try:
            if file:
                # Diff for specific file
                result = subprocess.run(
                    ["git", "diff", "HEAD~1", "--", file],
                    cwd=self.working_dir,
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                return ToolResult(success=True, output=result.stdout or "No changes")

            # Recent commits with stats
            log = subprocess.run(
                ["git", "log", "--oneline", "--stat", f"-{commits}"],
                cwd=self.working_dir,
                capture_output=True,
                text=True,
                timeout=10
            )

            # Current diff (uncommitted)
            diff = subprocess.run(
                ["git", "diff", "--stat"],
                cwd=self.working_dir,
                capture_output=True,
                text=True,
                timeout=10
            )

            output = f"=== Recent {commits} commits ===\n{log.stdout}\n\n"
            if diff.stdout:
                output += f"=== Uncommitted changes ===\n{diff.stdout}"
            else:
                output += "No uncommitted changes"

            return ToolResult(success=True, output=output)
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class ChromeAutomationTool(BaseTool):
    """Browser automation — Claude Code Chrome equivalent"""
    name = "chrome_automation"
    description = "Automate browser for testing, screenshots, interaction"

    def execute(self, action: str = "screenshot", url: str = "", 
                selector: str = "", text: str = "", wait_ms: int = 1000) -> ToolResult:
        if not sync_playwright:
            return ToolResult(
                success=False, 
                error="Playwright not installed. Run: pip install playwright && playwright install"
            )

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1280, "height": 720})

                if action == "screenshot":
                    if not url:
                        return ToolResult(success=False, error="URL required for screenshot")
                    page.goto(url, wait_until="networkidle", timeout=30000)
                    page.wait_for_timeout(wait_ms)
                    screenshot_path = f".ai-agent/screenshots/{int(time.time())}.png"
                    Path(screenshot_path).parent.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=screenshot_path, full_page=True)
                    browser.close()
                    return ToolResult(
                        success=True, 
                        output=f"Screenshot saved: {screenshot_path}",
                        data={"path": screenshot_path}
                    )

                elif action == "test":
                    if not url:
                        return ToolResult(success=False, error="URL required")
                    page.goto(url, wait_until="networkidle", timeout=30000)

                    # Check for errors in console
                    logs = []
                    page.on("console", lambda msg: logs.append(f"{msg.type}: {msg.text}"))
                    page.wait_for_timeout(wait_ms)

                    # Check for error elements
                    errors = page.query_selector_all(".error, [class*="error"], [id*="error"]")

                    browser.close()
                    return ToolResult(
                        success=True,
                        output=f"Console logs: {len(logs)}\nErrors found: {len(errors)}\n{chr(10).join(logs[:20])}",
                        data={"logs": logs, "errors": len(errors)}
                    )

                elif action == "click":
                    if not url or not selector:
                        return ToolResult(success=False, error="URL and selector required")
                    page.goto(url, wait_until="networkidle", timeout=30000)
                    page.click(selector, timeout=10000)
                    page.wait_for_timeout(wait_ms)
                    browser.close()
                    return ToolResult(success=True, output=f"Clicked {selector}")

                elif action == "fill":
                    if not url or not selector or not text:
                        return ToolResult(success=False, error="URL, selector and text required")
                    page.goto(url, wait_until="networkidle", timeout=30000)
                    page.fill(selector, text, timeout=10000)
                    page.wait_for_timeout(wait_ms)
                    browser.close()
                    return ToolResult(success=True, output=f"Filled {selector} with '{text}'")

                else:
                    browser.close()
                    return ToolResult(success=False, error=f"Unknown action: {action}")

        except Exception as e:
            return ToolResult(success=False, error=str(e))


class BackgroundTaskTool(BaseTool):
    """Run background tasks — Claude Code & equivalent"""
    name = "background_task"
    description = "Run tasks in background while continuing main work"

    def __init__(self):
        super().__init__()
        self.tasks: Dict[str, Any] = {}

    def execute(self, command: str = "", task_id: str = "", action: str = "start") -> ToolResult:
        try:
            if action == "start":
                if not command:
                    return ToolResult(success=False, error="Command required")

                import threading
                import uuid

                tid = task_id or str(uuid.uuid4())[:8]

                def run_in_background():
                    result = subprocess.run(
                        command,
                        shell=True,
                        capture_output=True,
                        text=True,
                        timeout=3600
                    )
                    self.tasks[tid] = {
                        "status": "done",
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                        "returncode": result.returncode
                    }

                thread = threading.Thread(target=run_in_background, daemon=True)
                self.tasks[tid] = {"status": "running", "command": command}
                thread.start()

                return ToolResult(
                    success=True,
                    output=f"Background task started: {tid}\nCommand: {command}",
                    data={"task_id": tid}
                )

            elif action == "status":
                if task_id not in self.tasks:
                    return ToolResult(success=False, error=f"Task {task_id} not found")

                task = self.tasks[task_id]
                status = task.get("status", "unknown")

                if status == "done":
                    output = f"Task {task_id} completed\n"
                    if task.get("stdout"):
                        output += f"\nOutput:\n{task['stdout'][:2000]}"
                    if task.get("stderr"):
                        output += f"\nErrors:\n{task['stderr'][:1000]}"
                    return ToolResult(success=True, output=output, data=task)
                else:
                    return ToolResult(
                        success=True, 
                        output=f"Task {task_id} is {status}",
                        data={"status": status}
                    )

            elif action == "list":
                tasks = [f"{k}: {v.get('status', 'unknown')}" for k, v in self.tasks.items()]
                return ToolResult(success=True, output="\n".join(tasks) or "No tasks")

            else:
                return ToolResult(success=False, error=f"Unknown action: {action}")

        except Exception as e:
            return ToolResult(success=False, error=str(e))


class CodeInstructionsTool(BaseTool):
    """Inline code editing — Cursor Ctrl+K equivalent"""
    name = "code_instructions"
    description = "Edit code inline with natural language instructions"

    def __init__(self, working_dir: str = "."):
        super().__init__()
        self.working_dir = Path(working_dir)

    def execute(self, file: str, instructions: str, selection: str = "") -> ToolResult:
        try:
            file_path = self.working_dir / file
            if not file_path.exists():
                return ToolResult(success=False, error=f"File not found: {file}")

            content = file_path.read_text(encoding="utf-8")

            # If selection provided, replace only that part
            if selection and selection in content:
                # Mark the selection for the LLM
                marked_content = content.replace(
                    selection,
                    f"<<<SELECTION_START>>>\n{selection}\n<<<SELECTION_END>>>"
                )
                prompt = f"""Edit the following code according to instructions.

INSTRUCTIONS: {instructions}

CODE:
{marked_content}

Replace ONLY the content between <<<SELECTION_START>>> and <<<SELECTION_END>>>.
Return the complete file with the edit applied.
"""
            else:
                prompt = f"""Edit the following code according to instructions.

INSTRUCTIONS: {instructions}

CODE:
{content}

Return the complete edited file.
"""

            # This would be sent to LLM in practice
            return ToolResult(
                success=True,
                output=f"Instructions prepared for {file}\nInstructions: {instructions}",
                data={
                    "file": file,
                    "instructions": instructions,
                    "has_selection": bool(selection),
                    "prompt": prompt[:500] + "..."
                }
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
