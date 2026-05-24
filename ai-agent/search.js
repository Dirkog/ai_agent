// AI Agent v6 — Search Component
class SearchComponent {
  constructor() {
    this.overlay = null;
    this.input = null;
    this.resultsEl = null;
    this.init();
  }

  init() {
    this.overlay = document.createElement('div');
    this.overlay.style.cssText = `
      position:fixed;inset:0;background:rgba(0,0,0,0.5);
      display:none;align-items:flex-start;justify-content:center;
      z-index:2000;padding-top:80px;backdrop-filter:blur(2px);
    `;

    this.overlay.innerHTML = `
      <div style="background:var(--bg-secondary);border:1px solid var(--border-color);border-radius:12px;width:600px;max-width:90vw;box-shadow:0 20px 60px rgba(0,0,0,0.5);overflow:hidden">
        <div style="display:flex;align-items:center;padding:12px 16px;border-bottom:1px solid var(--border-color);gap:8px">
          <span style="color:var(--text-muted);font-size:18px">Q</span>
          <input type="text" id="search-input" placeholder="Search files, symbols, or content..." style="flex:1;background:transparent;border:none;outline:none;color:var(--text-primary);font-size:15px" autocomplete="off">
          <span style="color:var(--text-muted);font-size:11px;padding:2px 6px;border-radius:4px;background:var(--bg-hover)">ESC to close</span>
        </div>
        <div id="search-results" style="max-height:400px;overflow-y:auto;padding:8px 0"></div>
      </div>
    `;

    document.body.appendChild(this.overlay);
    this.input = this.overlay.querySelector('#search-input');
    this.resultsEl = this.overlay.querySelector('#search-results');

    this.bindEvents();
  }

  bindEvents() {
    document.addEventListener('keydown', (e) => {
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'f') {
        e.preventDefault();
        this.open();
      }
      if (e.key === 'Escape' && this.overlay.style.display === 'flex') {
        this.close();
      }
    });

    this.input.addEventListener('input', (e) => {
      this.debounceSearch(e.target.value);
    });

    this.input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        this.performSearch(this.input.value);
      }
    });

    this.overlay.addEventListener('click', (e) => {
      if (e.target === this.overlay) this.close();
    });
  }

  open() {
    this.overlay.style.display = 'flex';
    this.input.value = '';
    this.input.focus();
    this.resultsEl.innerHTML = '';
  }

  close() {
    this.overlay.style.display = 'none';
  }

  debounceSearch(query) {
    clearTimeout(this.searchTimeout);
    if (!query.trim()) {
      this.resultsEl.innerHTML = '';
      return;
    }
    this.searchTimeout = setTimeout(() => this.performSearch(query), 300);
  }

  async performSearch(query) {
    if (!query.trim()) return;

    this.resultsEl.innerHTML = '<div style="padding:16px;text-align:center;color:var(--text-muted)"><span class="spinner"></span> Searching...</div>';

    try {
      const res = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
      const data = await res.json();
      this.renderResults(data.results || [], query);
    } catch (e) {
      this.resultsEl.innerHTML = `<div style="padding:16px;color:var(--danger)">Search failed: ${e.message}</div>`;
    }
  }

  renderResults(results, query) {
    if (results.length === 0) {
      this.resultsEl.innerHTML = `<div style="padding:16px;text-align:center;color:var(--text-muted)">No results for "${query}"</div>`;
      return;
    }

    let html = `<div style="padding:8px 16px;font-size:11px;color:var(--text-muted);border-bottom:1px solid var(--border-color)">${results.length} results</div>`;

    results.forEach(r => {
      const highlighted = r.content.replace(
        new RegExp(query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi'),
        match => `<span style="background:rgba(88,166,255,0.3);color:var(--accent)">${match}</span>`
      );

      html += `
        <div class="search-result" data-file="${r.file}" data-line="${r.line}" style="padding:8px 16px;cursor:pointer;border-bottom:1px solid var(--border-color);transition:background 0.15s">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
            <span style="font-size:12px;color:var(--accent);font-weight:500">${r.file}</span>
            <span style="font-size:11px;color:var(--text-muted)">Line ${r.line}</span>
          </div>
          <div style="font-family:var(--font-mono);font-size:12px;color:var(--text-secondary);white-space:pre-wrap">${highlighted}</div>
        </div>
      `;
    });

    this.resultsEl.innerHTML = html;

    this.resultsEl.querySelectorAll('.search-result').forEach(el => {
      el.addEventListener('click', () => {
        const file = el.dataset.file;
        const line = parseInt(el.dataset.line);
        window.dispatchEvent(new CustomEvent('open-file-request', { detail: { file, line } }));
        this.close();
      });
      el.addEventListener('mouseenter', () => el.style.background = 'var(--bg-hover)');
      el.addEventListener('mouseleave', () => el.style.background = 'transparent');
    });
  }
}
