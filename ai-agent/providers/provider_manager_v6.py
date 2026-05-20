"""Provider manager with ensemble support, failover and rate limit handling
v6 update: добавлен EnsembleProvider для параллельного Local + API
"""
import time
from typing import Generator, Optional, List, Dict, Any
from config import CONFIG, ProviderConfig
from providers import BaseProvider, RateLimitError, ProviderError
from providers.openrouter import OpenRouterProvider
from providers.nvidia_nim import NvidiaNimProvider
from providers.ollama import OllamaProvider
from providers.ensemble_provider import EnsembleProvider


class ProviderManager:
    def __init__(self):
        self.providers: Dict[str, BaseProvider] = {}
        self.provider_order: List[str] = []
        self.unavailable_providers: set = set()
        self.ensemble: Optional[EnsembleProvider] = None
        self.current_provider_name: str = "unknown"

        for cfg in sorted(CONFIG.providers, key=lambda x: x.priority):
            if cfg.name == "openrouter":
                provider = OpenRouterProvider(cfg)
            elif cfg.name == "nvidia_nim":
                provider = NvidiaNimProvider(cfg)
            elif cfg.name == "ollama":
                provider = OllamaProvider(cfg)
            else:
                continue

            self.providers[cfg.name] = provider
            self.provider_order.append(cfg.name)

        self._check_availability()
        self._init_ensemble()

    def _check_availability(self):
        """Check which providers are available"""
        print("[Provider Manager] Checking availability...")
        for name, provider in self.providers.items():
            if provider.is_available():
                print(f"  ✓ {name} available")
            else:
                print(f"  ✗ {name} unavailable")
                self.unavailable_providers.add(name)

    def _init_ensemble(self):
        """Initialize ensemble provider if both API and local are available"""
        nvidia_cfg = next((c for c in CONFIG.providers if c.name == "nvidia_nim"), None)
        ollama_cfg = next((c for c in CONFIG.providers if c.name == "ollama"), None)

        if nvidia_cfg and nvidia_cfg.api_key and ollama_cfg:
            self.ensemble = EnsembleProvider(
                nvidia_api_key=nvidia_cfg.api_key,
                nvidia_model=nvidia_cfg.model,
                ollama_base_url=ollama_cfg.base_url,
                ollama_model=ollama_cfg.model,
            )
            print("  ✓ Ensemble provider initialized (NVIDIA + Ollama)")
        else:
            print("  ⚠ Ensemble not available (need both NVIDIA and Ollama)")

    def get_available_providers(self) -> List[str]:
        return [p for p in self.provider_order if p not in self.unavailable_providers]

    def complete(
        self,
        messages: list,
        tools: Optional[list] = None,
        stream: bool = False,
        preferred: Optional[str] = None,
        use_ensemble: bool = False,
        task_type: str = "general"
    ) -> Generator[str, None, None]:
        """
        Complete with provider selection.

        Args:
            messages: Chat messages
            tools: Available tools
            stream: Stream response
            preferred: Preferred provider name
            use_ensemble: Use parallel ensemble (NVIDIA + Ollama)
            task_type: Task type for ensemble quality scoring
        """
        # Если запрошен ensemble и он доступен — используем
        if use_ensemble and self.ensemble:
            self.current_provider_name = "ensemble"
            yield from self.ensemble.chat(
                messages,
                task_type=task_type,
                stream=stream,
                preferred_provider=preferred
            )
            return

        # Иначе — стандартный failover
        yield from self._failover_chat(messages, tools, stream, preferred)

    def _failover_chat(
        self,
        messages: list,
        tools: Optional[list] = None,
        stream: bool = False,
        preferred: Optional[str] = None
    ) -> Generator[str, None, None]:
        """Chat with automatic failover between providers"""
        providers_to_try = self.get_available_providers()

        if preferred and preferred in providers_to_try:
            providers_to_try.insert(0, preferred)

        last_error = None

        for provider_name in providers_to_try:
            provider = self.providers[provider_name]
            self.current_provider_name = provider_name
            retries = 0
            max_retries = 2

            while retries <= max_retries:
                try:
                    print(f"[Provider] Using {provider_name}...")
                    full_response = ""

                    for chunk in provider.chat(messages, tools, stream):
                        full_response += chunk
                        yield chunk

                    return  # Success

                except RateLimitError as e:
                    print(f"[Rate Limit] {provider_name}: {e}. Waiting {e.retry_after}s...")
                    time.sleep(e.retry_after)
                    retries += 1
                    if retries > max_retries:
                        print(f"[Rate Limit] {provider_name}: Max retries exceeded, trying next provider...")
                        break

                except ProviderError as e:
                    print(f"[Error] {provider_name}: {e}")
                    last_error = e
                    break  # Try next provider

                except Exception as e:
                    print(f"[Unexpected] {provider_name}: {e}")
                    last_error = e
                    break

        # All providers failed
        error_msg = f"All providers failed. Last error: {last_error}" if last_error else "No providers available"
        yield f"[ERROR] {error_msg}"

    def get_ensemble_status(self) -> Dict[str, Any]:
        """Get ensemble status"""
        if self.ensemble:
            return self.ensemble.get_status()
        return {"available": False, "reason": "Not initialized"}
