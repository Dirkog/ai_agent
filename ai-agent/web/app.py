"""Web interface for AI Agent using Flask/SocketIO — FIXED VERSION
Real API endpoints for file operations, streaming, and IDE features.
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

app = Flask(__name__)
app.config['SECRET_KEY'] = 'ai-agent-secret-key'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

sessions = {}

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

@app.route('/api/file')
def get_file():
    """Read file content"""
    path = request.args.get('path', '')
    if not path:
        return jsonify({"error": "No path provided"}), 400
    
    try:
        full_path = Path(CONFIG.working_directory) / path
        full_path = full_path.resolve()
        root = Path(CONFIG.working_directory).resolve()
        
        if not str(full_path).startswith(str(root)):
            return jsonify({"error": "Access denied"}), 403
        
        if not full_path.exists():
            return jsonify({"error": "File not found"}), 404
        
        content = full_path.read_text(encoding='utf-8', errors='replace')
        return jsonify({
            "path": path,
            "content": content,
            "language": _get_language(full_path.suffix),
            "size": len(content),
            "lines": content.count('\n') + 1
        })
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
        full_path = Path(CONFIG.working_directory) / path
        full_path = full_path.resolve()
        root = Path(CONFIG.working_directory).resolve()
        
        if not str(full_path).startswith(str(root)):
            return jsonify({"error": "Access denied"}), 403
        
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding='utf-8')
        
        return jsonify({"success": True, "path": path})
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

@socketio.on('connect')
def handle_connect():
    print(f"Client connected: {request.sid}")
    sessions[request.sid] = {
        "agent": None,
        "mode": "interactive",
        "history": [],
        "stop_requested": False,
        "thread": None
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
    
    session = sessions.get(sid)
    if not session or not session.get('agent'):
        try:
            agent = Agent(mode="interactive")
            sessions[sid] = sessions.get(sid, {})
            sessions[sid]['agent'] = agent
        except Exception as e:
            emit('error', {'message': f'Failed to create agent: {str(e)}'})
            return
    
    agent = sessions[sid]['agent']
    
    def run_chat():
        try:
            full_response = []
            for chunk in agent.chat(message):
                if session.get('stop_requested'):
                    break
                emit('chunk', {'content': chunk}, room=sid)
                full_response.append(chunk)
                time.sleep(0.01)
            
            emit('message_complete', {'content': ''.join(full_response)}, room=sid)
        except Exception as e:
            emit('error', {'message': str(e)}, room=sid)
    
    thread = threading.Thread(target=run_chat)
    thread.daemon = True
    thread.start()

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
