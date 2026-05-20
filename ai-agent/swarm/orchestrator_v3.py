"""AI Agent Orchestrator v3 — Smart Model Router with Ensemble Support
Главный оркестратор (NVIDIA NIM) назначает бесплатные модели ролям.
OpenRouter используется ТОЛЬКО для дебаггера (анализ расхождений).
Kimi K2.6 — ЛОКАЛЬНАЯ модель через vLLM/llama.cpp/Ollama (open-weight).
v6 update: Fixed provider instantiation, added ensemble support, proper ProviderConfig usage
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

from config import CONFIG, ProviderConfig
from providers.base import BaseProvider, RateLimitError
from providers.openrouter import OpenRouterProvider
from providers.nvidia_nim import NvidiaNimProvider
from providers.ensemble_provider import EnsembleProvider


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


# NVIDIA NIM — ВСЕ модели БЕСПЛАТНЫЕ (80+ models, 40 RPM, no credit card)
NVIDIA_FREE_MODELS = {
    "deepseek-r1": {
        "id": "deepseek/deepseek-r1-0528",
        "description": "DeepSeek R1 — лучшая для reasoning, математики, алгоритмов",
        "strengths": ["reasoning", "math", "algorithms", "complex_logic", "planning"],
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
    "gemma-4-31b": {
        "id": "google/gemma-4-31b-it",
        "description": "Gemma 4 31B — для локального кодинга и агентов",
        "strengths": ["coding", "agent", "local", "edge"],
        "rpm": 40,
        "context": 128000
    },
}

# LOCAL MODELS — Open-weight, downloadable, run via vLLM/llama.cpp/Ollama
LOCAL_MODELS = {
    "kimi-k2.6": {
        "id": "moonshotai/Kimi-K2.6",
        "description": "Kimi K2.6 — 1T params, 32B active, 256K context, open-weight. Лучшая для кодинга и агентов.",
        "strengths": ["coding", "long_horizon", "agent", "swarm", "multimodal", "reasoning"],
        "context": 256000,
        "vram_gb": 48,  # INT4 quantization, 4x H100 or dual Mac Studio 512GB
        "quantization": "INT4",
        "engine": "vLLM/SGLang/KTransformers/llama.cpp",
        "license": "Modified MIT"
    },
    "kimi-k2.5": {
        "id": "moonshotai/Kimi-K2.5",
        "description": "Kimi K2.5 — предыдущая версия, 1T params, хороша для кодинга",
        "strengths": ["coding", "reasoning", "long_context"],
        "context": 128000,
        "vram_gb": 48,
        "quantization": "INT4",
        "engine": "vLLM/llama.cpp",
        "license": "Modified MIT"
    },
    "deepseek-v4-pro": {
        "id": "deepseek-ai/deepseek-v4-pro",
        "description": "DeepSeek V4 Pro — 48GB VRAM, 1M контекст, reasoning",
        "strengths": ["reasoning", "architecture", "planning", "math"],
        "context": 1000000,
        "vram_gb": 48,
        "quantization": "Q4_K_M",
        "engine": "vLLM",
        "license": "Custom"
    },
    "qwen3.5-122b": {
        "id": "qwen/qwen3.5-122b-a10b",
        "description": "Qwen 3.5 122B — 24GB VRAM, кодинг, reasoning",
        "strengths": ["coding", "reasoning", "agent"],
        "context": 128000,
        "vram_gb": 24,
        "quantization": "Q4_K_M",
        "engine": "vLLM/Ollama",
        "license": "Custom"
    },
    "mistral-small-4": {
        "id": "mistralai/mistral-small-4-119b-2603",
        "description": "Mistral Small 4 — 48GB VRAM, кодинг, мультимодал",
        "strengths": ["coding", "multimodal", "reasoning"],
        "context": 256000,
        "vram_gb": 48,
        "quantization": "Q4_K_M",
        "engine": "vLLM",
        "license": "Apache 2.0"
    },
    "llama-3.3-70b": {
        "id": "meta/llama-3.3-70b-instruct",
        "description": "Llama 3.3 70B — 48GB VRAM, планирование, чат",
        "strengths": ["planning", "chat", "general"],
        "context": 128000,
        "vram_gb": 48,
        "quantization": "Q4_K_M",
        "engine": "vLLM/Ollama",
        "license": "Llama 3.1"
    },
    "phi-4-multimodal": {
        "id": "microsoft/phi-4-multimodal-instruct",
        "description": "Phi-4 Multimodal — 12GB VRAM, тесты, мультимодал",
        "strengths": ["testing", "multimodal", "lightweight"],
        "context": 128000,
        "vram_gb": 12,
        "quantization": "Q4_K_M",
        "engine": "Ollama",
        "license": "MIT"
    },
    "gemma-4-31b": {
        "id": "google/gemma-4-31b-it",
        "description": "Gemma 4 31B — 24GB VRAM, кодинг, агент",
        "strengths": ["coding", "agent", "edge"],
        "context": 128000,
        "vram_gb": 24,
        "quantization": "Q4_K_M",
        "engine": "vLLM/Ollama",
        "license": "Gemma"
    },
}

# OpenRouter — ТОЛЬКО для дебаггера (анализ расхождений)
OPENROUTER_DEBUG_MODELS = {
    "deepseek-r1-free": {
        "id": "deepseek/deepseek-r1:free",
        "description": "DeepSeek R1 Free — reasoning для сложного дебаггинга",
        "strengths": ["reasoning", "debugging", "complex_analysis"]
    },
    "llama-4-maverick-free": {
        "id": "meta-llama/llama-4-maverick:free",
        "description": "Llama 4 Maverick Free — для анализа ошибок",
        "strengths": ["analysis", "error_detection", "general"]
    }
}


@dataclass
class SubAgent:
    role: AgentRole
    name: str
    model_id: str
    provider: str  # "nvidia" | "local" | "ensemble"
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
    model_assignments: Dict[str, str]
    phases: List[Dict[str, Any]]
    estimated_time: int
    reasoning: str
    context_size_estimate: int = 0
    use_local: bool = False  # NEW: Whether to use local models


class RPMTracker:
    """Отслеживает RPM для NVIDIA (40/мин)"""
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
    Главный оркестратор:
    - NVIDIA NIM: ВСЕ модели бесплатные (80+ models, 40 RPM)
    - LOCAL: Kimi K2.6, DeepSeek V4, Qwen 3.5 и др. (open-weight, vLLM/llama.cpp)
    - OpenRouter: ТОЛЬКО для дебаггера (анализ расхождений)
    - Ensemble: Local + API параллельно
    - Автоматический выбор модели под задачу
    - RPM контроль
    """

    def __init__(self, nvidia_api_key: str, openrouter_api_key: Optional[str] = None,
                 use_ensemble: bool = False, ollama_url: str = "http://localhost:11434/v1",
                 vllm_url: Optional[str] = None, prefer_local: bool = False,
                 available_vram_gb: int = 48):

        self.prefer_local = prefer_local
        self.available_vram = available_vram_gb

        # FIX: Create proper ProviderConfig for brain
        brain_cfg = ProviderConfig(
            name="nvidia_nim",
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=nvidia_api_key,
            model="deepseek/deepseek-r1-0528",
            priority=1,
            rate_limit_rpm=40,
            is_free=True,
            timeout=120,
            max_retries=3
        )
        self.brain = NvidiaNimProvider(brain_cfg)

        # FIX: Create proper ProviderConfig for debugger
        self.debugger = None
        if openrouter_api_key:
            debug_cfg = ProviderConfig(
                name="openrouter",
                base_url="https://openrouter.ai/api/v1",
                api_key=openrouter_api_key,
                model="deepseek/deepseek-r1:free",
                priority=2,
                rate_limit_rpm=20,
                is_free=False,
                timeout=120,
                max_retries=3
            )
            self.debugger = OpenRouterProvider(debug_cfg)

        # Ensemble provider
        self.ensemble = None
        if use_ensemble and nvidia_api_key:
            self.ensemble = EnsembleProvider(
                nvidia_api_key=nvidia_api_key,
                nvidia_model="deepseek/deepseek-r1-0528",
                ollama_base_url=ollama_url,
                ollama_model="codellama:34b"
            )

        # Local provider (vLLM)
        self.local_provider = None
        if vllm_url:
            local_cfg = ProviderConfig(
                name="vllm",
                base_url=vllm_url,
                api_key=None,
                model="moonshotai/Kimi-K2.6",
                priority=0,
                rate_limit_rpm=9999,
                is_free=True,
                timeout=300,
                max_retries=1
            )
            from providers.vllm_provider import VLLMProvider
            self.local_provider = VLLMProvider(local_cfg)

        # RPM трекер для NVIDIA
        self.rpm_tracker = RPMTracker(max_rpm=40)

        self.agents: List[SubAgent] = []
        self.task_history: List[Dict] = []

        # Callbacks
        self.on_status_update: Optional[Callable] = None
        self.on_agent_complete: Optional[Callable] = None
        self.on_error: Optional[Callable] = None

    def _select_model_for_role(self, role: AgentRole, task_description: str,
                             complexity: int, context_size: int, use_local: bool = False) -> Tuple[str, str]:
        """
        Выбирает лучшую модель для роли.
        Returns: (model_id, provider_type)
        provider_type: "nvidia" | "local" | "ensemble"
        """
        role_str = role.value

        # If local preferred and enough VRAM
        if use_local and self.available_vram >= 48:
            # For coding/architect — Kimi K2.6
            if role in (AgentRole.CODER, AgentRole.ARCHITECT, AgentRole.ORCHESTRATOR):
                if context_size > 100000:
                    return (LOCAL_MODELS["kimi-k2.6"]["id"], "local")
                return (LOCAL_MODELS["kimi-k2.6"]["id"], "local")

            # For reasoning — DeepSeek V4
            if role in (AgentRole.DEBUGGER, AgentRole.OPTIMIZER) or complexity >= 8:
                return (LOCAL_MODELS["deepseek-v4-pro"]["id"], "local")

            # For testing — Phi-4
            if role == AgentRole.TESTER:
                return (LOCAL_MODELS["phi-4-multimodal"]["id"], "local")

        # For больших контекстов — Kimi K2.6 local (256K)
        if context_size > 100000 and self.available_vram >= 48:
            return (LOCAL_MODELS["kimi-k2.6"]["id"], "local")

        # NVIDIA NIM models (fallback or API-only)
        if role in (AgentRole.ARCHITECT, AgentRole.SCRUM_MASTER, AgentRole.ORCHESTRATOR) or complexity >= 8:
            if "reasoning" in task_description.lower() or "algorithm" in task_description.lower():
                return (NVIDIA_FREE_MODELS["deepseek-r1"]["id"], "nvidia")
            return (NVIDIA_FREE_MODELS["llama-3-3-70b"]["id"], "nvidia")

        if role == AgentRole.CODER:
            if "refactor" in task_description.lower() or "optimize" in task_description.lower():
                return (NVIDIA_FREE_MODELS["qwen-2-5-coder"]["id"], "nvidia")
            if "complex" in task_description.lower() or "algorithm" in task_description.lower():
                return (NVIDIA_FREE_MODELS["deepseek-coder"]["id"], "nvidia")
            return (NVIDIA_FREE_MODELS["qwen3-coder"]["id"], "nvidia")

        if role == AgentRole.REVIEWER:
            return (NVIDIA_FREE_MODELS["mistral-large"]["id"], "nvidia")

        if role == AgentRole.TESTER:
            return (NVIDIA_FREE_MODELS["phi-4"]["id"], "nvidia")

        if role == AgentRole.DEBUGGER:
            return (NVIDIA_FREE_MODELS["deepseek-r1"]["id"], "nvidia")

        if role == AgentRole.DEVOPS:
            return (NVIDIA_FREE_MODELS["llama-3-3-70b"]["id"], "nvidia")

        if role == AgentRole.EXPLAINER:
            return (NVIDIA_FREE_MODELS["llama-3-3-70b"]["id"], "nvidia")

        if role == AgentRole.OPTIMIZER:
            return (NVIDIA_FREE_MODELS["deepseek-r1"]["id"], "nvidia")

        # Default
        return (NVIDIA_FREE_MODELS["nemotron-70b"]["id"], "nvidia")

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
            # FIX: Use complete() which returns string
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
        """Главный оркестратор анализирует задачу и выбирает модели"""
        context_size = len(task) * 4

        # Determine if local models should be used
        use_local = self.prefer_local and self.available_vram >= 48

        prompt = f"""Ты — Главный Оркестратор AI Agent. Проанализируй задачу и составь план.

Доступные БЕСПЛАТНЫЕ модели NVIDIA NIM (API, 40 RPM):
{json.dumps(NVIDIA_FREE_MODELS, indent=2, ensure_ascii=False)}

Доступные ЛОКАЛЬНЫЕ модели (Open-weight, vLLM/llama.cpp):
{json.dumps(LOCAL_MODELS, indent=2, ensure_ascii=False)}

Доступная VRAM: {self.available_vram}GB
Предпочитать локальные: {use_local}

Задача: {task}

Проанализируй:
1. Сложность задачи (1-10)
2. Какие роли нужны (coder, reviewer, tester, debugger, devops, scrum, architect, explainer, optimizer)
3. Какую модель назначить каждой роли (NVIDIA API или Local)
4. Порядок выполнения фаз
5. Оцени размер контекста в токенах
6. Оцени время в минутах

Верни ТОЛЬКО JSON:
{{
    "complexity": 7,
    "roles_needed": ["scrum", "architect", "coder", "tester", "reviewer"],
    "model_assignments": {{
        "scrum": "llama-3-3-70b",
        "architect": "deepseek-r1",
        "coder": "qwen3-coder",
        "tester": "phi-4",
        "reviewer": "mistral-large"
    }},
    "use_local": false,
    "phases": [
        {{"role": "scrum", "task": "Разбить на подзадачи", "depends_on": [], "estimated_tokens": 2000}},
        {{"role": "architect", "task": "Спроектировать архитектуру", "depends_on": ["scrum"], "estimated_tokens": 4000}},
        {{"role": "coder", "task": "Написать код", "depends_on": ["architect"], "estimated_tokens": 8000}},
        {{"role": "tester", "task": "Написать тесты", "depends_on": ["coder"], "estimated_tokens": 3000}},
        {{"role": "reviewer", "task": "Ревью кода", "depends_on": ["coder"], "estimated_tokens": 5000}}
    ],
    "estimated_time": 15,
    "context_size_estimate": 22000,
    "reasoning": "Задача средней сложности, нужен план + архитектура + код + тесты + ревью"
}}
"""

        response = self._call_brain(prompt, temperature=0.2)

        try:
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                plan_data = json.loads(json_match.group())
            else:
                plan_data = json.loads(response)

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
                reasoning=plan_data.get("reasoning", ""),
                context_size_estimate=plan_data.get("context_size_estimate", 0),
                use_local=plan_data.get("use_local", use_local)
            )
        except Exception as e:
            return TaskPlan(
                complexity=5,
                roles_needed=[AgentRole.CODER],
                model_assignments={"coder": "nemotron-70b"},
                phases=[{"role": "coder", "task": task, "depends_on": [], "estimated_tokens": 4000}],
                estimated_time=10,
                reasoning=f"Fallback: {str(e)}",
                context_size_estimate=len(task) * 4,
                use_local=use_local
            )

    def create_agents(self, plan: TaskPlan) -> List[SubAgent]:
        """Создаёт агентов по плану с автоматическим выбором моделей"""
        self.agents = []

        for role in plan.roles_needed:
            role_str = role.value

            # Получаем модель из плана или автовыбор
            model_key = plan.model_assignments.get(role_str)

            if model_key and model_key in NVIDIA_FREE_MODELS:
                model_info = NVIDIA_FREE_MODELS[model_key]
                provider = "nvidia"
            elif model_key and model_key in LOCAL_MODELS:
                model_info = LOCAL_MODELS[model_key]
                provider = "local"
            else:
                task_desc = ""
                for phase in plan.phases:
                    if phase.get("role") == role_str:
                        task_desc = phase.get("task", "")
                        break
                model_id, provider = self._select_model_for_role(
                    role, task_desc, plan.complexity, plan.context_size_estimate, plan.use_local
                )
                model_key = "custom"
                model_info = {"id": model_id, "description": "Auto-selected", "strengths": []}

            agent = SubAgent(
                role=role,
                name=f"{role_str}_{model_key}",
                model_id=model_info["id"],
                provider=provider,
                system_prompt=self._get_role_prompt(role)
            )
            self.agents.append(agent)

        return self.agents

    def _get_role_prompt(self, role: AgentRole) -> str:
        prompts = {
            AgentRole.ORCHESTRATOR: "Ты — Главный Оркестратор. Анализируй, планируй, назначай.",
            AgentRole.ARCHITECT: "Ты — Software Architect. Проектируй чистые, масштабируемые системы. Только дизайн, без имплементации.",
            AgentRole.CODER: "Ты — Senior Developer. Пиши production-ready код. SOLID, DRY, KISS.",
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
        yield f"💻 VRAM: {self.available_vram}GB | Local: {self.prefer_local}\n"

        # Шаг 1: Анализ
        plan = self.analyze_task(task)
        yield f"\n📊 Анализ:\n"
        yield f"  Сложность: {plan.complexity}/10\n"
        yield f"  Роли: {[r.value for r in plan.roles_needed]}\n"
        yield f"  Модели: {plan.model_assignments}\n"
        yield f"  Локальные: {plan.use_local}\n"
        yield f"  Контекст: ~{plan.context_size_estimate} токенов\n"
        yield f"  Время: ~{plan.estimated_time} мин\n"
        yield f"  Логика: {plan.reasoning}\n"

        # Шаг 2: Создаём агентов
        agents = self.create_agents(plan)
        yield f"\n👥 Создано агентов: {len(agents)}\n"
        for a in agents:
            model_name = a.model_id.split("/")[-1] if "/" in a.model_id else a.model_id
            yield f"  • {a.name} → {model_name} ({a.provider})\n"

        # Шаг 3: Выполняем фазы
        completed_phases = set()

        for phase in plan.phases:
            role_str = phase["role"]
            phase_task = phase["task"]
            depends = phase.get("depends_on", [])
            est_tokens = phase.get("estimated_tokens", 4000)

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
            yield f"🤖 Модель: {agent.model_id} ({agent.provider})\n"
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

                # Дебаггер (OpenRouter)
                if self.debugger:
                    yield f"\n🔍 Вызываю дебаггера (OpenRouter)...\n"
                    debug_result = self._call_debugger(agent, str(e), task)
                    yield f"🩺 Диагноз: {debug_result[:1000]}...\n"
                    yield f"\n🔄 Перепланирую с учётом диагноза...\n"
                else:
                    yield f"⚠️ Дебаггер не настроен\n"

        # Итог
        yield f"\n{'='*60}\n"
        yield f"🏁 ВСЕ ФАЗЫ ЗАВЕРШЕНЫ\n"
        yield f"{'='*60}\n"

        success = sum(1 for a in agents if a.status == "done")
        errors = sum(1 for a in agents if a.status == "error")

        yield f"\n📊 Статистика:\n"
        yield f"  ✅ Успешно: {success}/{len(agents)}\n"
        yield f"  ❌ Ошибок: {errors}\n"
        yield f"  🔄 RPM использовано: {self.rpm_tracker.get_status()}\n"

        for a in agents:
            model_name = a.model_id.split("/")[-1] if "/" in a.model_id else a.model_id
            yield f"\n  {a.name} ({model_name}): {a.status.upper()} ({a.tasks_completed} задач)\n"

    def _execute_agent_task(self, agent: SubAgent, task: str, context_agents: List[SubAgent]) -> str:
        """Выполняет задачу агента через его модель"""

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

        start = time.time()
        messages = [{"role": "user", "content": prompt}]

        if agent.provider == "local" and self.local_provider:
            # Use local provider (vLLM with Kimi K2.6)
            response = self.local_provider.complete(messages, temperature=0.3)
        elif agent.provider == "nvidia":
            # Use NVIDIA NIM
            # FIX: Create proper ProviderConfig
            agent_cfg = ProviderConfig(
                name="nvidia_nim",
                base_url="https://integrate.api.nvidia.com/v1",
                api_key=self.brain.config.api_key,
                model=agent.model_id,
                priority=1,
                rate_limit_rpm=40,
                is_free=True,
                timeout=120,
                max_retries=3
            )
            from providers.nvidia_nim import NvidiaNimProvider
            provider = NvidiaNimProvider(agent_cfg)

            # RPM контроль
            while not self.rpm_tracker.can_request():
                time.sleep(self.rpm_tracker.wait_time())
            self.rpm_tracker.add_request()

            response = provider.complete(messages, temperature=0.3)
        else:
            # Fallback to brain
            response = self.brain.complete(messages, temperature=0.3)

        agent.latency_ms = int((time.time() - start) * 1000)
        agent.tokens_used = len(prompt) // 4 + len(response) // 4

        return response

    def _call_debugger(self, failed_agent: SubAgent, error: str, original_task: str) -> str:
        """Вызывает OpenRouter дебаггер (анализ расхождений, не генерация)"""

        if not self.debugger:
            return "Дебаггер не настроен"

        prompt = f"""Ты — Senior Debug Analyst. Проанализируй ошибку и дай рекомендации.

Оригинальная задача: {original_task}

Агент: {failed_agent.name}
Модель: {failed_agent.model_id} ({failed_agent.provider})
Роль: {failed_agent.role.value}

Ошибка:
{error}

Вывод агента перед ошибкой:
{failed_agent.output[:3000]}

Проанализируй:
1. Причина ошибки (root cause)
2. Что пошло не так в логике модели
3. Как исправить (конкретные шаги)
4. Нужна ли другая модель для этой подзадачи (NVIDIA или Local)
5. Рекомендации для оркестратора

Верни структурированный ответ.
"""

        try:
            messages = [{"role": "user", "content": prompt}]
            # FIX: Use complete() which returns string
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
                    "model": a.model_id,
                    "provider": a.provider,
                    "tasks": a.tasks_completed,
                    "errors": len(a.error_log),
                    "tokens": a.tokens_used,
                    "latency_ms": a.latency_ms
                }
                for a in self.agents
            ],
            "brain_model": self.brain.config.model,
            "debugger_available": self.debugger is not None,
            "debugger_model": self.debugger.config.model if self.debugger else None,
            "ensemble_available": self.ensemble is not None,
            "local_available": self.local_provider is not None,
            "nvidia_models_available": len(NVIDIA_FREE_MODELS),
            "local_models_available": len(LOCAL_MODELS),
            "available_vram": self.available_vram,
            "prefer_local": self.prefer_local,
        }
