"""Language Server Protocol client — FIXED VERSION
Provides IDE features: go-to-definition, hover info, diagnostics, symbol search.
"""
import subprocess
import json
import threading
import queue
import os
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass

@dataclass
class LSPDiagnostic:
    severity: int
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

def _path_to_uri(path: Path) -> str:
    """Convert Path to file URI (cross-platform)"""
    absolute = path.resolve()
    return absolute.as_uri()

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
        self._lock = threading.Lock()
        self._callbacks: List[Callable] = []

    def start(self) -> bool:
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

            root_uri = _path_to_uri(self.project_path)
            init_id = self._next_id()
            self._send({
                "jsonrpc": "2.0",
                "id": init_id,
                "method": "initialize",
                "params": {
                    "processId": None,
                    "rootUri": root_uri,
                    "capabilities": {
                        "textDocument": {
                            "hover": {"dynamicRegistration": True},
                            "definition": {"dynamicRegistration": True},
                            "documentSymbol": {"dynamicRegistration": True},
                            "publishDiagnostics": {"relatedInformation": True}
                        }
                    },
                    "workspaceFolders": None
                }
            })

            init_queue = queue.Queue()
            with self._lock:
                self._pending[init_id] = init_queue

            try:
                response = init_queue.get(timeout=10)
                if "result" in response:
                    print(f"[LSP] Connected to {self.command}")
                    self._send({
                        "jsonrpc": "2.0",
                        "method": "initialized",
                        "params": {}
                    })
                    return True
            except queue.Empty:
                print(f"[LSP] Init timeout for {self.command}")
                return False

        except FileNotFoundError:
            print(f"[LSP] Command not found: {self.command}")
            return False
        except Exception as e:
            print(f"[LSP] Failed to start {self.command}: {e}")
            return False

    def _next_id(self) -> int:
        with self._lock:
            self._message_id += 1
            return self._message_id

    def _send(self, message: dict):
        if self.process and self.process.stdin:
            content = json.dumps(message)
            header = f"Content-Length: {len(content)}\r\n\r\n"
            try:
                self.process.stdin.write(header + content)
                self.process.stdin.flush()
            except (BrokenPipeError, OSError) as e:
                print(f"[LSP] Send error: {e}")
                self._running = False

    def _read_loop(self):
        while self._running and self.process and self.process.poll() is None:
            try:
                header = ""
                while True:
                    char = self.process.stdout.read(1)
                    if not char:
                        break
                    header += char
                    if header.endswith("\r\n\r\n"):
                        break

                if not header:
                    continue

                length = 0
                for line in header.split("\r\n"):
                    if line.startswith("Content-Length:"):
                        length = int(line.split(":")[1].strip())
                        break

                if length > 0:
                    content = self.process.stdout.read(length)
                    if content:
                        try:
                            message = json.loads(content)
                            self._handle_message(message)
                        except json.JSONDecodeError as e:
                            print(f"[LSP] JSON decode error: {e}")

            except Exception as e:
                if self._running:
                    print(f"[LSP] Read error: {e}")

    def _handle_message(self, message: dict):
        msg_id = message.get("id")

        if msg_id is not None:
            with self._lock:
                pending_queue = self._pending.pop(msg_id, None)
            if pending_queue:
                pending_queue.put(message)

        if message.get("method") == "textDocument/publishDiagnostics":
            params = message.get("params", {})
            uri = params.get("uri", "")
            diagnostics = params.get("diagnostics", [])

            path = uri.replace("file://", "")
            if os.name == 'nt':
                path = path.lstrip('/')

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

            for cb in self._callbacks:
                try:
                    cb(path, self._diagnostics[path])
                except Exception:
                    pass

    def open_document(self, path: str, content: str = ""):
        full_path = self.project_path / path
        uri = _path_to_uri(full_path)
        self._send({
            "jsonrpc": "2.0",
            "method": "textDocument/didOpen",
            "params": {
                "textDocument": {
                    "uri": uri,
                    "languageId": Path(path).suffix.lstrip('.') or "python",
                    "version": 1,
                    "text": content
                }
            }
        })

    def change_document(self, path: str, content: str):
        full_path = self.project_path / path
        uri = _path_to_uri(full_path)
        self._send({
            "jsonrpc": "2.0",
            "method": "textDocument/didChange",
            "params": {
                "textDocument": {"uri": uri, "version": 2},
                "contentChanges": [{"text": content}]
            }
        })

    def hover(self, path: str, line: int, column: int) -> Optional[str]:
        msg_id = self._next_id()
        response_queue = queue.Queue()
        with self._lock:
            self._pending[msg_id] = response_queue

        full_path = self.project_path / path
        uri = _path_to_uri(full_path)

        self._send({
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": "textDocument/hover",
            "params": {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": column}
            }
        })

        try:
            response = response_queue.get(timeout=5)
            result = response.get("result", {})
            if not result:
                return None
            contents = result.get("contents", "")
            if isinstance(contents, dict):
                return contents.get("value", "")
            elif isinstance(contents, list) and contents:
                return str(contents[0])
            return str(contents)
        except queue.Empty:
            return None
        finally:
            with self._lock:
                self._pending.pop(msg_id, None)

    def goto_definition(self, path: str, line: int, column: int) -> List[LSPLocation]:
        msg_id = self._next_id()
        response_queue = queue.Queue()
        with self._lock:
            self._pending[msg_id] = response_queue

        full_path = self.project_path / path
        uri = _path_to_uri(full_path)

        self._send({
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": "textDocument/definition",
            "params": {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": column}
            }
        })

        try:
            response = response_queue.get(timeout=5)
            result = response.get("result", [])
            if not isinstance(result, list):
                result = [result] if result else []

            locations = []
            for r in result:
                if not r:
                    continue
                uri = r.get("uri", "")
                path_str = uri.replace("file://", "")
                if os.name == 'nt':
                    path_str = path_str.lstrip('/')
                range_data = r.get("range", {})
                start = range_data.get("start", {})
                locations.append(LSPLocation(
                    path=path_str,
                    line=start.get("line", 0),
                    column=start.get("character", 0)
                ))
            return locations
        except queue.Empty:
            return []
        finally:
            with self._lock:
                self._pending.pop(msg_id, None)

    def get_symbols(self, path: str) -> List[Dict[str, Any]]:
        msg_id = self._next_id()
        response_queue = queue.Queue()
        with self._lock:
            self._pending[msg_id] = response_queue

        full_path = self.project_path / path
        uri = _path_to_uri(full_path)

        self._send({
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": "textDocument/documentSymbol",
            "params": {"textDocument": {"uri": uri}}
        })

        try:
            response = response_queue.get(timeout=5)
            return response.get("result", [])
        except queue.Empty:
            return []
        finally:
            with self._lock:
                self._pending.pop(msg_id, None)

    def get_diagnostics(self, path: str) -> List[LSPDiagnostic]:
        full_path = str(self.project_path / path)
        return self._diagnostics.get(full_path, [])

    def add_diagnostics_callback(self, callback: Callable):
        self._callbacks.append(callback)

    def stop(self):
        self._running = False
        if self.process:
            try:
                self._send({"jsonrpc": "2.0", "id": self._next_id(), "method": "shutdown"})
                import time
                time.sleep(0.5)
                self.process.terminate()
                self.process.wait(timeout=3)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
