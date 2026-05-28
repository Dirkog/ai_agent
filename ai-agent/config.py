"""AI Agent Configuration — v6 with Ensemble, Roles, and vLLM support
Fixed: Filter None from providers, correct Ollama URL, typed env vars
"""
import os
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from dotenv import load_dotenv

load_dotenv()

@dataclass
class ProviderConfig:
    name: str
    base_url: str
    api_key: Optional[str]
    model: str
    priority: int
    rate_limit_rpm: int
    is_free: bool = True
    timeout: int = 120
    max_retries: int = 3
    vllm_config: Optional[Dict] = None

@dataclass
class AgentConfig:
    max_iterations: int = int(os.getenv("MAX_ITERATIONS", "50"))
    working_directory: str = field(default_factory=lambda: os.getenv("WORKING_DIRECTORY", "."))
    auto_validate: bool = os.getenv("AUTO_VALIDATE", "true").lower() == "true"
    auto_checkpoint: bool = os.getenv("AUTO_CHECKPOINT", "true").lower() == "true"
    context_window: int = int(os.getenv("CONTEXT_WINDOW", "200000"))

    # Orchestrator settings
    orchestrator_brain: str = os.getenv("NVIDIA_ORCHESTRATOR_MODEL", "mistralai/mistral-large-3-675b-instruct-2512")
    debugger_model: str = os.getenv("DEBUG_MODEL", "deepseek/deepseek-v4-pro:free")
    default_rpm_limit: int = 40

    # Ensemble settings
    ensemble_enabled: bool = os.getenv("ENSEMBLE_ENABLED", "true").lower() == "true"
    ensemble_confidence_threshold: float = float(os.getenv("ENSEMBLE_CONFIDENCE_THRESHOLD", "0.7"))
    ensemble_divergence_threshold: float = float(os.getenv("ENSEMBLE_DIVERGENCE_THRESHOLD", "0.3"))
    ensemble_max_workers: int = int(os.getenv("ENSEMBLE_MAX_WORKERS", "4"))

    # Role assigner settings
    available_vram_gb: int = int(os.getenv("AVAILABLE_VRAM_GB", "48"))
    prefer_local_models: bool = os.getenv("PREFER_LOCAL_MODELS", "true").lower() == "true"

    # Providers — filter out None entries
    providers: List[ProviderConfig] = field(default_factory=lambda: _build_providers())

    # Security levels
    security_levels: Dict[str, str] = field(default_factory=lambda: {
        "read_file": "low",
        "write_file": "medium",
        "execute_command": "high",
        "git_rollback": "critical",
    })

    # LSP
    lsp_command: str = os.getenv("LSP_COMMAND", "pylsp")

    # Vector store
    vector_db_path: str = ".ai-agent/vector_db"

    # Session memory
    memory_path: str = ".ai-agent/memory"

    # Debug analyzer settings
    debug_analyzer_model: str = os.getenv("DEBUG_MODEL", "deepseek/deepseek-v4-pro:free")
    debug_analyzer_enabled: bool = os.getenv("DEBUG_ANALYZER_ENABLED", "true").lower() == "true"

    # Flask settings (typed)
    flask_port: int = int(os.getenv("FLASK_PORT", "5000"))
    flask_debug: bool = os.getenv("FLASK_DEBUG", "false").lower() == "true"


def _build_providers() -> List[ProviderConfig]:
    """Build provider list, filtering out None/unconfigured entries."""
    providers = []

    # NVIDIA NIM
    nvidia_key = os.getenv("NVIDIA_API_KEY")
    if nvidia_key:
        providers.append(ProviderConfig(
            name="nvidia_nim",
            base_url=os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
            api_key=nvidia_key,
            model=os.getenv("NVIDIA_MODEL", "mistralai/mistral-large-3-675b-instruct-2512"),
            priority=1,
            rate_limit_rpm=40,
            is_free=True,
            timeout=120,
            max_retries=3
        ))

    # OpenRouter
    or_key = os.getenv("OPENROUTER_API_KEY")
    if or_key:
        providers.append(ProviderConfig(
            name="openrouter",
            base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            api_key=or_key,
            model=os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-v4-pro:free"),
            priority=2,
            rate_limit_rpm=20,
            is_free=False,
            timeout=120,
            max_retries=3
        ))

    # Ollama — use OpenAI-compatible endpoint
    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    if ollama_url:
        providers.append(ProviderConfig(
            name="ollama",
            base_url=ollama_url,
            api_key=None,
            model=os.getenv("OLLAMA_MODEL", "codellama:34b"),
            priority=3,
            rate_limit_rpm=9999,
            is_free=True,
            timeout=300,
            max_retries=1
        ))

    # vLLM
    vllm_url = os.getenv("VLLM_BASE_URL")
    if vllm_url:
        providers.append(ProviderConfig(
            name="vllm",
            base_url=vllm_url,
            api_key=None,
            model=os.getenv("VLLM_MODEL", ""),
            priority=4,
            rate_limit_rpm=9999,
            is_free=True,
            timeout=300,
            max_retries=1,
            vllm_config={
                "tensor_parallel_size": int(os.getenv("VLLM_TP_SIZE", "1")),
                "quantization": os.getenv("VLLM_QUANTIZATION", None),
            }
        ))

    return providers


# Global config instance
CONFIG = AgentConfig()
