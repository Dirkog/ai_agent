"""AI Agent Configuration — v6 with Ensemble, Roles, and vLLM support
Fixed: Added timeout, max_retries, vllm_config to ProviderConfig
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
    timeout: int = 120           # FIX: Added for BaseProvider
    max_retries: int = 3          # FIX: Added for BaseProvider._make_request
    vllm_config: Optional[Dict] = None  # NEW: For vLLM provider

@dataclass
class AgentConfig:
    max_iterations: int = 50
    working_directory: str = field(default_factory=lambda: os.getenv("WORKING_DIRECTORY", "."))
    auto_validate: bool = True
    auto_checkpoint: bool = True
    context_window: int = 200000

    # Orchestrator settings
    orchestrator_brain: str = "nvidia/llama-3.1-nemotron-70b-instruct"
    debugger_model: str = "anthropic/claude-3.5-sonnet"
    default_rpm_limit: int = 40

    # Ensemble settings (NEW)
    ensemble_enabled: bool = True
    ensemble_confidence_threshold: float = 0.7
    ensemble_divergence_threshold: float = 0.3
    ensemble_max_workers: int = 4

    # Role assigner settings (NEW)
    available_vram_gb: int = field(default_factory=lambda: int(os.getenv("AVAILABLE_VRAM_GB", "48")))
    prefer_local_models: bool = True

    # Providers
    providers: List[ProviderConfig] = field(default_factory=lambda: [
        ProviderConfig(
            name="nvidia_nim",
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=os.getenv("NVIDIA_API_KEY"),
            model=os.getenv("NVIDIA_MODEL", "nvidia/llama-3.1-nemotron-70b-instruct"),
            priority=1,
            rate_limit_rpm=40,
            is_free=True,
            timeout=120,
            max_retries=3
        ),
        ProviderConfig(
            name="openrouter",
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY"),
            model=os.getenv("OPENROUTER_MODEL", "anthropic/claude-3.5-sonnet"),
            priority=2,
            rate_limit_rpm=20,
            is_free=False,
            timeout=120,
            max_retries=3
        ),
        ProviderConfig(
            name="ollama",
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
            api_key=None,  # FIX: Ollama doesn't need API key
            model=os.getenv("OLLAMA_MODEL", "codellama:34b"),
            priority=3,
            rate_limit_rpm=9999,
            is_free=True,
            timeout=300,
            max_retries=1
        ),
        # NEW: vLLM provider config
        ProviderConfig(
            name="vllm",
            base_url=os.getenv("VLLM_BASE_URL", "http://localhost:8000/v1"),
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
        ) if os.getenv("VLLM_BASE_URL") else None,
    ])

    # Security levels
    security_levels: Dict[str, str] = field(default_factory=lambda: {
        "read_file": "low",
        "write_file": "medium",
        "execute_command": "high",
        "git_rollback": "critical",
    })

    # LSP
    lsp_command: str = "pylsp"

    # Vector store
    vector_db_path: str = ".ai-agent/vector_db"

    # Session memory
    memory_path: str = ".ai-agent/memory"

    # NEW: Debug analyzer settings
    debug_analyzer_model: str = "deepseek/deepseek-r1:free"
    debug_analyzer_enabled: bool = True

# Global config instance
CONFIG = AgentConfig()
