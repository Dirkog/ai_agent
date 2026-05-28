"""Provider manager with ensemble support, failover and rate limit handling
Fixed: Unified complete() API (returns string when stream=False, generator when stream=True),
       proper ProviderConfig passing to ensemble, removed dead code
"""
import time
from typing import Generator, Optional, List, Dict, Any, Union
from config import CONFIG, ProviderConfig
from providers.base import BaseProvider, RateLimitError, ProviderError
from providers.openrouter import OpenRouterProvider
from providers.nvidia_nim import NvidiaNimProvider
from providers.ollama import OllamaProvider
from providers.vllm_provider import VLLMProvider
from providers.ensemble_provider import EnsembleProvider


class ProviderManager:
    def __init__(self):
        self.providers: Dict[str, BaseProvider] = {}
        self.provider_order: List[str] = []
        self.unavailable_providers: set = set()
        self.ensemble: Optional[EnsembleProvider] = None
        self.current_provider_name: str = "unknown"

        for cfg in sorted(CONFIG.providers, key=lambda x: x.priority):
            if cfg is None:
                continue
            if cfg.name == "openrouter":
                provider = OpenRouterProvider(cfg)
            elif cfg.name == "nvidia_nim":
                provider = NvidiaNimProvider(cfg)
            elif cfg.name == "ollama":
                provider = OllamaProvider(cfg)
            elif cfg.name == "vllm":
                provider = VLLMProvider(cfg)
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
        if not CONFIG.ensemble_enabled:
            print("  ⚠ Ensemble disabled in config")
            return

        nvidia_cfg = next((c for c in CONFIG.providers if c and c.name == "nvidia_nim"), None)
        ollama_cfg = next((c for c in CONFIG.providers if c and c.name == "ollama"), None)

        if nvidia_cfg and nvidia_cfg.api_key and ollama_cfg:
            self.ensemble = EnsembleProvider(
                nvidia_api_key=nvidia_cfg.api_key,
                nvidia_model=nvidia_cfg.model,
                ollama_base_url=ollama_cfg.base_url,
                ollama_model=ollama_cfg.model,
                confidence_threshold=CONFIG.ensemble_confidence_threshold,
                divergence_threshold=CONFIG.ensemble_divergence_threshold,
                max_workers=CONFIG.ensemble_max_workers,
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
        task_type: str = "general",
        temperature: float = 0.7,
        max_tokens: int = 4096
    ) -> Union[str, Generator[str, None, None]]:
        """
        Complete with provider selection.
        FIXED: Returns string when stream=False, Generator when stream=True.
        """
        if use_ensemble and self.ensemble:
            self.current_provider_name = "ensemble"
            if stream:
                yield from self.ensemble.chat(
                    messages, task_type=task_type, stream=True, preferred_provider=preferred
                )
            else:
                yield "".join(self.ensemble.chat(
                    messages, task_type=task_type, stream=False, preferred_provider=preferred
                ))
            return

        # Standard failover
        if stream:
            yield from self._failover_chat_stream(
                messages, tools, preferred, temperature, max_tokens
            )
        else:
            yield self._failover_chat_string(
                messages, tools, preferred, temperature, max_tokens
            )

    def _failover_chat_stream(
        self,
        messages: list,
        tools: Optional[list] = None,
        preferred: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096
    ) -> Generator[str, None, None]:
        """Stream chat with automatic failover"""
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
                    for chunk in provider.chat(messages, tools, True, temperature, max_tokens):
                        yield chunk
                    return

                except RateLimitError as e:
                    print(f"[Rate Limit] {provider_name}: {e}. Waiting {e.retry_after}s...")
                    time.sleep(e.retry_after)
                    retries += 1
                    if retries > max_retries:
                        break

                except ProviderError as e:
                    print(f"[Error] {provider_name}: {e}")
                    last_error = e
                    break

                except Exception as e:
                    print(f"[Unexpected] {provider_name}: {e}")
                    last_error = e
                    break

        error_msg = f"All providers failed. Last error: {last_error}" if last_error else "No providers available"
        yield f"[ERROR] {error_msg}"

    def _failover_chat_string(
        self,
        messages: list,
        tools: Optional[list] = None,
        preferred: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096
    ) -> str:
        """Non-streaming chat with automatic failover"""
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
                    return "".join(provider.chat(messages, tools, False, temperature, max_tokens))

                except RateLimitError as e:
                    print(f"[Rate Limit] {provider_name}: {e}. Waiting {e.retry_after}s...")
                    time.sleep(e.retry_after)
                    retries += 1
                    if retries > max_retries:
                        break

                except ProviderError as e:
                    print(f"[Error] {provider_name}: {e}")
                    last_error = e
                    break

                except Exception as e:
                    print(f"[Unexpected] {provider_name}: {e}")
                    last_error = e
                    break

        error_msg = f"All providers failed. Last error: {last_error}" if last_error else "No providers available"
        return f"[ERROR] {error_msg}"

    def get_ensemble_status(self) -> Dict[str, Any]:
        if self.ensemble:
            return self.ensemble.get_status()
        return {"available": False, "reason": "Not initialized"}

    def close(self):
        """Close all providers"""
        for provider in self.providers.values():
            provider.close()
        if self.ensemble:
            self.ensemble.close()
