"""Ensemble Provider — параллельный запуск Local + API + голосование
Fixed: Proper ProviderConfig initialization, ordered merge, exact pattern matching
"""
import time
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional, Generator
from dataclasses import dataclass
from pathlib import Path

from providers.base import BaseProvider, ProviderError
from providers.nvidia_nim import NvidiaNimProvider
from providers.ollama import OllamaProvider
from config import ProviderConfig

@dataclass
class EnsembleResult:
    """Результат одного провайдера в ансамбле"""
    provider_name: str
    model_id: str
    response: str
    latency_ms: float
    tokens_used: int
    quality_score: float = 0.0
    error: Optional[str] = None

@dataclass
class VoteResult:
    """Итог голосования ансамбля"""
    winner: EnsembleResult
    all_results: List[EnsembleResult]
    merge_needed: bool = False
    merged_response: Optional[str] = None
    confidence: float = 0.0
    divergence_reason: Optional[str] = None


class QualityScorer:
    """Оценивает качество ответа по multiple criteria"""

    @staticmethod
    def score(response: str, task_type: str = "general") -> float:
        """Score 0.0-1.0 по нескольким метрикам"""
        scores = []

        # 1. Длина (не слишком короткий, не слишком длинный)
        length = len(response)
        if 100 < length < 10000:
            scores.append(0.9)
        elif length > 0:
            scores.append(0.5)
        else:
            scores.append(0.0)

        # 2. Структурированность
        structure_score = 0.0
        if "```" in response:
            structure_score += 0.3
        if any(c in response for c in ["# ", "## ", "### "]):
            structure_score += 0.2
        if "|" in response and "---" in response:
            structure_score += 0.2
        if "- " in response or re.search(r"^\d+\. ", response, re.MULTILINE):
            structure_score += 0.2
        scores.append(min(structure_score, 1.0))

        # 3. Code quality
        if "```" in response:
            code_score = 0.0
            code_blocks = response.split("```")
            for block in code_blocks[1::2]:
                lines = block.strip().split("\n")
                if len(lines) > 3:
                    code_score += 0.3
                if re.search(r"\b(def|class)\b", block):
                    code_score += 0.2
                if re.search(r"\b(import|from)\b", block):
                    code_score += 0.1
            scores.append(min(code_score, 1.0))
        else:
            scores.append(0.5)

        # 4. Completeness
        if any(w in response.lower()[-500:] for w in ["summary", "итог", "conclusion", "result", "output"]):
            scores.append(0.9)
        else:
            scores.append(0.5)

        # 5. Task-specific scoring (FIXED: exact word boundaries)
        if task_type == "coding":
            if re.search(r"\b(test|pytest|unittest|assert)\b", response.lower()):
                scores.append(0.9)
            else:
                scores.append(0.5)
        elif task_type == "debugging":
            if re.search(r"\b(error|bug|fix|issue|exception)\b", response.lower()):
                scores.append(0.9)
            else:
                scores.append(0.5)
        else:
            scores.append(0.7)

        return sum(scores) / len(scores)


class EnsembleProvider:
    """
    Параллельный ансамбль: NVIDIA NIM API + Ollama/vLLM.
    Запускает оба, сравнивает, выбирает лучший или объединяет.
    """

    def __init__(
        self,
        nvidia_api_key: str,
        nvidia_model: str = "mistralai/mistral-large-3-675b-instruct-2512",
        ollama_base_url: str = "http://localhost:11434/v1",
        ollama_model: str = "codellama:34b",
        vllm_base_url: Optional[str] = None,
        vllm_model: Optional[str] = None,
        max_workers: int = 4,
        confidence_threshold: float = 0.7,
        divergence_threshold: float = 0.3,
    ):
        # FIX: Create proper ProviderConfig for each provider
        nvidia_cfg = ProviderConfig(
            name="nvidia_nim",
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=nvidia_api_key,
            model=nvidia_model,
            priority=1,
            rate_limit_rpm=40,
            is_free=True,
            timeout=120,
            max_retries=3
        )
        self.nvidia = NvidiaNimProvider(nvidia_cfg)

        ollama_cfg = ProviderConfig(
            name="ollama",
            base_url=ollama_base_url,
            api_key=None,
            model=ollama_model,
            priority=3,
            rate_limit_rpm=9999,
            is_free=True,
            timeout=300,
            max_retries=1
        )
        self.ollama = OllamaProvider(ollama_cfg)

        self.vllm = None
        if vllm_base_url and vllm_model:
            vllm_cfg = ProviderConfig(
                name="vllm",
                base_url=vllm_base_url,
                api_key=None,
                model=vllm_model,
                priority=4,
                rate_limit_rpm=9999,
                is_free=True,
                timeout=300,
                max_retries=1
            )
            from providers.vllm_provider import VLLMProvider
            self.vllm = VLLMProvider(vllm_cfg)

        self.max_workers = max_workers
        self.confidence_threshold = confidence_threshold
        self.divergence_threshold = divergence_threshold
        self.scorer = QualityScorer()

    def _call_single_provider(
        self,
        provider_name: str,
        provider: BaseProvider,
        messages: List[Dict[str, str]],
        task_type: str = "general"
    ) -> EnsembleResult:
        """Вызов одного провайдера с замером метрик"""
        start = time.time()
        try:
            response = ""
            # FIX: Always stream=True, collect chunks
            for chunk in provider.chat(messages, stream=True):
                response += chunk

            latency = (time.time() - start) * 1000
            tokens = len(str(messages)) // 4 + len(response) // 4
            quality = self.scorer.score(response, task_type)

            return EnsembleResult(
                provider_name=provider_name,
                model_id=getattr(provider, 'model', 'unknown'),
                response=response,
                latency_ms=latency,
                tokens_used=tokens,
                quality_score=quality
            )
        except Exception as e:
            return EnsembleResult(
                provider_name=provider_name,
                model_id=getattr(provider, 'model', 'unknown'),
                response="",
                latency_ms=(time.time() - start) * 1000,
                tokens_used=0,
                quality_score=0.0,
                error=str(e)
            )

    def _compare_responses(self, results: List[EnsembleResult]) -> VoteResult:
        """
        Сравнивает ответы и принимает решение.
        """
        valid_results = [r for r in results if r.error is None and r.response]

        if not valid_results:
            return VoteResult(
                winner=results[0] if results else EnsembleResult("none", "", "", 0, 0),
                all_results=results,
                confidence=0.0,
                divergence_reason="All providers failed"
            )

        if len(valid_results) == 1:
            return VoteResult(
                winner=valid_results[0],
                all_results=results,
                confidence=1.0
            )

        # Score по quality + latency
        for r in valid_results:
            latency_bonus = max(0, 1.0 - (r.latency_ms / 30000)) * 0.1
            r.quality_score = min(1.0, r.quality_score + latency_bonus)

        valid_results.sort(key=lambda x: x.quality_score, reverse=True)
        winner = valid_results[0]
        runner_up = valid_results[1] if len(valid_results) > 1 else None

        if runner_up:
            score_diff = winner.quality_score - runner_up.quality_score

            if score_diff > self.divergence_threshold:
                return VoteResult(
                    winner=winner,
                    all_results=results,
                    confidence=winner.quality_score,
                    divergence_reason=f"Clear winner: {winner.provider_name} ({winner.quality_score:.2f} vs {runner_up.quality_score:.2f})"
                )
            else:
                merged = self._merge_responses(winner.response, runner_up.response)
                return VoteResult(
                    winner=winner,
                    all_results=results,
                    merge_needed=True,
                    merged_response=merged,
                    confidence=(winner.quality_score + runner_up.quality_score) / 2,
                    divergence_reason=f"Similar quality, merged responses ({winner.quality_score:.2f} vs {runner_up.quality_score:.2f})"
                )

        return VoteResult(
            winner=winner,
            all_results=results,
            confidence=winner.quality_score
        )

    def _merge_responses(self, response_a: str, response_b: str) -> str:
        """Умное объединение двух ответов (FIXED: preserves order)"""
        score_a = self.scorer.score(response_a)
        score_b = self.scorer.score(response_b)

        if score_a > score_b + 0.2:
            return response_a
        elif score_b > score_a + 0.2:
            return response_b

        # FIX: Preserve line order using seen set
        seen = set(response_a.split("\n"))
        unique_b = []
        for line in response_b.split("\n"):
            if line not in seen:
                unique_b.append(line)
                seen.add(line)

        if unique_b:
            return response_a + "\n\n# Additional insights from second model:\n" + "\n".join(unique_b)

        return response_a

    def chat(
        self,
        messages: List[Dict[str, str]],
        task_type: str = "general",
        stream: bool = False,
        preferred_provider: Optional[str] = None
    ) -> Generator[str, None, None]:
        """Главный метод ансамбля."""
        providers_to_run = []

        if self.nvidia.is_available():
            providers_to_run.append(("nvidia_nim", self.nvidia))
        if self.ollama.is_available():
            providers_to_run.append(("ollama", self.ollama))
        if self.vllm and self.vllm.is_available():
            providers_to_run.append(("vllm", self.vllm))

        if not providers_to_run:
            yield "[ERROR] No providers available for ensemble"
            return

        if preferred_provider:
            providers_to_run = [(n, p) for n, p in providers_to_run if n == preferred_provider]
            if not providers_to_run:
                yield "[ERROR] Preferred provider not available"
                return

        yield f"🔄 Ensemble: запускаю {len(providers_to_run)} провайдеров параллельно...\n"

        results = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(
                    self._call_single_provider,
                    name,
                    prov,
                    messages,
                    task_type
                ): name
                for name, prov in providers_to_run
            }

            for future in as_completed(futures):
                provider_name = futures[future]
                try:
                    result = future.result(timeout=120)
                    results.append(result)
                    status = "✅" if result.error is None else "❌"
                    yield f"{status} {provider_name} ({result.model_id}): {result.latency_ms:.0f}ms, quality={result.quality_score:.2f}\n"
                    if result.error:
                        yield f" Error: {result.error[:200]}\n"
                except Exception as e:
                    yield f"❌ {provider_name}: Timeout/Exception — {str(e)[:200]}\n"
                    results.append(EnsembleResult(
                        provider_name=provider_name,
                        model_id="unknown",
                        response="",
                        latency_ms=0,
                        tokens_used=0,
                        error=str(e)
                    ))

        # Голосование
        vote = self._compare_responses(results)

        yield f"\n📊 Ensemble Vote Results:\n"
        for r in vote.all_results:
            if r.error:
                yield f" ❌ {r.provider_name}: ERROR\n"
            else:
                yield f" {'🏆' if r == vote.winner else '  '} {r.provider_name}: score={r.quality_score:.2f} | {r.latency_ms:.0f}ms\n"

        yield f"\n🎯 Winner: {vote.winner.provider_name} ({vote.winner.model_id})\n"
        yield f"📈 Confidence: {vote.confidence:.2f}\n"
        if vote.divergence_reason:
            yield f"💡 {vote.divergence_reason}\n"

        if vote.merge_needed and vote.merged_response:
            yield f"\n🔀 Merged response used\n"
            final_response = vote.merged_response
        else:
            final_response = vote.winner.response

        if stream:
            for chunk in self._stream_response(final_response):
                yield chunk
        else:
            yield final_response

    def _stream_response(self, response: str) -> Generator[str, None, None]:
        """Стриминг ответа по чанкам"""
        chunk_size = 50
        for i in range(0, len(response), chunk_size):
            yield response[i:i + chunk_size]
            time.sleep(0.01)

    def get_status(self) -> Dict[str, Any]:
        """Статус ансамбля"""
        return {
            "nvidia_available": self.nvidia.is_available(),
            "nvidia_model": getattr(self.nvidia, 'model', 'unknown'),
            "ollama_available": self.ollama.is_available(),
            "ollama_model": getattr(self.ollama, 'model', 'unknown'),
            "vllm_available": self.vllm.is_available() if self.vllm else False,
            "vllm_model": getattr(self.vllm, 'model', None) if self.vllm else None,
            "max_workers": self.max_workers,
            "confidence_threshold": self.confidence_threshold,
            "divergence_threshold": self.divergence_threshold,
        }

    def close(self):
        """Close all providers to prevent connection leaks"""
        self.nvidia.close()
        self.ollama.close()
        if self.vllm:
            self.vllm.close()
