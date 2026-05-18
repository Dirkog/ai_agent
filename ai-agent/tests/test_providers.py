"""Tests for provider system"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from providers.base import BaseProvider, RateLimitError, ProviderError
from providers.openrouter import OpenRouterProvider
from providers.nvidia_nim import NvidiaNimProvider
from providers.ollama import OllamaProvider
from provider_manager import ProviderManager
from config import ProviderConfig


class MockProvider(BaseProvider):
    def chat(self, messages, tools=None, stream=False):
        yield "test response"

    def is_available(self):
        return True


class TestRateLimitError:
    def test_retry_after_parsing(self):
        error = RateLimitError("Rate limit", retry_after=120)
        assert error.retry_after == 120


class TestBaseProvider:
    def test_parse_retry_after_from_text(self):
        config = ProviderConfig(name="test", base_url="http://test")
        provider = MockProvider(config)

        # Test various formats
        assert provider._parse_retry_after("try again in 30s", {}) == 31
        assert provider._parse_retry_after("retry after 2 minutes", {}) == 121
        assert provider._parse_retry_after("wait 45 seconds", {}) == 46
        assert provider._parse_retry_after("no info here", {}) == 60  # default

    def test_parse_retry_after_from_headers(self):
        config = ProviderConfig(name="test", base_url="http://test")
        provider = MockProvider(config)

        headers = {"Retry-After": "90"}
        assert provider._parse_retry_after("", headers) == 90


class TestProviderManager:
    @patch('providers.openrouter.OpenRouterProvider')
    @patch('providers.nvidia_nim.NvidiaNimProvider')
    @patch('providers.ollama.OllamaProvider')
    def test_failover(self, mock_ollama, mock_nvidia, mock_openrouter):
        # Setup mocks
        mock_openrouter.return_value.is_available.return_value = False
        mock_nvidia.return_value.is_available.return_value = True
        mock_ollama.return_value.is_available.return_value = True

        pm = ProviderManager()
        available = pm.get_available_providers()

        # OpenRouter should be unavailable
        assert "openrouter" not in available
        assert "nvidia_nim" in available


class TestProviderSchemas:
    def test_openrouter_schema(self):
        config = ProviderConfig(
            name="openrouter",
            base_url="https://test",
            api_key="test-key",
            model="test-model"
        )
        provider = OpenRouterProvider(config)
        assert provider.config.name == "openrouter"
        assert provider.config.api_key == "test-key"
