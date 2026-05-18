"""Tests for project validator"""
import pytest
import tempfile
import os
from pathlib import Path
from validator.project_validator import ProjectValidator, ValidationResult


class TestProjectValidator:
    def test_empty_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            validator = ProjectValidator(tmpdir)
            results = validator.validate_all()

            # Should have results for all categories
            categories = [r.category for r in results]
            assert "Python Syntax" in categories
            assert "File Structure" in categories

    def test_project_with_syntax_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create file with syntax error
            with open(os.path.join(tmpdir, "bad.py"), "w") as f:
                f.write("def foo(\n")  # Missing closing parenthesis

            validator = ProjectValidator(tmpdir)
            results = validator.validate_all()

            syntax_result = next(r for r in results if r.category == "Python Syntax")
            assert syntax_result.passed is False
            assert len(syntax_result.details) > 0

    def test_project_with_valid_code(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "good.py"), "w") as f:
                f.write("def hello():\n    return 'world'\n")

            validator = ProjectValidator(tmpdir)
            results = validator.validate_all()

            syntax_result = next(r for r in results if r.category == "Python Syntax")
            assert syntax_result.passed is True

    def test_summary_generation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            validator = ProjectValidator(tmpdir)
            validator.validate_all()
            summary = validator.get_summary()

            assert "VALIDATION SUMMARY" in summary
            assert "checks passed" in summary
