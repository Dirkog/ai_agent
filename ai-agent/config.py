"""AI Agent Configuration — v5 with Orchestrator support"""
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
    is_free: bool = True  # NVIDIA NIM бесплатный

@dataclass
class AgentConfig:
    max_iterations: int = 50
    working_directory: str = field(default_factory=lambda: os.getenv("WORKING_DIRECTORY", "."))
    auto_validate: bool = True
    auto_checkpoint: bool = True
    context_window: int = 200000  # tokens

    # Orchestrator settings
    orchestrator_brain: str = "nvidia/llama-3.1-nemotron-70b-instruct"
    debugger_model: str = "anthropic/claude-3.5-sonnet"
    default_rpm_limit: int = 40

    # Providers
    providers: List[ProviderConfig] = field(default_factory=lambda: [
        ProviderConfig(
            name="nvidia_nim",
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=os.getenv("NVIDIA_API_KEY"),
            model=os.getenv("NVIDIA_MODEL", "nvidia/llama-3.1-nemotron-70b-instruct"),
            priority=1,
            rate_limit_rpm=40,
            is_free=True
        ),
        ProviderConfig(
            name="openrouter",
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY"),
            model=os.getenv("OPENROUTER_MODEL", "anthropic/claude-3.5-sonnet"),
            priority=2,
            rate_limit_rpm=20,
            is_free=False
        ),
        ProviderConfig(
            name="ollama",
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
            api_key="ollama",
            model=os.getenv("OLLAMA_MODEL", "codellama:34b"),
            priority=3,
            rate_limit_rpm=9999,
            is_free=True
        ),
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

# Global config instance
CONFIG = AgentConfig()
