// AI Agent v6 — Web UI Main Application
class AIAgentWebApp {
  constructor() {
    this.socket = io();
    this.components = {};
    this.init();
  }

  init() {
    this.renderLayout();
    this.initComponents();
    this.bindGlobalEvents();
    this.setupKeyboardShortcuts();
  }

  renderLayout() {
    document.body.innerHTML = `
      <div class="app-container">
        <aside class="sidebar" id="sidebar"></aside>
        <div class="main-area">
          <div class="model-selector" id="model-selector">
            <div class="model-chip local active" data-model="deepseek-v4-pro">DeepSeek V4 Pro</div>
            <div class="model-chip api active" data-model="mistral-large-3">Mistral Large 3</div>
            <div class="model-chip api" data-model="llama-4-maverick">Llama 4 Maverick</div>
            <div class="model-chip local" data-model="qwen3.5-122b">Qwen 3.5 122B</div>
            <div class="model-chip api" data-model="minimax-m2.7">MiniMax M2.7</div>
            <div class="ensemble-badge" id="ensemble-toggle" style="cursor:pointer">Ensemble ON</div>
          </div>
          <div style="flex:1;display:flex;overflow:hidden">
            <div style="flex:1;display:flex;flex-direction:column;min-width:0" id="editor-area">
              <div id="editor-component"></div>
            </div>
            <div style="width:360px;min-width:280px;border-left:1px solid var(--border-color);display:flex;flex-direction:column;background:var(--bg-secondary)" id="chat-area">
              <div style="padding:8px 12px;border-bottom:1px solid var(--border-color);display:flex;gap:8px;align-items:center;background:var(--bg-tertiary)">
                <select class="mode-selector" id="mode-selector" style="background:var(--bg-primary);border:1px solid var(--border-color);border-radius:4px;padding:4px 8px;color:var(--text-primary);font-size:12px;outline:none">
                  <option value="interactive">Interactive</option>
                  <option value="autonomous">Autonomous</option>
                  <option value="swarm">Swarm</option>
                </select>
                <button id="new-chat-btn" style="padding:4px 8px;background:var(--bg-hover);border:1px solid var(--border-color);border-radius:4px;color:var(--text-primary);cursor:pointer;font-size:12px">+ New</button>
              </div>
              <div id="chat-component" style="flex:1;overflow:hidden;display:flex;flex-direction:column"></div>
            </div>
          </div>
          <div class="status-bar" id="status-bar"></div>
        </div>
      </div>
      <div id="ensemble-panel" style="position:fixed;right:0;top:36px;width:320px;height:calc(100% - 36px);background:var(--bg-secondary);border-left:1px solid var(--border-color);transform:translateX(100%);transition:transform 0.3s;z-index:100;display:none"></div>
    `;
  }

  initComponents() {
    this.components.editor = new EditorComponent('editor-component');
    this.components.sidebar = new SidebarComponent('sidebar', this.components.editor);
    this.components.chat = new ChatComponent('chat-component', this.socket);
    this.components.statusbar = new StatusBarComponent('status-bar', this.socket);
    this.components.search = new SearchComponent();
    this.components.ensemble = new EnsembleMonitorComponent('ensemble-panel', this.socket);
    this.initModelSelector();
  }

  initModelSelector() {
    const selector = document.getElementById('model-selector');
    const ensembleToggle = document.getElementById('ensemble-toggle');

    selector.querySelectorAll('.model-chip').forEach(chip => {
      chip.addEventListener('click', () => {
        chip.classList.toggle('active');
        this.updateActiveModels();
      });
    });

    let ensembleEnabled = true;
    ensembleToggle.addEventListener('click', () => {
      ensembleEnabled = !ensembleEnabled;
      ensembleToggle.textContent = ensembleEnabled ? 'Ensemble ON' : 'Ensemble OFF';
      ensembleToggle.style.opacity = ensembleEnabled ? '1' : '0.5';
      document.dispatchEvent(new CustomEvent('ensemble-toggle', { detail: { enabled: ensembleEnabled } }));
    });

    let panelVisible = false;
    const panel = document.getElementById('ensemble-panel');
    document.addEventListener('keydown', (e) => {
      if (e.key === 'e' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        panelVisible = !panelVisible;
        panel.style.display = 'block';
        panel.style.transform = panelVisible ? 'translateX(0)' : 'translateX(100%)';
      }
    });
  }

  updateActiveModels() {
    const active = Array.from(document.querySelectorAll('.model-chip.active')).map(c => ({
      model: c.dataset.model,
      type: c.classList.contains('local') ? 'local' : 'api'
    }));
    console.log('Active models:', active);
  }

  bindGlobalEvents() {
    document.addEventListener('open-file-request', (e) => {
      const { file, line } = e.detail;
      this.components.sidebar.openFile(file);
    });

    document.addEventListener('search-request', (e) => {
      const { query, path } = e.detail;
      this.components.search.open();
      this.components.search.input.value = query;
      this.components.search.performSearch(query);
    });

    document.getElementById('mode-selector').addEventListener('change', (e) => {
      document.dispatchEvent(new CustomEvent('mode-change', { detail: { mode: e.target.value } }));
    });

    document.getElementById('new-chat-btn').addEventListener('click', () => {
      this.components.chat.messages = [];
      this.components.chat.renderMessages();
    });
  }

  setupKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'f') {
        e.preventDefault();
        this.components.search.open();
      }
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'n') {
        e.preventDefault();
        this.components.chat.messages = [];
        this.components.chat.renderMessages();
      }
      if ((e.ctrlKey || e.metaKey) && e.key === 'b') {
        e.preventDefault();
        const sidebar = document.querySelector('.sidebar');
        sidebar.style.display = sidebar.style.display === 'none' ? 'flex' : 'none';
      }
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'e') {
        e.preventDefault();
        document.getElementById('ensemble-toggle').click();
      }
    });
  }
}

document.addEventListener('DOMContentLoaded', () => {
  window.app = new AIAgentWebApp();
});
