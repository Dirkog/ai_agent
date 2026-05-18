const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
    selectFolder: () => ipcRenderer.invoke('select-folder'),
    openFile: (path) => ipcRenderer.invoke('open-file', path),
    showSaveDialog: (options) => ipcRenderer.invoke('show-save-dialog', options),

    getAppVersion: () => ipcRenderer.invoke('get-app-version'),
    platform: process.platform,

    onFolderSelected: (callback) => {
        ipcRenderer.on('folder-selected', (event, folder) => callback(folder));
    },

    showNotification: (title, body) => {
        new Notification(title, { body });
    }
});
