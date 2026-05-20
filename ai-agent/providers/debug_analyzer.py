"""Debug Analyzer — OpenRouter дебаггер для анализа расхождений
Используется ТОЛЬКО когда Local и API дают сильно разные ответы.
НЕ используется как fallback при падении API.
"""
import json
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from providers.openrouter import OpenRouterProvider


@dataclass
class DivergenceReport:
    """Отчёт о расхождении"""
    local_response: str
    api_response: str
    local_score: float
    api_score: float
    confidence: float                    # Уверенность в выборе
    winner: str                          # "local" | "api" | "merge" | "uncertain"
    analysis: str                        # Текстовый анализ дебаггера
    recommendations: List[str]           # Рекомендации
    merged_response: Optional[str] = None


class DebugAnalyzer:
    """
    OpenRouter дебаггер.
    Вызывается только при divergence > threshold.
    Анализирует ПОЧЕМУ модели расходятся, а не генерирует новый код.
    """

    def __init__(self, api_key: str, model: str = "deepseek/deepseek-r1:free"):
        self.provider = OpenRouterProvider(api_key=api_key, model=model)
        self.rpm_tracker = {"requests": [], "limit": 20, "daily_limit": 200}

    def _check_rate_limit(self) -> bool:
        """Проверяет лимиты OpenRouter Free"""
        now = time.time()
        # Очищаем старые запросы (> 1 мин)
        self.rpm_tracker["requests"] = [
            t for t in self.rpm_tracker["requests"] 
            if now - t < 60
        ]
        return len(self.rpm_tracker["requests"]) < self.rpm_tracker["limit"]

    def _wait_for_rate_limit(self):
        """Ждёт освобождения лимита"""
        while not self._check_rate_limit():
            time.sleep(3)
        self.rpm_tracker["requests"].append(time.time())

    def analyze_divergence(
        self,
        task: str,
        local_result: str,
        api_result: str,
        local_provider: str = "ollama",
        api_provider: str = "nvidia_nim",
        local_model: str = "unknown",
        api_model: str = "unknown",
        threshold: float = 0.3
    ) -> DivergenceReport:
        """
        Анализирует расхождение между Local и API ответами.

        Args:
            task: Оригинальная задача
            local_result: Ответ локальной модели
            api_result: Ответ API модели
            local_provider: Имя локального провайдера
            api_provider: Имя API провайдера
            threshold: Порог для flag divergence
        """
        self._wait_for_rate_limit()

        # Промпт для дебаггера — анализ, не генерация
        prompt = f"""Ты — Senior Debug Analyst. Проанализируй расхождение между двумя AI моделями.

## Оригинальная задача
{task[:2000]}

## Ответ от {local_provider} ({local_model})
```
{local_result[:4000]}
```

## Ответ от {api_provider} ({api_model})
```
{api_result[:4000]}
```

## Твоя задача
Проанализируй расхождения и ответь:
1. Какие ключевые различия между ответами?
2. Какой ответ более корректный и почему?
3. Какие ошибки/проблемы есть в каждом?
4. Какой ответ выбрать: local, api, или объединить?
5. Дай конкретные рекомендации по исправлению.

## Формат ответа (JSON)
{{
    "winner": "local" | "api" | "merge" | "uncertain",
    "confidence": 0.0-1.0,
    "analysis": "Подробный анализ расхождений...",
    "local_issues": ["проблема 1", "проблема 2"],
    "api_issues": ["проблема 1", "проблема 2"],
    "recommendations": ["рекомендация 1", "рекомендация 2"],
    "merge_suggestion": "Если merge — как объединить"
}}

Верни ТОЛЬКО JSON, без markdown."""

        try:
            messages = [{"role": "user", "content": prompt}]
            response = self.provider.complete(messages, temperature=0.1)

            # Парсим JSON
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group())
            else:
                analysis = json.loads(response)

            winner = analysis.get("winner", "uncertain")
            confidence = float(analysis.get("confidence", 0.5))

            # Оцениваем ответы
            local_score = self._score_response(local_result, analysis.get("local_issues", []))
            api_score = self._score_response(api_result, analysis.get("api_issues", []))

            # Merge если нужно
            merged = None
            if winner == "merge":
                merged = self._merge_responses(
                    local_result, api_result, 
                    analysis.get("merge_suggestion", "")
                )

            return DivergenceReport(
                local_response=local_result,
                api_response=api_result,
                local_score=local_score,
                api_score=api_score,
                confidence=confidence,
                winner=winner,
                analysis=analysis.get("analysis", ""),
                recommendations=analysis.get("recommendations", []),
                merged_response=merged
            )

        except Exception as e:
            # Fallback — простое сравнение
            return DivergenceReport(
                local_response=local_result,
                api_response=api_result,
                local_score=0.5,
                api_score=0.5,
                confidence=0.0,
                winner="uncertain",
                analysis=f"Debug analyzer failed: {str(e)}. Manual review needed.",
                recommendations=["Compare responses manually", "Run tests on both"]
            )

    def _score_response(self, response: str, issues: List[str]) -> float:
        """Оценивает качество ответа (меньше issues = выше score)"""
        base = 0.8
        penalty = len(issues) * 0.15
        return max(0.0, base - penalty)

    def _merge_responses(self, local: str, api: str, suggestion: str) -> str:
        """Умное объединение на основе рекомендаций дебаггера"""
        # Берём лучшие части из обоих
        lines_local = set(local.split("\n"))
        lines_api = set(api.split("\n"))

        # Уникальные строки из API (предполагаем API более точный)
        unique_api = lines_api - lines_local

        if unique_api and suggestion:
            return local + "\n\n# Additional from API model:\n" + "\n".join(unique_api)

        return local if len(local) > len(api) else api

    def quick_analyze_error(
        self,
        error_message: str,
        code_context: str,
        model_used: str = "unknown"
    ) -> str:
        """
        Быстрый анализ ошибки (для retry logic).
        Используется когда модель падает, не когда расходятся.
        """
        self._wait_for_rate_limit()

        prompt = f"""Ты — Error Analyst. Объясни ошибку и предложи фикс.

Модель: {model_used}
Ошибка:
{error_message[:2000]}

Контекст:
{code_context[:3000]}

Дай:
1. Root cause (1-2 предложения)
2. Конкретный фикс (код)
3. Как избежать в будущем"""

        try:
            messages = [{"role": "user", "content": prompt}]
            return self.provider.complete(messages, temperature=0.2)
        except Exception as e:
            return f"Quick analysis failed: {str(e)}"
