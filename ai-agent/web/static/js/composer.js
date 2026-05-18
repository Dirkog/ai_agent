/**
 * Composer UI - Cursor-like diff review
 */
class ComposerUI {
    constructor() {
        this.changes = [];
        this.container = document.getElementById('composer-panel');
        this.diffContainer = document.getElementById('composer-diff');
        this.statsElement = document.getElementById('composer-stats');
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    renderDiff(original, modified, filename) {
        const origLines = original.split('\n');
        const modLines = modified.split('\n');
        
        let html = `<div class="composer-file">`;
        html += `<div class="file-header">`;
        html += `<input type="checkbox" checked data-file="${this.escapeHtml(filename)}">`;
        html += `<label>${this.escapeHtml(filename)}</label>`;
        html += `<span class="file-status">Modified</span>`;
        html += `</div>`;
        
        html += `<div class="diff-view">`;
        
        const maxLen = Math.max(origLines.length, modLines.length);
        for (let i = 0; i < maxLen; i++) {
            const oldLine = origLines[i] || '';
            const newLine = modLines[i] || '';
            const lineNum = i + 1;
            
            if (oldLine === newLine) {
                html += `<div class="diff-line diff-context">`;
                html += `<span class="diff-prefix"> </span>`;
                html += `<span class="line-num">${lineNum}</span>`;
                html += `<span>${this.escapeHtml(newLine)}</span>`;
                html += `</div>`;
            } else if (!oldLine && newLine) {
                html += `<div class="diff-line diff-add">`;
                html += `<span class="diff-prefix">+</span>`;
                html += `<span class="line-num">${lineNum}</span>`;
                html += `<span>${this.escapeHtml(newLine)}</span>`;
                html += `</div>`;
            } else if (oldLine && !newLine) {
                html += `<div class="diff-line diff-remove">`;
                html += `<span class="diff-prefix">-</span>`;
                html += `<span class="line-num">${lineNum}</span>`;
                html += `<span>${this.escapeHtml(oldLine)}</span>`;
                html += `</div>`;
            } else {
                html += `<div class="diff-line diff-remove">`;
                html += `<span class="diff-prefix">-</span>`;
                html += `<span class="line-num">${lineNum}</span>`;
                html += `<span>${this.escapeHtml(oldLine)}</span>`;
                html += `</div>`;
                html += `<div class="diff-line diff-add">`;
                html += `<span class="diff-prefix">+</span>`;
                html += `<span class="line-num">${lineNum}</span>`;
                html += `<span>${this.escapeHtml(newLine)}</span>`;
                html += `</div>`;
            }
        }
        
        html += `</div></div>`;
        return html;
    }

    showPlan(plan) {
        if (!this.container) return;
        
        this.changes = plan.changes || [];
        let html = '';
        
        this.changes.forEach(change => {
            html += this.renderDiff(
                change.original_content || '',
                change.new_content || '',
                change.path
            );
        });
        
        if (this.diffContainer) {
            this.diffContainer.innerHTML = html;
        }
        
        if (this.statsElement) {
            this.statsElement.textContent = `${this.changes.length} files`;
        }
        
        this.container.style.display = 'block';
    }

    hide() {
        if (this.container) {
            this.container.style.display = 'none';
        }
    }

    getSelectedFiles() {
        const checkboxes = document.querySelectorAll('.file-header input[type="checkbox"]:checked');
        return Array.from(checkboxes).map(cb => cb.dataset.file);
    }

    applySelected() {
        const selected = this.getSelectedFiles();
        // Emit event to backend
        socket.emit('apply_composer_changes', { files: selected });
        this.hide();
    }

    rejectAll() {
        this.hide();
    }
}

// Initialize
const composerUI = new ComposerUI();
