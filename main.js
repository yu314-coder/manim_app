const { app, BrowserWindow, ipcMain, dialog, shell } = require('electron');
const path = require('path');
const fs = require('fs');
const { spawn, exec } = require('child_process');
const os = require('os');

// Remote module removed for security

let mainWindow;
let venvWindow = null;
let assetsWindow = null;

// Global flag to prevent duplicate IPC setup
global.ipcHandlersRegistered = global.ipcHandlersRegistered || false;

function createWindow() {
    mainWindow = new BrowserWindow({
        width: 1400,
        height: 900,
        icon: path.join(__dirname, 'icon.ico'),
        webPreferences: {
            nodeIntegration: false,           // SECURE: Disabled
            contextIsolation: true,           // SECURE: Enabled  
            webSecurity: true,               // SECURE: Re-enabled
            preload: path.join(__dirname, 'preload.js'), // Secure API bridge
            allowRunningInsecureContent: false,
            experimentalFeatures: false,
            nodeIntegrationInWorker: false,
            nodeIntegrationInSubFrames: false,
            enableRemoteModule: false        // SECURE: No remote module
        }
    });

    // Remote module removed for security

    mainWindow.loadFile('index.html');

    // Setup IPC handlers ONLY if not already registered
    if (!global.ipcHandlersRegistered) {
        setupIPCHandlers();
        global.ipcHandlersRegistered = true;
    }

    mainWindow.on('closed', () => {
        app.quit();
    });
}

// Enhanced VEnv Manager Window
function createVenvWindow() {
    if (venvWindow) {
        venvWindow.focus();
        return;
    }

    venvWindow = new BrowserWindow({
        width: 1200,
        height: 800,
        parent: mainWindow,
        modal: false,
        webPreferences: {
            nodeIntegration: false,
            contextIsolation: true,
            webSecurity: true,
            preload: path.join(__dirname, 'preload.js'),
            enableRemoteModule: false
        }
    });

    // Remote module removed for security

    venvWindow.loadFile('venv.html');
    
    venvWindow.on('closed', () => {
        venvWindow = null;
    });
}

// Enhanced Assets Manager Window
function createAssetsWindow() {
    if (assetsWindow) {
        assetsWindow.focus();
        return;
    }

    assetsWindow = new BrowserWindow({
        width: 1000,
        height: 700,
        parent: mainWindow,
        modal: false,
        webPreferences: {
            nodeIntegration: false,
            contextIsolation: true,
            webSecurity: true,
            preload: path.join(__dirname, 'preload.js'),
            enableRemoteModule: false
        }
    });

    // Remote module removed for security

    assetsWindow.loadFile('assets.html');
    
    assetsWindow.on('closed', () => {
        assetsWindow = null;
    });
}

function setupIPCHandlers() {
    console.log('🔧 Setting up IPC handlers (one-time setup)...');
    
    // Clear any existing handlers first to prevent duplicates
    ipcMain.removeAllListeners('open-assets-manager');
    ipcMain.removeAllListeners('open-venv-manager');
    ipcMain.removeAllListeners('execute-terminal-command');
    ipcMain.removeAllListeners('get-app-paths');
    ipcMain.removeAllListeners('save-file');
    ipcMain.removeAllListeners('load-file');
    ipcMain.removeAllListeners('select-folder');
    ipcMain.removeAllListeners('open-external');
    ipcMain.removeAllListeners('show-item-in-folder');
    ipcMain.removeAllListeners('kill-process');
    ipcMain.removeAllListeners('check-environment');
    ipcMain.removeAllListeners('setup-environment');
    
    // Window management handlers
    ipcMain.handle('open-assets-manager', () => {
        console.log('📂 Opening Assets Manager');
        createAssetsWindow();
    });

    ipcMain.handle('open-venv-manager', () => {
        console.log('🐍 Opening VEnv Manager');
        createVenvWindow();
    });

    // Enhanced terminal command handler with better error handling
    ipcMain.handle('execute-terminal-command', async (event, command, workingDir) => {
        try {
            console.log('🎯 IPC: Received terminal command request');
            console.log('📋 Command:', command);
            console.log('📁 Working Dir:', workingDir);
            
            // Validate inputs
            if (!command || typeof command !== 'string') {
                throw new Error('Invalid command provided');
            }
            
            // Send start notification to renderer
            if (mainWindow && !mainWindow.isDestroyed()) {
                mainWindow.webContents.send('process-started', { 
                    command: command,
                    workingDir: workingDir
                });
            }
            
            // Execute the command
            const result = await executeTerminalCommand(command, workingDir);
            console.log('🎯 IPC: Command execution completed');
            console.log('📊 Result:', {
                success: result.success,
                code: result.code,
                outputLength: result.output ? result.output.length : 0
            });
            
            return result;
        } catch (error) {
            console.error('❌ IPC: Terminal command error:', error);
            
            const errorResult = {
                success: false,
                output: '',
                error: `IPC Error: ${error.message}`,
                code: -1,
                timestamp: new Date().toISOString()
            };
            
            // Send error notification to renderer
            if (mainWindow && !mainWindow.isDestroyed()) {
                mainWindow.webContents.send('process-complete', errorResult);
            }
            
            return errorResult;
        }
    });

    // File operations
    ipcMain.handle('save-file', async (event, filePath, content) => {
        try {
            console.log('💾 Saving file:', filePath);
            await fs.promises.writeFile(filePath, content, 'utf8');
            return { success: true, filePath };
        } catch (error) {
            console.error('❌ File save error:', error);
            return { success: false, error: error.message };
        }
    });

    ipcMain.handle('load-file', async (event, filePath) => {
        try {
            console.log('📂 Loading file:', filePath);
            const content = await fs.promises.readFile(filePath, 'utf8');
            return { success: true, content, filePath };
        } catch (error) {
            console.error('❌ File load error:', error);
            return { success: false, error: error.message };
        }
    });

    // Environment management
    ipcMain.handle('check-environment', async () => {
        try {
            const venvPath = path.join(os.homedir(), '.manim_studio', 'venvs', 'manim_studio_default');
            const pythonPath = os.platform() === 'win32' 
                ? path.join(venvPath, 'Scripts', 'python.exe')
                : path.join(venvPath, 'bin', 'python');
            
            const envExists = fs.existsSync(venvPath);
            const pythonExists = fs.existsSync(pythonPath);
            
            return { 
                success: true, 
                exists: envExists && pythonExists,
                venvPath,
                pythonPath
            };
        } catch (error) {
            return { success: false, error: error.message };
        }
    });

    ipcMain.handle('setup-environment', async () => {
        try {
            const homeDir = os.homedir();
            const manimStudioDir = path.join(homeDir, '.manim_studio');
            const venvsDir = path.join(manimStudioDir, 'venvs');
            const venvDir = path.join(venvsDir, 'manim_studio_default');
            
            // Create directories
            await fs.promises.mkdir(venvsDir, { recursive: true });
            
            // Create virtual environment
            const createVenvCommand = `python -m venv "${venvDir}"`;
            const createResult = await executeTerminalCommand(createVenvCommand);
            
            if (!createResult.success) {
                throw new Error(`Failed to create virtual environment: ${createResult.error}`);
            }
            
            // Install manim
            const pythonPath = os.platform() === 'win32' 
                ? path.join(venvDir, 'Scripts', 'python.exe')
                : path.join(venvDir, 'bin', 'python');
            
            const installCommand = `"${pythonPath}" -m pip install manim[gui]`;
            const installResult = await executeTerminalCommand(installCommand);
            
            if (!installResult.success) {
                throw new Error(`Failed to install manim: ${installResult.error}`);
            }
            
            return { success: true };
            
        } catch (error) {
            console.error('Environment setup error:', error);
            return { success: false, error: error.message };
        }
    });

    // Other utility handlers
    ipcMain.handle('get-app-paths', () => {
        return {
            home: os.homedir(),
            manimStudio: path.join(os.homedir(), '.manim_studio'),
            assets: path.join(os.homedir(), '.manim_studio', 'assets'),
            venv: path.join(os.homedir(), '.manim_studio', 'venv')
        };
    });

    ipcMain.handle('select-folder', async () => {
        const result = await dialog.showOpenDialog(mainWindow, {
            properties: ['openDirectory']
        });
        return result;
    });

    ipcMain.handle('open-external', async (event, url) => {
        await shell.openExternal(url);
    });

    ipcMain.handle('show-item-in-folder', (event, fullPath) => {
        shell.showItemInFolder(fullPath);
    });

    // Add secure dialog handlers
    ipcMain.handle('show-save-dialog', async (event, options) => {
        try {
            const result = await dialog.showSaveDialog(mainWindow, {
                filters: [
                    { name: 'Python Files', extensions: ['py'] },
                    { name: 'All Files', extensions: ['*'] }
                ],
                defaultPath: 'untitled.py',
                ...options
            });
            return result;
        } catch (error) {
            return { canceled: true, error: error.message };
        }
    });

    ipcMain.handle('show-open-dialog', async (event, options) => {
        try {
            const result = await dialog.showOpenDialog(mainWindow, {
                filters: [
                    { name: 'Python Files', extensions: ['py'] },
                    { name: 'All Files', extensions: ['*'] }
                ],
                properties: ['openFile'],
                ...options
            });
            return result;
        } catch (error) {
            return { canceled: true, error: error.message };
        }
    });

    // Workspace file reading
    ipcMain.handle('read-workspace-files', async (event, dirPath) => {
        try {
            const files = await fs.promises.readdir(dirPath);
            const fileDetails = await Promise.all(files.map(async (file) => {
                const filePath = path.join(dirPath, file);
                const stats = await fs.promises.stat(filePath);
                return {
                    name: file,
                    path: filePath,
                    isDirectory: stats.isDirectory(),
                    size: stats.size,
                    modified: stats.mtime
                };
            }));
            return { success: true, files: fileDetails };
        } catch (error) {
            return { success: false, error: error.message };
        }
    });

    // Language server placeholder
    ipcMain.handle('request-language-server', async (event, request) => {
        try {
            return { success: true, response: null };
        } catch (error) {
            return { success: false, error: error.message };
        }
    });

    // Python environment info
    ipcMain.handle('get-python-info', async () => {
        try {
            const pythonPath = path.join(os.homedir(), '.manim_studio', 'venvs', 'manim_studio_default', 'Scripts', 'python.exe');
            const exists = await fs.promises.access(pythonPath).then(() => true).catch(() => false);
            return { success: true, pythonPath, exists };
        } catch (error) {
            return { success: false, error: error.message };
        }
    });

    console.log('✅ IPC handlers setup completed');
}

// Enhanced terminal command execution with proper Windows path handling
async function executeTerminalCommand(command, cwd = process.cwd()) {
    return new Promise((resolve) => {
        console.log(`🚀 Executing: ${command} in ${cwd}`);
        
        let output = '';
        let errorOutput = '';
        
        // FORCE manim_studio_default environment for ALL operations - NEVER use system Python
        const FORCED_VENV_PATH = path.join(os.homedir(), '.manim_studio', 'venvs', 'manim_studio_default');
        const FORCED_PYTHON_EXE = path.join(FORCED_VENV_PATH, 'Scripts', 'python.exe');
        
        console.log('🎯 FORCING virtual environment usage');
        console.log('📋 Original command:', command);
        console.log('📁 Working directory:', cwd);
        
        // ENFORCE: ONLY use our specific virtual environment Python - NO FALLBACKS
        if (!fs.existsSync(FORCED_PYTHON_EXE)) {
            console.error('❌ CRITICAL: Virtual environment not found at:', FORCED_PYTHON_EXE);
            const errorResult = {
                success: false,
                output: '',
                error: `Virtual environment not found at: ${FORCED_PYTHON_EXE}. Please run setup first.`,
                code: -1,
                timestamp: new Date().toISOString()
            };
            resolve(errorResult);
            return;
        }

        // FORCE: Replace any python calls with our specific Python executable
        let finalCommand = command;
        if (command.includes('python')) {
            finalCommand = command.replace(/python/g, `"${FORCED_PYTHON_EXE}"`);
            console.log('🔄 Command transformed to:', finalCommand);
        }

        // Enhanced environment with FORCED virtual environment paths
        const enhancedEnv = {
            ...process.env,
            PATH: `${FORCED_VENV_PATH}\\Scripts;${process.env.PATH}`,
            VIRTUAL_ENV: FORCED_VENV_PATH,
            PYTHONPATH: FORCED_VENV_PATH,
            MANIM_VENV: 'manim_studio_default' // Flag for our scripts
        };

        console.log('🌍 Environment PATH:', enhancedEnv.PATH.split(';').slice(0, 3).join(';') + '...');

        const childProcess = spawn(finalCommand, [], {
            cwd: cwd,
            shell: true,
            stdio: ['pipe', 'pipe', 'pipe'],
            env: enhancedEnv
        });

        childProcess.stdout.on('data', (data) => {
            const chunk = data.toString();
            output += chunk;
            console.log('📤 STDOUT:', chunk);
            
            // Send real-time output to renderer
            if (mainWindow && !mainWindow.isDestroyed()) {
                mainWindow.webContents.send('process-output', { 
                    type: 'stdout', 
                    data: chunk 
                });
            }
        });

        childProcess.stderr.on('data', (data) => {
            const chunk = data.toString();
            errorOutput += chunk;
            console.log('📤 STDERR:', chunk);
            
            // Send real-time output to renderer
            if (mainWindow && !mainWindow.isDestroyed()) {
                mainWindow.webContents.send('process-output', { 
                    type: 'stderr', 
                    data: chunk 
                });
            }
        });

        childProcess.on('close', (code) => {
            console.log(`✅ Process finished with code: ${code}`);
            
            const result = {
                success: code === 0,
                output: output + errorOutput,
                error: code !== 0 ? errorOutput : null,
                code: code,
                timestamp: new Date().toISOString()
            };

            // Send completion notification to renderer
            if (mainWindow && !mainWindow.isDestroyed()) {
                mainWindow.webContents.send('process-complete', result);
            }

            resolve(result);
        });

        childProcess.on('error', (error) => {
            console.error(`❌ Process error: ${error.message}`);
            
            const errorResult = {
                success: false,
                output: output,
                error: `Process error: ${error.message}`,
                code: -1,
                timestamp: new Date().toISOString()
            };

            if (mainWindow && !mainWindow.isDestroyed()) {
                mainWindow.webContents.send('process-complete', errorResult);
            }

            resolve(errorResult);
        });

        // Set a timeout for long-running processes (5 minutes)
        const timeout = setTimeout(() => {
            console.log('⏰ Process timeout reached, killing process...');
            if (!childProcess.killed) {
                childProcess.kill('SIGKILL');
            }
        }, 300000);

        childProcess.on('close', () => {
            clearTimeout(timeout);
        });
    });
}

// App event handlers
app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') {
        app.quit();
    }
});

app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
        createWindow();
    }
});

// Handle certificate errors for HTTPS CDN resources
app.on('certificate-error', (event, webContents, url, error, certificate, callback) => {
    // Allow CDN certificates
    if (url.includes('cdnjs.cloudflare.com')) {
        event.preventDefault();
        callback(true);
    } else {
        callback(false);
    }
});

// Security: Handle external navigation attempts
app.on('web-contents-created', (event, contents) => {
    contents.on('new-window', (event, navigationUrl) => {
        // Allow HTTPS CDN resources
        if (navigationUrl.startsWith('https://cdnjs.cloudflare.com')) {
            return;
        }
        
        event.preventDefault();
        shell.openExternal(navigationUrl);
    });
});

console.log('🚀 Main process initialized');