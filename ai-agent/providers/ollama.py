"""Ollama provider implementation (OpenAI-compatible API)"""
import json
from typing import Generator, Optional
from .base import BaseProvider, ProviderError

class OllamaProvider(BaseProvider):
    def chat(self, messages: list, tools: Optional[list] = None, stream: bool = False) -> Generator[str, None, None]:
        url = f"{self.config.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.config.model,
            "messages": messages,
            "stream": stream,
            "temperature": 0.7
        }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        if stream:
            response = self.client.post(url, headers=headers, json=payload, timeout=self.config.timeout)
            if response.status_code != 200:
                raise ProviderError(f"Ollama error: {response.text[:500]}")

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
                raise ProviderError(f"Ollama error: {data['error']}")

            content = data["choices"][0]["message"].get("content", "")
            tool_calls = data["choices"][0]["message"].get("tool_calls", [])

            if tool_calls:
                yield json.dumps({"tool_calls": tool_calls})
            else:
                yield content

    def is_available(self) -> bool:
        try:
            response = self.client.get(f"{self.config.base_url}/models", timeout=5)
            return response.status_code == 200
        except Exception:
            return False
