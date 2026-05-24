"""AI Agent v6 — Chat Feature Module
Handles chat sessions, message history, and context management.
"""
import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict

@dataclass
class ChatMessage:
    role: str  # 'user', 'assistant', 'system', 'tool'
    content: str
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    tool_calls: Optional[List[Dict]] = None
    model: Optional[str] = None
    tokens_used: Optional[int] = None

@dataclass
class ChatSession:
    session_id: str
    title: str = "New Chat"
    messages: List[ChatMessage] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    mode: str = "interactive"  # interactive, autonomous, swarm
    context_tokens: int = 0
    total_tokens: int = 0
    model_preferences: Dict[str, str] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)

class ChatManager:
    """Manages chat sessions with persistence"""

    def __init__(self, storage_path: str = ".ai-agent/sessions"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.sessions: Dict[str, ChatSession] = {}
        self.active_session: Optional[str] = None
        self._load_sessions()

    def _load_sessions(self):
        """Load all saved sessions from disk"""
        if not self.storage_path.exists():
            return
        for file in self.storage_path.glob("*.json"):
            try:
                data = json.loads(file.read_text())
                session = ChatSession(
                    session_id=data["session_id"],
                    title=data.get("title", "Untitled"),
                    messages=[ChatMessage(**m) for m in data.get("messages", [])],
                    created_at=data.get("created_at", time.time()),
                    updated_at=data.get("updated_at", time.time()),
                    mode=data.get("mode", "interactive"),
                    context_tokens=data.get("context_tokens", 0),
                    total_tokens=data.get("total_tokens", 0),
                    model_preferences=data.get("model_preferences", {}),
                    tags=data.get("tags", [])
                )
                self.sessions[session.session_id] = session
            except Exception:
                continue

    def create_session(self, title: str = None, mode: str = "interactive") -> ChatSession:
        """Create a new chat session"""
        import uuid
        session_id = str(uuid.uuid4())[:8]
        session = ChatSession(
            session_id=session_id,
            title=title or f"Chat {len(self.sessions) + 1}",
            mode=mode
        )
        self.sessions[session_id] = session
        self.active_session = session_id
        self._save_session(session)
        return session

    def get_session(self, session_id: str) -> Optional[ChatSession]:
        return self.sessions.get(session_id)

    def add_message(self, session_id: str, role: str, content: str, 
                    metadata: Dict = None, model: str = None) -> ChatMessage:
        """Add a message to a session"""
        session = self.sessions.get(session_id)
        if not session:
            session = self.create_session()

        msg = ChatMessage(
            role=role,
            content=content,
            metadata=metadata or {},
            model=model
        )
        session.messages.append(msg)
        session.updated_at = time.time()
        session.context_tokens += len(content) // 4  # rough estimate
        session.total_tokens += len(content) // 4

        # Auto-title from first user message
        if len(session.messages) == 1 and role == "user":
            session.title = content[:50] + ("..." if len(content) > 50 else "")

        self._save_session(session)
        return msg

    def get_history(self, session_id: str, limit: int = None) -> List[ChatMessage]:
        """Get message history for a session"""
        session = self.sessions.get(session_id)
        if not session:
            return []
        messages = session.messages
        if limit:
            messages = messages[-limit:]
        return messages

    def get_formatted_history(self, session_id: str, limit: int = 20) -> List[Dict]:
        """Get history formatted for LLM API"""
        messages = self.get_history(session_id, limit)
        return [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role in ("user", "assistant", "system")
        ]

    def delete_session(self, session_id: str) -> bool:
        """Delete a session"""
        if session_id in self.sessions:
            del self.sessions[session_id]
            file = self.storage_path / f"{session_id}.json"
            if file.exists():
                file.unlink()
            if self.active_session == session_id:
                self.active_session = next(iter(self.sessions.keys()), None)
            return True
        return False

    def rename_session(self, session_id: str, title: str) -> bool:
        """Rename a session"""
        session = self.sessions.get(session_id)
        if session:
            session.title = title
            self._save_session(session)
            return True
        return False

    def list_sessions(self) -> List[Dict]:
        """List all sessions with metadata"""
        return [
            {
                "session_id": s.session_id,
                "title": s.title,
                "message_count": len(s.messages),
                "mode": s.mode,
                "updated_at": s.updated_at,
                "tags": s.tags
            }
            for s in sorted(self.sessions.values(), key=lambda x: x.updated_at, reverse=True)
        ]

    def search_sessions(self, query: str) -> List[Dict]:
        """Search sessions by content"""
        results = []
        query_lower = query.lower()
        for session in self.sessions.values():
            for msg in session.messages:
                if query_lower in msg.content.lower():
                    results.append({
                        "session_id": session.session_id,
                        "title": session.title,
                        "matched_message": msg.content[:200],
                        "timestamp": msg.timestamp
                    })
                    break
        return results

    def export_session(self, session_id: str, format: str = "json") -> str:
        """Export session to various formats"""
        session = self.sessions.get(session_id)
        if not session:
            return ""

        if format == "json":
            return json.dumps(asdict(session), indent=2, default=str)
        elif format == "markdown":
            lines = [f"# {session.title}\n"]
            for msg in session.messages:
                role_emoji = {"user": "👤", "assistant": "🤖", "system": "⚙", "tool": "🔧"}.get(msg.role, "💬")
                lines.append(f"\n## {role_emoji} {msg.role.upper()}\n\n{msg.content}\n")
            return "\n".join(lines)
        elif format == "text":
            lines = [f"Session: {session.title}\n"]
            for msg in session.messages:
                lines.append(f"[{msg.role}] {msg.content}\n")
            return "\n".join(lines)
        return ""

    def _save_session(self, session: ChatSession):
        """Persist session to disk"""
        file = self.storage_path / f"{session.session_id}.json"
        data = {
            "session_id": session.session_id,
            "title": session.title,
            "messages": [
                {
                    "role": m.role,
                    "content": m.content,
                    "timestamp": m.timestamp,
                    "metadata": m.metadata,
                    "model": m.model,
                    "tokens_used": m.tokens_used
                }
                for m in session.messages
            ],
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "mode": session.mode,
            "context_tokens": session.context_tokens,
            "total_tokens": session.total_tokens,
            "model_preferences": session.model_preferences,
            "tags": session.tags
        }
        file.write_text(json.dumps(data, indent=2, default=str))

# Singleton instance
_chat_manager: Optional[ChatManager] = None

def get_chat_manager() -> ChatManager:
    global _chat_manager
    if _chat_manager is None:
        _chat_manager = ChatManager()
    return _chat_manager
