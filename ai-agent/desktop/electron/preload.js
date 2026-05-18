const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
    // File operations
    selectFolder: () => ipcRenderer.invoke('select-folder'),
    openFile: (path) => ipcRenderer.invoke('open-file', path),
    showSaveDialog: (options) => ipcRenderer.invoke('show-save-dialog', options),
    
    // App info
    getAppVersion: () => ipcRenderer.invoke('get-app-version'),
    platform: process.platform,
    
    // Events from main
    onFolderSelected: (callback) => {
        ipcRenderer.on('folder-selected', (event, folder) => callback(folder));
    },
    
    // Notifications
    showNotification: (title, body) => {
        new Notification(title, { body });
    }
});
