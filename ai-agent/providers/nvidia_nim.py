"""NVIDIA NIM provider implementation
v6 update: max_tokens=4096, temperature/max_tokens params, status check
"""
import json
from typing import Generator, Optional
from .base import BaseProvider, ProviderError


class NvidiaNimProvider(BaseProvider):
    def chat(self, messages: list, tools: Optional[list] = None,
             stream: bool = False, temperature: float = 0.2,
             max_tokens: int = 4096) -> Generator[str, None, None]:
        url = f"{self.config.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.config.model,
            "messages": messages,
            "stream": stream,
            "temperature": temperature,
            "max_tokens": max_tokens  # FIX: Was hardcoded 1024, now configurable
        }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        if stream:
            response = self.client.post(url, headers=headers, json=payload, 
                                       timeout=getattr(self.config, 'timeout', 120))
            # FIX: Add raise_for_status for streaming
            if response.status_code != 200:
                self._parse_retry_after(response.text, dict(response.headers))
                raise ProviderError(f"NVIDIA NIM error: {response.text[:500]}")

            response.raise_for_status()  # FIX: Check HTTP status

            for line in response.iter_lines():
                if line:
                    line = line.decode('utf-8') if isinstance(line, bytes) else line
                    if line.startswith('data: '):
                        data = line[6:]
                        if data == '[DONE]':
                            break
                        try:
                            chunk = json.loads(data)
                            if chunk.get('choices') and chunk['choices'][0].get('delta', {}).get('content'):
                                yield chunk['choices'][0]['delta']['content']
                        except json.JSONDecodeError:
                            continue
        else:
            data = self._make_request("POST", url, headers=headers, json=payload)

            if data.get("error"):
                error_msg = data["error"].get("message", "Unknown error")
                raise ProviderError(f"NVIDIA NIM API error: {error_msg}")

            content = data["choices"][0]["message"].get("content", "")
            tool_calls = data["choices"][0]["message"].get("tool_calls", [])

            if tool_calls:
                yield json.dumps({"tool_calls": tool_calls})
            else:
                yield content

    def is_available(self) -> bool:
        if not self.config.api_key:
            return False
        try:
            headers = {"Authorization": f"Bearer {self.config.api_key}"}
            response = self.client.get(f"{self.config.base_url}/models", headers=headers, timeout=10)
            return response.status_code == 200
        except Exception:
            return False
