

class HoverInfoTool(BaseTool):
    """Показать тип и документацию при наведении (LSP hover)"""
    name = "hover_info"
    description = "Get type info and documentation for symbol at position (LSP hover)"

    def __init__(self, working_dir: str = "."):
        self.working_dir = Path(working_dir)

    def execute(self, file_path: str, line: int, column: int) -> ToolResult:
        try:
            from lsp.client import LSPClient
            client = LSPClient(project_path=str(self.working_dir))
            client.start()
            result = client.hover(file_path, line, column)
            client.stop()
            if result:
                return ToolResult(success=True, output=json.dumps(result, indent=2))
            return ToolResult(success=True, output="No hover info available")
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class GoToDefinitionTool(BaseTool):
    """Переход к определению символа (LSP go-to-definition)"""
    name = "go_to_definition"
    description = "Jump to definition of symbol (LSP go-to-definition)"

    def __init__(self, working_dir: str = "."):
        self.working_dir = Path(working_dir)

    def execute(self, file_path: str, line: int, column: int) -> ToolResult:
        try:
            from lsp.client import LSPClient
            client = LSPClient(project_path=str(self.working_dir))
            client.start()
            locations = client.goto_definition(file_path, line, column)
            client.stop()
            if locations:
                summary = "\n".join([
                    f"  {loc.get('uri', 'unknown')}:{loc.get('range', {}).get('start', {}).get('line', '?')}"
                    for loc in locations[:10]
                ])
                return ToolResult(success=True, output=f"Definitions found:\n{summary}")
            return ToolResult(success=True, output="No definition found")
        except Exception as e:
            return ToolResult(success=False, error=str(e))
