"""Tests for tools"""
import pytest
import tempfile
import os
from pathlib import Path
from tools.file_tools import ReadFileTool, WriteFileTool, ListFilesTool, SearchFilesTool
from tools.shell_tools import ShellTool, PythonTool


class TestReadFileTool:
    def test_read_existing_file(self):
        tool = ReadFileTool()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("line1\nline2\nline3\n")
            path = f.name

        result = tool.execute(path=path)
        assert result.success is True
        assert "line1" in result.content
        os.unlink(path)

    def test_read_nonexistent_file(self):
        tool = ReadFileTool()
        result = tool.execute(path="/nonexistent/file.txt")
        assert result.success is False
        assert "not found" in result.error.lower() or "File not found" in result.error


class TestWriteFileTool:
    def test_write_file(self):
        tool = WriteFileTool()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.txt")
            result = tool.execute(path=path, content="hello world")
            assert result.success is True
            assert os.path.exists(path)
            with open(path) as f:
                assert f.read() == "hello world"

    def test_write_nested_file(self):
        tool = WriteFileTool()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "nested", "dir", "file.txt")
            result = tool.execute(path=path, content="nested content")
            assert result.success is True
            assert os.path.exists(path)


class TestListFilesTool:
    def test_list_directory(self):
        tool = ListFilesTool()
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create some files
            Path(tmpdir, "file1.txt").touch()
            Path(tmpdir, "file2.py").touch()

            result = tool.execute(path=tmpdir)
            assert result.success is True
            assert "file1.txt" in result.content
            assert "file2.py" in result.content


class TestShellTool:
    def test_echo_command(self):
        tool = ShellTool()
        result = tool.execute(command="echo hello")
        assert result.success is True
        assert "hello" in result.content

    def test_invalid_command(self):
        tool = ShellTool()
        result = tool.execute(command="nonexistent_command_12345")
        assert result.success is False


class TestPythonTool:
    def test_simple_code(self):
        tool = PythonTool()
        result = tool.execute(code="x = 2 + 2\nprint(x)")
        assert result.success is True
        assert "4" in result.content

    def test_error_handling(self):
        tool = PythonTool()
        result = tool.execute(code="1/0")
        assert result.success is False
        assert "ZeroDivisionError" in result.error
