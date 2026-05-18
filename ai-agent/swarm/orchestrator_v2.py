"""AI Agent Orchestrator v2 — Smart Model Router
Главный оркестратор (NVIDIA) назначает модели из NIM каталога ролям.
При ошибках — подключается OpenRouter для диагностики.
"""
import json
import os
import time
import threading
from typing import List, Dict, Any, Optional, Generator, Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

# Импортируем провайдеров
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from providers.base import BaseProvider, RateLimitError
from providers.openrouter import OpenRouterProvider
from providers.nvidia_nim import NvidiaNimProvider


class AgentRole(Enum):
    ORCHESTRATOR = "orchestrator"  # Главный мозг
    CODER = "coder"
    REVIEWER = "reviewer"
    TESTER = "tester"
    DEBUGGER = "debugger"
    DEVOPS = "devops"
    SCRUM_MASTER = "scrum"


# NVIDIA NIM бесплатные модели (каталог)
NVIDIA_MODELS = {
    "nemotron-70b": {
        "id": "nvidia/llama-3.1-nemotron-70b-instruct",
        "description": "Лучшая для сложного кодинга и архитектуры",
        "strengths": ["complex_logic", "architecture", "planning"],
        "rpm": 40
    },
    "qwen-coder-32b": {
        "id": "qwen/qwen-2.5-coder-32b-instruct",
        "description": "Специализированная для написания кода",
        "strengths": ["coding", "refactoring", "code_review"],
        "rpm": 40
    },
    "mistral-large": {
        "id": "mistralai/mistral-large-instruct-2407",
        "description": "Хороша для ревью и анализа",
        "strengths": ["review", "analysis", "documentation"],
        "rpm": 40
    },
    "phi-4": {
        "id": "microsoft/phi-4-multimodal-instruct",
        "description": "Для тестов и быстрых задач",
        "strengths": ["testing", "quick_tasks", "multimodal"],
        "rpm": 40
    },
    "llama-3.3-70b": {
        "id": "meta/llama-3.3-70b-instruct",
        "description": "Универсальная для планирования",
        "strengths": ["planning", "general", "chat"],
        "rpm": 40
    },
    "deepseek-coder": {
        "id": "deepseek-ai/deepseek-coder-33b-instruct",
        "description": "Для рефакторинга и оптимизации",
        "strengths": ["refactoring", "optimization", "debugging"],
        "rpm": 40
    }
}

# OpenRouter модели для дебаггера (платные/резерв)
OPENROUTER_MODELS = {
    "claude-sonnet": {
        "id": "anthropic/claude-3.5-sonnet",
        "description": "Лучший для сложного дебаггинга",
        "fallback": True
    },
    "gpt-4o": {
        "id": "openai/gpt-4o",
        "description": "Для анализа ошибок",
        "fallback": True
    },
    "o1-mini": {
        "id": "openai/o1-mini",
        "description": "Для глубокого reasoning",
        "fallback": True
    }
}


@dataclass
class SubAgent:
    role: AgentRole
    name: str
    model_id: str  # Полный ID модели
    provider: str  # "nvidia" или "openrouter"
    system_prompt: str
    tasks_completed: int = 0
    status: str = "idle"  # idle, working, done, error
    output: str = ""
    error_log: List[str] = field(default_factory=list)
    cost: float = 0.0
    tokens_used: int = 0


@dataclass
class TaskPlan:
    complexity: int  # 1-10
    roles_needed: List[AgentRole]
    model_assignments: Dict[str, str]  # role -> model_id
    phases: List[Dict[str, Any]]
    estimated_time: int  # минуты
    reasoning: str


class RPMTracker:
    """Отслеживает RPM для NVIDIA (40/мин)"""
    def __init__(self, max_rpm: int = 40):
        self.max_rpm = max_rpm
        self.requests: List[float] = []
        self._lock = threading.Lock()

    def can_request(self) -> bool:
        with self._lock:
            now = time.time()
            # Удаляем запросы старше 60 секунд
            self.requests = [t for t in self.requests if now - t < 60]
            return len(self.requests) < self.max_rpm

    def add_request(self):
        with self._lock:
            self.requests.append(time.time())

    def wait_time(self) -> float:
        with self._lock:
            now = time.time()
            self.requests = [t for t in self.requests if now - t < 60]
            if len(self.requests) < self.max_rpm:
                return 0
            oldest = min(self.requests)
            return 60 - (now - oldest)

    def get_status(self) -> Dict:
        with self._lock:
            now = time.time()
            self.requests = [t for t in self.requests if now - t < 60]
            return {
                "used": len(self.requests),
                "limit": self.max_rpm,
                "remaining": self.max_rpm - len(self.requests)
            }


class SmartOrchestrator:
    """
    Главный оркестратор:
    1. Получает задачу
    2. Анализирует через NVIDIA (главная модель)
    3. Назначает модели из NIM ролям
    4. Запускает параллельно
    5. При ошибке — вызывает OpenRouter дебаггер
    6. Дебаггер даёт команду оркестратору
    """

    def __init__(self, nvidia_api_key: str, openrouter_api_key: Optional[str] = None):
        # Главный мозг — NVIDIA nemotron-70b
        self.brain = NvidiaNimProvider(
            api_key=nvidia_api_key,
            model="nvidia/llama-3.1-nemotron-70b-instruct"
        )

        # Резервный дебаггер — OpenRouter
        self.debugger = None
        if openrouter_api_key:
            self.debugger = OpenRouterProvider(
                api_key=openrouter_api_key,
                model="anthropic/claude-3.5-sonnet"
            )

        # RPM трекер для NVIDIA
        self.rpm_tracker = RPMTracker(max_rpm=40)

        # Агенты
        self.agents: List[SubAgent] = []
        self.task_history: List[Dict] = []

        # Callbacks для UI
        self.on_status_update: Optional[Callable] = None
        self.on_agent_complete: Optional[Callable] = None
        self.on_error: Optional[Callable] = None

    def _call_brain(self, prompt: str, temperature: float = 0.3) -> str:
        """Вызов главного оркестратора (NVIDIA) с контролем RPM"""
        # Ждём, если RPM лимит
        while not self.rpm_tracker.can_request():
            wait = self.rpm_tracker.wait_time()
            if self.on_status_update:
                self.on_status_update(f"[RPM] Ждём {wait:.1f}с (лимит 40/мин)")
            time.sleep(wait)

        self.rpm_tracker.add_request()

        try:
            messages = [{"role": "user", "content": prompt}]
            response = self.brain.complete(messages, temperature=temperature)
            return response
        except RateLimitError as e:
            # Если NVIDIA заблокировал — ждём и повторяем
            retry_after = e.retry_after or 60
            if self.on_status_update:
                self.on_status_update(f"[RateLimit] NVIDIA: ждём {retry_after}с")
            time.sleep(retry_after)
            return self._call_brain(prompt, temperature)
        except Exception as e:
            if self.on_error:
                self.on_error(f"[Brain Error] {str(e)}")
            raise

    def analyze_task(self, task: str) -> TaskPlan:
        """Главный оркестратор анализирует задачу и выбирает модели"""

        prompt = f"""Ты — Главный Оркестратор AI Agent. Проанализируй задачу и составь план.

Доступные модели NVIDIA NIM (все бесплатные, 40 RPM):
{json.dumps(NVIDIA_MODELS, indent=2, ensure_ascii=False)}

Задача: {task}

Проанализируй:
1. Сложность задачи (1-10)
2. Какие роли нужны (coder, reviewer, tester, debugger, devops, scrum)
3. Какую модель NVIDIA назначить каждой роли (по силам модели)
4. Порядок выполнения фаз
5. Оцени время в минутах

Верни ТОЛЬКО JSON:
{{
    "complexity": 7,
    "roles_needed": ["scrum", "coder", "tester", "reviewer"],
    "model_assignments": {{
        "scrum": "llama-3.3-70b",
        "coder": "qwen-coder-32b",
        "tester": "phi-4",
        "reviewer": "mistral-large"
    }},
    "phases": [
        {{"role": "scrum", "task": "Разбить на подзадачи", "depends_on": []}},
        {{"role": "coder", "task": "Написать код", "depends_on": ["scrum"]}},
        {{"role": "tester", "task": "Написать тесты", "depends_on": ["coder"]}},
        {{"role": "reviewer", "task": "Ревью кода", "depends_on": ["coder"]}}
    ],
    "estimated_time": 15,
    "reasoning": "Задача средней сложности, нужен план + код + тесты + ревью"
}}
"""

        response = self._call_brain(prompt, temperature=0.2)

        # Парсим JSON
        try:
            # Ищем JSON в ответе
            json_match = __import__('re').search(r'\{.*\}', response, __import__('re').DOTALL)
            if json_match:
                plan_data = json.loads(json_match.group())
            else:
                plan_data = json.loads(response)

            # Конвертируем строки ролей в enum
            roles = []
            for r in plan_data.get("roles_needed", []):
                try:
                    roles.append(AgentRole(r))
                except ValueError:
                    pass

            return TaskPlan(
                complexity=plan_data.get("complexity", 5),
                roles_needed=roles,
                model_assignments=plan_data.get("model_assignments", {}),
                phases=plan_data.get("phases", []),
                estimated_time=plan_data.get("estimated_time", 10),
                reasoning=plan_data.get("reasoning", "")
            )
        except Exception as e:
            # Fallback — простой план
            return TaskPlan(
                complexity=5,
                roles_needed=[AgentRole.CODER],
                model_assignments={"coder": "nemotron-70b"},
                phases=[{"role": "coder", "task": task, "depends_on": []}],
                estimated_time=10,
                reasoning=f"Fallback: {str(e)}"
            )

    def create_agents(self, plan: TaskPlan) -> List[SubAgent]:
        """Создаёт агентов по плану"""
        self.agents = []

        for role in plan.roles_needed:
            role_str = role.value
            model_key = plan.model_assignments.get(role_str, "nemotron-70b")
            model_info = NVIDIA_MODELS.get(model_key, NVIDIA_MODELS["nemotron-70b"])

            agent = SubAgent(
                role=role,
                name=f"{role_str}_{model_key}",
                model_id=model_info["id"],
                provider="nvidia",
                system_prompt=self._get_role_prompt(role)
            )
            self.agents.append(agent)

        return self.agents

    def _get_role_prompt(self, role: AgentRole) -> str:
        """Промпт для роли"""
        prompts = {
            AgentRole.ORCHESTRATOR: "Ты — Главный Оркестратор. Анализируй, планируй, назначай.",
            AgentRole.CODER: "Ты — Senior Developer. Пиши чистый, production-ready код. Используй best practices.",
            AgentRole.REVIEWER: "Ты — Code Reviewer. Ищи баги, уязвимости, проблемы производительности.",
            AgentRole.TESTER: "Ты — QA Engineer. Пиши comprehensive тесты. Coverage > 80%.",
            AgentRole.DEBUGGER: "Ты — Debugger. Анализируй ошибки, находи root cause, предлагай фиксы.",
            AgentRole.DEVOPS: "Ты — DevOps. Docker, CI/CD, мониторинг.",
            AgentRole.SCRUM_MASTER: "Ты — Project Manager. Декомпозируй задачи, оценивай, трека прогресс."
        }
        return prompts.get(role, "Выполни свою роль профессионально.")

    def run_task(self, task: str) -> Generator[str, None, None]:
        """Главный метод — запускает полный workflow"""

        yield f"🧠 [Оркестратор] Анализирую задачу...
"
        yield f"📋 Задача: {task[:200]}...
"

        # Шаг 1: Анализ
        plan = self.analyze_task(task)
        yield f"
📊 Анализ:
"
        yield f"   Сложность: {plan.complexity}/10
"
        yield f"   Роли: {[r.value for r in plan.roles_needed]}
"
        yield f"   Модели: {plan.model_assignments}
"
        yield f"   Время: ~{plan.estimated_time} мин
"
        yield f"   Логика: {plan.reasoning}
"

        # Шаг 2: Создаём агентов
        agents = self.create_agents(plan)
        yield f"
👥 Создано агентов: {len(agents)}
"
        for a in agents:
            yield f"   • {a.name} → {a.model_id}
"

        # Шаг 3: Выполняем фазы
        completed_phases = set()

        for phase in plan.phases:
            role_str = phase["role"]
            phase_task = phase["task"]
            depends = phase.get("depends_on", [])

            # Ждём зависимости
            if depends:
                yield f"
⏳ Жду завершения: {depends}
"
                while not all(d in completed_phases for d in depends):
                    time.sleep(0.5)

            # Находим агента
            agent = next((a for a in agents if a.role.value == role_str), None)
            if not agent:
                yield f"⚠️ Агент {role_str} не найден, пропускаю
"
                continue

            yield f"
{'='*60}
"
            yield f"🚀 Фаза: {role_str.upper()} — {phase_task}
"
            yield f"🤖 Модель: {agent.model_id}
"
            yield f"{'='*60}
"

            agent.status = "working"

            try:
                # Выполняем задачу через модель
                result = self._execute_agent_task(agent, phase_task, agents)
                agent.output = result
                agent.status = "done"
                agent.tasks_completed += 1

                yield f"
✅ {agent.name} завершил
"
                yield f"📤 Результат: {result[:500]}...
"

                completed_phases.add(role_str)

                if self.on_agent_complete:
                    self.on_agent_complete(agent)

            except Exception as e:
                agent.status = "error"
                agent.error_log.append(str(e))

                yield f"
❌ ОШИБКА в {agent.name}: {str(e)}
"

                # Шаг 4: Дебаггер (OpenRouter)
                if self.debugger:
                    yield f"
🔍 Вызываю дебаггера (OpenRouter)...
"
                    debug_result = self._call_debugger(agent, str(e), task)
                    yield f"🩺 Диагноз: {debug_result}
"

                    # Даём команду оркестратору
                    yield f"
🔄 Перепланирую с учётом диагноза...
"
                    # Можно добавить повторную попытку или альтернативный план
                else:
                    yield f"⚠️ Дебаггер не настроен (нет OpenRouter API ключа)
"

        # Итог
        yield f"
{'='*60}
"
        yield f"🏁 ВСЕ ФАЗЫ ЗАВЕРШЕНЫ
"
        yield f"{'='*60}
"

        success = sum(1 for a in agents if a.status == "done")
        errors = sum(1 for a in agents if a.status == "error")

        yield f"
📊 Статистика:
"
        yield f"   ✅ Успешно: {success}/{len(agents)}
"
        yield f"   ❌ Ошибок: {errors}
"
        yield f"   🔄 RPM использовано: {self.rpm_tracker.get_status()}
"

        for a in agents:
            yield f"
   {a.name}: {a.status.upper()} ({a.tasks_completed} задач)
"

    def _execute_agent_task(self, agent: SubAgent, task: str, context_agents: List[SubAgent]) -> str:
        """Выполняет задачу агента через его модель"""

        # Собираем контекст от предыдущих агентов
        context = ""
        for a in context_agents:
            if a != agent and a.status == "done" and a.output:
                context += f"
[{a.role.value.upper()} OUTPUT]:
{a.output[:2000]}
"

        prompt = f"""{agent.system_prompt}

КОНТЕКСТ ОТ ДРУГИХ АГЕНТОВ:
{context}

ТВОЯ ЗАДАЧА:
{task}

Выполни задачу профессионально. Верни результат.
"""

        # Создаём провайдер для этой модели
        if agent.provider == "nvidia":
            provider = NvidiaNimProvider(
                api_key=self.brain.api_key,
                model=agent.model_id
            )
        else:
            provider = self.debugger

        messages = [{"role": "user", "content": prompt}]
        response = provider.complete(messages, temperature=0.3)

        return response

    def _call_debugger(self, failed_agent: SubAgent, error: str, original_task: str) -> str:
        """Вызывает OpenRouter дебаггер для анализа ошибки"""

        if not self.debugger:
            return "Дебаггер не настроен"

        prompt = f"""Ты — Senior Debugger. Проанализируй ошибку и дай рекомендации.

Оригинальная задача: {original_task}

Агент: {failed_agent.name}
Модель: {failed_agent.model_id}
Роль: {failed_agent.role.value}

Ошибка:
{error}

Вывод агента перед ошибкой:
{failed_agent.output[:3000]}

Проанализируй:
1. Причина ошибки (root cause)
2. Что пошло не так в логике модели
3. Как исправить (конкретные шаги)
4. Нужна ли другая модель для этой подзадачи
5. Команда для оркестратора

Верни структурированный ответ с JSON:
{{
    "root_cause": "...",
    "fix_steps": ["...", "..."],
    "recommended_model": "...",
    "orchestrator_command": "...",
    "severity": "low|medium|high|critical"
}}
"""

        try:
            messages = [{"role": "user", "content": prompt}]
            response = self.debugger.complete(messages, temperature=0.2)
            return response
        except Exception as e:
            return f"Ошибка дебаггера: {str(e)}"

    def get_status(self) -> Dict[str, Any]:
        """Текущий статус оркестратора"""
        return {
            "rpm": self.rpm_tracker.get_status(),
            "agents": [
                {
                    "name": a.name,
                    "role": a.role.value,
                    "status": a.status,
                    "model": a.model_id,
                    "tasks": a.tasks_completed,
                    "errors": len(a.error_log)
                }
                for a in self.agents
            ],
            "brain_model": self.brain.model if hasattr(self.brain, 'model') else "unknown",
            "debugger_available": self.debugger is not None
        }
