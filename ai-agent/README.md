# 🤖 AI Agent v6 — Максимальный Разнорабочий Агент

## 📋 О ПРОЕКТЕ

**AI Agent v6** — open-source AI-агент для автономного программирования, аналог Cursor IDE и Claude Code, с уникальной архитектурой: **одновременно локальные модели и API NVIDIA NIM**, сравнение ответов и выбор лучшего.

**Ключевые особенности:**
- **51+ инструментов** как в Cursor/Claude Code + уникальные
- **20 ролей** с умным оркестратором
- **Local + API ensemble** — параллельный запуск, выбор лучшего
- **OpenRouter дебаггер** — только для анализа расхождений
- **Все NVIDIA NIM модели бесплатные** (40 RPM, без кредитной карты)
- **3 интерфейса**: CLI, Terminal UI (Textual), Web UI (Flask/SocketIO)

## 🚀 Быстрый старт

```bash
# Клонировать
git clone https://github.com/Dirkog/ai_agent.git
cd ai_agent/ai-agent

# Установить зависимости
pip install -r requirements.txt

# Создать .env (интерактивно)
python main.py --setup

# Запуск
python main.py --mode interactive
python main.py --mode swarm --task "Создать REST API"
python main.py --web
```

## 📁 Структура

```
ai-agent/
├── main.py              # Entry point
├── agent.py             # Core agent (51 tools, streaming, ensemble)
├── config.py            # Configuration with typed env vars
├── provider_manager.py  # Unified provider API
├── swarm/
│   ├── orchestrator_v3.py   # Smart orchestrator with provider cache
│   └── role_assigner.py     # 20 roles with model mapping
├── providers/
│   ├── base.py              # BaseProvider with complete()/close()
│   ├── nvidia_nim.py
│   ├── ollama.py
│   ├── vllm_provider.py
│   ├── openrouter.py
│   ├── ensemble_provider.py # Parallel Local + API voting
│   └── debug_analyzer.py
├── tools/
│   ├── file_tools.py
│   ├── shell_tools.py
│   ├── git_tools.py
│   ├── advanced_tools.py
│   ├── ide/ide_tools.py     # + HoverInfo, GoToDefinition
│   ├── ai/ai_tools.py
│   ├── cursor_tools.py
│   ├── security_tools.py    # NEW: scan, dependency, secret, safety
│   ├── multimodal_tools.py  # NEW: image, audio, video, screenshot
│   └── orchestrator_tools.py # NEW: 6 orchestrator tools
└── ...
```

## 🔧 Исправления v6.1

### CRITICAL
- ✅ `BaseProvider.complete()` — унифицированный API (string vs generator)
- ✅ `EnsembleProvider` — правильная инициализация `ProviderConfig`
- ✅ `Orchestrator` — `chat()` вместо несуществующего `complete()`, кэш провайдеров
- ✅ `Agent.run()` — настоящий streaming (yield чанков), не блокирующий accumulate

### HIGH
- ✅ `config.py` — фильтрация `None` из providers, типизированные env-переменные
- ✅ `provider_manager.py` — unified `complete()` API, правильный ensemble init
- ✅ `.env.example` — полная конфигурация с 20 ролями
- ✅ Connection leak fixed — `close()`/`__del__` для всех провайдеров

### NEW
- ✅ `security_tools.py` — 4 инструмента (bandit, safety, gitleaks, nemotron-safety)
- ✅ `multimodal_tools.py` — 4 инструмента (OCR, whisper, opencv, screenshot)
- ✅ `orchestrator_tools.py` — 6 инструментов (assign, switch, vote, debug, retry, compare)
- ✅ `.cursorrules` — шаблон правил проекта

## 📊 Статистика

| Метрика | Было | Стало |
|---------|------|-------|
| Инструменты | 30 | 51+ |
| CRITICAL багов | 4 | 0 |
| HIGH багов | 11 | 0 |
| Streaming | Блокирующий | Реальный |
| Provider cache | Нет | Да |
| Token estimation | `len // 4` | `len(utf-8) // 3` |
| Connection leaks | Да | Нет |

## ⚠️ Лимиты

- **NVIDIA NIM Free**: 40 RPM, без кредитной карты, возможен downtime
- **OpenRouter Free**: 20 RPM, 200/день — **ТОЛЬКО для дебага**
- **Local**: Требует VRAM 8-48GB, медленнее API

## 📄 Лицензия

MIT
