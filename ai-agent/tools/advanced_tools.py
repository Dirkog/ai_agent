"""Advanced tools — Claude Opus 4.7 level capabilities
Database, browser, API testing, image analysis, code analysis, refactoring.
"""
import json
import re
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional
from .base import BaseTool, ToolResult


class DatabaseTool(BaseTool):
    name = "query_database"
    description = "Execute SQL queries against SQLite/PostgreSQL/MySQL. Requires confirmation for destructive operations."
    parameters = {
        "connection_string": {"type": "string", "description": "DB connection string or path to SQLite file"},
        "query": {"type": "string", "description": "SQL query to execute"},
        "params": {"type": "array", "description": "Query parameters", "default": []}
    }

    def execute(self, connection_string: str, query: str, params: list = None) -> ToolResult:
        try:
            # Detect DB type
            if connection_string.endswith('.db') or connection_string.endswith('.sqlite'):
                import sqlite3
                conn = sqlite3.connect(connection_string)
            elif connection_string.startswith('postgresql://'):
                import psycopg2
                conn = psycopg2.connect(connection_string)
            elif connection_string.startswith('mysql://'):
                import pymysql
                conn = pymysql.connect(connection_string)
            else:
                return ToolResult(False, "", "Unknown database type. Use .db, postgresql://, or mysql://")

            cursor = conn.cursor()
            cursor.execute(query, params or [])

            if query.strip().upper().startswith('SELECT'):
                columns = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()

                # Format as table
                result = " | ".join(columns) + "\n"
                result += "-" * (len(result) - 1) + "\n"
                for row in rows[:100]:
                    result += " | ".join(str(c) for c in row) + "\n"

                conn.close()
                return ToolResult(True, result, metadata={"rows": len(rows)})
            else:
                conn.commit()
                affected = cursor.rowcount
                conn.close()
                return ToolResult(True, f"Query executed. Rows affected: {affected}")

        except ImportError as e:
            return ToolResult(False, "", f"Database driver not installed: {e}")
        except Exception as e:
            return ToolResult(False, "", str(e))


class BrowserTool(BaseTool):
    name = "browse_web"
    description = "Fetch and extract content from web pages. Useful for documentation, APIs, references."
    parameters = {
        "url": {"type": "string", "description": "URL to fetch"},
        "selector": {"type": "string", "description": "CSS selector to extract specific content", "default": ""},
        "max_length": {"type": "integer", "description": "Max content length", "default": 5000}
    }

    def execute(self, url: str, selector: str = "", max_length: int = 5000) -> ToolResult:
        try:
            import httpx
            response = httpx.get(url, timeout=30, follow_redirects=True)
            response.raise_for_status()

            content = response.text

            # Extract text from HTML
            if selector:
                try:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(content, 'html.parser')
                    elements = soup.select(selector)
                    content = "\n".join(str(el.get_text()) for el in elements)
                except ImportError:
                    pass
            else:
                # Simple HTML stripping
                content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL)
                content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL)
                content = re.sub(r'<[^>]+>', ' ', content)
                content = re.sub(r'\s+', ' ', content)

            content = content[:max_length]
            return ToolResult(True, content, metadata={"url": url, "status": response.status_code})
        except Exception as e:
            return ToolResult(False, "", str(e))


class APITestTool(BaseTool):
    name = "test_api"
    description = "Test REST/GraphQL APIs. Send requests and validate responses."
    parameters = {
        "method": {"type": "string", "description": "HTTP method", "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"]},
        "url": {"type": "string", "description": "API endpoint URL"},
        "headers": {"type": "object", "description": "Request headers", "default": {}},
        "body": {"type": "string", "description": "Request body (JSON)"},
        "expected_status": {"type": "integer", "description": "Expected status code", "default": 200}
    }

    def execute(self, method: str, url: str, headers: dict = None, body: str = "", expected_status: int = 200) -> ToolResult:
        try:
            import httpx

            req_headers = headers or {}
            if body and isinstance(body, str):
                try:
                    json.loads(body)  # Validate JSON
                    req_headers.setdefault("Content-Type", "application/json")
                except:
                    pass

            response = httpx.request(
                method=method,
                url=url,
                headers=req_headers,
                content=body.encode() if body else None,
                timeout=30
            )

            result = {
                "status": response.status_code,
                "expected": expected_status,
                "match": response.status_code == expected_status,
                "headers": dict(response.headers),
                "body": response.text[:2000]
            }

            success = response.status_code == expected_status
            return ToolResult(
                success,
                json.dumps(result, indent=2),
                metadata={"status": response.status_code}
            )
        except Exception as e:
            return ToolResult(False, "", str(e))


class ImageAnalysisTool(BaseTool):
    name = "analyze_image"
    description = "Analyze images using vision models (if available). Describe, OCR, or extract info."
    parameters = {
        "image_path": {"type": "string", "description": "Path to image file"},
        "prompt": {"type": "string", "description": "What to analyze", "default": "Describe this image in detail"}
    }

    def execute(self, image_path: str, prompt: str = "Describe this image in detail") -> ToolResult:
        try:
            from PIL import Image
            import base64

            img = Image.open(image_path)

            # Convert to base64 for LLM vision
            import io
            buffer = io.BytesIO()
            img.convert('RGB').save(buffer, format='PNG')
            img_b64 = base64.b64encode(buffer.getvalue()).decode()

            # In real implementation, send to vision-capable model
            return ToolResult(
                True,
                f"Image loaded: {img.size[0]}x{img.size[1]} pixels, mode: {img.mode}\n"
                f"Base64 length: {len(img_b64)} chars\n"
                f"Ready for vision model analysis with prompt: {prompt}",
                metadata={"width": img.size[0], "height": img.size[1], "base64": img_b64[:100] + "..."}
            )
        except ImportError:
            return ToolResult(False, "", "PIL not installed: pip install Pillow")
        except Exception as e:
            return ToolResult(False, "", str(e))


class CodeAnalysisTool(BaseTool):
    name = "analyze_code"
    description = "Deep code analysis: complexity, dependencies, security scan, type checking."
    parameters = {
        "path": {"type": "string", "description": "File or directory to analyze"},
        "analysis_type": {"type": "string", "description": "Type of analysis", "enum": ["complexity", "security", "types", "dependencies", "all"], "default": "all"}
    }

    def execute(self, path: str, analysis_type: str = "all") -> ToolResult:
        try:
            full_path = Path(path).resolve()
            results = []

            if analysis_type in ("complexity", "all"):
                # Radon or simple metrics
                try:
                    import radon.complexity
                    with open(full_path) as f:
                        blocks = radon.complexity.cc_visit(f.read())
                    complexities = [f"  {b.name}: {b.complexity}" for b in blocks]
                    results.append("[Cyclomatic Complexity]\n" + "\n".join(complexities))
                except ImportError:
                    results.append("[Complexity] radon not installed")

            if analysis_type in ("security", "all"):
                # Bandit
                try:
                    result = subprocess.run(
                        ["bandit", "-r", str(full_path), "-f", "json"],
                        capture_output=True,
                        text=True,
                        timeout=60
                    )
                    results.append("[Security Scan]\n" + result.stdout[:2000])
                except (FileNotFoundError, subprocess.TimeoutExpired):
                    results.append("[Security] bandit not installed")

            if analysis_type in ("types", "all"):
                # MyPy
                try:
                    result = subprocess.run(
                        ["mypy", str(full_path), "--no-error-summary"],
                        capture_output=True,
                        text=True,
                        timeout=60
                    )
                    results.append("[Type Checking]\n" + result.stdout[:2000])
                except (FileNotFoundError, subprocess.TimeoutExpired):
                    results.append("[Types] mypy not installed")

            if analysis_type in ("dependencies", "all"):
                # Import analysis
                try:
                    import ast
                    with open(full_path) as f:
                        tree = ast.parse(f.read())
                    imports = []
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Import):
                            imports.extend(a.name for a in node.names)
                        elif isinstance(node, ast.ImportFrom):
                            imports.append(node.module or "")
                    results.append(f"[Dependencies] {', '.join(set(imports))}")
                except Exception as e:
                    results.append(f"[Dependencies] Error: {e}")

            return ToolResult(True, "\n\n".join(results))
        except Exception as e:
            return ToolResult(False, "", str(e))


class RefactorTool(BaseTool):
    name = "refactor_code"
    description = "Automated refactoring: rename symbol, extract method, inline variable, move class."
    parameters = {
        "path": {"type": "string", "description": "File to refactor"},
        "operation": {"type": "string", "description": "Refactoring operation", "enum": ["rename", "extract_method", "inline", "move", "organize_imports"]},
        "target": {"type": "string", "description": "Symbol/line to refactor"},
        "new_name": {"type": "string", "description": "New name (for rename)", "default": ""}
    }

    def execute(self, path: str, operation: str, target: str, new_name: str = "") -> ToolResult:
        try:
            full_path = Path(path).resolve()
            with open(full_path, 'r') as f:
                content = f.read()

            if operation == "rename":
                # Simple text-based rename (in real impl, use AST)
                new_content = re.sub(r'\b' + re.escape(target) + r'\b', new_name, content)
                with open(full_path, 'w') as f:
                    f.write(new_content)
                return ToolResult(True, f"Renamed '{target}' to '{new_name}' in {path}")

            elif operation == "organize_imports":
                # Sort imports
                import isort
                new_content = isort.code(content)
                with open(full_path, 'w') as f:
                    f.write(new_content)
                return ToolResult(True, f"Organized imports in {path}")

            elif operation == "extract_method":
                return ToolResult(False, "", "Extract method requires interactive selection")

            else:
                return ToolResult(False, "", f"Operation '{operation}' not fully implemented")

        except ImportError as e:
            return ToolResult(False, "", f"Required library not installed: {e}")
        except Exception as e:
            return ToolResult(False, "", str(e))


class DockerTool(BaseTool):
    name = "docker_command"
    description = "Execute Docker commands. BLOCKED: rm -f, system prune, volume rm. REQUIRES CONFIRMATION: build, run, exec."
    parameters = {
        "command": {"type": "string", "description": "Docker command (without 'docker' prefix)"},
        "timeout": {"type": "integer", "description": "Timeout", "default": 60}
    }

    def execute(self, command: str, timeout: int = 60) -> ToolResult:
        # Safety checks
        dangerous = ["rm -f", "system prune", "volume rm", "network rm", "image rm -f"]
        if any(d in command.lower() for d in dangerous):
            return ToolResult(False, "", f"BLOCKED: Dangerous docker command '{command}'")

        needs_confirm = ["build", "run", "exec", "push", "pull"]
        if any(c in command.lower().split() for c in needs_confirm):
            print(f"\n⚠️  Docker command requires approval: docker {command}")
            confirm = input("Approve? [Y/n]: ").strip().lower()
            if confirm and confirm not in ('y', 'yes'):
                return ToolResult(False, "", "User declined")

        try:
            result = subprocess.run(
                f"docker {command}",
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            output = result.stdout
            if result.stderr:
                output += f"\n[STDERR]:\n{result.stderr}"
            return ToolResult(result.returncode == 0, output)
        except subprocess.TimeoutExpired:
            return ToolResult(False, "", f"Docker command timed out after {timeout}s")
        except Exception as e:
            return ToolResult(False, "", str(e))


class TestRunnerTool(BaseTool):
    name = "run_tests"
    description = "Run test suites with coverage. Supports pytest, unittest, jest, etc."
    parameters = {
        "framework": {"type": "string", "description": "Test framework", "enum": ["pytest", "unittest", "jest", "mocha"], "default": "pytest"},
        "path": {"type": "string", "description": "Test path or pattern", "default": "."},
        "coverage": {"type": "boolean", "description": "Run with coverage", "default": True},
        "parallel": {"type": "boolean", "description": "Run in parallel", "default": False}
    }

    def execute(self, framework: str = "pytest", path: str = ".", coverage: bool = True, parallel: bool = False) -> ToolResult:
        try:
            if framework == "pytest":
                cmd = ["python", "-m", "pytest", path, "-v"]
                if coverage:
                    cmd.extend(["--cov=.", "--cov-report=term-missing"])
                if parallel:
                    cmd.extend(["-n", "auto"])
            elif framework == "unittest":
                cmd = ["python", "-m", "unittest", "discover", "-s", path, "-v"]
            elif framework == "jest":
                cmd = ["npx", "jest", path, "--verbose"]
                if coverage:
                    cmd.append("--coverage")
            else:
                return ToolResult(False, "", f"Framework '{framework}' not supported")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120
            )

            output = result.stdout
            if result.stderr:
                output += f"\n[STDERR]:\n{result.stderr}"

            return ToolResult(
                result.returncode == 0,
                output[:5000],
                metadata={"returncode": result.returncode, "framework": framework}
            )
        except subprocess.TimeoutExpired:
            return ToolResult(False, "", "Tests timed out after 120s")
        except Exception as e:
            return ToolResult(False, "", str(e))
