"""OpenRouter provider implementation"""
import json
from typing import Generator, Optional, List, Dict, Any
from .base import BaseProvider, ProviderError

class OpenRouterProvider(BaseProvider):
    def chat(self, messages: list, tools: Optional[list] = None, stream: bool = False) -> Generator[str, None, None]:
        url = f"{self.config.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://ai-agent.local",
            "X-Title": "AI Agent"
        }

        payload = {
            "model": self.config.model,
            "messages": messages,
            "stream": stream,
            "temperature": 0.7,
            "max_tokens": 4096
        }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        if stream:
            # For streaming, we use a different approach
            response = self.client.post(url, headers=headers, json=payload, timeout=self.config.timeout)
            if response.status_code != 200:
                self._parse_retry_after(response.text, dict(response.headers))
                raise ProviderError(f"OpenRouter error: {response.text[:500]}")

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
                raise ProviderError(f"OpenRouter API error: {error_msg}")

            content = data["choices"][0]["message"].get("content", "")

            # Check for tool calls
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
