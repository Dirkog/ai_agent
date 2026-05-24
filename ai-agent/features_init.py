"""AI Agent v6 — Features Package
High-level feature modules for chat, editor, and terminal.
"""
from .chat.chat_feature import ChatManager, ChatSession, ChatMessage, get_chat_manager
from .editor.editor_feature import EditorManager, EditOperation, get_editor_manager
from .terminal.terminal_feature import TerminalManager, TerminalSession, get_terminal_manager

__all__ = [
    'ChatManager', 'ChatSession', 'ChatMessage', 'get_chat_manager',
    'EditorManager', 'EditOperation', 'get_editor_manager',
    'TerminalManager', 'TerminalSession', 'get_terminal_manager',
]
