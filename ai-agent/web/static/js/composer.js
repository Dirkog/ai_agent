
class ComposerUI {
    constructor() {
        this.changes = [];
        this.currentPlan = null;
        this.socket = null;
    }

    connect(socket) {
        this.socket = socket;
        socket.on('composer_plan', (data) => this.showPlan(data));
        socket.on('composer_progress', (data) => this.updateProgress(data));
    }

    showPlan(data) {
        const plan = data.plan;
        this.currentPlan = plan;

        let html = `
            <div class="composer-panel">
                <div class="composer-header">
                    <h3>Composer Plan</h3>
                    <span class="composer-stats">
                        ${plan.total_files} files | ${plan.estimated_tokens} tokens
                    </span>
                </div>
                <div class="composer-files">
        `;

        plan.changes.forEach((change, i) => {
            html += `
                <div class="composer-file" data-index="${i}">
                    <div class="file-header">
                        <input type="checkbox" class="file-toggle" checked id="file-${i}">
                        <label for="file-${i}">${change.path}</label>
                        <span class="file-status">${change.status}</span>
                    </div>
                    <div class="file-reason">${change.reason}</div>
                    <div class="file-diff" id="diff-${i}"></div>
                </div>
            `;
        });

        html += `
                </div>
                <div class="composer-actions">
                    <button onclick="composer.acceptAll()" class="btn-primary">Accept All</button>
                    <button onclick="composer.rejectAll()" class="btn-danger">Reject All</button>
                    <button onclick="composer.reviewEach()" class="btn-secondary">Review One by One</button>
                </div>
            </div>
        `;

        document.getElementById('composer-container').innerHTML = html;

        // Generate diffs
        plan.changes.forEach((change, i) => {
            if (change.original && change.new) {
                this.renderDiff(i, change.original, change.new);
            }
        });
    }

    renderDiff(index, original, modified) {
        // Simple line diff
        const origLines = original.split('\n');
        const modLines = modified.split('\n');
        let html = '<div class="diff-view">';

        const maxLen = Math.max(origLines.length, modLines.length);
        for (let i = 0; i < maxLen; i++) {
            const oldLine = origLines[i] || '';
            const newLine = modLines[i] || '';

            if (oldLine === newLine) {
                html += `<div class="diff-line diff-context"><span class="diff-prefix"> </span>${this.escapeHtml(newLine)}</div>`;
            } else if (!oldLine && newLine) {
                html += `<div class="diff-line diff-add"><span class="diff-prefix">+</span>${this.escapeHtml(newLine)}</div>`;
            } else if (oldLine && !newLine) {
                html += `<div class="diff-line diff-remove"><span class="diff-prefix">-</span>${this.escapeHtml(oldLine)}</div>`;
            } else {
                html += `<div class="diff-line diff-remove"><span class="diff-prefix">-</span>${this.escapeHtml(oldLine)}</div>`;
                html += `<div class="diff-line diff-add"><span class="diff-prefix">+</span>${this.escapeHtml(newLine)}</div>`;
            }
        }

        html += '</div>';
        document.getElementById(`diff-${index}`).innerHTML = html;
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    acceptAll() {
        const approved = this.changes.map((_, i) => i);
        this.socket.emit('composer_apply', { approved, rejected: [] });
    }

    rejectAll() {
        this.socket.emit('composer_apply', { approved: [], rejected: this.changes.map((_, i) => i) });
    }

    reviewEach() {
        this.showReviewModal(0);
    }

    showReviewModal(index) {
        const change = this.currentPlan.changes[index];
        const modal = document.createElement('div');
        modal.className = 'modal';
        modal.innerHTML = `
            <div class="modal-content">
                <h3>${change.path}</h3>
                <div class="modal-diff" id="modal-diff"></div>
                <div class="modal-actions">
                    <button onclick="composer.acceptFile(${index})" class="btn-primary">Accept</button>
                    <button onclick="composer.rejectFile(${index})" class="btn-danger">Reject</button>
                    <button onclick="composer.nextFile(${index})" class="btn-secondary">Skip</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
        this.renderDiffInElement('modal-diff', change.original, change.new);
    }

    renderDiffInElement(elementId, original, modified) {
        const el = document.getElementById(elementId);
        if (!el) return;
        const origLines = original.split('\n');
        const modLines = modified.split('\n');
        let html = '<div class="diff-view">';
        const maxLen = Math.max(origLines.length, modLines.length);
        for (let i = 0; i < maxLen; i++) {
            const oldLine = origLines[i] || '';
            const newLine = modLines[i] || '';
            if (oldLine === newLine) {
                html += `<div class="diff-line diff-context"><span class="diff-prefix"> </span>${this.escapeHtml(newLine)}</div>`;
            } else if (!oldLine && newLine) {
                html += `<div class="diff-line diff-add"><span class="diff-prefix">+</span>${this.escapeHtml(newLine)}</div>`;
            } else if (oldLine && !newLine) {
                html += `<div class="diff-line diff-remove"><span class="diff-prefix">-</span>${this.escapeHtml(oldLine)}</div>`;
            } else {
                html += `<div class="diff-line diff-remove"><span class="diff-prefix">-</span>${this.escapeHtml(oldLine)}</div>`;
                html += `<div class="diff-line diff-add"><span class="diff-prefix">+</span>${this.escapeHtml(newLine)}</div>`;
            }
        }
        html += '</div>';
        el.innerHTML = html;
    }

    acceptFile(index) {
        document.querySelector(`.composer-file[data-index="${index}"] .file-toggle`).checked = true;
        this.nextFile(index);
    }

    rejectFile(index) {
        document.querySelector(`.composer-file[data-index="${index}"] .file-toggle`).checked = false;
        this.nextFile(index);
    }

    nextFile(currentIndex) {
        document.querySelector('.modal')?.remove();
        if (currentIndex + 1 < this.currentPlan.changes.length) {
            this.showReviewModal(currentIndex + 1);
        }
    }

    updateProgress(data) {
        const { applied, total, current_file } = data;
        const el = document.getElementById('composer-progress');
        if (el) {
            el.textContent = `Applying: ${current_file} (${applied}/${total})`;
        }
    }
}

const composer = new ComposerUI();
