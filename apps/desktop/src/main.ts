import { app, BrowserWindow, dialog } from 'electron';
import * as path from 'path';

// Diagnostics for dev setup
const isElectron = !!(process.versions && process.versions.electron);
if (!isElectron) {
    console.error('ERROR: This process is running as standard Node.js, not Electron.');
    console.error('Ensure you are launching the app via "electron" and not "node".');
    if (process.env.ELECTRON_RUN_AS_NODE) {
        console.error('Resolution: Unset ELECTRON_RUN_AS_NODE environment variable.');
    }
    process.exit(1);
}

const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged;
const isWriteMode = process.env.WRITE_MODE === 'true';

function createWindow(): void {
    const mainWindow = new BrowserWindow({
        width: 1200,
        height: 800,
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            contextIsolation: true,
            nodeIntegration: false,
        },
    });

    if (isDev) {
        // In development, prefer the URL from Vite dev server if passed
        const devServerUrl = process.env.VITE_DEV_SERVER_URL || 'http://localhost:5173';
        console.log(`[DEV] Loading from: ${devServerUrl}`);
        
        mainWindow.loadURL(devServerUrl).catch((err) => {
            console.error(`[DEV] Failed to load ${devServerUrl}:`, err);
            dialog.showErrorBox(
                'Dev Server unreachable',
                `Electron could not connect to the Vite dev server at ${devServerUrl}. \n\nPlease make sure the dev server is running before starting Electron.`
            );
        });
        
        mainWindow.webContents.openDevTools();
    } else {
        // In production, load the built index.html
        const indexPath = path.join(__dirname, '../dist/index.html');
        console.log(`[PROD] Loading from: ${indexPath}`);
        mainWindow.loadFile(indexPath);
    }

    console.log(`Milestone running in ${isWriteMode ? 'WRITE' : 'READ-ONLY'} mode`);
}

app.whenReady().then(() => {
    createWindow();

    app.on('activate', () => {
        if (BrowserWindow.getAllWindows().length === 0) {
            createWindow();
        }
    });
});

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') {
        app.quit();
    }
});

// Export for testing
export { isWriteMode };
