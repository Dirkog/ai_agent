"""Terminal UI for AI Agent using Textual"""
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, Container
from textual.widgets import (
    Header, Footer, Static, Input, Log, Tree, Button,
    RichLog, Markdown, TabbedContent, TabPane
)
from textual.reactive import reactive
from textual.binding import Binding
from pathlib import Path


class FileTree(Tree):
    """File browser sidebar"""
    def __init__(self, path: str = "."):
        super().__init__(Path(path).name)
        self.root_path = Path(path).resolve()
        self._populate(self.root, self.root_path)

    def _populate(self, node, path: Path):
        try:
            for item in sorted(path.iterdir()):
                if item.name.startswith('.') and item.name not in ('.env', '.gitignore'):
                    continue
                if item.is_dir():
                    child = node.add(item.name)
                    self._populate(child, item)
                else:
                    node.add_leaf(item.name)
        except PermissionError:
            pass


class AgentTUI(App):
    """Textual interface for AI Agent"""

    CSS = """
    Screen { align: center middle; }
    #main { width: 100%; height: 100%; }
    #sidebar { width: 25%; height: 100%; border-right: solid $primary; }
    #chat { width: 75%; height: 100%; }
    #log { height: 80%; border: solid $primary; padding: 1; }
    #input { height: 20%; }
    .status { color: $success; }
    .error { color: $error; }
    .warning { color: $warning; }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", show=True),
        Binding("ctrl+s", "send", "Send", show=True),
        Binding("ctrl+r", "refresh", "Refresh Files", show=True),
    ]

    mode = reactive("interactive")
    provider = reactive("auto")

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with Horizontal(id="main"):
            with Vertical(id="sidebar"):
                yield Static("📁 PROJECT", classes="status")
                yield FileTree(".")
                yield Static("\n⚙️ STATUS", classes="status")
                yield Static("Mode: interactive\nProvider: auto\nIter: 0", id="status")

            with Vertical(id="chat"):
                yield RichLog(id="log", highlight=True, wrap=True)
                with Container(id="input"):
                    yield Input(placeholder="Describe task... (Ctrl+S to send)", id="msg_input")
                    yield Horizontal(
                        Button("Interactive", id="btn_interactive", variant="primary"),
                        Button("Autonomous", id="btn_autonomous"),
                        Button("Swarm", id="btn_swarm"),
                    )

        yield Footer()

    def on_mount(self):
        self.query_one("#log", RichLog).write("🤖 AI Agent Terminal UI\n")
        self.query_one("#log", RichLog).write("Providers: OpenRouter | NVIDIA NIM | Ollama\n")
        self.query_one("#log", RichLog).write("Mode: INTERACTIVE\n")
        self.query_one("#log", RichLog).write("-" * 50 + "\n")

    def on_input_submitted(self, event: Input.Submitted):
        if event.input.id == "msg_input":
            self._send_message(event.value)

    def on_button_pressed(self, event: Button.Pressed):
        btn_id = event.button.id
        if btn_id == "btn_interactive":
            self.mode = "interactive"
            self._update_status()
        elif btn_id == "btn_autonomous":
            self.mode = "autonomous"
            self._update_status()
        elif btn_id == "btn_swarm":
            self.mode = "swarm"
            self._update_status()

    def action_send(self):
        inp = self.query_one("#msg_input", Input)
        if inp.value:
            self._send_message(inp.value)
            inp.value = ""

    def _send_message(self, text: str):
        log = self.query_one("#log", RichLog)
        log.write(f"\n[bold blue]You:[/] {text}\n")

        if self.mode == "swarm":
            log.write("[bold yellow]🐝 Swarm mode — orchestrating agents...[/]\n")
            # In production: run orchestrator
            log.write("[green]✅ Swarm workflow complete[/]\n")
        else:
            log.write("[dim]Agent thinking...[/]\n")
            # In production: stream from agent
            log.write("[green]✅ Done[/]\n")

    def _update_status(self):
        status = self.query_one("#status", Static)
        status.update(f"Mode: {self.mode}\nProvider: {self.provider}\nIter: 0")

        log = self.query_one("#log", RichLog)
        log.write(f"[dim]Switched to {self.mode.upper()} mode[/]\n")

    def action_refresh(self):
        # Refresh file tree
        sidebar = self.query_one("#sidebar", Vertical)
        sidebar.remove_children()
        # Re-compose would be better but this is simple demo


if __name__ == "__main__":
    app = AgentTUI()
    app.run()
