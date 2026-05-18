"""Dynamic tool picker — selects relevant tools based on task context"""
from typing import List, Dict, Any, Set
from dataclasses import dataclass

@dataclass
class ToolCategory:
    name: str
    tools: List[str]
    keywords: List[str]
    description: str

TOOL_CATEGORIES = [
    ToolCategory(
        name="file_operations",
        tools=["read_file", "write_file", "list_files", "search_files", "apply_diff", "generate_diff"],
        keywords=["file", "read", "write", "edit", "create", "modify", "folder", "directory", 
                 "code", "script", "save", "open", "find", "search", "replace", "diff", "patch"],
        description="File system operations"
    ),
    ToolCategory(
        name="execution",
        tools=["execute_command", "execute_python"],
        keywords=["run", "execute", "command", "shell", "terminal", "python", "script", 
                 "test", "build", "install", "pip", "npm", "start", "stop"],
        description="Command and code execution"
    ),
    ToolCategory(
        name="git",
        tools=["git_checkpoint", "git_rollback", "git_status", "git_log"],
        keywords=["git", "commit", "branch", "merge", "history", "log", "status", 
                 "diff", "revert", "rollback", "checkpoint", "version control"],
        description="Git version control"
    ),
    ToolCategory(
        name="advanced",
        tools=["query_database", "browse_web", "test_api", "analyze_image", 
               "analyze_code", "refactor_code", "docker_command", "run_tests"],
        keywords=["database", "sql", "web", "http", "api", "image", "docker", 
                 "container", "test", "pytest", "refactor", "analyze", "lint", "security"],
        description="Advanced operations"
    ),
    ToolCategory(
        name="ide",
        tools=["get_breadcrumbs", "get_outline", "find_references", 
               "rename_symbol", "get_minimap", "quick_fix"],
        keywords=["navigate", "find", "reference", "definition", "symbol", 
                 "outline", "breadcrumb", "minimap", "rename", "structure"],
        description="IDE navigation features"
    ),
    ToolCategory(
        name="ai_powered",
        tools=["explain_code", "generate_tests", "generate_docs", "smart_import"],
        keywords=["explain", "document", "test", "import", "organize", 
                 "comment", "docstring", "understand", "learn"],
        description="AI-powered code operations"
    ),
]

class ToolPicker:
    """Selects relevant tools based on task description"""
    
    def __init__(self, all_tools: Dict[str, Any]):
        self.all_tools = all_tools
    
    def pick_tools(self, task: str, max_tools: int = 15) -> Dict[str, Any]:
        """Select most relevant tools for the task"""
        task_lower = task.lower()
        
        category_scores = {}
        for cat in TOOL_CATEGORIES:
            score = 0
            for keyword in cat.keywords:
                if keyword in task_lower:
                    score += 1
            category_scores[cat.name] = score
        
        selected_tools = set(TOOL_CATEGORIES[0].tools)
        
        for cat in TOOL_CATEGORIES[1:]:
            if category_scores[cat.name] > 0:
                selected_tools.update(cat.tools)
        
        if len(selected_tools) < 6:
            selected_tools.update(TOOL_CATEGORIES[1].tools)
            selected_tools.update(TOOL_CATEGORIES[2].tools)
        
        selected = {}
        for tool_name in list(selected_tools)[:max_tools]:
            if tool_name in self.all_tools:
                selected[tool_name] = self.all_tools[tool_name]
        
        return selected
    
    def get_system_prompt_tools_section(self, task: str) -> str:
        """Generate tools section for system prompt"""
        selected = self.pick_tools(task)
        
        lines = []
        for tool_name, tool in selected.items():
            lines.append(f"- {tool_name}: {tool.description}")
        
        return "\n".join(lines)
