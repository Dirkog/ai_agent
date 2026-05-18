"""Local project validation after task completion"""
import os
import re
import subprocess
import ast
from pathlib import Path
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass

@dataclass
class ValidationResult:
    category: str
    passed: bool
    message: str
    details: List[str] = None
    severity: str = "info"  # info, warning, error

class ProjectValidator:
    def __init__(self, project_path: str = "."):
        self.project_path = Path(project_path).resolve()
        self.results: List[ValidationResult] = []

    def validate_all(self) -> List[ValidationResult]:
        """Run all validation checks"""
        print("\n🔍 Running project validation...")
        self.results = []

        self._check_python_syntax()
        self._check_imports()
        self._run_tests()
        self._run_linter()
        self._check_requirements()
        self._check_file_structure()

        return self.results

    def _check_python_syntax(self):
        """Check Python files for syntax errors"""
        python_files = list(self.project_path.rglob("*.py"))
        errors = []

        for py_file in python_files:
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    source = f.read()
                ast.parse(source)
            except SyntaxError as e:
                rel_path = py_file.relative_to(self.project_path)
                errors.append(f"{rel_path}:{e.lineno}: {e.msg}")
            except Exception as e:
                rel_path = py_file.relative_to(self.project_path)
                errors.append(f"{rel_path}: {str(e)}")

        self.results.append(ValidationResult(
            category="Python Syntax",
            passed=len(errors) == 0,
            message=f"Checked {len(python_files)} files" + (" ✓" if not errors else f", {len(errors)} errors"),
            details=errors,
            severity="error" if errors else "info"
        ))

    def _check_imports(self):
        """Check for missing imports"""
        python_files = list(self.project_path.rglob("*.py"))
        missing = []

        for py_file in python_files:
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    tree = ast.parse(f.read())

                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            try:
                                __import__(alias.name)
                            except ImportError:
                                missing.append(f"{py_file.name}: {alias.name}")
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            try:
                                __import__(node.module)
                            except ImportError:
                                missing.append(f"{py_file.name}: {node.module}")
            except Exception:
                continue

        self.results.append(ValidationResult(
            category="Imports",
            passed=len(missing) == 0,
            message=f"Found {len(missing)} potentially missing imports",
            details=missing,
            severity="warning" if missing else "info"
        ))

    def _run_tests(self):
        """Run pytest if available"""
        test_paths = [
            self.project_path / "tests",
            self.project_path / "test",
            self.project_path / "*_test.py",
            self.project_path / "test_*.py"
        ]

        has_tests = any(
            p.exists() if isinstance(p, Path) else list(self.project_path.glob(p.name))
            for p in test_paths
        )

        if not has_tests:
            self.results.append(ValidationResult(
                category="Tests",
                passed=True,
                message="No tests found (skipped)",
                severity="info"
            ))
            return

        try:
            result = subprocess.run(
                ["python", "-m", "pytest", "-v", "--tb=short"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=120
            )

            passed = result.returncode == 0
            output = result.stdout + result.stderr

            # Extract summary
            summary_match = re.search(r"(passed|failed|error).*?\d+", output)
            summary = summary_match.group(0) if summary_match else "Unknown"

            self.results.append(ValidationResult(
                category="Tests",
                passed=passed,
                message=f"Tests {summary}",
                details=output.split("\n")[-20:] if not passed else [],
                severity="error" if not passed else "info"
            ))
        except FileNotFoundError:
            self.results.append(ValidationResult(
                category="Tests",
                passed=False,
                message="pytest not installed",
                severity="warning"
            ))
        except subprocess.TimeoutExpired:
            self.results.append(ValidationResult(
                category="Tests",
                passed=False,
                message="Tests timed out",
                severity="warning"
            ))

    def _run_linter(self):
        """Run flake8 or pylint"""
        linters = [
            (["python", "-m", "flake8", "--max-line-length=120", "--exclude=venv,.venv,__pycache__"], "flake8"),
            (["python", "-m", "pylint", "--disable=C,R", "*.py"], "pylint")
        ]

        for cmd, name in linters:
            try:
                result = subprocess.run(
                    cmd,
                    cwd=self.project_path,
                    capture_output=True,
                    text=True,
                    timeout=60
                )

                has_issues = bool(result.stdout.strip())
                self.results.append(ValidationResult(
                    category=f"Linting ({name})",
                    passed=not has_issues,
                    message=f"{name} {'passed ✓' if not has_issues else 'found issues'}",
                    details=result.stdout.split("\n")[:20] if has_issues else [],
                    severity="warning" if has_issues else "info"
                ))
                return  # Only run first available linter
            except FileNotFoundError:
                continue

        self.results.append(ValidationResult(
            category="Linting",
            passed=True,
            message="No linter available (flake8/pylint not installed)",
            severity="info"
        ))

    def _check_requirements(self):
        """Check requirements.txt exists and is valid"""
        req_file = self.project_path / "requirements.txt"

        if not req_file.exists():
            self.results.append(ValidationResult(
                category="Requirements",
                passed=True,
                message="No requirements.txt found (optional)",
                severity="info"
            ))
            return

        try:
            with open(req_file, 'r') as f:
                lines = f.readlines()

            empty = [i+1 for i, line in enumerate(lines) if line.strip() and not line.startswith('#')]

            self.results.append(ValidationResult(
                category="Requirements",
                passed=len(empty) > 0,
                message=f"requirements.txt has {len(empty)} dependencies",
                severity="info"
            ))
        except Exception as e:
            self.results.append(ValidationResult(
                category="Requirements",
                passed=False,
                message=f"Error reading requirements: {e}",
                severity="warning"
            ))

    def _check_file_structure(self):
        """Check for common project structure issues"""
        issues = []

        # Check for __pycache__ in repo
        pycache = list(self.project_path.rglob("__pycache__"))
        if pycache:
            issues.append(f"Found {len(pycache)} __pycache__ directories (should be gitignored)")

        # Check for .pyc files
        pyc_files = list(self.project_path.rglob("*.pyc"))
        if pyc_files:
            issues.append(f"Found {len(pyc_files)} .pyc files (should be gitignored)")

        # Check for .env files
        env_files = list(self.project_path.rglob(".env"))
        if env_files:
            issues.append(f"⚠️  Found {len(env_files)} .env files (ensure not committed)")

        self.results.append(ValidationResult(
            category="File Structure",
            passed=len(issues) == 0,
            message=f"Structure check {'passed ✓' if not issues else f'found {len(issues)} issues'}",
            details=issues,
            severity="warning" if issues else "info"
        ))

    def get_summary(self) -> str:
        """Get formatted validation summary"""
        summary = "\n" + "="*60 + "\n"
        summary += "📊 VALIDATION SUMMARY\n"
        summary += "="*60 + "\n"

        passed = sum(1 for r in self.results if r.passed)
        total = len(self.results)

        for result in self.results:
            icon = "✅" if result.passed else "⚠️" if result.severity == "warning" else "❌"
            summary += f"\n{icon} {result.category}: {result.message}\n"
            if result.details:
                for detail in result.details[:5]:
                    summary += f"   • {detail}\n"
                if len(result.details) > 5:
                    summary += f"   ... and {len(result.details) - 5} more\n"

        summary += f"\n{'='*60}\n"
        summary += f"Result: {passed}/{total} checks passed\n"
        summary += "="*60 + "\n"

        return summary

    def has_critical_errors(self) -> bool:
        return any(r.severity == "error" and not r.passed for r in self.results)
