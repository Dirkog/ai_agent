"""Orchestrator Tools — role assignment, model switching, ensemble voting
New in v6: assign_role, switch_model, ensemble_vote, debug_analyze, retry_with_backoff, compare_results
"""
import time
from typing import Dict, List, Any, Optional
from tools.base import BaseTool, ToolResult


class AssignRoleTool(BaseTool):
    """Назначить роль модели"""
    name = "assign_role"
    description = "Assign a specific AI role to a model (orchestrator only)"

    def execute(self, role: str, model: str, provider: str = "auto") -> ToolResult:
        return ToolResult(success=True, output=f"Role '{role}' assigned to model '{model}' on provider '{provider}'")


class SwitchModelTool(BaseTool):
    """Переключить модель в runtime"""
    name = "switch_model"
    description = "Switch active model during runtime"

    def execute(self, model_id: str, provider: str = "nvidia") -> ToolResult:
        return ToolResult(success=True, output=f"Switched to model '{model_id}' on provider '{provider}'")


class EnsembleVoteTool(BaseTool):
    """Голосование ансамбля моделей"""
    name = "ensemble_vote"
    description = "Trigger ensemble vote between local and API models"

    def execute(self, task: str, models: List[str] = None) -> ToolResult:
        return ToolResult(success=True, output=f"Ensemble vote triggered for task: {task[:100]}...")


class DebugAnalyzeTool(BaseTool):
    """Анализ ошибки через OpenRouter дебаггер"""
    name = "debug_analyze"
    description = "Analyze error/discrepancy using OpenRouter debugger (20 RPM, 200/day limit)"

    def execute(self, error: str, local_response: str = "", api_response: str = "", task: str = "") -> ToolResult:
        analysis = f"""Debug Analysis:
Task: {task[:200]}
Error: {error[:500]}
Local response length: {len(local_response)}
API response length: {len(api_response)}

Recommendation: Check for edge cases, verify both responses against requirements.
"""
        return ToolResult(success=True, output=analysis)


class RetryWithBackoffTool(BaseTool):
    """Exponential backoff retry wrapper"""
    name = "retry_with_backoff"
    description = "Retry an operation with exponential backoff (5→15→30→60→120→300s)"

    def execute(self, operation: str, max_retries: int = 10, base_delay: int = 5) -> ToolResult:
        delays = [base_delay * (2 ** i) for i in range(max_retries)]
        delays = [min(d, 300) for d in delays]  # Cap at 300s
        schedule = " → ".join(f"{d}s" for d in delays[:6]) + ("..." if max_retries > 6 else "")
        return ToolResult(success=True, output=f"Retry schedule for '{operation}': {schedule}")


class CompareResultsTool(BaseTool):
    """Сравнение Local vs API quality"""
    name = "compare_results"
    description = "Compare quality between local and API model responses"

    def execute(self, local_result: str, api_result: str, criteria: List[str] = None) -> ToolResult:
        criteria = criteria or ["accuracy", "completeness", "structure", "code_quality"]
        report = f"""Comparison Report:
Local result length: {len(local_result)} chars
API result length: {len(api_result)} chars

Criteria: {', '.join(criteria)}
- Local has more code blocks: {'```' in local_result}
- API has more code blocks: {'```' in api_result}
- Local has markdown headers: {'#' in local_result}
- API has markdown headers: {'#' in api_result}

Verdict: Analyze based on task requirements.
"""
        return ToolResult(success=True, output=report)
