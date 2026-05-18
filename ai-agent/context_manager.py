"""Context management — trim history, summarize old iterations"""
import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class ContextWindow:
    max_tokens: int = 120_000  # Claude 3.5 Sonnet context
    reserve_tokens: int = 20_000  # Reserve for response

    def estimate_tokens(self, messages: List[Dict[str, str]]) -> int:
        """Rough token estimation (1 token ≈ 4 chars)"""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            total += len(content) // 4 + 50  # +50 for overhead
        return total

    def trim(self, messages: List[Dict[str, str]], keep_recent: int = 10) -> List[Dict[str, str]]:
        """Trim old messages while preserving system prompt and recent context"""
        if len(messages) <= keep_recent + 1:
            return messages

        # Always keep system prompt (first message)
        system = messages[0] if messages[0].get("role") == "system" else None

        # Keep recent messages verbatim
        recent = messages[-keep_recent:]

        # Summarize middle section
        middle = messages[1:-keep_recent] if system else messages[:-keep_recent]

        if middle:
            summary = self._summarize_iterations(middle)
            result = []
            if system:
                result.append(system)
            result.append({
                "role": "user",
                "content": f"[PREVIOUS CONTEXT SUMMARY]\n{summary}\n\nContinue from recent messages below."
            })
            result.extend(recent)
            return result

        return messages

    def _summarize_iterations(self, messages: List[Dict[str, str]]) -> str:
        """Compress old iterations into summary"""
        # Extract tool calls and results
        tools_used = []
        files_modified = []
        key_decisions = []

        for msg in messages:
            content = msg.get("content", "")
            if "[Executing]" in content:
                # Extract tool name
                if "write_file" in content or "apply_diff" in content:
                    # Try to extract filename
                    import re
                    match = re.search(r'"path":\s*"([^"]+)"', content)
                    if match:
                        files_modified.append(match.group(1))
                tools_used.append(content.split("[")[1].split("]")[0] if "[" in content else "tool")
            elif "decided" in content.lower() or "chosen" in content.lower():
                key_decisions.append(content[:200])

        summary_parts = []
        if files_modified:
            summary_parts.append(f"Files modified: {', '.join(set(files_modified))}")
        if tools_used:
            summary_parts.append(f"Tools used: {', '.join(set(tools_used))}")
        if key_decisions:
            summary_parts.append(f"Key decisions: {'; '.join(key_decisions[:3])}")

        return "\n".join(summary_parts) if summary_parts else "Previous work completed."

    def add_prompt_caching(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Add cache_control for Anthropic prompt caching (if supported)"""
        # Mark system prompt and first user message as cacheable
        for i, msg in enumerate(messages):
            if i < 2 and msg.get("role") in ("system", "user"):
                # Add cache marker (provider-specific, ignored by others)
                msg["_cache"] = True
        return messages
