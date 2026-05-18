"""Cost tracking and rate limit dashboard"""
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime


@dataclass
class UsageRecord:
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    timestamp: datetime = field(default_factory=datetime.now)
    error: Optional[str] = None


class CostTracker:
    """Track usage across all providers"""

    # Approximate pricing per 1M tokens (input / output)
    PRICING = {
        "anthropic/claude-3.5-sonnet": (3.0, 15.0),
        "gpt-4": (30.0, 60.0),
        "nvidia/llama-3.1-nemotron-70b-instruct": (0.5, 1.0),
        "codellama:34b": (0.0, 0.0),  # Local = free
        "llama3:70b": (0.0, 0.0),
    }

    def __init__(self):
        self.records: List[UsageRecord] = []
        self.provider_totals: Dict[str, Dict[str, float]] = {}

    def log_request(
        self,
        provider: str,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        latency_ms: int = 0,
        error: Optional[str] = None
    ):
        """Log a single request"""
        cost = self._estimate_cost(model, input_tokens, output_tokens)

        record = UsageRecord(
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            latency_ms=latency_ms,
            error=error
        )
        self.records.append(record)

        # Update totals
        if provider not in self.provider_totals:
            self.provider_totals[provider] = {
                "requests": 0, "tokens": 0, "cost": 0.0, "errors": 0
            }
        self.provider_totals[provider]["requests"] += 1
        self.provider_totals[provider]["tokens"] += input_tokens + output_tokens
        self.provider_totals[provider]["cost"] += cost
        if error:
            self.provider_totals[provider]["errors"] += 1

    def _estimate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Estimate cost in USD"""
        prices = self.PRICING.get(model, (1.0, 2.0))
        input_cost = (input_tokens / 1_000_000) * prices[0]
        output_cost = (output_tokens / 1_000_000) * prices[1]
        return round(input_cost + output_cost, 6)

    def get_summary(self) -> str:
        """Get formatted summary"""
        if not self.records:
            return "No usage recorded yet."

        total_cost = sum(r.cost_usd for r in self.records)
        total_tokens = sum(r.input_tokens + r.output_tokens for r in self.records)
        total_latency = sum(r.latency_ms for r in self.records)
        avg_latency = total_latency / len(self.records) if self.records else 0

        lines = [
            "\n" + "=" * 60,
            "📊 USAGE & COST SUMMARY",
            "=" * 60,
            f"Total Requests: {len(self.records)}",
            f"Total Tokens: {total_tokens:,}",
            f"Total Cost: ${total_cost:.4f}",
            f"Avg Latency: {avg_latency:.0f}ms",
            "",
            "By Provider:",
        ]

        for provider, stats in self.provider_totals.items():
            lines.append(
                f"  {provider}: {stats['requests']} req, "
                f"{stats['tokens']:,} tokens, "
                f"${stats['cost']:.4f}, "
                f"{stats['errors']} errors"
            )

        lines.append("=" * 60)
        return "\n".join(lines)

    def get_rate_limit_status(self) -> Dict[str, Dict]:
        """Get current rate limit status per provider"""
        # In real implementation, this would track from API headers
        return {
            p: {"requests_last_min": 0, "limit": 60, "remaining": 60}
            for p in self.provider_totals.keys()
        }
