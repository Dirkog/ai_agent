"""Tools package — Cursor/Claude Code compatible
v6: 51+ tools including security, multimodal, orchestrator
"""
from .base import BaseTool, ToolResult
from .file_tools import ReadFileTool, WriteFileTool, ListFilesTool, SearchFilesTool
from .shell_tools import ShellTool, PythonTool
from .diff_tool import ApplyDiffTool, GenerateDiffTool
from .git_tools import GitCheckpointTool, GitRollbackTool, GitStatusTool, GitLogTool
from .advanced_tools import (
    DatabaseTool, BrowserTool, APITestTool, ImageAnalysisTool,
    CodeAnalysisTool, RefactorTool, DockerTool, TestRunnerTool
)
from .ide.ide_tools import (
    BreadcrumbsTool, OutlineTool, FindReferencesTool,
    RenameSymbolTool, MinimapTool, QuickFixTool,
    HoverInfoTool, GoToDefinitionTool  # NEW v6
)
from .ai.ai_tools import (
    ExplainCodeTool, GenerateTestsTool, GenerateDocsTool, SmartImportTool
)
from .cursor_tools import (
    WebSearchTool, FetchDocsTool, NotepadTool, GitDiffTool,
    ChromeAutomationTool, BackgroundTaskTool, CodeInstructionsTool
)
from .security_tools import (
    SecurityScanTool, DependencyCheckTool, SecretScanTool, ContentSafetyTool
)
from .multimodal_tools import (
    ProcessImageTool, ProcessAudioTool, ProcessVideoTool, ScreenshotTool
)
from .orchestrator_tools import (
    AssignRoleTool, SwitchModelTool, EnsembleVoteTool,
    DebugAnalyzeTool, RetryWithBackoffTool, CompareResultsTool
)

__all__ = [
    # Base
    'BaseTool', 'ToolResult',
    # File
    'ReadFileTool', 'WriteFileTool', 'ListFilesTool', 'SearchFilesTool',
    # Shell
    'ShellTool', 'PythonTool',
    # Diff
    'ApplyDiffTool', 'GenerateDiffTool',
    # Git
    'GitCheckpointTool', 'GitRollbackTool', 'GitStatusTool', 'GitLogTool',
    # Advanced
    'DatabaseTool', 'BrowserTool', 'APITestTool', 'ImageAnalysisTool',
    'CodeAnalysisTool', 'RefactorTool', 'DockerTool', 'TestRunnerTool',
    # IDE (8 tools)
    'BreadcrumbsTool', 'OutlineTool', 'FindReferencesTool',
    'RenameSymbolTool', 'MinimapTool', 'QuickFixTool',
    'HoverInfoTool', 'GoToDefinitionTool',
    # AI
    'ExplainCodeTool', 'GenerateTestsTool', 'GenerateDocsTool', 'SmartImportTool',
    # Cursor
    'WebSearchTool', 'FetchDocsTool', 'NotepadTool', 'GitDiffTool',
    'ChromeAutomationTool', 'BackgroundTaskTool', 'CodeInstructionsTool',
    # Security (4)
    'SecurityScanTool', 'DependencyCheckTool', 'SecretScanTool', 'ContentSafetyTool',
    # Multimodal (4)
    'ProcessImageTool', 'ProcessAudioTool', 'ProcessVideoTool', 'ScreenshotTool',
    # Orchestrator (6)
    'AssignRoleTool', 'SwitchModelTool', 'EnsembleVoteTool',
    'DebugAnalyzeTool', 'RetryWithBackoffTool', 'CompareResultsTool',
]
