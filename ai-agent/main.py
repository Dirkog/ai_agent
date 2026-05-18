#!/usr/bin/env python3
"""AI Agent v3 — Cursor-like experience with Composer, @-mentions, persistent memory"""
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent))

from agent import Agent
from config import CONFIG
from modes import InteractiveMode


def main():
    parser = argparse.ArgumentParser(
        description="AI Agent v3 — Cursor-like multi-provider coding assistant"
    )
    parser.add_argument(
        "--mode", choices=["interactive", "autonomous", "swarm"], default="interactive",
        help="Agent mode"
    )
    parser.add_argument("--task", type=str, help="Task description")
    parser.add_argument("--web", action="store_true", help="Start web interface")
    parser.add_argument("--tui", action="store_true", help="Start terminal UI")
    parser.add_argument("--validate", action="store_true", help="Run validation only")
    parser.add_argument("--index", action="store_true", help="Index project for vector search")
    parser.add_argument("--complete", type=str, help="Inline complete at file:line:col")
    parser.add_argument(
        "--provider", choices=["openrouter", "nvidia_nim", "ollama"],
        help="Preferred provider"
    )

    args = parser.parse_args()

    if args.tui:
        print("Starting Terminal UI...")
        try:
            from tui.app import AgentTUI
            app = AgentTUI()
            app.run()
        except ImportError as e:
            print(f"TUI requires textual: pip install textual")
            print(f"Error: {e}")
        return

    if args.web:
        print("Starting web interface...")
        from web.app import app, socketio
        socketio.run(app, host="0.0.0.0", port=5000, debug=True)
        return

    if args.validate:
        print("Running project validation...")
        from validator import ProjectValidator
        validator = ProjectValidator(CONFIG.working_directory)
        validator.validate_all()
        print(validator.get_summary())
        return

    if args.index:
        print("Indexing project for vector search...")
        from memory.vector_store import ProjectIndex
        index = ProjectIndex(CONFIG.working_directory)
        count = index.index_files("*.py")
        print(f"Indexed {count} chunks")
        return

    if args.complete:
        # Inline completion mode
        parts = args.complete.split(":")
        if len(parts) >= 2:
            file_path = parts[0]
            line = int(parts[1]) if parts[1] else 0
            col = int(parts[2]) if len(parts) > 2 and parts[2] else 0

            print(f"Inline completion for {file_path}:{line}:{col}")
            agent = Agent(mode="autonomous")
            print("\nCompletion: ", end="", flush=True)
            for chunk in agent.inline_complete(file_path, line, col):
                print(chunk, end="", flush=True)
            print()
        return

    # CLI mode
    print("AI Agent v3 — Cursor-like Experience")
    print("Features: Composer | @-mentions | Persistent memory | LSP | Inline completion")
    print("Commands: exit | mode | swarm | cost | checkpoint | @file:path | @symbol:Name")
    print("-" * 60)

    agent = Agent(mode="interactive" if args.mode == "swarm" else args.mode)

    if args.task:
        if args.mode == "swarm":
            print("\nSwarm mode — multi-agent orchestration")
            for chunk in agent.run_swarm(args.task):
                print(chunk, end="", flush=True)
        else:
            for chunk in agent.run(args.task):
                print(chunk, end="", flush=True)
        print()
        return

    # Interactive chat loop
    while True:
        try:
            user_input = input("\nYou: ").strip()

            if user_input.lower() in ("exit", "quit", "q"):
                print("Goodbye!")
                break

            if user_input.lower() == "mode":
                new_mode = "autonomous" if agent.mode == "interactive" else "interactive"
                agent.mode = new_mode
                agent.interactive = InteractiveMode() if new_mode == "interactive" else None
                print(f"Switched to {new_mode} mode")
                continue

            if user_input.lower() == "swarm":
                task = input("Swarm task: ").strip()
                if task:
                    print("\nStarting swarm...")
                    for chunk in agent.run_swarm(task):
                        print(chunk, end="", flush=True)
                    print()
                continue

            if user_input.lower() == "cost":
                print(agent.cost_tracker.get_summary())
                continue

            if user_input.lower() == "checkpoint":
                from tools.git_tools import GitCheckpointTool
                cp = GitCheckpointTool()
                result = cp.execute(message="manual checkpoint")
                print(result.content or result.error)
                continue

            if user_input.lower() == "memory":
                print(agent.memory.get_project_summary())
                continue

            if user_input.lower().startswith("learn "):
                # Learn preference: "learn prefer_fastapi: True"
                pref = user_input[6:].strip()
                if ":" in pref:
                    key, value = pref.split(":", 1)
                    agent.memory.record_preference(key.strip(), value.strip())
                    print(f"Learned: {key.strip()} = {value.strip()}")
                continue

            if not user_input:
                continue

            print("\nAgent: ", end="", flush=True)
            for chunk in agent.chat(user_input):
                print(chunk, end="", flush=True)
            print()

        except KeyboardInterrupt:
            print("\n\nInterrupted")
            break
        except EOFError:
            break


if __name__ == "__main__":
    main()
