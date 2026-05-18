"""Web interface for AI Agent using Flask/SocketIO"""
import os
import sys
import json
import threading
from pathlib import Path
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent import Agent
from config import CONFIG

app = Flask(__name__)
app.config['SECRET_KEY'] = 'ai-agent-secret-key'
socketio = SocketIO(app, cors_allowed_origins="*")

# Store active sessions
sessions = {}

@app.route('/')
def index():
    return render_template('index.html')

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
        "history": []
    }
    emit('connected', {'status': 'connected', 'sid': request.sid})

@socketio.on('disconnect')
def handle_disconnect():
    print(f"Client disconnected: {request.sid}")
    sessions.pop(request.sid, None)

@socketio.on('start_task')
def handle_start_task(data):
    sid = request.sid
    task = data.get('task', '')
    mode = data.get('mode', 'interactive')

    if not task:
        emit('error', {'message': 'No task provided'})
        return

    # Create agent for this session
    agent = Agent(mode=mode)
    sessions[sid]['agent'] = agent
    sessions[sid]['mode'] = mode

    emit('status', {'message': f'Starting task in {mode} mode...'})

    # Run agent in background thread
    def run_agent():
        try:
            for chunk in agent.run(task):
                socketio.emit('chunk', {'content': chunk}, room=sid)
            socketio.emit('complete', {'message': 'Task completed'}, room=sid)
        except Exception as e:
            socketio.emit('error', {'message': str(e)}, room=sid)

    thread = threading.Thread(target=run_agent)
    thread.daemon = True
    thread.start()

@socketio.on('user_input')
def handle_user_input(data):
    sid = request.sid
    user_input = data.get('input', '')

    session = sessions.get(sid)
    if session and session['agent']:
        # In real implementation, we'd need a way to inject user input into running agent
        emit('status', {'message': f'User input received: {user_input}'})
    else:
        emit('error', {'message': 'No active agent session'})

@socketio.on('chat_message')
def handle_chat(data):
    sid = request.sid
    message = data.get('message', '')

    if sid not in sessions or not sessions[sid]['agent']:
        # Create simple chat agent
        agent = Agent(mode="interactive")
        sessions[sid]['agent'] = agent

    agent = sessions[sid]['agent']

    def run_chat():
        try:
            full_response = ""
            for chunk in agent.chat(message):
                full_response += chunk
                socketio.emit('chunk', {'content': chunk}, room=sid)
            socketio.emit('message_complete', {'content': full_response}, room=sid)
        except Exception as e:
            socketio.emit('error', {'message': str(e)}, room=sid)

    thread = threading.Thread(target=run_chat)
    thread.daemon = True
    thread.start()

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
