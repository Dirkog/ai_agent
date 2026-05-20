"""Role Assigner — умное назначение моделей под 20 ролей
Интегрируется с orchestrator_v3 для автоматического назначения.
v6 update: Kimi K2.6 как главная локальная модель, реальные open-weight модели
"""
from enum import Enum
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from pathlib import Path


class AgentRole(Enum):
    """20 ролей агента"""
    ORCHESTRATOR = "orchestrator"           # Главный, планирование
    SCRUM_MASTER = "scrum"                  # Декомпозиция, спринты
    ARCHITECT = "architect"                 # System design, паттерны
    CODER = "coder"                         # Генерация кода
    CODE_REVIEWER = "reviewer"              # Security, best practices
    TESTER = "tester"                       # Тесты, edge cases
    DEBUGGER = "debugger"                   # Поиск багов, root cause
    REFACTORER = "refactorer"               # Переписывание, clean code
    EXPLAINER = "explainer"                 # Объяснение сложного кода
    DOCS_WRITER = "docs_writer"             # README, API docs
    SECURITY_AUDITOR = "security"           # Аудит, guardrails
    UI_FRONTEND = "ui_frontend"             # HTML/CSS/JS, React
    DEVOPS = "devops"                       # Docker, CI/CD, K8s
    DATABASE = "database"                   # SQL, миграции
    API_DESIGNER = "api_designer"           # REST, GraphQL, OpenAPI
    PERFORMANCE = "performance"             # Профилирование, оптимизация
    VISION = "vision"                       # Анализ UI, скриншоты
    EDGE_FAST = "edge"                      # Быстрые задачи, autocomplete
    REASONING = "reasoning"                 # Сложная логика, математика
    MULTIMODAL = "multimodal"             # Аудио, изображения, видео


# NVIDIA NIM модели (Free Endpoint, 40 RPM) — API-only
NVIDIA_MODELS = {
    "deepseek-r1": "deepseek/deepseek-r1-0528",
    "qwen3-coder": "qwen/qwen3-235b-a22b",
    "mistral-large": "mistralai/mistral-large-instruct-2407",
    "llama-3-3-70b": "meta/llama-3.3-70b-instruct",
    "phi-4": "microsoft/phi-4-multimodal-instruct",
    "nemotron-70b": "nvidia/llama-3.1-nemotron-70b-instruct",
    "deepseek-coder": "deepseek-ai/deepseek-coder-33b-instruct",
    "qwen-2-5-coder": "qwen/qwen-2.5-coder-32b-instruct",
    "gemma-4-31b": "google/gemma-4-31b-it",
}

# LOCAL модели (Open-weight, vLLM/llama.cpp/Ollama) — DOWNLOADABLE
LOCAL_MODELS = {
    # Kimi K2.6 — ГЛАВНАЯ локальная модель (1T params, 32B active, 256K context)
    "kimi-k2.6": {
        "id": "moonshotai/Kimi-K2.6",
        "vram_gb": 48,
        "context": 256000,
        "quantization": "INT4",
        "engine": "vLLM/SGLang/KTransformers/llama.cpp",
        "license": "Modified MIT",
        "description": "1T params MoE, 32B active, native multimodal, agent swarm"
    },
    "kimi-k2.5": {
        "id": "moonshotai/Kimi-K2.5",
        "vram_gb": 48,
        "context": 128000,
        "quantization": "INT4",
        "engine": "vLLM/llama.cpp",
        "license": "Modified MIT"
    },
    "deepseek-v4-pro": {
        "id": "deepseek-ai/deepseek-v4-pro",
        "vram_gb": 48,
        "context": 1000000,
        "quantization": "Q4_K_M",
        "engine": "vLLM",
        "license": "Custom"
    },
    "deepseek-v4-flash": {
        "id": "deepseek-ai/deepseek-v4-flash",
        "vram_gb": 24,
        "context": 1000000,
        "quantization": "Q4_K_M",
        "engine": "vLLM",
        "license": "Custom"
    },
    "qwen3.5-122b": {
        "id": "qwen/qwen3.5-122b-a10b",
        "vram_gb": 24,
        "context": 128000,
        "quantization": "Q4_K_M",
        "engine": "vLLM/Ollama",
        "license": "Custom"
    },
    "qwen3.5-397b": {
        "id": "qwen/qwen3.5-397b-a17b",
        "vram_gb": 48,
        "context": 128000,
        "quantization": "Q4_K_M",
        "engine": "vLLM",
        "license": "Custom"
    },
    "mistral-small-4": {
        "id": "mistralai/mistral-small-4-119b-2603",
        "vram_gb": 48,
        "context": 256000,
        "quantization": "Q4_K_M",
        "engine": "vLLM",
        "license": "Apache 2.0"
    },
    "llama-3.3-70b": {
        "id": "meta/llama-3.3-70b-instruct",
        "vram_gb": 48,
        "context": 128000,
        "quantization": "Q4_K_M",
        "engine": "vLLM/Ollama",
        "license": "Llama 3.1"
    },
    "llama-3.2-90b-vision": {
        "id": "meta/llama-3.2-90b-vision-instruct",
        "vram_gb": 48,
        "context": 128000,
        "quantization": "Q4_K_M",
        "engine": "vLLM",
        "license": "Llama 3.2"
    },
    "phi-4-mini": {
        "id": "microsoft/phi-4-mini-instruct",
        "vram_gb": 8,
        "context": 128000,
        "quantization": "Q4_K_M",
        "engine": "Ollama",
        "license": "MIT"
    },
    "phi-4-multimodal": {
        "id": "microsoft/phi-4-multimodal-instruct",
        "vram_gb": 12,
        "context": 128000,
        "quantization": "Q4_K_M",
        "engine": "Ollama",
        "license": "MIT"
    },
    "gemma-4-31b": {
        "id": "google/gemma-4-31b-it",
        "vram_gb": 24,
        "context": 128000,
        "quantization": "Q4_K_M",
        "engine": "vLLM/Ollama",
        "license": "Gemma"
    },
    "gpt-oss-120b": {
        "id": "openai/gpt-oss-120b",
        "vram_gb": 80,
        "context": 128000,
        "quantization": "Q4_K_M",
        "engine": "vLLM",
        "license": "Custom"
    },
    "nemotron-3-super-120b": {
        "id": "nvidia/nemotron-3-super-120b-a12b",
        "vram_gb": 48,
        "context": 1000000,
        "quantization": "Q4_K_M",
        "engine": "vLLM",
        "license": "Custom"
    },
    "nemotron-3-nano-30b": {
        "id": "nvidia/nemotron-3-nano-30b-a3b",
        "vram_gb": 24,
        "context": 1000000,
        "quantization": "Q4_K_M",
        "engine": "vLLM",
        "license": "Custom"
    },
    "qwen3-next-80b": {
        "id": "qwen/qwen3-next-80b-a3b-instruct",
        "vram_gb": 48,
        "context": 256000,
        "quantization": "Q4_K_M",
        "engine": "vLLM",
        "license": "Custom"
    },
    "llama-3.3-nemotron-super-49b": {
        "id": "nvidia/llama-3.3-nemotron-super-49b-v1.5",
        "vram_gb": 24,
        "context": 128000,
        "quantization": "Q4_K_M",
        "engine": "vLLM",
        "license": "Custom"
    },
    "llama-3.1-nemotron-nano-8b": {
        "id": "nvidia/llama-3.1-nemotron-nano-8b-v1",
        "vram_gb": 8,
        "context": 128000,
        "quantization": "Q4_K_M",
        "engine": "Ollama",
        "license": "Custom"
    },
    "seed-oss-36b": {
        "id": "bytedance/seed-oss-36b-instruct",
        "vram_gb": 24,
        "context": 128000,
        "quantization": "Q4_K_M",
        "engine": "vLLM",
        "license": "Custom"
    },
    "glm-5.1": {
        "id": "z-ai/glm-5.1",
        "vram_gb": 48,
        "context": 128000,
        "quantization": "Q4_K_M",
        "engine": "vLLM",
        "license": "MIT"
    },
}


# OPENROUTER (Free tier, 20 RPM, 200/день) — ТОЛЬКО ДЕБАГГЕР
OPENROUTER_MODELS = {
    "deepseek-r1-free": "deepseek/deepseek-r1:free",
    "llama-4-maverick-free": "meta-llama/llama-4-maverick:free",
    "deepseek-v4-pro-free": "deepseek/deepseek-v4-pro:free",
    "qwen3-235b-free": "qwen/qwen3-235b-a22b:free",
    "gpt-oss-120b-free": "openai/gpt-oss-120b:free",
}


@dataclass
class RoleConfig:
    """Конфигурация роли"""
    role: AgentRole
    local_model: str                        # Local model ID (vLLM/llama.cpp/Ollama)
    api_model: str                          # NVIDIA NIM model ID
    vram_gb: int                            # Требуемая VRAM
    context_size: int                       # Контекст в токенах
    strengths: List[str]                    # Ключевые навыки
    system_prompt: str                      # Системный промпт
    temperature: float = 0.3                # Температура по умолчанию
    max_tokens: int = 8192                  # Макс токенов на ответ
    preferred_provider: str = "auto"        # "local" | "api" | "auto"


# 20 ролей с конфигурацией — Kimi K2.6 как главная для кодинга
ROLE_CONFIGS: Dict[AgentRole, RoleConfig] = {
    AgentRole.ORCHESTRATOR: RoleConfig(
        role=AgentRole.ORCHESTRATOR,
        local_model=LOCAL_MODELS["kimi-k2.6"]["id"],
        api_model=NVIDIA_MODELS["deepseek-r1"],
        vram_gb=48,
        context_size=256000,
        strengths=["planning", "analysis", "role_assignment", "ensemble_vote"],
        system_prompt="Ты — Главный Оркестратор. Анализируй задачи, назначай роли, сравнивай результаты моделей, выбирай лучшее. 256K контекст.",
        temperature=0.2,
        max_tokens=4096,
        preferred_provider="local"
    ),

    AgentRole.SCRUM_MASTER: RoleConfig(
        role=AgentRole.SCRUM_MASTER,
        local_model=LOCAL_MODELS["llama-3.3-70b"]["id"],
        api_model=NVIDIA_MODELS["llama-3-3-70b"],
        vram_gb=48,
        context_size=128000,
        strengths=["decomposition", "sprints", "estimation", "planning"],
        system_prompt="Ты — Scrum Master. Декомпозируй задачи на подзадачи, оценивай сложность, определяй acceptance criteria.",
        temperature=0.3,
        preferred_provider="auto"
    ),

    AgentRole.ARCHITECT: RoleConfig(
        role=AgentRole.ARCHITECT,
        local_model=LOCAL_MODELS["kimi-k2.6"]["id"],
        api_model=NVIDIA_MODELS["deepseek-r1"],
        vram_gb=48,
        context_size=256000,
        strengths=["system_design", "technology_selection", "patterns", "scalability"],
        system_prompt="Ты — Software Architect. Проектируй масштабируемые системы, выбирай технологии, определяй паттерны. Только дизайн, без кода.",
        temperature=0.2,
        preferred_provider="local"
    ),

    AgentRole.CODER: RoleConfig(
        role=AgentRole.CODER,
        local_model=LOCAL_MODELS["kimi-k2.6"]["id"],
        api_model=NVIDIA_MODELS["qwen3-coder"],
        vram_gb=48,
        context_size=256000,
        strengths=["code_generation", "algorithms", "data_structures", "implementation"],
        system_prompt="Ты — Senior Developer. Пиши production-ready код. SOLID, DRY, KISS. Комментируй сложные части. Всегда пиши тесты.",
        temperature=0.3,
        preferred_provider="local"
    ),

    AgentRole.CODE_REVIEWER: RoleConfig(
        role=AgentRole.CODE_REVIEWER,
        local_model=LOCAL_MODELS["mistral-small-4"]["id"],
        api_model=NVIDIA_MODELS["mistral-large"],
        vram_gb=48,
        context_size=256000,
        strengths=["security", "best_practices", "vulnerabilities", "compliance"],
        system_prompt="Ты — Code Reviewer. Ищи уязвимости, антипаттерны, проблемы производительности. Давай конкретные строки и предложения.",
        temperature=0.2,
        preferred_provider="auto"
    ),

    AgentRole.TESTER: RoleConfig(
        role=AgentRole.TESTER,
        local_model=LOCAL_MODELS["phi-4-multimodal"]["id"],
        api_model=NVIDIA_MODELS["phi-4"],
        vram_gb=12,
        context_size=128000,
        strengths=["test_generation", "edge_cases", "fuzzing", "coverage"],
        system_prompt="Ты — QA Engineer. Пиши comprehensive тесты: unit, integration, edge cases. Coverage > 80%. Используй pytest, mock, parametrize.",
        temperature=0.3,
        preferred_provider="auto"
    ),

    AgentRole.DEBUGGER: RoleConfig(
        role=AgentRole.DEBUGGER,
        local_model=LOCAL_MODELS["deepseek-v4-pro"]["id"],
        api_model=NVIDIA_MODELS["deepseek-r1"],
        vram_gb=48,
        context_size=1000000,
        strengths=["bug_hunting", "stack_trace_analysis", "root_cause", "fixing"],
        system_prompt="Ты — Debugger. Анализируй stack traces, находи root cause. Предлагай минимальные фиксы с объяснением почему.",
        temperature=0.2,
        preferred_provider="auto"
    ),

    AgentRole.REFACTORER: RoleConfig(
        role=AgentRole.REFACTORER,
        local_model=LOCAL_MODELS["kimi-k2.6"]["id"],
        api_model=NVIDIA_MODELS["qwen-2-5-coder"],
        vram_gb=48,
        context_size=256000,
        strengths=["rewriting", "optimization", "legacy", "clean_code"],
        system_prompt="Ты — Refactoring Expert. Переписывай legacy код в современный. Сохраняй поведение, улучшай читаемость. Метрики: cyclomatic complexity, cognitive complexity.",
        temperature=0.3,
        preferred_provider="local"
    ),

    AgentRole.EXPLAINER: RoleConfig(
        role=AgentRole.EXPLAINER,
        local_model=LOCAL_MODELS["kimi-k2.6"]["id"],
        api_model=NVIDIA_MODELS["llama-3-3-70b"],
        vram_gb=48,
        context_size=256000,
        strengths=["explanation", "onboarding", "documentation", "teaching"],
        system_prompt="Ты — Technical Writer. Объясняй сложный код просто. Используй аналогии, диаграммы (ASCII), примеры. 256K контекст для больших файлов.",
        temperature=0.4,
        preferred_provider="local"
    ),

    AgentRole.DOCS_WRITER: RoleConfig(
        role=AgentRole.DOCS_WRITER,
        local_model=LOCAL_MODELS["kimi-k2.6"]["id"],
        api_model=NVIDIA_MODELS["llama-3-3-70b"],
        vram_gb=48,
        context_size=256000,
        strengths=["readme", "api_docs", "docstrings", "long_docs"],
        system_prompt="Ты — Documentation Specialist. Пиши README, API docs, docstrings. Поддерживай OpenAPI/Swagger, Markdown. 256K контекст.",
        temperature=0.3,
        preferred_provider="local"
    ),

    AgentRole.SECURITY_AUDITOR: RoleConfig(
        role=AgentRole.SECURITY_AUDITOR,
        local_model=LOCAL_MODELS["llama-3.3-nemotron-super-49b"]["id"],
        api_model=NVIDIA_MODELS["nemotron-70b"],
        vram_gb=24,
        context_size=128000,
        strengths=["audit", "guardrails", "compliance", "secret_detection"],
        system_prompt="Ты — Security Auditor. Ищи OWASP Top 10, утечки секретов, SQL injection, XSS. Проверяй compliance (SOC2, GDPR).",
        temperature=0.2,
        preferred_provider="auto"
    ),

    AgentRole.UI_FRONTEND: RoleConfig(
        role=AgentRole.UI_FRONTEND,
        local_model=LOCAL_MODELS["gemma-4-31b"]["id"],
        api_model=NVIDIA_MODELS["gemma-4-31b"],
        vram_gb=24,
        context_size=128000,
        strengths=["html_css_js", "react", "vue", "tailwind", "responsive"],
        system_prompt="Ты — Frontend Developer. React, Vue, Tailwind, адаптивный дизайн. Доступность (a11y), семантический HTML. CSS Grid/Flexbox.",
        temperature=0.3,
        preferred_provider="auto"
    ),

    AgentRole.DEVOPS: RoleConfig(
        role=AgentRole.DEVOPS,
        local_model=LOCAL_MODELS["qwen3.5-122b"]["id"],
        api_model=NVIDIA_MODELS["llama-3-3-70b"],
        vram_gb=24,
        context_size=128000,
        strengths=["docker", "ci_cd", "scripts", "terraform", "kubernetes"],
        system_prompt="Ты — DevOps Engineer. Docker, Kubernetes, Terraform, GitHub Actions. Infrastructure as Code, monitoring, logging.",
        temperature=0.3,
        preferred_provider="auto"
    ),

    AgentRole.DATABASE: RoleConfig(
        role=AgentRole.DATABASE,
        local_model=LOCAL_MODELS["qwen3.5-122b"]["id"],
        api_model=NVIDIA_MODELS["qwen3-coder"],
        vram_gb=24,
        context_size=128000,
        strengths=["sql", "migrations", "optimization", "indexes", "schema"],
        system_prompt="Ты — Database Engineer. SQL, PostgreSQL, MongoDB. Миграции, индексы, query optimization, нормализация. EXPLAIN ANALYZE.",
        temperature=0.3,
        preferred_provider="auto"
    ),

    AgentRole.API_DESIGNER: RoleConfig(
        role=AgentRole.API_DESIGNER,
        local_model=LOCAL_MODELS["kimi-k2.6"]["id"],
        api_model=NVIDIA_MODELS["deepseek-r1"],
        vram_gb=48,
        context_size=256000,
        strengths=["rest", "graphql", "openapi", "grpc", "websocket"],
        system_prompt="Ты — API Designer. REST, GraphQL, gRPC, WebSocket. OpenAPI 3.0, versioning, rate limiting, HATEOAS. Idempotency.",
        temperature=0.2,
        preferred_provider="local"
    ),

    AgentRole.PERFORMANCE: RoleConfig(
        role=AgentRole.PERFORMANCE,
        local_model=LOCAL_MODELS["deepseek-v4-pro"]["id"],
        api_model=NVIDIA_MODELS["deepseek-r1"],
        vram_gb=48,
        context_size=1000000,
        strengths=["profiling", "optimization", "caching", "async", "memory"],
        system_prompt="Ты — Performance Engineer. Профилирование, оптимизация алгоритмов, caching (Redis), async/await, memory leaks. Big O analysis.",
        temperature=0.2,
        preferred_provider="auto"
    ),

    AgentRole.VISION: RoleConfig(
        role=AgentRole.VISION,
        local_model=LOCAL_MODELS["llama-3.2-90b-vision"]["id"],
        api_model=NVIDIA_MODELS["phi-4"],
        vram_gb=48,
        context_size=128000,
        strengths=["ui_analysis", "screenshots", "diagrams", "wireframes"],
        system_prompt="Ты — Vision Analyst. Анализируй UI скриншоты, диаграммы, wireframes. Описывай компоненты, цвета, layout. Accessibility audit.",
        temperature=0.3,
        preferred_provider="auto"
    ),

    AgentRole.EDGE_FAST: RoleConfig(
        role=AgentRole.EDGE_FAST,
        local_model=LOCAL_MODELS["phi-4-mini"]["id"],
        api_model=NVIDIA_MODELS["gemma-4-31b"],
        vram_gb=8,
        context_size=128000,
        strengths=["fast_tasks", "autocomplete", "lint_fix", "quick"],
        system_prompt="Ты — Fast Assistant. Быстрые задачи: autocomplete, lint fix, simple refactor. Минимум токенов, максимум скорости.",
        temperature=0.1,
        max_tokens=2048,
        preferred_provider="auto"
    ),

    AgentRole.REASONING: RoleConfig(
        role=AgentRole.REASONING,
        local_model=LOCAL_MODELS["deepseek-v4-pro"]["id"],
        api_model=NVIDIA_MODELS["deepseek-r1"],
        vram_gb=48,
        context_size=1000000,
        strengths=["complex_logic", "math", "planning", "algorithms"],
        system_prompt="Ты — Reasoning Expert. Сложная логика, математика, алгоритмы. Chain-of-thought, step-by-step. Докажи correctness.",
        temperature=0.2,
        preferred_provider="auto"
    ),

    AgentRole.MULTIMODAL: RoleConfig(
        role=AgentRole.MULTIMODAL,
        local_model=LOCAL_MODELS["phi-4-multimodal"]["id"],
        api_model=NVIDIA_MODELS["phi-4"],
        vram_gb=12,
        context_size=128000,
        strengths=["audio", "images", "video", "speech_to_text"],
        system_prompt="Ты — Multimodal Analyst. Аудио, изображения, видео, speech-to-text. Whisper, CLIP, транскрипция, описание.",
        temperature=0.3,
        preferred_provider="auto"
    ),
}


class RoleAssigner:
    """Назначает роли на основе анализа задачи"""

    def __init__(self, available_vram_gb: int = 48, prefer_local: bool = True):
        self.available_vram = available_vram_gb
        self.prefer_local = prefer_local
        self.role_configs = ROLE_CONFIGS

    def analyze_task(self, task: str) -> Dict[str, any]:
        """Анализирует задачу и определяет нужные роли"""
        task_lower = task.lower()

        detected_roles = []

        role_keywords = {
            AgentRole.SCRUM_MASTER: ["plan", "decompose", "sprint", "estimate", "break down"],
            AgentRole.ARCHITECT: ["design", "architecture", "structure", "system", "pattern"],
            AgentRole.CODER: ["write", "implement", "create", "build", "code", "develop"],
            AgentRole.CODE_REVIEWER: ["review", "audit", "check", "inspect", "quality"],
            AgentRole.TESTER: ["test", "coverage", "pytest", "unit test", "spec"],
            AgentRole.DEBUGGER: ["fix", "bug", "error", "debug", "broken", "crash", "issue"],
            AgentRole.REFACTORER: ["refactor", "rewrite", "clean", "improve", "modernize"],
            AgentRole.EXPLAINER: ["explain", "understand", "clarify", "describe", "what does"],
            AgentRole.DOCS_WRITER: ["document", "readme", "docstring", "api doc", "wiki"],
            AgentRole.SECURITY_AUDITOR: ["security", "vulnerability", "audit", "pentest", "owasp"],
            AgentRole.UI_FRONTEND: ["frontend", "react", "vue", "html", "css", "ui", "design"],
            AgentRole.DEVOPS: ["docker", "deploy", "ci/cd", "pipeline", "kubernetes", "infra"],
            AgentRole.DATABASE: ["database", "sql", "migration", "schema", "postgres", "mongo"],
            AgentRole.API_DESIGNER: ["api", "rest", "graphql", "endpoint", "swagger", "openapi"],
            AgentRole.PERFORMANCE: ["optimize", "performance", "speed", "memory", "cache", "profile"],
            AgentRole.VISION: ["image", "screenshot", "ui analysis", "diagram", "vision"],
            AgentRole.EDGE_FAST: ["quick", "fast", "autocomplete", "lint", "small"],
            AgentRole.REASONING: ["algorithm", "math", "logic", "prove", "complex", "optimize algorithm"],
            AgentRole.MULTIMODAL: ["audio", "video", "speech", "multimodal", "transcribe"],
        }

        for role, keywords in role_keywords.items():
            if any(kw in task_lower for kw in keywords):
                detected_roles.append(role)

        # Всегда добавляем оркестратора
        if AgentRole.ORCHESTRATOR not in detected_roles:
            detected_roles.insert(0, AgentRole.ORCHESTRATOR)

        # Если ничего не определилось — coder по умолчанию
        if len(detected_roles) == 1:
            detected_roles.append(AgentRole.CODER)

        # Оценка сложности
        complexity = 5
        if any(k in task_lower for k in ["complex", "large", "architecture", "system"]):
            complexity = 8
        elif any(k in task_lower for k in ["simple", "small", "quick", "fix"]):
            complexity = 3

        # Оценка размера контекста
        context_size = len(task) * 4

        # Определяем task_type
        task_type = "general"
        if any(k in task_lower for k in ["write", "implement", "create", "code"]):
            task_type = "coding"
        elif any(k in task_lower for k in ["fix", "bug", "debug", "error"]):
            task_type = "debugging"
        elif any(k in task_lower for k in ["design", "architecture", "structure"]):
            task_type = "architecture"
        elif any(k in task_lower for k in ["test", "coverage"]):
            task_type = "testing"
        elif any(k in task_lower for k in ["document", "readme", "explain"]):
            task_type = "documentation"

        return {
            "roles": detected_roles,
            "complexity": complexity,
            "context_size": context_size,
            "task_type": task_type,
        }

    def assign_roles(
        self,
        task: str,
        prefer_local: bool = None,
        force_api: bool = False
    ) -> List[RoleConfig]:
        """
        Назначает роли и выбирает модели (local или API).

        Args:
            task: Описание задачи
            prefer_local: Предпочитать локальные модели (override init value)
            force_api: Принудительно использовать API
        """
        if prefer_local is None:
            prefer_local = self.prefer_local

        analysis = self.analyze_task(task)
        assigned = []

        for role in analysis["roles"]:
            config = self.role_configs[role]

            # Определяем провайдер
            if force_api:
                provider = "api"
            elif config.preferred_provider == "local" and prefer_local:
                provider = "local" if config.vram_gb <= self.available_vram else "api"
            elif config.preferred_provider == "api":
                provider = "api"
            else:
                # auto — выбираем на основе VRAM
                if prefer_local and config.vram_gb <= self.available_vram:
                    provider = "local"
                else:
                    provider = "api"

            assigned.append((config, provider))

        return assigned

    def get_role_config(self, role: AgentRole) -> Optional[RoleConfig]:
        """Получить конфигурацию роли"""
        return self.role_configs.get(role)

    def list_all_roles(self) -> List[Dict[str, any]]:
        """Список всех ролей с информацией"""
        return [
            {
                "role": r.value,
                "local_model": cfg.local_model,
                "api_model": cfg.api_model,
                "vram_gb": cfg.vram_gb,
                "context_size": cfg.context_size,
                "strengths": cfg.strengths,
                "preferred_provider": cfg.preferred_provider,
            }
            for r, cfg in self.role_configs.items()
        ]

    def get_local_models_catalog(self) -> Dict[str, Dict]:
        """Каталог всех доступных локальных моделей"""
        return LOCAL_MODELS

    def get_nvidia_models_catalog(self) -> Dict[str, str]:
        """Каталог всех доступных NVIDIA NIM моделей"""
        return NVIDIA_MODELS
