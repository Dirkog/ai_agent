"""AI Agent v6 — Terminal Feature Module
Handles terminal sessions, command execution, and output streaming.
"""
import os
import sys
import pty
import select
import struct
import fcntl
import termios
import signal
import threading
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
import time

@dataclass
class TerminalSession:
    session_id: str
    working_dir: str
    shell: str = "/bin/bash"
    pid: Optional[int] = None
    fd: Optional[int] = None
    active: bool = False
    output_buffer: List[str] = field(default_factory=list)
    command_history: List[str] = field(default_factory=list)
    env_vars: Dict[str, str] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    size: tuple = (24, 80)  # rows, cols

class TerminalManager:
    """Manages pseudo-terminal sessions"""

    def __init__(self, working_dir: str = "."):
        self.working_dir = Path(working_dir).resolve()
        self.sessions: Dict[str, TerminalSession] = {}
        self.output_callbacks: Dict[str, List[Callable]] = {}
        self._lock = threading.Lock()

    def create_session(self, session_id: str = None, shell: str = None) -> TerminalSession:
        """Create a new PTY session"""
        import uuid
        if session_id is None:
            session_id = str(uuid.uuid4())[:8]

        shell = shell or os.environ.get("SHELL", "/bin/bash")

        # Create PTY
        pid, fd = pty.fork()

        if pid == 0:
            # Child process
            os.chdir(self.working_dir)
            os.execv(shell, [shell])

        # Parent process
        session = TerminalSession(
            session_id=session_id,
            working_dir=str(self.working_dir),
            shell=shell,
            pid=pid,
            fd=fd,
            active=True
        )

        with self._lock:
            self.sessions[session_id] = session
            self.output_callbacks[session_id] = []

        # Start output reader thread
        reader = threading.Thread(target=self._read_output, args=(session_id,), daemon=True)
        reader.start()

        return session

    def _read_output(self, session_id: str):
        """Read output from PTY in background"""
        session = self.sessions.get(session_id)
        if not session or session.fd is None:
            return

        while session.active:
            try:
                ready, _, _ = select.select([session.fd], [], [], 0.1)
                if ready:
                    data = os.read(session.fd, 4096)
                    if data:
                        text = data.decode('utf-8', errors='replace')
                        session.output_buffer.append(text)
                        session.last_activity = time.time()

                        # Notify callbacks
                        for callback in self.output_callbacks.get(session_id, []):
                            try:
                                callback(text)
                            except Exception:
                                pass
                    else:
                        break
            except (OSError, IOError):
                break

        session.active = False

    def write(self, session_id: str, data: str) -> bool:
        """Write data to terminal"""
        session = self.sessions.get(session_id)
        if not session or not session.active or session.fd is None:
            return False

        try:
            os.write(session.fd, data.encode('utf-8'))
            session.last_activity = time.time()
            return True
        except OSError:
            return False

    def execute_command(self, session_id: str, command: str, 
                        timeout: float = 30.0) -> Dict[str, Any]:
        """Execute a command and capture output"""
        session = self.sessions.get(session_id)

        if not session or not session.active:
            # Create new session if needed
            session = self.create_session(session_id)

        # Clear buffer before command
        session.output_buffer.clear()

        # Send command
        self.write(session_id, command + '\n')
        session.command_history.append(command)

        # Wait for output with timeout
        start_time = time.time()
        output = []

        while time.time() - start_time < timeout:
            if session.output_buffer:
                output.extend(session.output_buffer)
                session.output_buffer.clear()

            # Check for prompt (simple heuristic)
            full_output = ''.join(output)
            if full_output.strip().endswith(('$', '#', '>', '%')):
                break

            time.sleep(0.1)

        return {
            "command": command,
            "output": ''.join(output),
            "duration": time.time() - start_time,
            "session_id": session_id
        }

    def resize(self, session_id: str, rows: int, cols: int) -> bool:
        """Resize terminal"""
        session = self.sessions.get(session_id)
        if not session or session.fd is None:
            return False

        try:
            size = struct.pack('HHHH', rows, cols, 0, 0)
            fcntl.ioctl(session.fd, termios.TIOCSWINSZ, size)
            session.size = (rows, cols)
            return True
        except OSError:
            return False

    def get_output(self, session_id: str, clear: bool = True) -> str:
        """Get buffered output"""
        session = self.sessions.get(session_id)
        if not session:
            return ""

        output = ''.join(session.output_buffer)
        if clear:
            session.output_buffer.clear()

        return output

    def kill_session(self, session_id: str) -> bool:
        """Kill a terminal session"""
        session = self.sessions.get(session_id)
        if not session:
            return False

        session.active = False

        if session.pid:
            try:
                os.kill(session.pid, signal.SIGTERM)
                time.sleep(0.5)
                os.kill(session.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

        if session.fd:
            try:
                os.close(session.fd)
            except OSError:
                pass

        with self._lock:
            self.sessions.pop(session_id, None)
            self.output_callbacks.pop(session_id, None)

        return True

    def list_sessions(self) -> List[Dict]:
        """List active sessions"""
        return [
            {
                "session_id": s.session_id,
                "shell": s.shell,
                "active": s.active,
                "working_dir": s.working_dir,
                "command_count": len(s.command_history),
                "created_at": s.created_at,
                "last_activity": s.last_activity,
                "size": s.size
            }
            for s in self.sessions.values()
        ]

    def set_env(self, session_id: str, key: str, value: str) -> bool:
        """Set environment variable"""
        session = self.sessions.get(session_id)
        if not session:
            return False

        session.env_vars[key] = value
        # Export in terminal
        self.write(session_id, f"export {key}={value}\n")
        return True

    def run_script(self, script_path: str, args: List[str] = None,
                   env: Dict[str, str] = None, cwd: str = None) -> Dict[str, Any]:
        """Run a script as subprocess (non-interactive)"""
        full_path = self.working_dir / script_path

        if not str(full_path.resolve()).startswith(str(self.working_dir)):
            return {"error": "Path traversal detected"}

        cmd = [str(full_path)] + (args or [])

        env_vars = os.environ.copy()
        if env:
            env_vars.update(env)

        working = cwd or str(self.working_dir)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                cwd=working,
                env=env_vars
            )

            return {
                "command": ' '.join(cmd),
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "duration": None  # subprocess.run doesn't give this easily
            }
        except subprocess.TimeoutExpired:
            return {
                "command": ' '.join(cmd),
                "error": "Command timed out after 300s",
                "returncode": -1
            }
        except Exception as e:
            return {
                "command": ' '.join(cmd),
                "error": str(e),
                "returncode": -1
            }

    def cleanup_inactive(self, max_idle: float = 3600):
        """Kill sessions idle longer than max_idle seconds"""
        now = time.time()
        to_kill = []

        for session_id, session in self.sessions.items():
            if now - session.last_activity > max_idle:
                to_kill.append(session_id)

        for session_id in to_kill:
            self.kill_session(session_id)

        return len(to_kill)

# Singleton
_terminal_manager: Optional[TerminalManager] = None

def get_terminal_manager(working_dir: str = ".") -> TerminalManager:
    global _terminal_manager
    if _terminal_manager is None:
        _terminal_manager = TerminalManager(working_dir)
    return _terminal_manager
