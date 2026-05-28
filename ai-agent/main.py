"""AI Agent v6 — Entry Point
Fixed: Proper .env creation with all V6 settings, typed values,
       correct provider imports, streaming support
"""
import os
import sys
import json
import time
from pathlib import Path
from typing import Optional

def check_env_file() -> bool:
    """Проверяет .env, создаёт если нет с полной V6 конфигурацией"""
    env_path = Path(".env")

    if env_path.exists():
        return True

    print("=" * 60)
    print("🚀 Первый запуск AI Agent v6")
    print("=" * 60)
    print("\nНужно настроить API ключи.\n")

    config = {}

    print("--- NVIDIA NIM (Главный провайдер, бесплатно, 40 RPM) ---")
    print("Получи ключ: https://build.nvidia.com/")
    nvidia_key = input("NVIDIA API Key: ").strip()
    if nvidia_key:
        config["NVIDIA_API_KEY"] = nvidia_key
        config["NVIDIA_MODEL"] = "mistralai/mistral-large-3-675b-instruct-2512"

    print("\n--- OpenRouter (Дебаггер, fallback) ---")
    print("Получи ключ: https://openrouter.ai/keys")
    print("(можно пропустить — fallback будет недоступен)")
    openrouter_key = input("OpenRouter API Key (Enter для пропуска): ").strip()
    if openrouter_key:
        config["OPENROUTER_API_KEY"] = openrouter_key
        config["OPENROUTER_MODEL"] = "deepseek/deepseek-v4-pro:free"

    print("\n--- Ollama (Локальные модели) ---")
    print("(если установлен локально)")
    ollama_url = input("Ollama URL (Enter для пропуска, default http://localhost:11434/v1): ").strip()
    config["OLLAMA_BASE_URL"] = ollama_url or "http://localhost:11434/v1"
    config["OLLAMA_MODEL"] = "codellama:34b"

    print("\n--- vLLM (Опционально, для ensemble) ---")
    vllm_url = input("vLLM URL (Enter для пропуска): ").strip()
    if vllm_url:
        config["VLLM_BASE_URL"] = vllm_url
        config["VLLM_MODEL"] = input("vLLM Model ID: ").strip()

    print("\n--- Настройки ---")
    work_dir = input("Рабочая директория (Enter для текущей): ").strip()
    config["WORKING_DIRECTORY"] = work_dir or "."
    config["FLASK_PORT"] = "5000"
    config["FLASK_DEBUG"] = "false"

    # v6 settings
    config["ENSEMBLE_ENABLED"] = "true"
    config["ENSEMBLE_CONFIDENCE_THRESHOLD"] = "0.7"
    config["ENSEMBLE_DIVERGENCE_THRESHOLD"] = "0.3"
    config["ENSEMBLE_MAX_WORKERS"] = "4"
    config["AVAILABLE_VRAM_GB"] = input("Доступная VRAM в GB (Enter для 48): ").strip() or "48"
    config["PREFER_LOCAL_MODELS"] = "true"
    config["MAX_ITERATIONS"] = "50"
    config["SECURITY_LEVEL"] = "medium"
    config["TRACK_COSTS"] = "true"
    config["COST_LIMIT_USD"] = "10.0"

    # Write .env
    env_content = "# AI Agent v6 Configuration\n# Auto-generated on first run\n\n"
    for key, value in config.items():
        if ' ' in str(value) or any(c in str(value) for c in ['#', '"', "'"]):
            env_content += f'{key}="{value}"\n'
        else:
            env_content += f"{key}={value}\n"

    env_path.write_text(env_content, encoding="utf-8")
    print(f"\n✅ Конфигурация сохранена в {env_path.absolute()}")
    print("Можно редактировать: notepad .env\n")
    return True

def setup_environment():
    """Загружает .env и проверяет зависимости"""
    from dotenv import load_dotenv
    load_dotenv()

    required = ["NVIDIA_API_KEY"]
    missing = [r for r in required if not os.getenv(r)]

    if missing:
        print(f"❌ Отсутствуют обязательные переменные: {', '.join(missing)}")
        print("Отредактируй .env и перезапусти.")
        sys.exit(1)

    try:
        import flask
        import flask_socketio
        import httpx
        print("✅ Flask, SocketIO, HTTPX — OK")
    except ImportError as e:
        print(f"❌ Не установлены зависимости: {e}")
        print("Запусти: pip install -r requirements.txt")
        sys.exit(1)

def print_banner():
    print("""
 ╔═══════════════════════════════════════════════════════════╗
 ║                                                           ║
 ║ 🤖 AI Agent v6 — Cursor-like IDE with Ensemble            ║
 ║ Главный: NVIDIA NIM (mistral-large-3)                     ║
 ║ Ensemble: NVIDIA + Ollama/vLLM параллельно                ║
 ║ Дебаггер: OpenRouter (deepseek-v4-pro)                    ║
 ║ Инструментов: 51+                                         ║
 ║                                                           ║
 ║ Режимы:                                                   ║
 ║ • interactive — как Cursor, с вопросами                   ║
 ║ • autonomous — полностью автономный                       ║
 ║ • swarm — multi-agent оркестратор с 20 ролями             ║
 ║                                                           ║
 ║ Команды:                                                  ║
 ║ • python main.py --mode interactive                       ║
 ║ • python main.py --mode swarm --task "Создать API"        ║
 ║ • python main.py --ensemble --task "Рефакторинг"          ║
 ║ • python main.py --web                                    ║
 ║ • python main.py --tui                                    ║
 ║                                                           ║
 ╚═══════════════════════════════════════════════════════════╝
 """)

def main():
    import argparse

    parser = argparse.ArgumentParser(description="AI Agent v6")
    parser.add_argument("--mode", choices=["interactive", "autonomous", "swarm"],
                        default="interactive", help="Режим работы")
    parser.add_argument("--task", type=str, help="Задача для автономного/swarm режима")
    parser.add_argument("--ensemble", action="store_true", help="Использовать ensemble (NVIDIA + Local)")
    parser.add_argument("--web", action="store_true", help="Запустить Web UI")
    parser.add_argument("--tui", action="store_true", help="Запустить Terminal UI")
    parser.add_argument("--complete", type=str, help="Inline completion: file.py:line:col")
    parser.add_argument("--validate", action="store_true", help="Валидировать проект")
    parser.add_argument("--index", action="store_true", help="Индексировать проект")
    parser.add_argument("--cost", action="store_true", help="Показать статистику расходов")
    parser.add_argument("--setup", action="store_true", help="Пересоздать .env")
    parser.add_argument("--prefer-local", action="store_true", help="Предпочитать локальные модели")
    parser.add_argument("--force-api", action="store_true", help="Принудительно использовать API")

    args = parser.parse_args()

    if args.setup or not Path(".env").exists():
        check_env_file()

    setup_environment()
    print_banner()

    from agent import Agent
    from swarm.orchestrator_v3 import SmartOrchestrator
    from swarm.role_assigner import RoleAssigner
    from provider_manager import ProviderManager

    pm = ProviderManager()
    providers = pm.get_available_providers()
    print(f"\n📡 Провайдеры: {', '.join(providers)}")

    ensemble_status = pm.get_ensemble_status()
    if ensemble_status.get("available"):
        print(f"🔄 Ensemble: доступен (NVIDIA + Ollama)")
    else:
        print(f"⚠️ Ensemble: {ensemble_status.get('reason', 'недоступен')}")
    print()

    if args.web:
        print("🌐 Запуск Web UI на http://localhost:5000")
        from web.app import app, socketio
        socketio.run(app, host="0.0.0.0", port=5000, debug=False)

    elif args.tui:
        print("🖥️ Запуск Terminal UI")
        from tui.app import TUIApp
        app = TUIApp()
        app.run()

    elif args.complete:
        parts = args.complete.split(":")
        if len(parts) >= 2:
            file_path = parts[0]
            line = int(parts[1]) if parts[1].isdigit() else 1
            col = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1
            agent = Agent(mode="interactive")
            print(f"\n✏️ Inline completion для {file_path}:{line}:{col}")
            for chunk in agent.inline_complete(file_path, line, col):
                print(chunk, end="")
            print()

    elif args.validate:
        agent = Agent(mode="interactive")
        print("\n🔍 Валидация проекта...")
        report = agent.validate_project()
        print(report)

    elif args.index:
        agent = Agent(mode="interactive")
        print("\n📚 Индексация проекта...")
        result = agent.index_project()
        print(result)

    elif args.cost:
        agent = Agent(mode="interactive")
        print("\n💰 Статистика расходов:")
        print(agent.get_cost_report())

    elif args.mode == "swarm":
        if not args.task:
            print("❌ Укажи задачу: --task \"Создать REST API\"")
            sys.exit(1)

        print(f"\n🐝 Swarm режим: {args.task}\n")

        nvidia_key = os.getenv("NVIDIA_API_KEY")
        openrouter_key = os.getenv("OPENROUTER_API_KEY")
        ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        vllm_url = os.getenv("VLLM_BASE_URL")
        vram = int(os.getenv("AVAILABLE_VRAM_GB", "48"))
        prefer_local = args.prefer_local or os.getenv("PREFER_LOCAL_MODELS", "true").lower() == "true"

        orchestrator = SmartOrchestrator(
            nvidia_api_key=nvidia_key,
            openrouter_api_key=openrouter_key,
            use_ensemble=args.ensemble,
            ollama_url=ollama_url,
            vllm_url=vllm_url,
            prefer_local=prefer_local,
            available_vram_gb=vram
        )

        def on_status(msg):
            print(f"[Status] {msg}")
        def on_agent_done(agent):
            print(f"[Done] {agent.name} завершил работу")
        def on_err(msg):
            print(f"[Error] {msg}")

        orchestrator.on_status_update = on_status
        orchestrator.on_agent_complete = on_agent_done
        orchestrator.on_error = on_err

        try:
            for chunk in orchestrator.run_task(args.task):
                print(chunk, end="")
                sys.stdout.flush()
        finally:
            orchestrator.close()

    elif args.mode == "autonomous":
        if not args.task:
            print("❌ Укажи задачу: --task \"Создать Flask API\"")
            sys.exit(1)

        print(f"\n🤖 Автономный режим: {args.task}\n")
        agent = Agent(mode="autonomous")

        if args.ensemble:
            print("🔄 Ensemble mode enabled (NVIDIA + Local)\n")

        try:
            for chunk in agent.run(args.task):
                print(chunk, end="")
                sys.stdout.flush()
        finally:
            # Cleanup
            pass

    else:
        print("\n💬 Интерактивный режим (введи 'exit' для выхода)")
        agent = Agent(mode="interactive")

        while True:
            try:
                user_input = input("\nYou: ").strip()
                if user_input.lower() in ("exit", "quit", "q"):
                    break
                if not user_input:
                    continue

                print("\nAgent: ", end="")
                for chunk in agent.chat(user_input):
                    print(chunk, end="")
                    sys.stdout.flush()
                print()

            except KeyboardInterrupt:
                print("\n\n⛔ Остановлено")
                agent.stop()
                break
            except EOFError:
                break

        print("\n👋 До свидания!")

if __name__ == "__main__":
    main()
