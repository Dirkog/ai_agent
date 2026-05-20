"""MCP Bridge — интеграция Model Context Protocol в Agent
Позволяет агенту использовать внешние MCP серверы (файловая система, браузер, БД).
"""
import json
import asyncio
from typing import Dict, Any, List, Optional
from mcp.client import MCPClient


class MCPBridge:
    """Bridge between Agent and MCP servers"""

    def __init__(self, working_dir: str = "."):
        self.working_dir = working_dir
        self.clients: Dict[str, MCPClient] = {}
        self.tools_cache: Dict[str, List[Dict]] = {}

    async def connect_server(self, name: str, command: str, args: List[str] = None):
        """Подключиться к MCP серверу"""
        client = MCPClient()
        await client.connect(command, args or [])
        self.clients[name] = client

        # Кэшируем инструменты
        tools = await client.list_tools()
        self.tools_cache[name] = tools

        return {"connected": True, "tools": len(tools)}

    async def disconnect_all(self):
        """Отключить все серверы"""
        for name, client in self.clients.items():
            await client.disconnect()
        self.clients.clear()
        self.tools_cache.clear()

    def get_all_tools(self) -> List[Dict[str, Any]]:
        """Получить все инструменты от всех MCP серверов"""
        all_tools = []
        for server_name, tools in self.tools_cache.items():
            for tool in tools:
                all_tools.append({
                    "name": f"mcp_{server_name}_{tool['name']}",
                    "original_name": tool["name"],
                    "server": server_name,
                    "description": tool.get("description", ""),
                    "parameters": tool.get("parameters", {}),
                })
        return all_tools

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Вызвать MCP инструмент"""
        # Парсим имя: mcp_serverName_toolName
        parts = tool_name.split("_", 2)
        if len(parts) < 3 or parts[0] != "mcp":
            return f"[Error] Invalid MCP tool name: {tool_name}"

        server_name = parts[1]
        original_name = parts[2]

        if server_name not in self.clients:
            return f"[Error] MCP server not connected: {server_name}"

        client = self.clients[server_name]

        try:
            result = await client.call_tool(original_name, arguments)

            # Форматируем результат
            if hasattr(result, 'content'):
                contents = []
                for item in result.content:
                    if hasattr(item, 'text'):
                        contents.append(item.text)
                    elif hasattr(item, 'data'):
                        contents.append(str(item.data))
                return "\n".join(contents)

            return str(result)

        except Exception as e:
            return f"[Error] MCP tool call failed: {str(e)}"

    def get_status(self) -> Dict[str, Any]:
        """Статус MCP подключений"""
        return {
            "connected_servers": list(self.clients.keys()),
            "total_tools": sum(len(tools) for tools in self.tools_cache.values()),
            "servers": {
                name: {
                    "tools_count": len(self.tools_cache.get(name, [])),
                    "status": "connected"
                }
                for name in self.clients.keys()
            }
        }


# Синхронная обёртка для использования в Agent
class MCPBridgeSync:
    """Синхронная обёртка над MCPBridge"""

    def __init__(self, working_dir: str = "."):
        self.bridge = MCPBridge(working_dir)
        self._loop = asyncio.new_event_loop()

    def connect(self, name: str, command: str, args: List[str] = None):
        return self._loop.run_until_complete(
            self.bridge.connect_server(name, command, args)
        )

    def disconnect(self):
        return self._loop.run_until_complete(self.bridge.disconnect_all())

    def get_tools(self) -> List[Dict]:
        return self.bridge.get_all_tools()

    def call(self, tool_name: str, arguments: Dict) -> str:
        return self._loop.run_until_complete(
            self.bridge.call_tool(tool_name, arguments)
        )

    def status(self) -> Dict:
        return self.bridge.get_status()
