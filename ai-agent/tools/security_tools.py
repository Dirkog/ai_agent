"""Security Tools — vulnerability scanning, dependency check, secret detection
New in v6: security_scan, dependency_check, secret_scan, content_safety
"""
import os
import re
import json
import subprocess
from pathlib import Path
from typing import Dict, List, Optional
from tools.base import BaseTool, ToolResult


class SecurityScanTool(BaseTool):
    """Сканирование уязвимостей кода (bandit, semgrep)"""
    name = "security_scan"
    description = "Scan Python code for security vulnerabilities (bandit, semgrep)"

    def __init__(self, working_dir: str = "."):
        self.working_dir = Path(working_dir)

    def execute(self, path: str = ".", tool: str = "bandit") -> ToolResult:
        target = self.working_dir / path
        if not target.exists():
            return ToolResult(success=False, error=f"Path not found: {path}")

        try:
            if tool == "bandit":
                result = subprocess.run(
                    ["bandit", "-r", "-f", "json", str(target)],
                    capture_output=True, text=True, timeout=60
                )
                data = json.loads(result.stdout) if result.stdout else {}
                issues = data.get("results", [])
                if issues:
                    summary = "\n".join([
                        f"  {i['issue_severity']}: {i['issue_text']} at {i['filename']}:{i['line_number']}"
                        for i in issues[:20]
                    ])
                    return ToolResult(success=True, output=f"Found {len(issues)} issues:\n{summary}")
                return ToolResult(success=True, output="No security issues found by bandit.")

            elif tool == "semgrep":
                result = subprocess.run(
                    ["semgrep", "--config=auto", "--json", str(target)],
                    capture_output=True, text=True, timeout=120
                )
                data = json.loads(result.stdout) if result.stdout else {}
                findings = data.get("results", [])
                if findings:
                    summary = "\n".join([
                        f"  {f['extra']['severity']}: {f['extra']['message']} at {f['path']}:{f['start']['line']}"
                        for f in findings[:20]
                    ])
                    return ToolResult(success=True, output=f"Found {len(findings)} findings:\n{summary}")
                return ToolResult(success=True, output="No issues found by semgrep.")

            else:
                return ToolResult(success=False, error=f"Unknown security tool: {tool}")

        except FileNotFoundError:
            return ToolResult(success=False, error=f"{tool} not installed. Install: pip install {tool}")
        except subprocess.TimeoutExpired:
            return ToolResult(success=False, error=f"{tool} scan timed out")
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class DependencyCheckTool(BaseTool):
    """Проверка уязвимых зависимостей (safety, pip-audit)"""
    name = "dependency_check"
    description = "Check dependencies for known vulnerabilities (safety, pip-audit)"

    def execute(self, requirements_file: str = "requirements.txt", tool: str = "safety") -> ToolResult:
        req_path = Path(requirements_file)
        if not req_path.exists():
            return ToolResult(success=False, error=f"Requirements file not found: {requirements_file}")

        try:
            if tool == "safety":
                result = subprocess.run(
                    ["safety", "check", "--file", str(req_path), "--json"],
                    capture_output=True, text=True, timeout=120
                )
                data = json.loads(result.stdout) if result.stdout else {}
                vulns = data.get("vulnerabilities", [])
                if vulns:
                    summary = "\n".join([
                        f"  {v['package_name']} {v['vulnerable_spec']}: {v['advisory'][:100]}"
                        for v in vulns[:20]
                    ])
                    return ToolResult(success=True, output=f"Found {len(vulns)} vulnerabilities:\n{summary}")
                return ToolResult(success=True, output="No known vulnerabilities in dependencies.")

            elif tool == "pip-audit":
                result = subprocess.run(
                    ["pip-audit", "--requirement", str(req_path), "--format=json"],
                    capture_output=True, text=True, timeout=120
                )
                data = json.loads(result.stdout) if result.stdout else {}
                if data:
                    summary = json.dumps(data, indent=2)[:2000]
                    return ToolResult(success=True, output=f"Audit results:\n{summary}")
                return ToolResult(success=True, output="No issues found by pip-audit.")

            else:
                return ToolResult(success=False, error=f"Unknown tool: {tool}")

        except FileNotFoundError:
            return ToolResult(success=False, error=f"{tool} not installed. pip install {tool}")
        except subprocess.TimeoutExpired:
            return ToolResult(success=False, error=f"{tool} timed out")
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class SecretScanTool(BaseTool):
    """Поиск API ключей, токенов, секретов (gitleaks, truffleHog)"""
    name = "secret_scan"
    description = "Scan for leaked secrets, API keys, tokens in code (gitleaks)"

    def __init__(self, working_dir: str = "."):
        self.working_dir = Path(working_dir)

    def execute(self, path: str = ".", tool: str = "gitleaks") -> ToolResult:
        target = self.working_dir / path
        if not target.exists():
            return ToolResult(success=False, error=f"Path not found: {path}")

        try:
            if tool == "gitleaks":
                result = subprocess.run(
                    ["gitleaks", "detect", "--source", str(target), "--verbose", "--redact"],
                    capture_output=True, text=True, timeout=120
                )
                if result.returncode == 0:
                    return ToolResult(success=True, output="No secrets leaked (gitleaks).")
                else:
                    return ToolResult(success=True, output=f"Potential secrets found:\n{result.stdout[:2000]}")

            elif tool == "regex":
                # Built-in regex-based scan (no external tool needed)
                patterns = {
                    "AWS Access Key": r"AKIA[0-9A-Z]{16}",
                    "AWS Secret Key": r"[0-9a-zA-Z/+]{40}",
                    "GitHub Token": r"ghp_[0-9a-zA-Z]{36}",
                    "Slack Token": r"xox[baprs]-[0-9a-zA-Z]{10,48}",
                    "Generic API Key": r"[aA][pP][iI][_-]?[kK][eE][yY][\s]*[=:][\s]*[\'"][0-9a-zA-Z]{16,}[\'"]",
                    "Private Key": r"-----BEGIN (RSA |DSA |EC |OPENSSH )?PRIVATE KEY-----",
                    "Password in URL": r"[a-zA-Z]{3,10}://[^/\s:@]*:[^/\s:@]*@[^/\s:@]*",
                }
                findings = []
                for root, _, files in os.walk(target):
                    for f in files:
                        if f.endswith(('.py', '.js', '.ts', '.json', '.yml', '.yaml', '.env', '.md')):
                            fp = Path(root) / f
                            try:
                                content = fp.read_text(errors='ignore')
                                for name, pattern in patterns.items():
                                    for match in re.finditer(pattern, content):
                                        findings.append(f"  {name} in {fp.relative_to(target)}:{content[:match.start()].count(chr(10))+1}")
                            except Exception:
                                pass
                if findings:
                    return ToolResult(success=True, output=f"Found potential secrets:\n" + "\n".join(findings[:50]))
                return ToolResult(success=True, output="No obvious secrets found by regex scan.")

            else:
                return ToolResult(success=False, error=f"Unknown tool: {tool}")

        except FileNotFoundError:
            return ToolResult(success=False, error=f"{tool} not installed. See docs for install.")
        except subprocess.TimeoutExpired:
            return ToolResult(success=False, error=f"{tool} timed out")
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class ContentSafetyTool(BaseTool):
    """Проверка токсичности контента через NVIDIA Nemotron Content Safety"""
    name = "content_safety"
    description = "Check content for toxicity, hate speech, unsafe content (NVIDIA nemotron-content-safety)"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("NVIDIA_API_KEY")
        self.model = "nvidia/nemotron-3-content-safety"
        self.base_url = "https://integrate.api.nvidia.com/v1"

    def execute(self, text: str = "", image_path: Optional[str] = None) -> ToolResult:
        if not self.api_key:
            return ToolResult(success=False, error="NVIDIA_API_KEY not set for content safety")

        try:
            import httpx
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": text}],
                "max_tokens": 256
            }
            response = httpx.post(f"{self.base_url}/chat/completions", headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()
            result = data["choices"][0]["message"]["content"]
            return ToolResult(success=True, output=f"Safety check result:\n{result}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))
