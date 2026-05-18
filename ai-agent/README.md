# 🤖 AI Agent — Multi-Provider Coding Agent

Агент для разработки с поддержкой нескольких LLM-провайдеров, автоматическим failover, интерактивным и автономным режимами работы.

## Возможности

- **Мульти-провайдерная система**: OpenRouter, NVIDIA NIM, Ollama (локальная)
- **Умная обработка rate limits**: автоматическое ожидание, retry с exponential backoff, переключение на резервный провайдер
- **Два режима работы**:
  - **Интерактивный** (как Cursor): задаёт уточняющие вопросы, ждёт ответа
  - **Автономный**: полностью самостоятельная работа
- **Самостоятельный вызов инструментов**: чтение/запись файлов, терминал, поиск, Python
- **Локальная валидация**: проверка синтаксиса, тесты, линтер после завершения задачи
- **Веб-интерфейс**: управление через браузер

## Архитектура

```
ai-agent/
├── config.py              # Конфигурация провайдеров
├── provider_manager.py    # Менеджер провайдеров с failover
├── agent.py               # Ядро агента
├── main.py                # Точка входа
├── providers/
│   ├── base.py           # Базовый класс + обработка rate limits
│   ├── openrouter.py     # OpenRouter provider
│   ├── nvidia_nim.py     # NVIDIA NIM provider
│   └── ollama.py         # Ollama provider
├── tools/
│   ├── base.py           # Базовый класс инструментов
│   ├── file_tools.py     # Работа с файлами
│   └── shell_tools.py    # Shell и Python
├── modes/
│   ├── interactive.py    # Интерактивный режим
│   └── autonomous.py     # Автономный режим
├── validator/
│   └── project_validator.py # Валидация проекта
├── web/
│   ├── app.py            # Flask/SocketIO сервер
│   └── templates/
│       └── index.html    # Web UI
└── tests/                # Тесты
```

## Установка

### Быстрый старт

```bash
# Клонировать репозиторий
cd ai-agent

# Установить зависимости
pip install -r requirements.txt

# Или через pyproject.toml
pip install -e ".[dev,web]"

# Настроить переменные окружения
cp .env.example .env
# Отредактировать .env, добавить API ключи
```

### Docker

```bash
# Запуск с OpenRouter/NVIDIA
docker-compose up -d

# Запуск с локальными моделями (Ollama)
docker-compose --profile local up -d
```

## Использование

### CLI режим

```bash
# Интерактивный режим (по умолчанию)
python main.py --mode interactive

# Автономный режим с конкретной задачей
python main.py --mode autonomous --task "Создать REST API на Flask с авторизацией JWT"

# Только валидация проекта
python main.py --validate

# Web интерфейс
python main.py --web
```

### Web интерфейс

```bash
python main.py --web
# Открыть http://localhost:5000
```

### Примеры задач

```bash
# Создать проект
python main.py --mode autonomous --task "Создать Python CLI утилиту для конвертации JSON в CSV"

# Рефакторинг
python main.py --mode interactive --task "Рефакторить main.py, вынести логику в отдельные модули"

# Добавить тесты
python main.py --mode autonomous --task "Написать unit-тесты для всех модулей проекта"

# Исправить баги
python main.py --mode autonomous --task "Найти и исправить все TODO и баги в коде"
```

## Конфигурация провайдеров

Провайдеры настраиваются в `config.py` по приоритету:

1. **OpenRouter** — доступ к Claude, GPT-4, Llama и др.
2. **NVIDIA NIM** — оптимизированные модели NVIDIA
3. **Ollama** — локальные модели (Codellama, Llama и др.)

При rate limit или ошибке система автоматически переключается на следующий доступный провайдер.

### Настройка Ollama (локальные модели)

```bash
# Установить Ollama
# macOS/Linux: curl -fsSL https://ollama.com/install.sh | sh

# Запустить сервер
ollama serve

# Скачать модель
ollama pull codellama:34b
# или
ollama pull llama3:70b
```

## Обработка ошибок серверов

Система распознаёт типы ошибок:

| Ошибка | Действие |
|--------|----------|
| **429 Rate Limit** | Парсит `Retry-After` из заголовков и тела ответа, ожидает указанное время |
| **5xx Server Error** | Exponential backoff (2^retry секунд) |
| **Network Error** | До 3 попыток с увеличивающейся задержкой |
| **Provider Unavailable** | Автоматический failover на следующий провайдер |
| **Auth Error** | Переключение на следующий провайдер |

### Пример обработки rate limit

```
[Rate Limit] openrouter: 429 detected. Waiting 45s...
[Rate Limit] Error detail: Rate limit exceeded. Retry after 45s
[Provider] Switching to nvidia_nim...
```

## Режимы работы

### Интерактивный (Interactive)
- Агент останавливается при неоднозначности
- Задаёт уточняющие вопросы пользователю
- Подтверждение опасных операций (rm, форматирование)
- Похоже на Cursor AI

**Пример диалога:**
```
Agent: Для создания API мне нужно уточнить:
❓ Question: Какой фреймворк предпочитаете — Flask или FastAPI?
Your answer: FastAPI

Agent: [Продолжает работу с FastAPI...]
```

### Автономный (Autonomous)
- Принимает решения самостоятельно
- Auto-confirm безопасных операций
- Логирование всех решений
- End-to-end выполнение задач

**Безопасные операции (auto-confirm):**
- Чтение файлов
- Запись файлов
- Запуск Python кода
- Безопасные shell команды (ls, cat, echo, grep)

**Требуют подтверждения:**
- rm, dd, mkfs
- Сетевые операции
- Системные команды

## Валидация проекта

После завершения задачи автоматически запускается:

- ✅ Проверка синтаксиса Python (AST)
- ✅ Проверка импортов
- ✅ Запуск тестов (pytest)
- ✅ Линтинг (flake8/pylint)
- ✅ Проверка структуры проекта

**Пример вывода:**
```
============================================================
📊 VALIDATION SUMMARY
============================================================

✅ Python Syntax: Checked 5 files ✓
✅ Imports: Found 0 potentially missing imports
✅ Tests: Tests 5 passed
✅ Linting (flake8): flake8 passed ✓
✅ Requirements: requirements.txt has 8 dependencies
⚠️ File Structure: Structure check found 2 issues
   • Found 3 __pycache__ directories (should be gitignored)

============================================================
Result: 5/6 checks passed
============================================================
```

## API Keys

- **OpenRouter**: https://openrouter.ai/keys
- **NVIDIA NIM**: https://build.nvidia.com/
- **Ollama**: https://ollama.ai (локально, ключ не нужен)

## Тестирование

```bash
# Запустить все тесты
pytest tests/ -v

# Запустить конкретный модуль
pytest tests/test_providers.py -v
pytest tests/test_tools.py -v
pytest tests/test_validator.py -v

# С покрытием
pytest tests/ --cov=. --cov-report=html
```

## Разработка

```bash
# Установить dev зависимости
pip install -e ".[dev]"

# Запуск линтера
flake8 . --max-line-length=120

# Форматирование
black .
```

## Лицензия

MIT
