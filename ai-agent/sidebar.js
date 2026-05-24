// AI Agent v6 — Sidebar / File Tree Component
class SidebarComponent {
  constructor(containerId, editor) {
    this.container = document.getElementById(containerId);
    this.editor = editor;
    this.treeData = null;
    this.expandedDirs = new Set();
    this.init();
  }

  init() {
    this.container.innerHTML = `
      <div class="sidebar-header">Explorer</div>
      <div class="sidebar-section" id="file-tree"></div>
      <div style="padding:8px 12px;border-top:1px solid var(--border-color);font-size:11px;color:var(--text-muted)">
        <div style="display:flex;gap:8px;justify-content:space-between">
          <span id="file-count">0 files</span>
          <span id="project-size">0 KB</span>
        </div>
      </div>
    `;
    this.treeEl = this.container.querySelector('#file-tree');
    this.loadProject();
  }

  async loadProject() {
    try {
      const res = await fetch('/api/project');
      const data = await res.json();
      this.treeData = data;
      this.renderTree(data);
      this.updateStats(data);
    } catch (e) {
      this.treeEl.innerHTML = `<div style="padding:12px;color:var(--danger)">Failed to load project: ${e.message}</div>`;
    }
  }

  renderTree(node, level = 0) {
    if (!node) return '';

    const isDir = node.type === 'directory';
    const isExpanded = this.expandedDirs.has(node.path);
    const padding = level * 12 + 12;

    let html = '';

    if (isDir) {
      html += `
        <div class="file-tree-item directory" data-path="${node.path}" style="padding-left:${padding}px">
          <span class="icon">${isExpanded ? 'v' : '>'}</span>
          <span>${node.name}</span>
        </div>
      `;
      if (isExpanded && node.children) {
        node.children.forEach(child => {
          html += this.renderTree(child, level + 1);
        });
      }
    } else {
      html += `
        <div class="file-tree-item" data-path="${node.path}" data-type="file" style="padding-left:${padding}px">
          <span class="icon">${this.getFileIcon(node.name)}</span>
          <span>${node.name}</span>
        </div>
      `;
    }

    return html;
  }

  render(node = this.treeData) {
    if (!node) return;
    this.treeEl.innerHTML = this.renderTree(node);
    this.bindEvents();
  }

  bindEvents() {
    this.treeEl.querySelectorAll('.file-tree-item').forEach(item => {
      item.addEventListener('click', (e) => {
        const path = item.dataset.path;
        const type = item.dataset.type;

        if (type === 'file') {
          this.openFile(path);
          this.treeEl.querySelectorAll('.file-tree-item').forEach(i => i.classList.remove('active'));
          item.classList.add('active');
        } else {
          if (this.expandedDirs.has(path)) {
            this.expandedDirs.delete(path);
          } else {
            this.expandedDirs.add(path);
          }
          this.render();
        }
      });

      item.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        this.showContextMenu(e, item.dataset.path, item.dataset.type);
      });
    });
  }

  async openFile(path) {
    try {
      const res = await fetch(`/api/file?path=${encodeURIComponent(path)}`);
      const data = await res.json();
      if (data.error) {
        console.error(data.error);
        return;
      }
      this.editor.openFile(path, data.content, data.language);
    } catch (e) {
      console.error('Failed to open file:', e);
    }
  }

  showContextMenu(e, path, type) {
    const menu = document.createElement('div');
    menu.style.cssText = `
      position:fixed;left:${e.clientX}px;top:${e.clientY}px;
      background:var(--bg-secondary);border:1px solid var(--border-color);
      border-radius:6px;padding:4px 0;z-index:1000;min-width:160px;
      box-shadow:0 4px 12px rgba(0,0,0,0.3);
    `;

    const items = [
      { label: 'New Folder', action: () => this.createFolder(path) },
      { label: 'New File', action: () => this.createFile(path) },
      { label: 'Rename', action: () => this.renameItem(path) },
      { label: 'Delete', action: () => this.deleteItem(path), danger: true },
      { label: 'Search in Folder', action: () => this.searchInFolder(path) },
    ];

    if (type === 'file') {
      items.unshift({ label: 'Open', action: () => this.openFile(path) });
    }

    items.forEach(item => {
      const el = document.createElement('div');
      el.style.cssText = `
        padding:6px 16px;cursor:pointer;font-size:13px;
        color:${item.danger ? 'var(--danger)' : 'var(--text-primary)'};
        transition:background 0.15s;
      `;
      el.textContent = item.label;
      el.addEventListener('click', () => {
        item.action();
        menu.remove();
      });
      el.addEventListener('mouseenter', () => el.style.background = 'var(--bg-hover)');
      el.addEventListener('mouseleave', () => el.style.background = 'transparent');
      menu.appendChild(el);
    });

    document.body.appendChild(menu);
    const closeMenu = () => { menu.remove(); document.removeEventListener('click', closeMenu); };
    setTimeout(() => document.addEventListener('click', closeMenu), 0);
  }

  createFile(path) {
    const name = prompt('Enter file name:');
    if (!name) return;
    const dir = path || '';
    const fullPath = dir ? `${dir}/${name}` : name;
    fetch('/api/file', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: fullPath, content: '' })
    }).then(() => this.loadProject());
  }

  createFolder(path) {
    const name = prompt('Enter folder name:');
    if (!name) return;
    const dir = path || '';
    const fullPath = dir ? `${dir}/${name}/.gitkeep` : `${name}/.gitkeep`;
    fetch('/api/file', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: fullPath, content: '' })
    }).then(() => this.loadProject());
  }

  renameItem(path) {
    const newName = prompt('Enter new name:', path.split('/').pop());
    if (!newName || newName === path.split('/').pop()) return;
    alert('Rename API not yet implemented');
  }

  deleteItem(path) {
    if (!confirm(`Delete ${path}?`)) return;
    fetch(`/api/file?path=${encodeURIComponent(path)}`, { method: 'DELETE' })
      .then(() => this.loadProject());
  }

  searchInFolder(path) {
    const query = prompt('Search query:');
    if (!query) return;
    window.dispatchEvent(new CustomEvent('search-request', { detail: { query, path } }));
  }

  getFileIcon(name) {
    const ext = name.split('.').pop();
    const icons = {
      py: 'PY', js: 'JS', ts: 'TS', jsx: 'JSX', tsx: 'TSX',
      html: 'HTML', css: 'CSS', json: 'JSON', md: 'MD', yml: 'YML', yaml: 'YML',
      rs: 'RS', go: 'GO', java: 'JAVA', cpp: 'CPP', c: 'C',
      sh: 'SH', dockerfile: 'DOCKER', sql: 'SQL', toml: 'TOML', txt: 'TXT',
      gitignore: 'GIT', env: 'ENV'
    };
    return icons[ext] || 'FILE';
  }

  updateStats(node) {
    let fileCount = 0;
    let totalSize = 0;

    const count = (n) => {
      if (n.type === 'file') {
        fileCount++;
        totalSize += n.size || 0;
      }
      if (n.children) n.children.forEach(count);
    };
    count(node);

    this.container.querySelector('#file-count').textContent = `${fileCount} files`;
    const sizeKB = (totalSize / 1024).toFixed(1);
    const sizeMB = (totalSize / 1024 / 1024).toFixed(1);
    this.container.querySelector('#project-size').textContent =
      totalSize > 1024 * 1024 ? `${sizeMB} MB` : `${sizeKB} KB`;
  }

  refresh() {
    this.loadProject();
  }
}
