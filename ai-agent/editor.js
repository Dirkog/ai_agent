// AI Agent v6 — Editor Component
class EditorComponent {
  constructor(containerId) {
    this.container = document.getElementById(containerId);
    this.tabs = new Map();
    this.activeTab = null;
    this.init();
  }

  init() {
    this.container.innerHTML = `
      <div class="tab-bar" id="editor-tabs"></div>
      <div class="editor-container">
        <div class="editor-pane" id="editor-pane">
          <div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--text-muted);font-size:14px">
            Select a file from the sidebar to edit
          </div>
        </div>
      </div>
    `;
    this.tabsEl = this.container.querySelector('#editor-tabs');
    this.paneEl = this.container.querySelector('#editor-pane');
  }

  openFile(path, content, language = 'plaintext') {
    if (this.tabs.has(path)) {
      this.switchTab(path);
      return;
    }

    const tabId = 'tab-' + Math.random().toString(36).substr(2, 9);
    const tab = {
      path,
      content,
      language,
      modified: false,
      tabId,
      scrollPos: 0
    };

    this.tabs.set(path, tab);
    this.renderTab(tab);
    this.switchTab(path);
  }

  renderTab(tab) {
    const el = document.createElement('div');
    el.className = 'tab';
    el.dataset.path = tab.path;
    el.innerHTML = `
      <span class="tab-icon">${this.getFileIcon(tab.path)}</span>
      <span class="tab-name">${tab.path.split('/').pop()}</span>
      <span class="modified-indicator" style="display:none">*</span>
      <span class="close-btn">x</span>
    `;

    el.addEventListener('click', (e) => {
      if (e.target.classList.contains('close-btn')) {
        this.closeTab(tab.path);
      } else {
        this.switchTab(tab.path);
      }
    });

    this.tabsEl.appendChild(el);
  }

  switchTab(path) {
    if (this.activeTab) {
      const current = this.tabs.get(this.activeTab);
      if (current) {
        current.scrollPos = this.paneEl.scrollTop;
      }
    }

    this.activeTab = path;

    this.tabsEl.querySelectorAll('.tab').forEach(t => {
      t.classList.toggle('active', t.dataset.path === path);
    });

    const tab = this.tabs.get(path);
    if (!tab) return;

    this.renderEditor(tab);
  }

  renderEditor(tab) {
    const ext = tab.path.split('.').pop() || '';
    const langMap = {
      py: 'python', js: 'javascript', ts: 'typescript',
      jsx: 'jsx', tsx: 'tsx', html: 'html', css: 'css',
      json: 'json', md: 'markdown', yml: 'yaml', yaml: 'yaml',
      rs: 'rust', go: 'go', java: 'java', cpp: 'cpp',
      c: 'c', h: 'c', hpp: 'cpp', sh: 'shell',
      sql: 'sql', toml: 'toml', txt: 'plaintext'
    };
    const language = langMap[ext] || ext || 'plaintext';

    const highlighted = this.simpleHighlight(tab.content, language);

    this.paneEl.innerHTML = `
      <div style="display:flex;flex-direction:column;height:100%">
        <div style="display:flex;justify-content:space-between;align-items:center;padding:4px 12px;background:var(--bg-tertiary);border-bottom:1px solid var(--border-color);font-size:11px;color:var(--text-muted)">
          <span>${tab.path} ${tab.modified ? '(modified)' : ''}</span>
          <span>${tab.content.split('\n').length} lines | ${tab.content.length} chars</span>
        </div>
        <pre style="flex:1;margin:0;overflow:auto;tab-size:4" id="code-editor">${highlighted}</pre>
      </div>
    `;

    const editor = this.paneEl.querySelector('#code-editor');
    if (editor) {
      editor.scrollTop = tab.scrollPos;
    }
  }

  simpleHighlight(code, language) {
    const escaped = code
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');

    let result = escaped.replace(
      /("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')/g,
      '<span style="color:#a5d6ff">$1</span>'
    );

    if (language === 'python') {
      result = result.replace(
        /(#.*$)/gm,
        '<span style="color:#8b949e">$1</span>'
      );
    } else {
      result = result.replace(
        /(\/\/.*$|\/\*[\s\S]*?\*\/)/gm,
        '<span style="color:#8b949e">$1</span>'
      );
    }

    const keywords = ['def', 'class', 'import', 'from', 'return', 'if', 'else', 'elif',
      'for', 'while', 'try', 'except', 'finally', 'with', 'as', 'lambda',
      'async', 'await', 'yield', 'pass', 'break', 'continue', 'raise',
      'function', 'const', 'let', 'var', 'async', 'await', 'return',
      'if', 'else', 'for', 'while', 'switch', 'case', 'break', 'class'];
    const kwRegex = new RegExp(`\b(${keywords.join('|')})\b`, 'g');
    result = result.replace(kwRegex, '<span style="color:#ff7b72">$1</span>');

    result = result.replace(
      /\b(\d+\.?\d*)\b/g,
      '<span style="color:#79c0ff">$1</span>'
    );

    return result;
  }

  closeTab(path) {
    const tab = this.tabs.get(path);
    if (!tab) return;

    if (tab.modified) {
      if (!confirm(`Save changes to ${tab.path}?`)) {
      } else {
        this.saveFile(path);
      }
    }

    this.tabs.delete(path);
    const tabEl = this.tabsEl.querySelector(`[data-path="${path}"]`);
    if (tabEl) tabEl.remove();

    if (this.activeTab === path) {
      const remaining = Array.from(this.tabs.keys());
      this.activeTab = null;
      if (remaining.length > 0) {
        this.switchTab(remaining[0]);
      } else {
        this.paneEl.innerHTML = `
          <div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--text-muted);font-size:14px">
            Select a file from the sidebar to edit
          </div>
        `;
      }
    }
  }

  saveFile(path) {
    const tab = this.tabs.get(path);
    if (!tab) return;

    fetch('/api/file', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: tab.path, content: tab.content })
    }).then(r => r.json()).then(data => {
      if (data.success) {
        tab.modified = false;
        this.switchTab(path);
      }
    });
  }

  getFileIcon(path) {
    const ext = path.split('.').pop();
    const icons = {
      py: 'PY', js: 'JS', ts: 'TS', jsx: 'JSX', tsx: 'TSX',
      html: 'HTML', css: 'CSS', json: 'JSON', md: 'MD', yml: 'YML', yaml: 'YML',
      rs: 'RS', go: 'GO', java: 'JAVA', cpp: 'CPP', c: 'C',
      sh: 'SH', dockerfile: 'DOCKER', sql: 'SQL', toml: 'TOML', txt: 'TXT'
    };
    return icons[ext] || 'FILE';
  }

  updateFile(path, content) {
    const tab = this.tabs.get(path);
    if (tab) {
      tab.content = content;
      tab.modified = true;
      if (this.activeTab === path) {
        this.renderEditor(tab);
      }
    }
  }
}
