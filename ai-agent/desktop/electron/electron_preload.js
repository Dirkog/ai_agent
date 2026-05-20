const { contextBridge, ipcRenderer } = require('electron');

// Expose safe API to renderer
contextBridge.exposeInMainWorld('electronAPI', {
    // Agent control
    startAgent: () => ipcRenderer.invoke('agent-start'),
    stopAgent: () => ipcRenderer.invoke('agent-stop'),
    getAgentStatus: () => ipcRenderer.invoke('agent-status'),
    onAgentLog: (callback) => ipcRenderer.on('agent-log', (_, data) => callback(data)),

    // File system
    selectFolder: () => ipcRenderer.invoke('select-folder'),
    readFile: (path) => ipcRenderer.invoke('read-file', path),
    writeFile: (path, content) => ipcRenderer.invoke('write-file', path, content),

    // External
    openExternal: (url) => ipcRenderer.invoke('open-external', url),

    // Platform
    platform: process.platform,
    versions: {
        node: process.versions.node,
        electron: process.versions.electron,
        chrome: process.versions.chrome
    }
});
