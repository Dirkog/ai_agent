const { app, BrowserWindow, ipcMain, dialog, shell, Menu } = require('electron');
const path = require('path');
const { spawn } = require('child_process');

let mainWindow;
let pythonProcess;

function createWindow() {
    mainWindow = new BrowserWindow({
        width: 1400,
        height: 900,
        minWidth: 800,
        minHeight: 600,
        webPreferences: {
            nodeIntegration: false,
            contextIsolation: true,
            preload: path.join(__dirname, 'preload.js')
        },
        titleBarStyle: 'hiddenInset',
        show: false
    });

    const isDev = process.env.NODE_ENV === 'development';
    if (isDev) {
        mainWindow.loadURL('http://localhost:3000');
        mainWindow.webContents.openDevTools();
    } else {
        mainWindow.loadURL('http://localhost:5000');
    }

    mainWindow.once('ready-to-show', () => {
        mainWindow.show();
    });

    mainWindow.webContents.setWindowOpenHandler(({ url }) => {
        shell.openExternal(url);
        return { action: 'deny' };
    });
}

function startPythonBackend() {
    const pythonPath = process.env.PYTHON_PATH || 'python';
    const scriptPath = path.join(__dirname, '..', '..', 'web', 'app.py');

    pythonProcess = spawn(pythonPath, [scriptPath], {
        env: { 
            ...process.env, 
            PYTHONPATH: path.join(__dirname, '..', '..'),
            PORT: '5000'
        }
    });

    pythonProcess.stdout.on('data', (data) => {
        console.log(`[Python] ${data}`);
    });

    pythonProcess.stderr.on('data', (data) => {
        console.error(`[Python Error] ${data}`);
    });

    pythonProcess.on('close', (code) => {
        console.log(`Python process exited with code ${code}`);
    });
}

ipcMain.handle('select-folder', async () => {
    const result = await dialog.showOpenDialog(mainWindow, {
        properties: ['openDirectory'],
        title: 'Select Project Folder'
    });
    return result.filePaths[0] || null;
});

ipcMain.handle('open-file', async (event, filePath) => {
    shell.openPath(filePath);
});

ipcMain.handle('show-save-dialog', async (event, options) => {
    const result = await dialog.showSaveDialog(mainWindow, options);
    return result.filePath || null;
});

ipcMain.handle('get-app-version', () => {
    return app.getVersion();
});

const menuTemplate = [
    {
        label: 'File',
        submenu: [
            {
                label: 'Open Folder',
                accelerator: 'CmdOrCtrl+O',
                click: async () => {
                    const folder = await ipcMain.invoke('select-folder');
                    if (folder) {
                        mainWindow.webContents.send('folder-selected', folder);
                    }
                }
            },
            { type: 'separator' },
            {
                label: 'Quit',
                accelerator: process.platform === 'darwin' ? 'Cmd+Q' : 'Ctrl+Q',
                click: () => app.quit()
            }
        ]
    },
    {
        label: 'View',
        submenu: [
            { role: 'reload' },
            { role: 'forceReload' },
            { role: 'toggleDevTools' },
            { type: 'separator' },
            { role: 'resetZoom' },
            { role: 'zoomIn' },
            { role: 'zoomOut' }
        ]
    }
];

const menu = Menu.buildFromTemplate(menuTemplate);
Menu.setApplicationMenu(menu);

app.whenReady().then(() => {
    startPythonBackend();
    setTimeout(createWindow, 2000);

    app.on('activate', () => {
        if (BrowserWindow.getAllWindows().length === 0) createWindow();
    });
});

app.on('window-all-closed', () => {
    if (pythonProcess) pythonProcess.kill();
    if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', () => {
    if (pythonProcess) pythonProcess.kill();
});
