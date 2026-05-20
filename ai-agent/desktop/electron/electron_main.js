const { app, BrowserWindow, ipcMain, dialog, shell } = require('electron');
const path = require('path');
const { spawn } = require('child_process');

// Global agent process
let agentProcess = null;
let mainWindow = null;

function createWindow() {
    mainWindow = new BrowserWindow({
        width: 1400,
        height: 900,
        minWidth: 800,
        minHeight: 600,
        titleBarStyle: 'hiddenInset',
        webPreferences: {
            nodeIntegration: false,
            contextIsolation: true,
            preload: path.join(__dirname, 'preload.js'),
            sandbox: false
        },
        icon: path.join(__dirname, 'assets', 'icon.png')
    });

    // Load web UI from Flask server
    mainWindow.loadURL('http://localhost:5000');

    // DevTools in development
    if (process.env.NODE_ENV === 'development') {
        mainWindow.webContents.openDevTools();
    }

    mainWindow.on('closed', () => {
        mainWindow = null;
        if (agentProcess) {
            agentProcess.kill();
        }
    });
}

// Start Python agent backend
function startAgentBackend() {
    const pythonPath = process.platform === 'win32' ? 'python' : 'python3';
    const scriptPath = path.join(__dirname, '..', '..', 'main.py');

    agentProcess = spawn(pythonPath, [scriptPath, '--web'], {
        cwd: path.join(__dirname, '..', '..'),
        env: { ...process.env, PYTHONUNBUFFERED: '1' }
    });

    agentProcess.stdout.on('data', (data) => {
        console.log(`[Agent] ${data}`);
        if (mainWindow) {
            mainWindow.webContents.send('agent-log', data.toString());
        }
    });

    agentProcess.stderr.on('data', (data) => {
        console.error(`[Agent Error] ${data}`);
    });

    agentProcess.on('close', (code) => {
        console.log(`[Agent] Process exited with code ${code}`);
        agentProcess = null;
    });
}

// IPC handlers
ipcMain.handle('agent-start', async () => {
    if (!agentProcess) {
        startAgentBackend();
        // Wait for server to start
        await new Promise(resolve => setTimeout(resolve, 3000));
        return { success: true, message: 'Agent started' };
    }
    return { success: false, message: 'Agent already running' };
});

ipcMain.handle('agent-stop', async () => {
    if (agentProcess) {
        agentProcess.kill();
        agentProcess = null;
        return { success: true, message: 'Agent stopped' };
    }
    return { success: false, message: 'Agent not running' };
});

ipcMain.handle('agent-status', async () => {
    return {
        running: agentProcess !== null,
        pid: agentProcess ? agentProcess.pid : null
    };
});

ipcMain.handle('select-folder', async () => {
    const result = await dialog.showOpenDialog(mainWindow, {
        properties: ['openDirectory'],
        title: 'Select Project Folder'
    });
    return result.filePaths[0] || null;
});

ipcMain.handle('open-external', async (event, url) => {
    await shell.openExternal(url);
});

ipcMain.handle('read-file', async (event, filePath) => {
    const fs = require('fs').promises;
    try {
        const content = await fs.readFile(filePath, 'utf-8');
        return { success: true, content };
    } catch (e) {
        return { success: false, error: e.message };
    }
});

ipcMain.handle('write-file', async (event, filePath, content) => {
    const fs = require('fs').promises;
    try {
        await fs.writeFile(filePath, content, 'utf-8');
        return { success: true };
    } catch (e) {
        return { success: false, error: e.message };
    }
});

// App lifecycle
app.whenReady().then(() => {
    startAgentBackend();
    createWindow();

    app.on('activate', () => {
        if (BrowserWindow.getAllWindows().length === 0) {
            createWindow();
        }
    });
});

app.on('window-all-closed', () => {
    if (agentProcess) {
        agentProcess.kill();
    }
    if (process.platform !== 'darwin') {
        app.quit();
    }
});

app.on('before-quit', () => {
    if (agentProcess) {
        agentProcess.kill();
    }
});
