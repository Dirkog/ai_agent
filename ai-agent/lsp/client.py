"""Language Server Protocol client
Provides IDE features: go-to-definition, hover info, diagnostics, symbol search.
"""
import subprocess
import json
import threading
import queue
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass


@dataclass
class LSPDiagnostic:
    severity: int  # 1=Error, 2=Warning, 3=Info, 4=Hint
    message: str
    line: int
    column: int
    source: str = ""
    code: str = ""


@dataclass
class LSPLocation:
    path: str
    line: int
    column: int
    name: str = ""


class LSPClient:
    """Generic LSP client for Python (pylsp, pyright, jedi) and other languages"""

    def __init__(self, command: str = "pylsp", args: List[str] = None, project_path: str = "."):
        self.command = command
        self.args = args or []
        self.project_path = Path(project_path).resolve()
        self.process: Optional[subprocess.Popen] = None
        self._message_id = 0
        self._pending: Dict[int, queue.Queue] = {}
        self._diagnostics: Dict[str, List[LSPDiagnostic]] = {}
        self._running = False
        self._reader_thread: Optional[threading.Thread] = None

    def start(self) -> bool:
        """Start LSP server process"""
        try:
            self.process = subprocess.Popen(
                [self.command] + self.args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                cwd=str(self.project_path)
            )
            self._running = True
            self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
            self._reader_thread.start()

            # Initialize
            self._send({
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "initialize",
                "params": {
                    "processId": None,
                    "rootUri": self.project_path.as_uri() if hasattr(self.project_path, 'as_uri') else f"file://{self.project_path}",
                    "capabilities": {},
                    "workspaceFolders": None
                }
            })

            # Wait for init response
            init_queue = queue.Queue()
            self._pending[1] = init_queue
            try:
                response = init_queue.get(timeout=5)
                if "result" in response:
                    print(f"[LSP] Connected to {self.command}")
                    return True
            except queue.Empty:
                print(f"[LSP] Init timeout for {self.command}")
                return False

        except Exception as e:
            print(f"[LSP] Failed to start {self.command}: {e}")
            return False

    def _next_id(self) -> int:
        self._message_id += 1
        return self._message_id

    def _send(self, message: dict):
        if self.process and self.process.stdin:
            content = json.dumps(message)
            header = f"Content-Length: {len(content)}\r\n\r\n"
            self.process.stdin.write(header + content)
            self.process.stdin.flush()

    def _read_loop(self):
        """Read LSP messages from stdout"""
        while self._running and self.process and self.process.poll() is None:
            try:
                # Read header
                header = ""
                while True:
                    char = self.process.stdout.read(1)
                    if not char:
                        break
                    header += char
                    if header.endswith("\r\n\r\n"):
                        break

                # Parse Content-Length
                length = 0
                for line in header.split("\r\n"):
                    if line.startswith("Content-Length:"):
                        length = int(line.split(":")[1].strip())

                if length > 0:
                    content = self.process.stdout.read(length)
                    message = json.loads(content)
                    self._handle_message(message)

            except Exception as e:
                if self._running:
                    print(f"[LSP] Read error: {e}")

    def _handle_message(self, message: dict):
        """Handle incoming LSP message"""
        msg_id = message.get("id")

        if msg_id and msg_id in self._pending:
            self._pending[msg_id].put(message)

        # Handle diagnostics notifications
        if message.get("method") == "textDocument/publishDiagnostics":
            params = message.get("params", {})
            uri = params.get("uri", "")
            diagnostics = params.get("diagnostics", [])

            path = uri.replace("file://", "")
            self._diagnostics[path] = [
                LSPDiagnostic(
                    severity=d.get("severity", 1),
                    message=d.get("message", ""),
                    line=d.get("range", {}).get("start", {}).get("line", 0),
                    column=d.get("range", {}).get("start", {}).get("character", 0),
                    source=d.get("source", ""),
                    code=str(d.get("code", ""))
                )
                for d in diagnostics
            ]

    def get_diagnostics(self, path: str) -> List[LSPDiagnostic]:
        """Get diagnostics for a file"""
        full_path = str(self.project_path / path)
        return self._diagnostics.get(full_path, [])

    def open_document(self, path: str, content: str = ""):
        """Notify LSP that document is open"""
        full_path = str(self.project_path / path)
        self._send({
            "jsonrpc": "2.0",
            "method": "textDocument/didOpen",
            "params": {
                "textDocument": {
                    "uri": f"file://{full_path}",
                    "languageId": Path(path).suffix.lstrip('.') or "python",
                    "version": 1,
                    "text": content
                }
            }
        })

    def hover(self, path: str, line: int, column: int) -> Optional[str]:
        """Get hover information at position"""
        msg_id = self._next_id()
        response_queue = queue.Queue()
        self._pending[msg_id] = response_queue

        full_path = str(self.project_path / path)
        self._send({
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": "textDocument/hover",
            "params": {
                "textDocument": {"uri": f"file://{full_path}"},
                "position": {"line": line, "character": column}
            }
        })

        try:
            response = response_queue.get(timeout=3)
            result = response.get("result", {})
            contents = result.get("contents", "")
            if isinstance(contents, dict):
                return contents.get("value", "")
            return str(contents)
        except queue.Empty:
            return None

    def goto_definition(self, path: str, line: int, column: int) -> List[LSPLocation]:
        """Find definition of symbol at position"""
        msg_id = self._next_id()
        response_queue = queue.Queue()
        self._pending[msg_id] = response_queue

        full_path = str(self.project_path / path)
        self._send({
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": "textDocument/definition",
            "params": {
                "textDocument": {"uri": f"file://{full_path}"},
                "position": {"line": line, "character": column}
            }
        })

        try:
            response = response_queue.get(timeout=3)
            result = response.get("result", [])
            if not isinstance(result, list):
                result = [result] if result else []

            return [
                LSPLocation(
                    path=r.get("uri", "").replace("file://", ""),
                    line=r.get("range", {}).get("start", {}).get("line", 0),
                    column=r.get("range", {}).get("start", {}).get("character", 0)
                )
                for r in result
            ]
        except queue.Empty:
            return []

    def get_symbols(self, path: str) -> List[Dict[str, Any]]:
        """Get document symbols (functions, classes, variables)"""
        msg_id = self._next_id()
        response_queue = queue.Queue()
        self._pending[msg_id] = response_queue

        full_path = str(self.project_path / path)
        self._send({
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": "textDocument/documentSymbol",
            "params": {
                "textDocument": {"uri": f"file://{full_path}"}
            }
        })

        try:
            response = response_queue.get(timeout=3)
            return response.get("result", [])
        except queue.Empty:
            return []

    def stop(self):
        """Shutdown LSP server"""
        self._running = False
        if self.process:
            try:
                self._send({"jsonrpc": "2.0", "id": self._next_id(), "method": "shutdown"})
                self.process.terminate()
                self.process.wait(timeout=2)
            except Exception:
                self.process.kill()
