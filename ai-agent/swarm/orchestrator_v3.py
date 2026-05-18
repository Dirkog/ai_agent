"""AI Agent Orchestrator v3 — Autonomous Model Selection
Главный оркестратор САМ выбирает бесплатные NVIDIA модели под задачу.
Не ждёт model_assignments от LLM — принимает решение сам на основе анализа.
"""
import json
import os
import time
import threading
from typing import List, Dict, Any, Optional, Generator, Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from providers.base import BaseProvider, RateLimitError
from providers.openrouter import OpenRouterProvider
from providers.nvidia_nim import NvidiaNimProvider


class AgentRole(Enum):
    ORCHESTRATOR = "orchestrator"
    CODER = "coder"
    REVIEWER = "reviewer"
    TESTER = "tester"
    DEBUGGER = "debugger"
    DEVOPS = "devops"
    SCRUM_MASTER = "scrum"
    ARCHITECT = "architect"
    EXPLAINER = "explainer"
    OPTIMIZER = "optimizer"


# NVIDIA NIM — ВСЕ модели БЕСПЛАТНЫЕ
NVIDIA_MODELS = {
    "deepseek-r1": {
        "id": "deepseek/deepseek-r1-0528",
        "description": "DeepSeek R1 — лучшая для reasoning, математики, алгоритмов",
        "strengths": ["reasoning", "math", "algorithms", "complex_logic", "planning", "debugging"],
        "rpm": 40,
        "context": 128000
    },
    "qwen3-coder": {
        "id": "qwen/qwen3-235b-a22b",
        "description": "Qwen3 235B — специализированная для кодинга, архитектуры",
        "strengths": ["coding", "architecture", "refactoring", "code_review", "design_patterns"],
        "rpm": 40,
        "context": 128000
    },
    "kimi-2-5": {
        "id": "moonshotai/kimi-2.5",
        "description": "Kimi 2.5 — огромный контекст, лучшая для анализа больших файлов",
        "strengths": ["long_context", "analysis", "documentation", "summarization", "large_files"],
        "rpm": 40,
        "context": 256000
    },
    "glm-5-1": {
        "id": "zhipuai/glm-5.1",
        "description": "GLM 5.1 — мультиязычная, хороша для документации и комментариев",
        "strengths": ["multilingual", "documentation", "comments", "general", "chat"],
        "rpm": 40,
        "context": 128000
    },
    "nemotron-vision": {
        "id": "nvidia/nemotron-nano-12b-v2-vl",
        "description": "Nemotron Nano VL — vision-language, анализ UI/скриншотов",
        "strengths": ["vision", "ui_analysis", "screenshots", "multimodal", "frontend"],
        "rpm": 40,
        "context": 32000
    },
    "gpt-oss-120b": {
        "id": "openai/gpt-oss-120b",
        "description": "GPT-OSS-120B — быстрая, для простых задач и quick fixes",
        "strengths": ["fast", "simple_tasks", "quick_fixes", "lightweight", "responses"],
        "rpm": 40,
        "context": 128000
    },
    "sarvam-m": {
        "id": "sarvam/sarvam-m",
        "description": "Sarvam-M — для индийских языков и специализированных задач",
        "strengths": ["indic_languages", "specialized", "niche"],
        "rpm": 40,
        "context": 128000
    },
    "nemotron-70b": {
        "id": "nvidia/llama-3.1-nemotron-70b-instruct",
        "description": "Nemotron 70B — универсальная, хороший баланс скорости/качества",
        "strengths": ["general", "balanced", "coding", "review", "testing"],
        "rpm": 40,
        "context": 128000
    },
    "deepseek-coder": {
        "id": "deepseek-ai/deepseek-coder-33b-instruct",
        "description": "DeepSeek Coder 33B — специально для программирования",
        "strengths": ["coding", "debugging", "algorithm", "data_structures"],
        "rpm": 40,
        "context": 16000
    },
    "qwen-2-5-coder": {
        "id": "qwen/qwen-2.5-coder-32b-instruct",
        "description": "Qwen 2.5 Coder 32B — оптимизирована для кода",
        "strengths": ["coding", "completion", "inline_edit", "refactoring"],
        "rpm": 40,
        "context": 128000
    },
    "mistral-large": {
        "id": "mistralai/mistral-large-instruct-2407",
        "description": "Mistral Large — для ревью и анализа кода",
        "strengths": ["review", "analysis", "security", "best_practices"],
        "rpm": 40,
        "context": 128000
    },
    "llama-3-3-70b": {
        "id": "meta/llama-3.3-70b-instruct",
        "description": "Llama 3.3 70B — для планирования и архитектуры",
        "strengths": ["planning", "architecture", "system_design", "general"],
        "rpm": 40,
        "context": 128000
    },
    "phi-4": {
        "id": "microsoft/phi-4-multimodal-instruct",
        "description": "Phi-4 — для тестов и быстрых задач",
        "strengths": ["testing", "quick_tasks", "multimodal", "lightweight"],
        "rpm": 40,
        "context": 128000
    }
}

# OpenRouter — ТОЛЬКО БЕСПЛАТНЫЕ модели
OPENROUTER_FREE = {
    "deepseek-r1-free": {
        "id": "deepseek/deepseek-r1:free",
        "description": "DeepSeek R1 Free — reasoning для сложного дебаггинга",
        "strengths": ["reasoning", "debugging", "complex_analysis"]
    },
    "llama-4-maverick-free": {
        "id": "meta-llama/llama-4-maverick:free",
        "description": "Llama 4 Maverick Free — для анализа ошибок",
        "strengths": ["analysis", "error_detection", "general"]
    },
    "deepseek-chat-free": {
        "id": "deepseek/deepseek-chat-v3-0324:free",
        "description": "DeepSeek Chat V3 Free — для быстрого дебаггинга",
        "strengths": ["fast_debugging", "quick_fixes", "chat"]
    },
    "qwen3-free": {
        "id": "qwen/qwen3-235b-a22b:free",
        "description": "Qwen3 Free — для анализа кода",
        "strengths": ["code_analysis", "review", "general"]
    },
    "openrouter-free": {
        "id": "openrouter/free",
        "description": "OpenRouter Free Router — случайная бесплатная модель",
        "strengths": ["general", "fallback", "random"]
    }
}


@dataclass
class SubAgent:
    role: AgentRole
    name: str
    model_id: str
    model_key: str
    provider: str
    system_prompt: str
    tasks_completed: int = 0
    status: str = "idle"
    output: str = ""
    error_log: List[str] = field(default_factory=list)
    tokens_used: int = 0
    latency_ms: int = 0


@dataclass
class TaskPlan:
    complexity: int
    roles_needed: List[AgentRole]
    phases: List[Dict[str, Any]]
    estimated_time: int
    reasoning: str
    context_size_estimate: int = 0


class RPMTracker:
    def __init__(self, max_rpm: int = 40):
        self.max_rpm = max_rpm
        self.requests: List[float] = []
        self._lock = threading.Lock()

    def can_request(self) -> bool:
        with self._lock:
            now = time.time()
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
    Главный оркестратор САМ выбирает модели:
    1. Анализирует задачу через LLM (просто текстовый анализ)
    2. Сам решает какие роли нужны (heuristic + LLM insight)
    3. Сам назначает модели из NVIDIA каталога по силам
    4. При ошибке — OpenRouter бесплатный дебаггер
    """

    def __init__(self, nvidia_api_key: str, openrouter_api_key: Optional[str] = None):
        self.brain = NvidiaNimProvider(
            api_key=nvidia_api_key,
            model="deepseek/deepseek-r1-0528"
        )

        self.debugger = None
        if openrouter_api_key:
            self.debugger = OpenRouterProvider(
                api_key=openrouter_api_key,
                model="deepseek/deepseek-r1:free"
            )

        self.rpm_tracker = RPMTracker(max_rpm=40)
        self.agents: List[SubAgent] = []
        self.task_history: List[Dict] = []

        self.on_status_update: Optional[Callable] = None
        self.on_agent_complete: Optional[Callable] = None
        self.on_error: Optional[Callable] = None

    def _score_model_for_role(self, model_key: str, role: AgentRole, 
                               task_desc: str, complexity: int, 
                               context_size: int) -> float:
        """
        Скоринг модели для роли. Чем выше — тем лучше подходит.
        Оркестратор САМ принимает решение, не LLM.
        """
        model = NVIDIA_MODELS[model_key]
        score = 0.0

        # 1. Соответствие роли и strengths модели
        role_keywords = {
            AgentRole.ARCHITECT: ["architecture", "system_design", "planning", "design_patterns"],
            AgentRole.CODER: ["coding", "completion", "inline_edit", "refactoring", "algorithm"],
            AgentRole.REVIEWER: ["review", "analysis", "security", "best_practices"],
            AgentRole.TESTER: ["testing", "quick_tasks", "lightweight"],
            AgentRole.DEBUGGER: ["reasoning", "debugging", "complex_logic", "math"],
            AgentRole.DEVOPS: ["fast", "simple_tasks", "general"],
            AgentRole.SCRUM_MASTER: ["planning", "architecture", "general"],
            AgentRole.EXPLAINER: ["documentation", "comments", "multilingual", "summarization"],
            AgentRole.OPTIMIZER: ["coding", "refactoring", "algorithm", "data_structures"],
        }

        keywords = role_keywords.get(role, ["general"])
        for kw in keywords:
            if kw in model["strengths"]:
                score += 3.0
            # Частичное совпадение
            for strength in model["strengths"]:
                if kw in strength or strength in kw:
                    score += 1.5

        # 2. Контекст — большие файлы нуждаются в большом контексте
        if context_size > 100000:
            if model["context"] >= 256000:
                score += 5.0
            elif model["context"] >= 128000:
                score += 2.0
            else:
                score -= 3.0

        # 3. Сложность — сложные задачи нуждаются в reasoning
        if complexity >= 8:
            if "reasoning" in model["strengths"] or "complex_logic" in model["strengths"]:
                score += 4.0

        # 4. Специфика задачи из описания
        task_lower = task_desc.lower()
        if "refactor" in task_lower and "refactoring" in model["strengths"]:
            score += 2.0
        if "test" in task_lower and "testing" in model["strengths"]:
            score += 2.0
        if "debug" in task_lower and "debugging" in model["strengths"]:
            score += 2.0
        if "ui" in task_lower or "frontend" in task_lower:
            if "vision" in model["strengths"] or "frontend" in model["strengths"]:
                score += 2.0
        if "document" in task_lower or "comment" in task_lower:
            if "documentation" in model["strengths"] or "comments" in model["strengths"]:
                score += 2.0

        # 5. Штраф за маленький контекст для больших задач
        if complexity >= 6 and model["context"] < 64000:
            score -= 2.0

        return score

    def _select_best_model(self, role: AgentRole, task_desc: str, 
                           complexity: int, context_size: int) -> tuple:
        """
        Выбирает лучшую модель для роли.
        Возвращает (model_key, model_id, score)
        """
        best_key = None
        best_score = -999

        for key, model in NVIDIA_MODELS.items():
            score = self._score_model_for_role(key, role, task_desc, complexity, context_size)
            if score > best_score:
                best_score = score
                best_key = key

        return best_key, NVIDIA_MODELS[best_key]["id"], best_score

    def _determine_roles(self, task: str, llm_analysis: str) -> List[AgentRole]:
        """
        Определяет нужные роли. Комбинирует heuristic + insight от LLM.
        """
        task_lower = task.lower()
        roles = []

        # Всегда начинаем с планирования
        roles.append(AgentRole.SCRUM_MASTER)

        # Архитектура для новых проектов
        if any(k in task_lower for k in ["create", "build", "new project", "design", "api", "structure", "architect"]):
            roles.append(AgentRole.ARCHITECT)

        # Кодинг почти всегда нужен
        if not any(k in task_lower for k in ["only review", "just review", "audit", "explain"]):
            roles.append(AgentRole.CODER)

        # Ревью
        if any(k in task_lower for k in ["review", "quality", "clean", "refactor", "improve"]):
            roles.append(AgentRole.REVIEWER)

        # Тесты
        if any(k in task_lower for k in ["test", "coverage", "pytest", "spec"]):
            roles.append(AgentRole.TESTER)

        # Дебаггинг
        if any(k in task_lower for k in ["fix", "bug", "error", "debug", "broken", "crash"]):
            roles.append(AgentRole.DEBUGGER)

        # DevOps
        if any(k in task_lower for k in ["docker", "deploy", "ci/cd", "pipeline", "infra", "kubernetes"]):
            roles.append(AgentRole.DEVOPS)

        # Объяснения
        if any(k in task_lower for k in ["explain", "document", "comment", "docstring", "understand"]):
            roles.append(AgentRole.EXPLAINER)

        # Оптимизация
        if any(k in task_lower for k in ["optimize", "performance", "speed", "memory", "cache"]):
            roles.append(AgentRole.OPTIMIZER)

        # Убираем дубликаты
        seen = set()
        unique = []
        for r in roles:
            if r not in seen:
                seen.add(r)
                unique.append(r)

        return unique

    def _call_brain(self, prompt: str, temperature: float = 0.3) -> str:
        """Вызов главного оркестратора (NVIDIA) с контролем RPM"""
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
        """
        Главный оркестратор анализирует задачу.
        НЕ просит LLM выбрать модели — сам решает.
        """

        # Шаг 1: LLM даёт анализ задачи (сложность, контекст, тип)
        prompt = f"""Ты — Главный Оркестратор AI Agent. Проанализируй задачу.

Задача: {task}

Проанализируй:
1. Сложность задачи (1-10)
2. Примерный размер контекста в токенах (оцени по длине задачи)
3. Тип задачи (coding, debugging, architecture, testing, documentation, etc.)
4. Ключевые требования
5. Потенциальные сложности

Верни ТОЛЬКО JSON:
{{
    "complexity": 7,
    "context_size_estimate": 5000,
    "task_type": "coding",
    "key_requirements": ["REST API", "FastAPI", "authentication"],
    "potential_challenges": ["JWT implementation", "database schema"],
    "estimated_time": 15,
    "reasoning": "Задача средней сложности — нужен API с авторизацией"
}}
"""

        response = self._call_brain(prompt, temperature=0.2)

        # Парсим анализ
        try:
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group())
            else:
                analysis = json.loads(response)
        except Exception:
            analysis = {
                "complexity": 5,
                "context_size_estimate": len(task) * 4,
                "task_type": "general",
                "key_requirements": [],
                "potential_challenges": [],
                "estimated_time": 10,
                "reasoning": "Default analysis"
            }

        complexity = analysis.get("complexity", 5)
        context_size = analysis.get("context_size_estimate", len(task) * 4)

        # Шаг 2: САМ определяем роли (heuristic)
        roles = self._determine_roles(task, response)

        # Шаг 3: САМ назначаем модели (scoring)
        phases = []
        for role in roles:
            # Находим лучшую модель для роли
            model_key, model_id, score = self._select_best_model(
                role, 
                analysis.get("task_type", ""),
                complexity,
                context_size
            )

            # Определяем зависимости
            depends = []
            if role == AgentRole.CODER and AgentRole.ARCHITECT in roles:
                depends = ["architect"]
            elif role == AgentRole.TESTER and AgentRole.CODER in roles:
                depends = ["coder"]
            elif role == AgentRole.REVIEWER and AgentRole.CODER in roles:
                depends = ["coder"]
            elif role == AgentRole.DEBUGGER:
                # Дебаггер может работать параллельно или после
                depends = []

            phases.append({
                "role": role.value,
                "task": self._get_task_for_role(role, task),
                "depends_on": depends,
                "model_key": model_key,
                "model_id": model_id,
                "model_score": score,
                "estimated_tokens": min(context_size, model["context"] // 2)
            })

        return TaskPlan(
            complexity=complexity,
            roles_needed=roles,
            phases=phases,
            estimated_time=analysis.get("estimated_time", 10),
            reasoning=analysis.get("reasoning", ""),
            context_size_estimate=context_size
        )

    def _get_task_for_role(self, role: AgentRole, original_task: str) -> str:
        """Генерирует специфичную задачу для роли"""
        role_tasks = {
            AgentRole.SCRUM_MASTER: f"Разбей задачу на подзадачи с acceptance criteria: {original_task}",
            AgentRole.ARCHITECT: f"Спроектируй архитектуру и структуру для: {original_task}",
            AgentRole.CODER: f"Напиши production-ready код для: {original_task}",
            AgentRole.REVIEWER: f"Проведи code review с security и performance анализом",
            AgentRole.TESTER: f"Напиши comprehensive тесты с edge cases",
            AgentRole.DEBUGGER: f"Найди и исправь потенциальные баги",
            AgentRole.DEVOPS: f"Настрой Docker, CI/CD и deployment",
            AgentRole.EXPLAINER: f"Напиши документацию и комментарии",
            AgentRole.OPTIMIZER: f"Оптимизируй производительность и память",
        }
        return role_tasks.get(role, original_task)

    def create_agents(self, plan: TaskPlan) -> List[SubAgent]:
        """Создаёт агентов по плану — модели уже выбраны оркестратором"""
        self.agents = []

        for phase in plan.phases:
            role_str = phase["role"]
            try:
                role = AgentRole(role_str)
            except ValueError:
                continue

            model_key = phase["model_key"]
            model_id = phase["model_id"]

            agent = SubAgent(
                role=role,
                name=f"{role_str}_{model_key}",
                model_id=model_id,
                model_key=model_key,
                provider="nvidia",
                system_prompt=self._get_role_prompt(role)
            )
            self.agents.append(agent)

        return self.agents

    def _get_role_prompt(self, role: AgentRole) -> str:
        prompts = {
            AgentRole.ORCHESTRATOR: "Ты — Главный Оркестратор. Анализируй, планируй, назначай.",
            AgentRole.ARCHITECT: "Ты — Software Architect. Проектируй чистые, масштабируемые системы. Только дизайн, без имплементации.",
            AgentRole.CODER: "Ты — Senior Developer. Пиши production-ready код. Follow best practices, SOLID, DRY.",
            AgentRole.REVIEWER: "Ты — Code Reviewer. Ищи баги, уязвимости, проблемы производительности. Давай конкретные строки.",
            AgentRole.TESTER: "Ты — QA Engineer. Пиши comprehensive тесты. Coverage > 80%. Edge cases.",
            AgentRole.DEBUGGER: "Ты — Debugger. Анализируй ошибки, находи root cause. Предлагай фиксы с объяснением.",
            AgentRole.DEVOPS: "Ты — DevOps. Docker, CI/CD, мониторинг. Infrastructure as Code.",
            AgentRole.SCRUM_MASTER: "Ты — Project Manager. Декомпозируй задачи, оценивай, трека прогресс. Acceptance criteria.",
            AgentRole.EXPLAINER: "Ты — Technical Writer. Объясняй сложное просто. Документация, комментарии, docstrings.",
            AgentRole.OPTIMIZER: "Ты — Performance Engineer. Оптимизируй код. Профилирование, алгоритмы, memory.",
        }
        return prompts.get(role, "Выполни свою роль профессионально.")

    def run_task(self, task: str) -> Generator[str, None, None]:
        """Главный метод — запускает полный workflow"""

        yield f"🧠 [Оркестратор] Анализирую задачу...\n"
        yield f"📋 Задача: {task[:200]}...\n"

        # Шаг 1: Анализ (оркестратор САМ решает)
        plan = self.analyze_task(task)
        yield f"\n📊 Анализ завершён:\n"
        yield f"   Сложность: {plan.complexity}/10\n"
        yield f"   Роли: {[r.value for r in plan.roles_needed]}\n"
        yield f"   Контекст: ~{plan.context_size_estimate} токенов\n"
        yield f"   Время: ~{plan.estimated_time} мин\n"
        yield f"   Логика: {plan.reasoning}\n"

        # Шаг 2: Показываем выбор моделей (оркестратор САМ выбрал)
        yield f"\n🎯 Модели выбраны оркестратором:\n"
        for phase in plan.phases:
            model_key = phase["model_key"]
            model_info = NVIDIA_MODELS[model_key]
            score = phase["model_score"]
            yield f"   • {phase['role'].upper()} → {model_key} ({model_info['id']})\n"
            yield f"     Почему: {model_info['description']}\n"
            yield f"     Score: {score:.1f} | Контекст: {model_info['context']}\n"

        # Шаг 3: Создаём агентов
        agents = self.create_agents(plan)
        yield f"\n👥 Создано агентов: {len(agents)}\n"

        # Шаг 4: Выполняем фазы
        completed_phases = set()

        for phase in plan.phases:
            role_str = phase["role"]
            phase_task = phase["task"]
            depends = phase["depends_on"]
            est_tokens = phase["estimated_tokens"]

            # Ждём зависимости
            if depends:
                yield f"\n⏳ Жду завершения: {depends}\n"
                while not all(d in completed_phases for d in depends):
                    time.sleep(0.5)

            # Находим агента
            agent = next((a for a in agents if a.role.value == role_str), None)
            if not agent:
                yield f"⚠️ Агент {role_str} не найден, пропускаю\n"
                continue

            yield f"\n{'='*60}\n"
            yield f"🚀 Фаза: {role_str.upper()} — {phase_task}\n"
            yield f"🤖 Модель: {agent.model_id}\n"
            yield f"📊 Оценка токенов: {est_tokens}\n"
            yield f"{'='*60}\n"

            agent.status = "working"

            try:
                result = self._execute_agent_task(agent, phase_task, agents)
                agent.output = result
                agent.status = "done"
                agent.tasks_completed += 1

                yield f"\n✅ {agent.name} завершил\n"
                yield f"📤 Результат: {result[:500]}...\n"

                completed_phases.add(role_str)

                if self.on_agent_complete:
                    self.on_agent_complete(agent)

            except Exception as e:
                agent.status = "error"
                agent.error_log.append(str(e))

                yield f"\n❌ ОШИБКА в {agent.name}: {str(e)}\n"

                # Дебаггер (OpenRouter бесплатный)
                if self.debugger:
                    yield f"\n🔍 Вызываю дебаггера (OpenRouter FREE)...\n"
                    debug_result = self._call_debugger(agent, str(e), task)
                    yield f"🩺 Диагноз: {debug_result[:1000]}...\n"
                else:
                    yield f"⚠️ Дебаггер не настроен\n"

        # Итог
        yield f"\n{'='*60}\n"
        yield f"🏁 ВСЕ ФАЗЫ ЗАВЕРШЕНЫ\n"
        yield f"{'='*60}\n"

        success = sum(1 for a in agents if a.status == "done")
        errors = sum(1 for a in agents if a.status == "error")

        yield f"\n📊 Статистика:\n"
        yield f"   ✅ Успешно: {success}/{len(agents)}\n"
        yield f"   ❌ Ошибок: {errors}\n"
        yield f"   🔄 RPM использовано: {self.rpm_tracker.get_status()}\n"

        for a in agents:
            yield f"\n   {a.name} ({a.model_key}): {a.status.upper()}\n"
            yield f"      Задач: {a.tasks_completed} | Токенов: {a.tokens_used}\n"

    def _execute_agent_task(self, agent: SubAgent, task: str, context_agents: List[SubAgent]) -> str:
        """Выполняет задачу агента через его модель NVIDIA"""

        context = ""
        for a in context_agents:
            if a != agent and a.status == "done" and a.output:
                context += f"\n[{a.role.value.upper()} OUTPUT]:\n{a.output[:2000]}\n"

        prompt = f"""{agent.system_prompt}

КОНТЕКСТ ОТ ДРУГИХ АГЕНТОВ:
{context}

ТВОЯ ЗАДАЧА:
{task}

Выполни задачу профессионально. Верни результат.
"""

        provider = NvidiaNimProvider(
            api_key=self.brain.api_key,
            model=agent.model_id
        )

        while not self.rpm_tracker.can_request():
            time.sleep(self.rpm_tracker.wait_time())
        self.rpm_tracker.add_request()

        messages = [{"role": "user", "content": prompt}]
        start = time.time()
        response = provider.complete(messages, temperature=0.3)
        agent.latency_ms = int((time.time() - start) * 1000)
        agent.tokens_used = len(prompt) // 4 + len(response) // 4

        return response

    def _call_debugger(self, failed_agent: SubAgent, error: str, original_task: str) -> str:
        """Вызывает OpenRouter дебаггер (бесплатная модель)"""

        if not self.debugger:
            return "Дебаггер не настроен"

        prompt = f"""Ты — Senior Debugger. Проанализируй ошибку.

Оригинальная задача: {original_task}

Агент: {failed_agent.name}
Модель NVIDIA: {failed_agent.model_id}
Роль: {failed_agent.role.value}

Ошибка:
{error}

Вывод агента:
{failed_agent.output[:3000]}

Проанализируй и дай рекомендации.
"""

        try:
            messages = [{"role": "user", "content": prompt}]
            response = self.debugger.complete(messages, temperature=0.2)
            return response
        except Exception as e:
            return f"Ошибка дебаггера: {str(e)}"

    def get_status(self) -> Dict[str, Any]:
        return {
            "rpm": self.rpm_tracker.get_status(),
            "agents": [
                {
                    "name": a.name,
                    "role": a.role.value,
                    "status": a.status,
                    "model_key": a.model_key,
                    "model_id": a.model_id,
                    "tasks": a.tasks_completed,
                    "errors": len(a.error_log),
                    "tokens": a.tokens_used,
                    "latency_ms": a.latency_ms
                }
                for a in self.agents
            ],
            "brain_model": self.brain.model if hasattr(self.brain, 'model') else "unknown",
            "debugger_available": self.debugger is not None,
            "debugger_model": self.debugger.model if self.debugger else None,
            "nvidia_models_available": len(NVIDIA_MODELS),
            "openrouter_free_models": len(OPENROUTER_FREE)
        }
