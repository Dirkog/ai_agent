// AI Agent v6 — Status Bar Component
class StatusBarComponent {
  constructor(containerId, socket) {
    this.container = document.getElementById(containerId);
    this.socket = socket;
    this.status = {
      mode: 'interactive',
      provider: 'nvidia_nim',
      model: 'mistral-large-3',
      ensemble: true,
      connected: true,
      tasks: 0,
      cost: 0
    };
    this.init();
  }

  init() {
    this.container.innerHTML = `
      <div class="status-item">
        <span class="indicator" id="connection-indicator"></span>
        <span id="connection-status">Connected</span>
      </div>
      <div class="status-item">
        <span id="mode-badge" style="padding:2px 8px;border-radius:4px;background:var(--bg-hover);font-size:11px">interactive</span>
      </div>
      <div class="status-item">
        <span class="ensemble-badge" id="ensemble-badge">Ensemble ON</span>
      </div>
      <div class="status-item" id="model-info">
        <span style="color:var(--text-muted)">Model:</span>
        <span id="current-model">mistral-large-3</span>
      </div>
      <div class="status-item" id="task-info" style="display:none">
        <span class="spinner" style="width:12px;height:12px;margin-right:4px"></span>
        <span id="task-count">0 tasks</span>
      </div>
      <div class="status-item" style="margin-left:auto">
        <span style="color:var(--text-muted)">Cost:</span>
        <span id="cost-display">$0.00</span>
      </div>
    `;

    this.bindEvents();
  }

  bindEvents() {
    this.socket.on('connect', () => this.setConnected(true));
    this.socket.on('disconnect', () => this.setConnected(false));

    document.addEventListener('mode-change', (e) => {
      this.setMode(e.detail.mode);
    });

    document.addEventListener('ensemble-toggle', (e) => {
      this.setEnsemble(e.detail.enabled);
    });
  }

  setConnected(connected) {
    this.status.connected = connected;
    const indicator = this.container.querySelector('#connection-indicator');
    const status = this.container.querySelector('#connection-status');
    if (connected) {
      indicator.style.background = 'var(--success)';
      indicator.style.animation = 'pulse 2s infinite';
      status.textContent = 'Connected';
    } else {
      indicator.style.background = 'var(--danger)';
      indicator.style.animation = 'none';
      status.textContent = 'Disconnected';
    }
  }

  setMode(mode) {
    this.status.mode = mode;
    const badge = this.container.querySelector('#mode-badge');
    badge.textContent = mode;
    badge.style.background = mode === 'autonomous' ? 'var(--warning)' : 'var(--bg-hover)';
  }

  setEnsemble(enabled) {
    this.status.ensemble = enabled;
    const badge = this.container.querySelector('#ensemble-badge');
    badge.textContent = enabled ? 'Ensemble ON' : 'Ensemble OFF';
    badge.style.opacity = enabled ? '1' : '0.5';
  }

  setModel(model) {
    this.status.model = model;
    this.container.querySelector('#current-model').textContent = model;
  }

  setTaskCount(count) {
    this.status.tasks = count;
    const info = this.container.querySelector('#task-info');
    info.style.display = count > 0 ? 'flex' : 'none';
    this.container.querySelector('#task-count').textContent = `${count} task${count !== 1 ? 's' : ''}`;
  }

  setCost(cost) {
    this.status.cost = cost;
    this.container.querySelector('#cost-display').textContent = `$${cost.toFixed(2)}`;
  }
}
