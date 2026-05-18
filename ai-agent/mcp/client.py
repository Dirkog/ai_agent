"""MCP (Model Context Protocol) client integration"""
import json
import subprocess
import threading
from typing import Dict, List, Any, Optional
from dataclasses import dataclass


@dataclass
class MCPTool:
    name: str
    description: str
    parameters: Dict[str, Any]
    server: str


class MCPClient:
    """Client for MCP servers (stdio or SSE transport)"""

    def __init__(self):
        self.servers: Dict[str, subprocess.Popen] = {}
        self.tools: List[MCPTool] = []
        self._lock = threading.Lock()

    def connect_stdio(self, name: str, command: str, args: List[str] = None):
        """Connect to MCP server via stdio"""
        try:
            proc = subprocess.Popen(
                [command] + (args or []),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            self.servers[name] = proc

            # Initialize
            init_msg = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "ai-agent", "version": "1.0.0"}}}
            self._send(name, init_msg)
            response = self._read_response(name)

            # List tools
            tools_msg = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
            self._send(name, tools_msg)
            tools_response = self._read_response(name)

            if tools_response and "result" in tools_response:
                for t in tools_response["result"].get("tools", []):
                    self.tools.append(MCPTool(
                        name=t["name"],
                        description=t.get("description", ""),
                        parameters=t.get("inputSchema", {}),
                        server=name
                    ))

            print(f"[MCP] Connected to {name} with {len(self.tools)} tools")
            return True
        except Exception as e:
            print(f"[MCP] Failed to connect to {name}: {e}")
            return False

    def _send(self, server_name: str, message: dict):
        proc = self.servers.get(server_name)
        if proc and proc.stdin:
            proc.stdin.write(json.dumps(message) + "\n")
            proc.stdin.flush()

    def _read_response(self, server_name: str, timeout: float = 10.0) -> Optional[dict]:
        proc = self.servers.get(server_name)
        if not proc or not proc.stdout:
            return None

        import select
        import time
        start = time.time()
        while time.time() - start < timeout:
            if proc.poll() is not None:
                return None
            line = proc.stdout.readline()
            if line:
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
            time.sleep(0.1)
        return None

    def call_tool(self, tool_name: str, arguments: dict) -> Any:
        """Call an MCP tool"""
        tool = next((t for t in self.tools if t.name == tool_name), None)
        if not tool:
            return {"error": f"Tool {tool_name} not found"}

        msg = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments}
        }
        self._send(tool.server, msg)
        return self._read_response(tool.server)

    def to_openai_schema(self) -> List[Dict]:
        """Convert MCP tools to OpenAI function schema"""
        schemas = []
        for t in self.tools:
            schemas.append({
                "type": "function",
                "function": {
                    "name": f"mcp_{t.name}",
                    "description": t.description,
                    "parameters": t.parameters
                }
            })
        return schemas

    def disconnect_all(self):
        for name, proc in self.servers.items():
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                proc.kill()
        self.servers.clear()
        self.tools.clear()
