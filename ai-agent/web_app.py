"""Web interface for AI Agent v6 — Full API
Real API endpoints for file operations, streaming, chat sessions, terminal, and IDE features.
"""
import os
import sys
import json
import threading
import time
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent import Agent
from config import CONFIG

# Import feature modules
from features.chat.chat_feature import get_chat_manager
from features.editor.editor_feature import get_editor_manager
from features.terminal.terminal_feature import get_terminal_manager

app = Flask(__name__)
app.config['SECRET_KEY'] = 'ai-agent-secret-key'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

sessions = {}

# Initialize managers
chat_manager = get_chat_manager()
editor_manager = get_editor_manager(CONFIG.working_directory)
terminal_manager = get_terminal_manager(CONFIG.working_directory)

def _get_language(ext: str) -> str:
    mapping = {
        '.py': 'python', '.js': 'javascript', '.ts': 'typescript',
        '.jsx': 'jsx', '.tsx': 'tsx', '.html': 'html', '.css': 'css',
        '.json': 'json', '.md': 'markdown', '.yml': 'yaml', '.yaml': 'yaml',
        '.rs': 'rust', '.go': 'go', '.java': 'java', '.cpp': 'cpp',
        '.c': 'c', '.h': 'c', '.hpp': 'cpp', '.sh': 'shell',
        '.dockerfile': 'dockerfile', '.sql': 'sql', '.toml': 'toml',
        '.txt': 'plaintext', '.xml': 'xml'
    }
    return mapping.get(ext, ext.lstrip('.') or 'plaintext')

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)

@app.route('/')
def index():
    return render_template('index.html')

# ============ PROJECT API ============

@app.route('/api/project')
def get_project():
    """Get project structure"""
    try:
        root = Path(CONFIG.working_directory).resolve()
        def build_tree(path: Path, rel_path: str = "") -> dict:
            result = {
                "name": path.name or root.name,
                "path": rel_path,
                "type": "directory" if path.is_dir() else "file",
                "children": []
            }
            if path.is_dir():
                try:
                    for item in sorted(path.iterdir()):
                        if item.name.startswith('.') and item.name not in ('.env', '.gitignore', '.cursorrules'):
                            continue
                        child_rel = f"{rel_path}/{item.name}" if rel_path else item.name
                        if item.is_dir():
                            result["children"].append(build_tree(item, child_rel))
                        else:
                            result["children"].append({
                                "name": item.name,
                                "path": child_rel,
                                "type": "file",
                                "size": item.stat().st_size,
                                "modified": item.stat().st_mtime,
                                "language": _get_language(item.suffix)
                            })
                except PermissionError:
                    pass
            return result

        return jsonify(build_tree(root))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============ FILE API ============

@app.route('/api/file')
def get_file():
    """Read file content"""
    path = request.args.get('path', '')
    offset = request.args.get('offset', 0, type=int)
    lines = request.args.get('lines', None, type=int)

    if not path:
        return jsonify({"error": "No path provided"}), 400

    try:
        content, total_lines = editor_manager.read_file(path, offset, lines)
        full_path = Path(CONFIG.working_directory) / path

        return jsonify({
            "path": path,
            "content": content,
            "language": _get_language(full_path.suffix),
            "lines": total_lines,
            "offset": offset,
            "info": editor_manager.get_file_info(path)
        })
    except ValueError as e:
        return jsonify({"error": str(e)}), 403
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/file', methods=['POST'])
def save_file():
    """Save file content"""
    data = request.json
    path = data.get('path', '')
    content = data.get('content', '')

    if not path:
        return jsonify({"error": "No path provided"}), 400

    try:
        editor_manager.write_file(path, content)
        return jsonify({"success": True, "path": path, "info": editor_manager.get_file_info(path)})
    except ValueError as e:
        return jsonify({"error": str(e)}), 403
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/file', methods=['DELETE'])
def delete_file():
    """Delete file"""
    path = request.args.get('path', '')
    if not path:
        return jsonify({"error": "No path provided"}), 400

    try:
        full_path = Path(CONFIG.working_directory) / path
        full_path = full_path.resolve()
        root = Path(CONFIG.working_directory).resolve()

        if not str(full_path).startswith(str(root)):
            return jsonify({"error": "Access denied"}), 403

        if full_path.is_file():
            full_path.unlink()
        elif full_path.is_dir():
            import shutil
            shutil.rmtree(full_path)

        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/file/diff', methods=['POST'])
def file_diff():
    """Generate diff for file"""
    data = request.json
    path = data.get('path', '')
    new_content = data.get('content', '')

    try:
        diff = editor_manager.generate_diff(path, new_content)
        return jsonify({"diff": diff, "path": path})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/file/apply-diff', methods=['POST'])
def apply_file_diff():
    """Apply diff to file"""
    data = request.json
    path = data.get('path', '')
    diff_text = data.get('diff', '')

    try:
        success, message = editor_manager.apply_diff(path, diff_text)
        return jsonify({"success": success, "message": message})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/file/undo', methods=['POST'])
def undo_file():
    """Undo last change to file"""
    data = request.json
    path = data.get('path', '')

    try:
        success, message = editor_manager.undo(path)
        return jsonify({"success": success, "message": message})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/file/redo', methods=['POST'])
def redo_file():
    """Redo last undone change"""
    data = request.json
    path = data.get('path', '')

    try:
        success, message = editor_manager.redo(path)
        return jsonify({"success": success, "message": message})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============ SEARCH API ============

@app.route('/api/search')
def search_files():
    """Search in files"""
    query = request.args.get('q', '')
    path = request.args.get('path', '.')

    if not query:
        return jsonify({"results": []})

    try:
        import re
        base = Path(CONFIG.working_directory) / path
        results = []

        for file_path in base.rglob('*'):
            if not file_path.is_file():
                continue
            if file_path.name.startswith('.'):
                continue

            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    for i, line in enumerate(f, 1):
                        if re.search(query, line, re.IGNORECASE):
                            rel = str(file_path.relative_to(base))
                            results.append({
                                "file": rel,
                                "line": i,
                                "content": line.strip()[:200]
                            })
            except Exception:
                continue

            if len(results) >= 100:
                break

        return jsonify({"results": results, "total": len(results)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============ CHAT SESSION API ============

@app.route('/api/chat/sessions')
def list_chat_sessions():
    """List all chat sessions"""
    return jsonify(chat_manager.list_sessions())

@app.route('/api/chat/session', methods=['POST'])
def create_chat_session():
    """Create new chat session"""
    data = request.json or {}
    title = data.get('title')
    mode = data.get('mode', 'interactive')
    session = chat_manager.create_session(title=title, mode=mode)
    return jsonify({
        "session_id": session.session_id,
        "title": session.title,
        "mode": session.mode
    })

@app.route('/api/chat/session/<session_id>')
def get_chat_session(session_id):
    """Get chat session details"""
    session = chat_manager.get_session(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404

    return jsonify({
        "session_id": session.session_id,
        "title": session.title,
        "mode": session.mode,
        "messages": [
            {"role": m.role, "content": m.content, "timestamp": m.timestamp, "model": m.model}
            for m in session.messages
        ],
        "total_tokens": session.total_tokens
    })

@app.route('/api/chat/session/<session_id>/history')
def get_chat_history(session_id):
    """Get formatted chat history for LLM"""
    limit = request.args.get('limit', 20, type=int)
    history = chat_manager.get_formatted_history(session_id, limit)
    return jsonify({"history": history})

@app.route('/api/chat/session/<session_id>/export')
def export_chat_session(session_id):
    """Export session"""
    format = request.args.get('format', 'json')
    content = chat_manager.export_session(session_id, format)
    if not content:
        return jsonify({"error": "Session not found"}), 404

    ext = {'json': 'json', 'markdown': 'md', 'text': 'txt'}.get(format, 'txt')
    from flask import Response
    return Response(
        content,
        mimetype={'json': 'application/json', 'markdown': 'text/markdown', 'text': 'text/plain'}.get(format, 'text/plain'),
        headers={"Content-Disposition": f"attachment; filename=chat_{session_id}.{ext}"}
    )

@app.route('/api/chat/session/<session_id>', methods=['DELETE'])
def delete_chat_session(session_id):
    """Delete chat session"""
    success = chat_manager.delete_session(session_id)
    return jsonify({"success": success})

@app.route('/api/chat/session/<session_id>/rename', methods=['POST'])
def rename_chat_session(session_id):
    """Rename chat session"""
    data = request.json or {}
    title = data.get('title', '')
    success = chat_manager.rename_session(session_id, title)
    return jsonify({"success": success})

# ============ TERMINAL API ============

@app.route('/api/terminal/sessions')
def list_terminal_sessions():
    """List active terminal sessions"""
    return jsonify(terminal_manager.list_sessions())

@app.route('/api/terminal/session', methods=['POST'])
def create_terminal_session():
    """Create new terminal session"""
    data = request.json or {}
    session_id = data.get('session_id')
    shell = data.get('shell')
    session = terminal_manager.create_session(session_id=session_id, shell=shell)
    return jsonify({
        "session_id": session.session_id,
        "shell": session.shell,
        "active": session.active
    })

@app.route('/api/terminal/session/<session_id>/execute', methods=['POST'])
def execute_terminal_command(session_id):
    """Execute command in terminal session"""
    data = request.json or {}
    command = data.get('command', '')
    timeout = data.get('timeout', 30.0)

    result = terminal_manager.execute_command(session_id, command, timeout)
    return jsonify(result)

@app.route('/api/terminal/session/<session_id>/write', methods=['POST'])
def write_terminal(session_id):
    """Write raw data to terminal"""
    data = request.json or {}
    text = data.get('data', '')
    success = terminal_manager.write(session_id, text)
    return jsonify({"success": success})

@app.route('/api/terminal/session/<session_id>/output')
def get_terminal_output(session_id):
    """Get terminal output"""
    clear = request.args.get('clear', 'true').lower() == 'true'
    output = terminal_manager.get_output(session_id, clear)
    return jsonify({"output": output})

@app.route('/api/terminal/session/<session_id>/resize', methods=['POST'])
def resize_terminal(session_id):
    """Resize terminal"""
    data = request.json or {}
    rows = data.get('rows', 24)
    cols = data.get('cols', 80)
    success = terminal_manager.resize(session_id, rows, cols)
    return jsonify({"success": success})

@app.route('/api/terminal/session/<session_id>', methods=['DELETE'])
def kill_terminal_session(session_id):
    """Kill terminal session"""
    success = terminal_manager.kill_session(session_id)
    return jsonify({"success": success})

# ============ AGENT / PROVIDER API ============

@app.route('/api/providers')
def get_providers():
    from provider_manager import ProviderManager
    pm = ProviderManager()
    providers = pm.get_available_providers()
    return jsonify({"providers": providers, "status": "ok"})

@app.route('/api/mode', methods=['POST'])
def set_mode():
    data = request.json
    mode = data.get('mode', 'interactive')
    return jsonify({"mode": mode, "status": "ok"})

@app.route('/api/cost')
def get_cost():
    """Get cost tracking report"""
    try:
        from metrics.cost_tracker import CostTracker
        tracker = CostTracker()
        return jsonify({"report": tracker.get_report()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/validate', methods=['POST'])
def validate_project():
    """Validate project"""
    try:
        from validator.project_validator import ProjectValidator
        validator = ProjectValidator(CONFIG.working_directory)
        report = validator.validate_all()
        return jsonify({"result": report})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/index', methods=['POST'])
def index_project():
    """Index project for semantic search"""
    try:
        from memory.vector_store import ProjectIndex
        index = ProjectIndex(CONFIG.working_directory)
        index.index_files("*.py")
        return jsonify({"result": f"Indexed {len(index.chunks)} code chunks"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============ SOCKET.IO EVENTS ============

@socketio.on('connect')
def handle_connect():
    print(f"Client connected: {request.sid}")
    sessions[request.sid] = {
        "agent": None,
        "mode": "interactive",
        "history": [],
        "stop_requested": False,
        "thread": None,
        "chat_session_id": None
    }
    emit('connected', {'status': 'connected', 'sid': request.sid})

@socketio.on('disconnect')
def handle_disconnect():
    print(f"Client disconnected: {request.sid}")
    session = sessions.pop(request.sid, None)
    if session and session.get('thread') and session['thread'].is_alive():
        session['stop_requested'] = True

@socketio.on('start_task')
def handle_start_task(data):
    sid = request.sid
    task = data.get('task', '')
    mode = data.get('mode', 'interactive')

    if not task:
        emit('error', {'message': 'No task provided'})
        return

    session = sessions.get(sid)
    if not session:
        emit('error', {'message': 'No session'})
        return

    if session.get('thread') and session['thread'].is_alive():
        session['stop_requested'] = True
        time.sleep(0.5)

    session['stop_requested'] = False
    session['mode'] = mode

    try:
        agent = Agent(mode=mode)
        sessions[sid]['agent'] = agent
    except Exception as e:
        emit('error', {'message': f'Failed to create agent: {str(e)}'})
        return

    emit('status', {'message': f'Starting task in {mode} mode...'})

    def run_agent():
        try:
            full_response = []
            for chunk in agent.run(task):
                if session.get('stop_requested'):
                    emit('chunk', {'content': '\n\n[STOPPED BY USER]\n'}, room=sid)
                    break

                emit('chunk', {'content': chunk}, room=sid)
                full_response.append(chunk)
                time.sleep(0.01)

            if not session.get('stop_requested'):
                emit('complete', {
                    'message': 'Task completed',
                    'full_response': ''.join(full_response)
                }, room=sid)

        except Exception as e:
            emit('error', {'message': str(e)}, room=sid)
        finally:
            session['thread'] = None

    thread = threading.Thread(target=run_agent)
    thread.daemon = True
    session['thread'] = thread
    thread.start()

@socketio.on('stop_task')
def handle_stop_task():
    sid = request.sid
    session = sessions.get(sid)
    if session:
        session['stop_requested'] = True
        emit('status', {'message': 'Stopping...'})

@socketio.on('user_input')
def handle_user_input(data):
    sid = request.sid
    user_input = data.get('input', '')

    session = sessions.get(sid)
    if session and session.get('agent'):
        emit('status', {'message': f'User input received: {user_input}'})
    else:
        emit('error', {'message': 'No active agent session'})

@socketio.on('chat_message')
def handle_chat(data):
    sid = request.sid
    message = data.get('message', '')
    session_id = data.get('session_id')

    session = sessions.get(sid)
    if not session:
        emit('error', {'message': 'No session'})
        return

    # Use existing or create chat session
    if not session_id:
        if not session.get('chat_session_id'):
            chat_session = chat_manager.create_session(mode=session.get('mode', 'interactive'))
            session['chat_session_id'] = chat_session.session_id
        session_id = session['chat_session_id']

    # Store user message
    chat_manager.add_message(session_id, 'user', message)

    # Get or create agent
    if not session.get('agent'):
        try:
            agent = Agent(mode=session.get('mode', 'interactive'))
            session['agent'] = agent
        except Exception as e:
            emit('error', {'message': f'Failed to create agent: {str(e)}'})
            return

    agent = session['agent']

    def run_chat():
        try:
            full_response = []
            for chunk in agent.chat(message):
                if session.get('stop_requested'):
                    break
                emit('chunk', {'content': chunk}, room=sid)
                full_response.append(chunk)
                time.sleep(0.01)

            response_text = ''.join(full_response)
            # Store assistant response
            chat_manager.add_message(session_id, 'assistant', response_text)

            emit('message_complete', {'content': response_text, 'session_id': session_id}, room=sid)
        except Exception as e:
            emit('error', {'message': str(e)}, room=sid)

    thread = threading.Thread(target=run_chat)
    thread.daemon = True
    thread.start()

@socketio.on('terminal_create')
def handle_terminal_create(data):
    """Create terminal via socket"""
    sid = request.sid
    shell = data.get('shell')
    session = terminal_manager.create_session(shell=shell)
    emit('terminal_created', {
        'session_id': session.session_id,
        'shell': session.shell
    }, room=sid)

@socketio.on('terminal_input')
def handle_terminal_input(data):
    """Send input to terminal"""
    sid = request.sid
    session_id = data.get('session_id')
    text = data.get('data', '')
    success = terminal_manager.write(session_id, text)
    emit('terminal_status', {'success': success}, room=sid)

@socketio.on('terminal_resize')
def handle_terminal_resize(data):
    """Resize terminal"""
    sid = request.sid
    session_id = data.get('session_id')
    rows = data.get('rows', 24)
    cols = data.get('cols', 80)
    success = terminal_manager.resize(session_id, rows, cols)
    emit('terminal_status', {'success': success}, room=sid)

@socketio.on('ensemble_toggle')
def handle_ensemble_toggle(data):
    """Toggle ensemble mode"""
    sid = request.sid
    enabled = data.get('enabled', True)
    emit('ensemble_status', {'enabled': enabled}, room=sid)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
