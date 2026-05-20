"""vLLM Provider — локальный inference через vLLM
Альтернатива Ollama для production-grade локального развёртывания.
Поддерживает tensor parallelism, quantization, speculative decoding.
"""
import httpx
import json
from typing import Generator, Dict, Any, Optional
from providers.base import BaseProvider, ProviderError, RateLimitError


class VLLMProvider(BaseProvider):
    """Provider for vLLM local server"""

    def __init__(self, config):
        super().__init__(config)
        self.model = config.model
        self.base_url = config.base_url.rstrip("/")
        # vLLM OpenAI-compatible API
        self.chat_url = f"{self.base_url}/chat/completions"
        self.models_url = f"{self.base_url}/models"

    def is_available(self) -> bool:
        """Check if vLLM server is running"""
        try:
            response = self.client.get(self.models_url, timeout=5)
            return response.status_code == 200
        except Exception:
            return False

    def chat(
        self,
        messages: list,
        tools: Optional[list] = None,
        stream: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 4096
    ) -> Generator[str, None, None]:
        """Chat with vLLM"""
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        try:
            if stream:
                response = self.client.post(
                    self.chat_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=120,
                    stream=True
                )
                response.raise_for_status()

                for line in response.iter_lines():
                    if line:
                        line = line.decode("utf-8")
                        if line.startswith("data: "):
                            data = line[6:]
                            if data == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data)
                                if "choices" in chunk and chunk["choices"]:
                                    delta = chunk["choices"][0].get("delta", {})
                                    if "content" in delta:
                                        yield delta["content"]
                            except json.JSONDecodeError:
                                pass
            else:
                response = self.client.post(
                    self.chat_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=120
                )
                response.raise_for_status()
                data = response.json()

                if "choices" in data and data["choices"]:
                    content = data["choices"][0].get("message", {}).get("content", "")
                    yield content
                else:
                    yield "[Error: No response from vLLM]"

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                raise RateLimitError("vLLM rate limited", 60)
            raise ProviderError(f"vLLM HTTP {e.response.status_code}: {e.response.text[:500]}")
        except httpx.RequestError as e:
            raise ProviderError(f"vLLM request error: {str(e)}")
        except Exception as e:
            raise ProviderError(f"vLLM unexpected error: {str(e)}")

    def get_model_info(self) -> Dict[str, Any]:
        """Get loaded model info from vLLM"""
        try:
            response = self.client.get(self.models_url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return {
                    "available": True,
                    "models": data.get("data", []),
                    "base_url": self.base_url,
                }
        except Exception as e:
            pass

        return {
            "available": False,
            "error": "Cannot connect to vLLM",
            "base_url": self.base_url,
        }
