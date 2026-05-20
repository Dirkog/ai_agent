"""Ensemble Provider — параллельный запуск Local + API + голосование
Ключевая фича v6: одновременно запускает NVIDIA NIM API и Ollama/vLLM,
сравнивает ответы и выбирает лучший (или объединяет).
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

        # 2. Структурированность (наличие markdown, списков, блоков кода)
        structure_score = 0.0
        if "```" in response:
            structure_score += 0.3
        if any(c in response for c in ["#", "##", "###"]):
            structure_score += 0.2
        if "|" in response and "---" in response:
            structure_score += 0.2
        if "- " in response or "1. " in response:
            structure_score += 0.2
        scores.append(min(structure_score, 1.0))

        # 3. Code quality (если есть код)
        if "```" in response:
            code_blocks = response.split("```")
            code_score = 0.0
            for block in code_blocks[1::2]:  # только содержимое блоков
                lines = block.strip().split("\n")
                if len(lines) > 3:
                    code_score += 0.3
                if "def " in block or "class " in block:
                    code_score += 0.2
                if "import " in block or "from " in block:
                    code_score += 0.1
            scores.append(min(code_score, 1.0))
        else:
            scores.append(0.5)

        # 4. Completeness (наличие заключения, summary)
        if any(w in response.lower()[-500:] for w in ["summary", "итог", "conclusion", "result", "output"]):
            scores.append(0.9)
        else:
            scores.append(0.5)

        # 5. Task-specific scoring
        if task_type == "coding":
            if "test" in response.lower() or "pytest" in response.lower():
                scores.append(0.9)
            else:
                scores.append(0.5)
        elif task_type == "debugging":
            if "error" in response.lower() or "bug" in response.lower() or "fix" in response.lower():
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
        nvidia_model: str = "nvidia/llama-3.1-nemotron-70b-instruct",
        ollama_base_url: str = "http://localhost:11434/v1",
        ollama_model: str = "codellama:34b",
        vllm_base_url: Optional[str] = None,
        vllm_model: Optional[str] = None,
        max_workers: int = 4,
        confidence_threshold: float = 0.7,
        divergence_threshold: float = 0.3,
    ):
        self.nvidia = NvidiaNimProvider(
            api_key=nvidia_api_key,
            model=nvidia_model
        )
        self.ollama = OllamaProvider(
            base_url=ollama_base_url,
            model=ollama_model
        )
        self.vllm = None
        if vllm_base_url and vllm_model:
            # vLLM provider будет создан при необходимости
            self.vllm_config = {"base_url": vllm_base_url, "model": vllm_model}
        else:
            self.vllm_config = None

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
            for chunk in provider.chat(messages, stream=False):
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
        Сравнивает ответы и принимает решение:
        - Если один явно лучше → берём его
        - Если похожие → merge
        - Если сильно разные → flag divergence
        """
        valid_results = [r for r in results if r.error is None and r.response]

        if not valid_results:
            # Все упали — вернуть ошибку
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

        # Score по quality + latency (быстрее = лучше, но с весом)
        for r in valid_results:
            latency_bonus = max(0, 1.0 - (r.latency_ms / 30000)) * 0.1  # 30s max
            r.quality_score = min(1.0, r.quality_score + latency_bonus)

        # Сортируем по quality score
        valid_results.sort(key=lambda x: x.quality_score, reverse=True)
        winner = valid_results[0]
        runner_up = valid_results[1] if len(valid_results) > 1 else None

        # Проверяем divergence
        if runner_up:
            score_diff = winner.quality_score - runner_up.quality_score

            if score_diff > self.divergence_threshold:
                # Победитель явно лучше
                return VoteResult(
                    winner=winner,
                    all_results=results,
                    confidence=winner.quality_score,
                    divergence_reason=f"Clear winner: {winner.provider_name} ({winner.quality_score:.2f} vs {runner_up.quality_score:.2f})"
                )
            else:
                # Разница маленькая — попробуем merge
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
        """Умное объединение двух ответов"""
        # Простая стратегия: берём более длинный/структурированный
        score_a = self.scorer.score(response_a)
        score_b = self.scorer.score(response_b)

        if score_a > score_b + 0.2:
            return response_a
        elif score_b > score_a + 0.2:
            return response_b

        # Если похожие — объединяем уникальные части
        lines_a = set(response_a.split("\n"))
        lines_b = set(response_b.split("\n"))

        unique_b = lines_b - lines_a
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
        """
        Главный метод ансамбля.
        Параллельно запускает все доступные провайдеры.
        """
        providers_to_run = []

        # Проверяем доступность
        if self.nvidia.is_available():
            providers_to_run.append(("nvidia_nim", self.nvidia))
        if self.ollama.is_available():
            providers_to_run.append(("ollama", self.ollama))

        if not providers_to_run:
            yield "[ERROR] No providers available for ensemble"
            return

        # Если preferred_provider указан и доступен — используем только его
        if preferred_provider:
            for name, prov in providers_to_run:
                if name == preferred_provider:
                    providers_to_run = [(name, prov)]
                    break

        yield f"🔄 Ensemble: запускаю {len(providers_to_run)} провайдеров параллельно...\n"

        results = []

        # Параллельный запуск
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
                        yield f"   Error: {result.error[:200]}\n"
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
                yield f"  ❌ {r.provider_name}: ERROR\n"
            else:
                yield f"  {'🏆' if r == vote.winner else '  '} {r.provider_name}: score={r.quality_score:.2f} | {r.latency_ms:.0f}ms\n"

        yield f"\n🎯 Winner: {vote.winner.provider_name} ({vote.winner.model_id})\n"
        yield f"📈 Confidence: {vote.confidence:.2f}\n"
        if vote.divergence_reason:
            yield f"💡 {vote.divergence_reason}\n"

        if vote.merge_needed and vote.merged_response:
            yield f"\n🔀 Merged response used\n"
            final_response = vote.merged_response
        else:
            final_response = vote.winner.response

        # Возвращаем финальный ответ
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
            "vllm_configured": self.vllm_config is not None,
            "max_workers": self.max_workers,
            "confidence_threshold": self.confidence_threshold,
            "divergence_threshold": self.divergence_threshold,
        }
