"""Base provider with rate limiting and error handling"""
import time
import re
import json
from abc import ABC, abstractmethod
from typing import Generator, Dict, Any, Optional
import httpx

class RateLimitError(Exception):
    def __init__(self, message: str, retry_after: int = 60):
        super().__init__(message)
        self.retry_after = retry_after

class ProviderError(Exception):
    pass

class BaseProvider(ABC):
    def __init__(self, config):
        self.config = config
        self.last_request_time = 0
        self.request_count = 0
        self.client = httpx.Client(timeout=config.timeout)

    def _check_rate_limit(self):
        """Simple rate limit tracking"""
        current_time = time.time()
        if current_time - self.last_request_time >= 60:
            self.request_count = 0
            self.last_request_time = current_time

        if self.request_count >= self.config.rate_limit_rpm:
            sleep_time = 60 - (current_time - self.last_request_time)
            if sleep_time > 0:
                print(f"[Rate Limit] Self-limiting: waiting {sleep_time:.1f}s")
                time.sleep(sleep_time)
                self.request_count = 0
                self.last_request_time = time.time()

    def _parse_retry_after(self, error_text: str, headers: Dict) -> int:
        """Extract retry time from error message or headers"""
        # Check headers first
        retry_after = headers.get("retry-after") or headers.get("Retry-After")
        if retry_after:
            try:
                return int(retry_after)
            except ValueError:
                # Could be HTTP date, ignore for simplicity
                pass

        # Parse from error text
        patterns = [
            r"try again in (\d+(?:\.\d+)?)s",
            r"retry after (\d+(?:\.\d+)?) (second|minute)",
            r"rate limit exceeded.*?(\d+(?:\.\d+)?) (second|minute)",
            r"please retry after (\d+(?:\.\d+)?)",
            r"wait (\d+(?:\.\d+)?) (second|minute)",
        ]

        text_lower = error_text.lower()
        for pattern in patterns:
            match = re.search(pattern, text_lower)
            if match:
                value = float(match.group(1))
                unit = match.group(2) if len(match.groups()) > 1 else "second"
                if "minute" in unit:
                    value *= 60
                return int(value) + 1

        return self.config.rate_limit_rpm  # Default fallback

    def _make_request(self, method: str, url: str, **kwargs) -> Dict[str, Any]:
        """Make request with rate limit handling and retries"""
        retries = 0
        max_retries = self.config.max_retries

        while retries <= max_retries:
            try:
                self._check_rate_limit()
                response = self.client.request(method, url, **kwargs)
                self.request_count += 1

                if response.status_code == 429:
                    error_text = response.text
                    retry_after = self._parse_retry_after(error_text, dict(response.headers))
                    print(f"[Rate Limit] {self.config.name}: 429 detected. Waiting {retry_after}s...")
                    print(f"[Rate Limit] Error detail: {error_text[:200]}")

                    if retries < max_retries:
                        time.sleep(retry_after)
                        retries += 1
                        continue
                    else:
                        raise RateLimitError(f"Rate limit exceeded for {self.config.name}", retry_after)

                response.raise_for_status()
                return response.json()

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    retry_after = self._parse_retry_after(e.response.text, dict(e.response.headers))
                    if retries < max_retries:
                        print(f"[Rate Limit] {self.config.name}: HTTP 429. Waiting {retry_after}s...")
                        time.sleep(retry_after)
                        retries += 1
                        continue
                raise ProviderError(f"HTTP {e.response.status_code}: {e.response.text[:500]}")
            except httpx.RequestError as e:
                if retries < max_retries:
                    wait_time = 2 ** retries
                    print(f"[Network] {self.config.name}: Request failed. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    retries += 1
                    continue
                raise ProviderError(f"Network error after {max_retries} retries: {str(e)}")

        raise ProviderError("Max retries exceeded")

    @abstractmethod
    def chat(self, messages: list, tools: Optional[list] = None, stream: bool = False) -> Generator[str, None, None]:
        pass

    @abstractmethod
    def is_available(self) -> bool:
        pass
