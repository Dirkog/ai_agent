// AI Agent v6 — Chat Component
class ChatComponent {
  constructor(containerId, socket) {
    this.container = document.getElementById(containerId);
    this.socket = socket;
    this.messages = [];
    this.isRunning = false;
    this.init();
  }

  init() {
    this.container.innerHTML = `
      <div class="panel-header">
        <div class="panel-tab active" data-tab="chat">Chat</div>
        <div class="panel-tab" data-tab="terminal">Terminal</div>
        <div class="panel-tab" data-tab="logs">Logs</div>
        <div class="panel-tab" data-tab="ensemble">Ensemble</div>
      </div>
      <div class="panel-content" id="panel-content"></div>
      <div class="input-area">
        <textarea id="chat-input" placeholder="Describe your task... Use @file:path.py to reference files" rows="1"></textarea>
        <button id="send-btn">Send</button>
        <button id="stop-btn" class="stop" style="display:none">Stop</button>
      </div>
    `;

    this.contentEl = this.container.querySelector('#panel-content');
    this.inputEl = this.container.querySelector('#chat-input');
    this.sendBtn = this.container.querySelector('#send-btn');
    this.stopBtn = this.container.querySelector('#stop-btn');

    this.bindEvents();
    this.switchTab('chat');
  }

  bindEvents() {
    this.container.querySelectorAll('.panel-tab').forEach(tab => {
      tab.addEventListener('click', () => this.switchTab(tab.dataset.tab));
    });

    this.sendBtn.addEventListener('click', () => this.sendMessage());
    this.inputEl.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        this.sendMessage();
      }
    });
    this.inputEl.addEventListener('input', () => this.autoResize());
    this.stopBtn.addEventListener('click', () => this.stopTask());

    this.socket.on('chunk', (data) => this.appendChunk(data.content));
    this.socket.on('complete', (data) => this.onComplete(data));
    this.socket.on('error', (data) => this.appendMessage('error', data.message));
    this.socket.on('status', (data) => this.appendMessage('system', data.message));
    this.socket.on('message_complete', (data) => this.onChatComplete(data));
  }

  autoResize() {
    this.inputEl.style.height = 'auto';
    this.inputEl.style.height = Math.min(this.inputEl.scrollHeight, 200) + 'px';
  }

  switchTab(tab) {
    this.container.querySelectorAll('.panel-tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
    this.currentTab = tab;
    if (tab === 'chat') {
      this.renderMessages();
    } else if (tab === 'terminal') {
      this.contentEl.innerHTML = '<div style="font-family:monospace;font-size:12px;padding:8px;color:var(--text-muted)">Terminal output will appear here...</div>';
    } else if (tab === 'logs') {
      this.contentEl.innerHTML = '<div style="font-family:monospace;font-size:11px;padding:8px;color:var(--text-muted)">System logs...</div>';
    } else if (tab === 'ensemble') {
      this.renderEnsemble();
    }
  }

  renderMessages() {
    this.contentEl.innerHTML = '';
    this.messages.forEach(msg => this._renderMessage(msg));
    this.scrollToBottom();
  }

  _renderMessage(msg) {
    const el = document.createElement('div');
    el.className = `message ${msg.type}`;
    el.innerHTML = this.formatContent(msg.content);
    this.contentEl.appendChild(el);
  }

  formatContent(text) {
    text = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    text = text.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code class="language-$1">$2</code></pre>');
    text = text.replace(/`([^`]+)`/g, '<code>$1</code>');
    text = text.replace(/\b(https?:\/\/[^\s]+)\b/g, '<a href="$1" target="_blank" style="color:var(--accent)">$1</a>');
    text = text.replace(/\n/g, '<br>');
    return text;
  }

  appendMessage(type, content) {
    const msg = { type, content, timestamp: Date.now() };
    this.messages.push(msg);
    if (this.currentTab === 'chat') {
      this._renderMessage(msg);
      this.scrollToBottom();
    }
  }

  appendChunk(chunk) {
    if (!this.currentChunk) {
      this.currentChunk = { type: 'assistant', content: '', timestamp: Date.now() };
      this.messages.push(this.currentChunk);
    }
    this.currentChunk.content += chunk;
    if (this.currentTab === 'chat') {
      const lastMsg = this.contentEl.lastElementChild;
      if (lastMsg && lastMsg.classList.contains('assistant') && !lastMsg.dataset.final) {
        lastMsg.innerHTML = this.formatContent(this.currentChunk.content);
      } else {
        this._renderMessage(this.currentChunk);
      }
      this.scrollToBottom();
    }
  }

  onComplete(data) {
    if (this.currentChunk) {
      this.currentChunk.content = data.full_response || this.currentChunk.content;
      this.currentChunk = null;
    }
    this.isRunning = false;
    this.updateUI();
  }

  onChatComplete(data) {
    this.appendMessage('assistant', data.content);
    this.currentChunk = null;
    this.isRunning = false;
    this.updateUI();
  }

  sendMessage() {
    const text = this.inputEl.value.trim();
    if (!text || this.isRunning) return;

    this.appendMessage('user', text);
    this.inputEl.value = '';
    this.inputEl.style.height = 'auto';
    this.isRunning = true;
    this.currentChunk = null;
    this.updateUI();

    const mode = document.querySelector('.mode-selector')?.value || 'interactive';
    if (text.startsWith('/')) {
      this.handleCommand(text);
    } else if (mode === 'interactive') {
      this.socket.emit('chat_message', { message: text });
    } else {
      this.socket.emit('start_task', { task: text, mode });
    }
  }

  handleCommand(cmd) {
    const parts = cmd.slice(1).split(' ');
    const command = parts[0];

    switch(command) {
      case 'mode':
        this.appendMessage('system', `Current mode: ${document.querySelector('.mode-selector')?.value || 'interactive'}`);
        break;
      case 'cost':
        fetch('/api/cost').then(r => r.json()).then(d => {
          this.appendMessage('system', `Cost report: ${JSON.stringify(d, null, 2)}`);
        });
        break;
      case 'validate':
        this.appendMessage('system', 'Running project validation...');
        fetch('/api/validate', { method: 'POST' }).then(r => r.json()).then(d => {
          this.appendMessage('system', d.result || 'Validation complete');
        });
        break;
      case 'index':
        this.appendMessage('system', 'Indexing project...');
        fetch('/api/index', { method: 'POST' }).then(r => r.json()).then(d => {
          this.appendMessage('system', d.result || 'Indexing complete');
        });
        break;
      case 'clear':
        this.messages = [];
        this.renderMessages();
        break;
      case 'help':
        this.appendMessage('system', 'Available commands: /mode, /cost, /validate, /index, /clear, /help');
        break;
      default:
        this.appendMessage('system', `Unknown command: ${command}. Type /help for available commands.`);
    }
    this.isRunning = false;
    this.updateUI();
  }

  stopTask() {
    this.socket.emit('stop_task');
    this.isRunning = false;
    this.updateUI();
  }

  updateUI() {
    this.sendBtn.style.display = this.isRunning ? 'none' : 'inline-block';
    this.stopBtn.style.display = this.isRunning ? 'inline-block' : 'none';
    this.inputEl.disabled = this.isRunning;
  }

  scrollToBottom() {
    this.contentEl.scrollTop = this.contentEl.scrollHeight;
  }

  renderEnsemble() {
    this.contentEl.innerHTML = `
      <div style="padding:16px">
        <h4 style="margin:0 0 12px 0">Ensemble Status</h4>
        <div style="font-family:monospace;font-size:12px">
          <div style="margin-bottom:8px;padding:8px;background:var(--bg-tertiary);border-radius:6px">
            <strong>Local Models:</strong> <span style="color:var(--success)">Online</span>
          </div>
          <div style="margin-bottom:8px;padding:8px;background:var(--bg-tertiary);border-radius:6px">
            <strong>NVIDIA NIM API:</strong> <span style="color:var(--success)">Online (40 RPM)</span>
          </div>
          <div style="margin-bottom:8px;padding:8px;background:var(--bg-tertiary);border-radius:6px">
            <strong>OpenRouter:</strong> <span style="color:var(--warning)">Standby (Debugger only)</span>
          </div>
        </div>
      </div>
    `;
  }
}
