// AI Agent v6 — Ensemble Monitor Component
class EnsembleMonitorComponent {
  constructor(containerId, socket) {
    this.container = document.getElementById(containerId);
    this.socket = socket;
    this.runs = [];
    this.init();
  }

  init() {
    this.container.innerHTML = `
      <div style="padding:16px;height:100%;overflow-y:auto">
        <h3 style="margin:0 0 16px 0;display:flex;align-items:center;gap:8px">
          Ensemble Monitor
          <span class="ensemble-badge">Live</span>
        </h3>
        <div id="ensemble-runs"></div>
        <div id="ensemble-stats" style="margin-top:16px;padding:12px;background:var(--bg-tertiary);border-radius:8px;border:1px solid var(--border-color)">
          <h4 style="margin:0 0 8px 0;font-size:13px">Statistics</h4>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:12px;color:var(--text-secondary)">
            <div>Total runs: <span id="total-runs" style="color:var(--text-primary)">0</span></div>
            <div>Avg confidence: <span id="avg-confidence" style="color:var(--text-primary)">-</span></div>
            <div>Local wins: <span id="local-wins" style="color:var(--success)">0</span></div>
            <div>API wins: <span id="api-wins" style="color:var(--accent)">0</span></div>
            <div>Merged: <span id="merged-count" style="color:var(--warning)">0</span></div>
            <div>Debug calls: <span id="debug-calls" style="color:var(--text-muted)">0</span></div>
          </div>
        </div>
      </div>
    `;

    this.runsEl = this.container.querySelector('#ensemble-runs');
    this.bindEvents();
  }

  bindEvents() {
    this.socket.on('ensemble_result', (data) => {
      this.addRun(data);
    });
  }

  addRun(data) {
    const run = {
      id: Math.random().toString(36).substr(2, 9),
      timestamp: Date.now(),
      task: data.task || 'Unknown task',
      localModel: data.local_model || 'Local',
      apiModel: data.api_model || 'API',
      winner: data.winner || 'unknown',
      confidence: data.confidence || 0,
      localLatency: data.local_latency || 0,
      apiLatency: data.api_latency || 0,
      debugUsed: data.debug_used || false,
      merged: data.merged || false
    };

    this.runs.unshift(run);
    if (this.runs.length > 50) this.runs.pop();

    this.renderRuns();
    this.updateStats();
  }

  renderRuns() {
    if (this.runs.length === 0) {
      this.runsEl.innerHTML = '<div style="text-align:center;color:var(--text-muted);padding:32px">No ensemble runs yet</div>';
      return;
    }

    let html = '';
    this.runs.forEach(run => {
      const time = new Date(run.timestamp).toLocaleTimeString();
      let winnerColor = 'var(--text-muted)';
      let winnerText = run.winner;

      if (run.winner === 'local') { winnerColor = 'var(--success)'; winnerText = 'Local wins'; }
      else if (run.winner === 'api') { winnerColor = 'var(--accent)'; winnerText = 'API wins'; }
      else if (run.merged) { winnerColor = 'var(--warning)'; winnerText = 'Merged'; }

      html += `
        <div style="margin-bottom:8px;padding:10px 12px;background:var(--bg-tertiary);border-radius:8px;border:1px solid var(--border-color);font-size:12px">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
            <span style="font-weight:500;color:var(--text-primary)">${run.task.substring(0, 60)}${run.task.length > 60 ? '...' : ''}</span>
            <span style="color:var(--text-muted);font-size:11px">${time}</span>
          </div>
          <div style="display:flex;gap:12px;margin-bottom:6px;color:var(--text-secondary)">
            <span>Local: ${run.localModel} (${run.localLatency}ms)</span>
            <span>API: ${run.apiModel} (${run.apiLatency}ms)</span>
          </div>
          <div style="display:flex;justify-content:space-between;align-items:center">
            <span style="color:${winnerColor};font-weight:600">${winnerText}</span>
            <span style="color:var(--text-muted)">Confidence: ${(run.confidence * 100).toFixed(1)}%</span>
            ${run.debugUsed ? '<span style="color:var(--warning);font-size:11px">Debug used</span>' : ''}
          </div>
        </div>
      `;
    });

    this.runsEl.innerHTML = html;
  }

  updateStats() {
    const total = this.runs.length;
    const localWins = this.runs.filter(r => r.winner === 'local').length;
    const apiWins = this.runs.filter(r => r.winner === 'api').length;
    const merged = this.runs.filter(r => r.merged).length;
    const debugUsed = this.runs.filter(r => r.debugUsed).length;
    const avgConf = total > 0 ? this.runs.reduce((a, r) => a + r.confidence, 0) / total : 0;

    this.container.querySelector('#total-runs').textContent = total;
    this.container.querySelector('#local-wins').textContent = localWins;
    this.container.querySelector('#api-wins').textContent = apiWins;
    this.container.querySelector('#merged-count').textContent = merged;
    this.container.querySelector('#debug-calls').textContent = debugUsed;
    this.container.querySelector('#avg-confidence').textContent = `${(avgConf * 100).toFixed(1)}%`;
  }
}
