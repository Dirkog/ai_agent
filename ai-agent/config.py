"""Configuration for AI Agent"""
import os
from dataclasses import dataclass, field
from typing import List, Optional
from dotenv import load_dotenv

# Load .env file if exists
load_dotenv()


@dataclass
class ProviderConfig:
    name: str
    base_url: str
    api_key: Optional[str] = None
    model: str = ""
    timeout: int = 60
    max_retries: int = 3
    priority: int = 1  # Lower = higher priority
    rate_limit_rpm: int = 60


@dataclass
class AgentConfig:
    # Providers in priority order
    providers: List[ProviderConfig] = field(default_factory=lambda: [
        ProviderConfig(
            name="openrouter",
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY"),
            model="anthropic/claude-3.5-sonnet",
            priority=1,
            rate_limit_rpm=20
        ),
        ProviderConfig(
            name="nvidia_nim",
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=os.getenv("NVIDIA_API_KEY"),
            model="nvidia/llama-3.1-nemotron-70b-instruct",
            priority=2,
            rate_limit_rpm=30
        ),
        ProviderConfig(
            name="ollama",
            base_url="http://localhost:11434/v1",
            api_key="ollama",  # Not used but required for OpenAI client
            model="codellama:34b",
            priority=3,
            rate_limit_rpm=9999
        ),
    ])

    # Agent settings
    max_iterations: int = 50
    auto_confirm: bool = False  # True = autonomous mode
    working_directory: str = os.getcwd()

    # Rate limiting
    default_retry_delay: int = 60
    max_retry_delay: int = 3600
    exponential_base: float = 2.0

    # Validation
    run_tests: bool = True
    run_linter: bool = True
    check_syntax: bool = True


CONFIG = AgentConfig()
