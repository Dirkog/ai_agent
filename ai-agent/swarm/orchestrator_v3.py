"""AI Agent Orchestrator v3 — Smart Model Router with Ensemble Support
Fixed: Unified chat() API, provider caching, correct model IDs,
       Kimi K2.6 restored (available as downloadable in NVIDIA NIM), all original models kept
"""
import json
import os
import time
import threading
from typing import List, Dict, Any, Optional, Generator, Callable, Tuple
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


# ═══════════════════════════════════════════════════════════════════════════════
# NVIDIA NIM API (Free Endpoint, 40 RPM, без кредитной карты)
# ВСЕ модели ниже доступны в каталоге build.nvidia.com (май 2026)
# ═══════════════════════════════════════════════════════════════════════════════
NVIDIA_FREE_MODELS = {
    # --- LLM / Chat / General ---
    "mistral-large-3": {
        "id": "mistralai/mistral-large-3-675b-instruct-2512",
        "description": "Mistral Large 3 — главная, язык, агент, 256K",
        "strengths": ["orchestrator", "language", "agent", "review", "analysis"],
        "rpm": 40,
        "context": 256000,
        "status": "Free Endpoint"
    },
    "llama-4-maverick": {
        "id": "meta/llama-4-maverick-17b-128e-instruct",
        "description": "Llama 4 Maverick — мультимодал, чат, 128K",
        "strengths": ["multimodal", "chat", "vision", "general"],
        "rpm": 40,
        "context": 128000,
        "status": "Free Endpoint"
    },
    "minimax-m2.7": {
        "id": "minimax/minimax-m2.7",
        "description": "MiniMax M2.7 — кодинг, reasoning, 128K",
        "strengths": ["coding", "reasoning", "math", "planning"],
        "rpm": 40,
        "context": 128000,
        "status": "Free Endpoint"
    },
    "mistral-nemotron": {
        "id": "mistralai/mistral-nemotron",
        "description": "Mistral Nemotron — агент, кодинг, функции, 128K",
        "strengths": ["agent", "coding", "functions", "tool_use"],
        "rpm": 40,
        "context": 128000,
        "status": "Free Endpoint"
    },
    "nemotron-content-safety": {
        "id": "nvidia/nemotron-3-content-safety",
        "description": "Nemotron Content Safety — guardrails, 4K",
        "strengths": ["safety", "guardrails", "content_filter"],
        "rpm": 40,
        "context": 4096,
        "status": "Free Endpoint"
    },
    "nemotron-voice-chat": {
        "id": "nvidia/nemotron-voice-chat",
        "description": "Nemotron Voice Chat — голос, 8K",
        "strengths": ["voice", "speech", "audio"],
        "rpm": 40,
        "context": 8192,
        "status": "Free Endpoint"
    },
    "nemotron-mini-4b": {
        "id": "nvidia/nemotron-mini-4b-instruct",
        "description": "Nemotron Mini 4B — edge, reasoning, 4K",
        "strengths": ["edge", "reasoning", "lightweight"],
        "rpm": 40,
        "context": 4096,
        "status": "Free Endpoint"
    },
    "llama-guard-4": {
        "id": "meta/llama-guard-4-12b",
        "description": "Llama Guard 4 — safety guard, 12K",
        "strengths": ["safety", "guardrails", "moderation"],
        "rpm": 40,
        "context": 12000,
        "status": "Free Endpoint"
    },
    "gemma-3n-e4b": {
        "id": "google/gemma-3n-e4b-it",
        "description": "Gemma 3N E4B — edge, мультимодал, 128K",
        "strengths": ["edge", "multimodal", "lightweight"],
        "rpm": 40,
        "context": 128000,
        "status": "Free Endpoint"
    },
    "gemma-3n-e2b": {
        "id": "google/gemma-3n-e2b-it",
        "description": "Gemma 3N E2B — edge, мультимодал, 128K",
        "strengths": ["edge", "multimodal", "lightweight"],
        "rpm": 40,
        "context": 128000,
        "status": "Free Endpoint"
    },
    "rerank-qa-mistral-4b": {
        "id": "nvidia/rerank-qa-mistral-4b",
        "description": "Rerank QA Mistral — реранк, 4K",
        "strengths": ["rerank", "retrieval", "qa"],
        "rpm": 40,
        "context": 4096,
        "status": "Free Endpoint"
    },
    "nv-embed-v1": {
        "id": "nvidia/nv-embed-v1",
        "description": "NV Embed v1 — эмбеддинги, 512",
        "strengths": ["embedding", "retrieval"],
        "rpm": 40,
        "context": 512,
        "status": "Free Endpoint"
    },
    "solar-10.7b": {
        "id": "upstage/solar-10.7b-instruct",
        "description": "Solar 10.7B — reasoning, 4K",
        "strengths": ["reasoning", "lightweight", "quick"],
        "rpm": 40,
        "context": 4096,
        "status": "Free Endpoint"
    },
    # --- Дополнительно подтвержденные в каталоге ---
    "step-3.5-flash": {
        "id": "stepfun/step-3.5-flash",
        "description": "Step 3.5 Flash — 200B MoE reasoning, agentic",
        "strengths": ["reasoning", "agentic", "coding"],
        "rpm": 40,
        "context": 128000,
        "status": "Free Endpoint"
    },
    "seed-oss-36b": {
        "id": "bytedance/seed-oss-36b-instruct",
        "description": "Seed OSS 36B — агент, reasoning",
        "strengths": ["agent", "reasoning", "coding"],
        "rpm": 40,
        "context": 128000,
        "status": "Free Endpoint"
    },
}

# ═══════════════════════════════════════════════════════════════════════════════
# LOCAL MODELS — Downloadable, Ollama/vLLM, требуют VRAM
# ВСЕ модели ниже подтверждены в каталоге NVIDIA NIM (май 2026)
# ═══════════════════════════════════════════════════════════════════════════════
LOCAL_MODELS = {
    # --- DeepSeek ---
    "deepseek-v4-pro": {
        "id": "deepseek-ai/deepseek-v4-pro",
        "description": "DeepSeek V4 Pro — 48GB VRAM, 1M контекст, reasoning",
        "strengths": ["reasoning", "architecture", "planning", "math", "orchestrator"],
        "context": 1000000,
        "vram_gb": 48,
        "quantization": "Q4_K_M",
        "engine": "vLLM",
        "status": "Downloadable"
    },
    "deepseek-v4-flash": {
        "id": "deepseek-ai/deepseek-v4-flash",
        "description": "DeepSeek V4 Flash — 24GB VRAM, быстрый кодинг, 1M",
        "strengths": ["coding", "quick", "reasoning"],
        "context": 1000000,
        "vram_gb": 24,
        "quantization": "Q4_K_M",
        "engine": "vLLM",
        "status": "Downloadable"
    },
    # --- Qwen ---
    "qwen3.5-122b": {
        "id": "qwen/qwen3.5-122b-a10b",
        "description": "Qwen 3.5 122B — 24GB VRAM, кодинг, reasoning, 128K",
        "strengths": ["coding", "reasoning", "agent"],
        "context": 128000,
        "vram_gb": 24,
        "quantization": "Q4_K_M",
        "engine": "vLLM/Ollama",
        "status": "Downloadable"
    },
    "qwen3.5-397b": {
        "id": "qwen/qwen3.5-397b-a17b",
        "description": "Qwen 3.5 397B — 48GB VRAM, VLM, агент, мультимодал, 128K",
        "strengths": ["vlm", "agent", "multimodal", "coding"],
        "context": 128000,
        "vram_gb": 48,
        "quantization": "Q4_K_M",
        "engine": "vLLM",
        "status": "Downloadable"
    },
    # --- Mistral ---
    "mistral-small-4": {
        "id": "mistralai/mistral-small-4-119b-2603",
        "description": "Mistral Small 4 — 48GB VRAM, кодинг, reasoning, мультимодал, 256K",
        "strengths": ["coding", "multimodal", "reasoning", "review"],
        "context": 256000,
        "vram_gb": 48,
        "quantization": "Q4_K_M",
        "engine": "vLLM",
        "status": "Downloadable"
    },
    "mistral-medium-3.5": {
        "id": "mistralai/mistral-medium-3.5-128b",
        "description": "Mistral Medium 3.5 — 48GB VRAM, агент, кодинг, 128K",
        "strengths": ["agent", "coding", "general"],
        "context": 128000,
        "vram_gb": 48,
        "quantization": "Q4_K_M",
        "engine": "vLLM",
        "status": "Downloadable"
    },
    # --- Llama ---
    "llama-3.3-70b": {
        "id": "meta/llama-3.3-70b-instruct",
        "description": "Llama 3.3 70B — 48GB VRAM, планирование, чат, 128K",
        "strengths": ["planning", "chat", "general", "scrum"],
        "context": 128000,
        "vram_gb": 48,
        "quantization": "Q4_K_M",
        "engine": "vLLM/Ollama",
        "status": "Downloadable"
    },
    "llama-3.2-90b-vision": {
        "id": "meta/llama-3.2-90b-vision-instruct",
        "description": "Llama 3.2 90B Vision — 48GB VRAM, vision, анализ изображений, 128K",
        "strengths": ["vision", "ui_analysis", "multimodal"],
        "context": 128000,
        "vram_gb": 48,
        "quantization": "Q4_K_M",
        "engine": "vLLM",
        "status": "Downloadable"
    },
    "llama-3.1-70b": {
        "id": "meta/llama-3.1-70b-instruct",
        "description": "Llama 3.1 70B — 48GB VRAM, чат, reasoning, 128K",
        "strengths": ["chat", "reasoning", "general"],
        "context": 128000,
        "vram_gb": 48,
        "quantization": "Q4_K_M",
        "engine": "vLLM/Ollama",
        "status": "Downloadable"
    },
    # --- Phi ---
    "phi-4-mini": {
        "id": "microsoft/phi-4-mini-instruct",
        "description": "Phi 4 Mini — 8GB VRAM, лёгкие задачи, edge, 128K",
        "strengths": ["edge", "quick", "lightweight", "autocomplete"],
        "context": 128000,
        "vram_gb": 8,
        "quantization": "Q4_K_M",
        "engine": "Ollama",
        "status": "Downloadable"
    },
    "phi-4-multimodal": {
        "id": "microsoft/phi-4-multimodal-instruct",
        "description": "Phi 4 Multimodal — 12GB VRAM, мультимодал, тесты, 128K",
        "strengths": ["testing", "multimodal", "lightweight"],
        "context": 128000,
        "vram_gb": 12,
        "quantization": "Q4_K_M",
        "engine": "Ollama",
        "status": "Free Endpoint"  # Также Free Endpoint
    },
    # --- Gemma ---
    "gemma-4-31b": {
        "id": "google/gemma-4-31b-it",
        "description": "Gemma 4 31B — 24GB VRAM, кодинг, агент, 128K",
        "strengths": ["coding", "agent", "edge", "frontend"],
        "context": 128000,
        "vram_gb": 24,
        "quantization": "Q4_K_M",
        "engine": "vLLM/Ollama",
        "status": "Downloadable"
    },
    # --- GPT OSS ---
    "gpt-oss-120b": {
        "id": "openai/gpt-oss-120b",
        "description": "GPT OSS 120B — 80GB+ VRAM, reasoning, 128K",
        "strengths": ["reasoning", "math", "complex_logic"],
        "context": 128000,
        "vram_gb": 80,
        "quantization": "Q4_K_M",
        "engine": "vLLM",
        "status": "Downloadable"
    },
    "gpt-oss-20b": {
        "id": "openai/gpt-oss-20b",
        "description": "GPT OSS 20B — 24GB VRAM, reasoning, 128K",
        "strengths": ["reasoning", "quick", "math"],
        "context": 128000,
        "vram_gb": 24,
        "quantization": "Q4_K_M",
        "engine": "vLLM",
        "status": "Downloadable"
    },
    # --- Nemotron ---
    "nemotron-3-super-120b": {
        "id": "nvidia/nemotron-3-super-120b-a12b",
        "description": "Nemotron 3 Super 120B — 48GB VRAM, агент, 1M контекст",
        "strengths": ["agent", "long_context", "coding", "explainer"],
        "context": 1000000,
        "vram_gb": 48,
        "quantization": "Q4_K_M",
        "engine": "vLLM",
        "status": "Downloadable"
    },
    "nemotron-3-nano-30b": {
        "id": "nvidia/nemotron-3-nano-30b-a3b",
        "description": "Nemotron 3 Nano 30B — 24GB VRAM, кодинг, 1M контекст",
        "strengths": ["coding", "long_context", "quick"],
        "context": 1000000,
        "vram_gb": 24,
        "quantization": "Q4_K_M",
        "engine": "vLLM",
        "status": "Downloadable"
    },
    "nemotron-3-nano-omni": {
        "id": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
        "description": "Nemotron 3 Nano Omni — 24GB VRAM, omni-modal reasoning",
        "strengths": ["omni_modal", "reasoning", "multimodal"],
        "context": 128000,
        "vram_gb": 24,
        "quantization": "Q4_K_M",
        "engine": "vLLM",
        "status": "Downloadable"
    },
    # --- Qwen Next ---
    "qwen3-next-80b": {
        "id": "qwen/qwen3-next-80b-a3b-instruct",
        "description": "Qwen 3 Next 80B — 48GB VRAM, длинный контекст, 256K",
        "strengths": ["long_context", "coding", "agent"],
        "context": 256000,
        "vram_gb": 48,
        "quantization": "Q4_K_M",
        "engine": "vLLM",
        "status": "Downloadable"
    },
    # --- Llama Nemotron ---
    "llama-3.3-nemotron-super-49b": {
        "id": "nvidia/llama-3.3-nemotron-super-49b-v1.5",
        "description": "Llama 3.3 Nemotron Super 49B — 24GB VRAM, reasoning, математика, 128K",
        "strengths": ["reasoning", "math", "security", "audit"],
        "context": 128000,
        "vram_gb": 24,
        "quantization": "Q4_K_M",
        "engine": "vLLM",
        "status": "Downloadable"
    },
    "llama-3.1-nemotron-nano-8b": {
        "id": "nvidia/llama-3.1-nemotron-nano-8b-v1",
        "description": "Llama 3.1 Nemotron Nano 8B — 8GB VRAM, edge, reasoning, 128K",
        "strengths": ["edge", "reasoning", "quick", "lightweight"],
        "context": 128000,
        "vram_gb": 8,
        "quantization": "Q4_K_M",
        "engine": "Ollama",
        "status": "Downloadable"
    },
    # --- Seed / GLM ---
    "seed-oss-36b": {
        "id": "bytedance/seed-oss-36b-instruct",
        "description": "Seed OSS 36B — 24GB VRAM, агент, reasoning, 128K",
        "strengths": ["agent", "reasoning", "coding"],
        "context": 128000,
        "vram_gb": 24,
        "quantization": "Q4_K_M",
        "engine": "vLLM",
        "status": "Downloadable"
    },
    "glm-5.1": {
        "id": "z-ai/glm-5.1",
        "description": "GLM 5.1 — 48GB VRAM, агент, кодинг, reasoning, 128K",
        "strengths": ["agent", "coding", "reasoning", "math"],
        "context": 128000,
        "vram_gb": 48,
        "quantization": "Q4_K_M",
        "engine": "vLLM",
        "status": "Downloadable"
    },
    # ═══════════════════════════════════════════════════════════════════════════════
    # Kimi K2.6 — ВОЗВРАЩЕНА! Доступна как downloadable в NVIDIA NIM (май 2026)
    # 1T MoE, 256K контекст, agentic coding, multimodal
    # ═══════════════════════════════════════════════════════════════════════════════
    "kimi-k2.6": {
        "id": "moonshotai/kimi-k2.6",
        "description": "Kimi K2.6 — 48GB VRAM, agentic coding, long-horizon, multimodal, 256K",
        "strengths": ["agentic_coding", "long_context", "multimodal", "reasoning", "orchestrator"],
        "context": 256000,
        "vram_gb": 48,
        "quantization": "Q4_K_M",
        "engine": "vLLM",
        "status": "Downloadable"
    },
}

# ═══════════════════════════════════════════════════════════════════════════════
# OPENROUTER (Free tier, 20 RPM, 200/день) — ТОЛЬКО ДЕБАГГЕР
# ═══════════════════════════════════════════════════════════════════════════════
OPENROUTER_DEBUG_MODELS = {
    "deepseek-v4-pro-free": {
        "id": "deepseek/deepseek-v4-pro:free",
        "description": "DeepSeek V4 Pro Free — сложный дебаггинг, reasoning",
        "strengths": ["reasoning", "debugging", "complex_analysis"]
    },
    "llama-4-maverick-free": {
        "id": "meta-llama/llama-4-maverick:free",
        "description": "Llama 4 Maverick Free — анализ ошибок",
        "strengths": ["analysis", "error_detection", "general"]
    },
    "deepseek-r1-free": {
        "id": "deepseek/deepseek-r1:free",
        "description": "DeepSeek R1 Free — reasoning",
        "strengths": ["reasoning", "math", "planning"]
    },
    "qwen3-235b-free": {
        "id": "qwen/qwen3-235b-a22b:free",
        "description": "Qwen 3 235B Free — анализ кода",
        "strengths": ["code_analysis", "review"]
    },
    "gpt-oss-120b-free": {
        "id": "openai/gpt-oss-120b:free",
        "description": "GPT OSS 120B Free — быстрый анализ",
        "strengths": ["quick_analysis", "general"]
    },
    "openrouter-free": {
        "id": "openrouter/free",
        "description": "OpenRouter Free — рандомный fallback",
        "strengths": ["fallback", "general"]
    },
}


@dataclass
class SubAgent:
    role: AgentRole
    name: str
    model_id: str
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
    model_assignments: Dict[str, str]
    phases: List[Dict[str, Any]]
    estimated_time: int
    reasoning: str
    context_size_estimate: int = 0
    use_local: bool = False


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
    - NVIDIA NIM: ВСЕ модели бесплатные (40 RPM)
    - LOCAL: Open-weight модели (vLLM/Ollama), включая Kimi K2.6
    - OpenRouter: ТОЛЬКО для дебаггера
    - Ensemble: Local + API параллельно
    """

    def __init__(self, nvidia_api_key: str, openrouter_api_key: Optional[str] = None,
                 use_ensemble: bool = False, ollama_url: str = "http://localhost:11434/v1",
                 vllm_url: Optional[str] = None, prefer_local: bool = False,
                 available_vram_gb: int = 48):

        self.prefer_local = prefer_local
        self.available_vram = available_vram_gb

        brain_model = os.getenv("NVIDIA_ORCHESTRATOR_MODEL", "mistralai/mistral-large-3-675b-instruct-2512")
        brain_cfg = ProviderConfig(
            name="nvidia_nim",
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=nvidia_api_key,
            model=brain_model,
            priority=1,
            rate_limit_rpm=40,
            is_free=True,
            timeout=120,
            max_retries=3
        )
        self.brain = NvidiaNimProvider(brain_cfg)

        self._provider_cache: Dict[str, BaseProvider] = {"brain": self.brain}

        self.debugger = None
        if openrouter_api_key:
            debug_model = os.getenv("DEBUG_MODEL", "deepseek/deepseek-v4-pro:free")
            debug_cfg = ProviderConfig(
                name="openrouter",
                base_url="https://openrouter.ai/api/v1",
                api_key=openrouter_api_key,
                model=debug_model,
                priority=2,
                rate_limit_rpm=20,
                is_free=False,
                timeout=120,
                max_retries=3
            )
            self.debugger = OpenRouterProvider(debug_cfg)
            self._provider_cache["debugger"] = self.debugger

        self.ensemble = None
        if use_ensemble and nvidia_api_key:
            self.ensemble = EnsembleProvider(
                nvidia_api_key=nvidia_api_key,
                nvidia_model=brain_model,
                ollama_base_url=ollama_url,
                ollama_model=os.getenv("OLLAMA_MODEL", "codellama:34b")
            )

        self.local_provider = None
        if vllm_url:
            local_model = os.getenv("LOCAL_ORCHESTRATOR_MODEL", "deepseek-ai/deepseek-v4-pro")
            local_cfg = ProviderConfig(
                name="vllm",
                base_url=vllm_url,
                api_key=None,
                model=local_model,
                priority=0,
                rate_limit_rpm=9999,
                is_free=True,
                timeout=300,
                max_retries=1
            )
            from providers.vllm_provider import VLLMProvider
            self.local_provider = VLLMProvider(local_cfg)
            self._provider_cache["local"] = self.local_provider

        self.rpm_tracker = RPMTracker(max_rpm=40)

        self.agents: List[SubAgent] = []
        self.task_history: List[Dict] = []

        self.on_status_update: Optional[Callable] = None
        self.on_agent_complete: Optional[Callable] = None
        self.on_error: Optional[Callable] = None

    def _get_cached_provider(self, provider_type: str, model_id: str) -> BaseProvider:
        """Reuse providers, create new only if model differs"""
        cache_key = f"{provider_type}:{model_id}"
        if cache_key in self._provider_cache:
            return self._provider_cache[cache_key]

        if provider_type == "nvidia":
            cfg = ProviderConfig(
                name="nvidia_nim",
                base_url="https://integrate.api.nvidia.com/v1",
                api_key=self.brain.config.api_key,
                model=model_id,
                priority=1,
                rate_limit_rpm=40,
                is_free=True,
                timeout=120,
                max_retries=3
            )
            provider = NvidiaNimProvider(cfg)
        elif provider_type == "local" and self.local_provider:
            cfg = ProviderConfig(
                name="vllm",
                base_url=self.local_provider.config.base_url,
                api_key=None,
                model=model_id,
                priority=0,
                rate_limit_rpm=9999,
                is_free=True,
                timeout=300,
                max_retries=1
            )
            from providers.vllm_provider import VLLMProvider
            provider = VLLMProvider(cfg)
        else:
            provider = self.brain

        self._provider_cache[cache_key] = provider
        return provider

    def _select_model_for_role(self, role: AgentRole, task_description: str,
                               complexity: int, context_size: int, use_local: bool = False) -> Tuple[str, str]:
        """Выбирает лучшую модель для роли. Returns: (model_id, provider_type)"""
        role_str = role.value

        # Local preferred and enough VRAM
        if use_local and self.available_vram >= 48:
            if role in (AgentRole.CODER, AgentRole.ARCHITECT, AgentRole.ORCHESTRATOR):
                if context_size > 100000:
                    return (LOCAL_MODELS["deepseek-v4-pro"]["id"], "local")
                # Kimi K2.6 отлично подходит для agentic coding и orchestrator
                if "agentic" in task_description.lower() or "orchestrator" in task_description.lower():
                    return (LOCAL_MODELS["kimi-k2.6"]["id"], "local")
                return (LOCAL_MODELS["deepseek-v4-pro"]["id"], "local")

            if role in (AgentRole.DEBUGGER, AgentRole.OPTIMIZER) or complexity >= 8:
                return (LOCAL_MODELS["deepseek-v4-pro"]["id"], "local")

            if role == AgentRole.TESTER:
                return (LOCAL_MODELS["phi-4-multimodal"]["id"], "local")

            if context_size > 100000 and self.available_vram >= 48:
                return (LOCAL_MODELS["deepseek-v4-pro"]["id"], "local")

        # NVIDIA NIM models
        if role in (AgentRole.ARCHITECT, AgentRole.SCRUM_MASTER, AgentRole.ORCHESTRATOR) or complexity >= 8:
            if "reasoning" in task_description.lower() or "algorithm" in task_description.lower():
                return (NVIDIA_FREE_MODELS["minimax-m2.7"]["id"], "nvidia")
            return (NVIDIA_FREE_MODELS["mistral-large-3"]["id"], "nvidia")

        if role == AgentRole.CODER:
            if "refactor" in task_description.lower() or "optimize" in task_description.lower():
                return (NVIDIA_FREE_MODELS["mistral-nemotron"]["id"], "nvidia")
            if "complex" in task_description.lower() or "algorithm" in task_description.lower():
                return (NVIDIA_FREE_MODELS["minimax-m2.7"]["id"], "nvidia")
            return (NVIDIA_FREE_MODELS["mistral-nemotron"]["id"], "nvidia")

        if role == AgentRole.REVIEWER:
            return (NVIDIA_FREE_MODELS["mistral-large-3"]["id"], "nvidia")

        if role == AgentRole.TESTER:
            return (NVIDIA_FREE_MODELS["llama-4-maverick"]["id"], "nvidia")

        if role == AgentRole.DEBUGGER:
            return (NVIDIA_FREE_MODELS["minimax-m2.7"]["id"], "nvidia")

        if role == AgentRole.DEVOPS:
            return (NVIDIA_FREE_MODELS["mistral-nemotron"]["id"], "nvidia")

        if role == AgentRole.EXPLAINER:
            return (NVIDIA_FREE_MODELS["mistral-large-3"]["id"], "nvidia")

        if role == AgentRole.OPTIMIZER:
            return (NVIDIA_FREE_MODELS["minimax-m2.7"]["id"], "nvidia")

        # Default
        return (NVIDIA_FREE_MODELS["mistral-large-3"]["id"], "nvidia")

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
            response = "".join(self.brain.chat(messages, temperature=temperature))
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
    "scrum": "llama-3.3-70b",
    "architect": "deepseek-v4-pro",
    "coder": "mistral-nemotron",
    "tester": "phi-4-multimodal",
    "reviewer": "mistral-large-3"
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
            json_match = re.search(r"\{.*\}", response, re.DOTALL)
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
                model_assignments={"coder": "mistral-large-3"},
                phases=[{"role": "coder", "task": task, "depends_on": [], "estimated_tokens": 4000}],
                estimated_time=10,
                reasoning=f"Fallback: {str(e)}",
                context_size_estimate=len(task) * 4,
                use_local=use_local
            )

    def create_agents(self, plan: TaskPlan) -> List[SubAgent]:
        """Создаёт агентов по плану"""
        self.agents = []

        for role in plan.roles_needed:
            role_str = role.value
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
                model_key = "auto"
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
            AgentRole.SCRUM_MASTER: "Ты — Project Manager. Декомпозируй задачи, оценивай, трекай прогресс. Acceptance criteria.",
            AgentRole.EXPLAINER: "Ты — Technical Writer. Объясняй сложное просто. Документация, комментарии, docstrings.",
            AgentRole.OPTIMIZER: "Ты — Performance Engineer. Оптимизируй код. Профилирование, алгоритмы, memory.",
        }
        return prompts.get(role, "Выполни свою роль профессионально.")

    def run_task(self, task: str) -> Generator[str, None, None]:
        """Главный метод — запускает полный workflow"""
        yield f"🧠 [Оркестратор] Анализирую задачу...\n"
        yield f"📋 Задача: {task[:200]}...\n"
        yield f"💻 VRAM: {self.available_vram}GB | Local: {self.prefer_local}\n"

        plan = self.analyze_task(task)
        yield f"\n📊 Анализ:\n"
        yield f"  Сложность: {plan.complexity}/10\n"
        yield f"  Роли: {[r.value for r in plan.roles_needed]}\n"
        yield f"  Модели: {plan.model_assignments}\n"
        yield f"  Локальные: {plan.use_local}\n"
        yield f"  Контекст: ~{plan.context_size_estimate} токенов\n"
        yield f"  Время: ~{plan.estimated_time} мин\n"
        yield f"  Логика: {plan.reasoning}\n"

        agents = self.create_agents(plan)
        yield f"\n👥 Создано агентов: {len(agents)}\n"
        for a in agents:
            model_name = a.model_id.split("/")[-1] if "/" in a.model_id else a.model_id
            yield f"  • {a.name} → {model_name} ({a.provider})\n"

        completed_phases = set()

        for phase in plan.phases:
            role_str = phase["role"]
            phase_task = phase["task"]
            depends = phase.get("depends_on", [])
            est_tokens = phase.get("estimated_tokens", 4000)

            if depends:
                yield f"\n⏳ Жду завершения: {depends}\n"
                while not all(d in completed_phases for d in depends):
                    time.sleep(0.5)

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

                if self.debugger:
                    yield f"\n🔍 Вызываю дебаггера (OpenRouter)...\n"
                    debug_result = self._call_debugger(agent, str(e), task)
                    yield f"🩺 Диагноз: {debug_result[:1000]}...\n"
                    yield f"\n🔄 Перепланирую с учётом диагноза...\n"
                else:
                    yield f"⚠️ Дебаггер не настроен\n"

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
            provider = self._get_cached_provider("local", agent.model_id)
            response = "".join(provider.chat(messages, temperature=0.3))
        elif agent.provider == "nvidia":
            provider = self._get_cached_provider("nvidia", agent.model_id)
            while not self.rpm_tracker.can_request():
                time.sleep(self.rpm_tracker.wait_time())
            self.rpm_tracker.add_request()
            response = "".join(provider.chat(messages, temperature=0.3))
        else:
            response = "".join(self.brain.chat(messages, temperature=0.3))

        agent.latency_ms = int((time.time() - start) * 1000)
        agent.tokens_used = len(prompt.encode("utf-8")) // 3 + len(response.encode("utf-8")) // 3

        return response

    def _call_debugger(self, failed_agent: SubAgent, error: str, original_task: str) -> str:
        """Вызывает OpenRouter дебаггер"""
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
            response = "".join(self.debugger.chat(messages, temperature=0.2))
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

    def close(self):
        """Close all providers"""
        for provider in self._provider_cache.values():
            provider.close()
        if self.ensemble:
            self.ensemble.close()
