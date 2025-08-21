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
        icon: path.join(__dirname, 'assets', 'icon.png'),
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
    ipcMain.removeAllListeners('get-python-info');
    ipcMain.removeAllListeners('auto-create-environment');
    ipcMain.removeAllListeners('show-save-dialog');
    ipcMain.removeAllListeners('show-open-dialog');
    ipcMain.removeAllListeners('read-workspace-files');
    ipcMain.removeAllListeners('request-language-server');
    ipcMain.removeAllListeners('add-asset');
    ipcMain.removeAllListeners('list-files');
    
    // Window management handlers
    ipcMain.handle('open-assets-manager', () => {
        console.log('📂 Opening Assets Manager');
        createAssetsWindow();
    });

    ipcMain.handle('open-venv-manager', () => {
        console.log('🐍 Opening VEnv Manager');
        createVenvWindow();
    });

    // Enhanced terminal command handler with better error handling and file creation
    ipcMain.handle('execute-terminal-command', async (event, command, workingDir, tempFileContent = null) => {
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
            
            // Create temporary file if content provided
            let tempFilePath = null;
            if (tempFileContent) {
                const tempDir = require('os').tmpdir();
                tempFilePath = path.join(tempDir, `manim_temp_${Date.now()}.py`);
                
                try {
                    await fs.promises.writeFile(tempFilePath, tempFileContent, 'utf8');
                    console.log('📄 Created temp file:', tempFilePath);
                    
                    // Modify command to use temp file if it references a file
                    command = command.replace(/\$TEMP_FILE/g, `"${tempFilePath}"`);
                } catch (tempFileError) {
                    console.error('❌ Temp file creation error:', tempFileError);
                }
            }
            
            // Execute the command with smart Python handling
            const result = await executeTerminalCommandSmart(command, workingDir);
            
            // Clean up temp file
            if (tempFilePath) {
                try {
                    await fs.promises.unlink(tempFilePath);
                    console.log('🗑️ Cleaned up temp file:', tempFilePath);
                } catch (cleanupError) {
                    console.warn('⚠️ Could not clean up temp file:', cleanupError.message);
                }
            }
            
            // Send completion notification to renderer
            if (mainWindow && !mainWindow.isDestroyed()) {
                mainWindow.webContents.send('process-complete', result);
            }
            
            console.log('✅ IPC: Command completed', {
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

    ipcMain.handle('delete-file', async (event, filePath) => {
        try {
            await fs.promises.unlink(filePath);
            return { success: true };
        } catch (error) {
            console.error('❌ File delete error:', error);
            return { success: false, error: error.message };
        }
    });

    // Dialog operations
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

    // ENHANCED: Auto-create environment handler with detailed logging
    ipcMain.handle('auto-create-environment', async () => {
        // Helper function to send progress updates to renderer
        const sendProgress = (message, type = 'info') => {
            console.log(`[ENV-SETUP] ${message}`);
            if (mainWindow && !mainWindow.isDestroyed()) {
                mainWindow.webContents.send('terminal-output', {
                    type: 'stdout',
                    data: `[${new Date().toLocaleTimeString()}] ${message}\n`
                });
            }
        };

        try {
            const homeDir = os.homedir();
            const manimStudioDir = path.join(homeDir, '.manim_studio');
            const venvsDir = path.join(manimStudioDir, 'venvs');
            const venvDir = path.join(venvsDir, 'manim_studio_default');
            
            sendProgress('🏗️ Starting virtual environment setup...');
            sendProgress(`📁 Target directory: ${venvDir}`);
            
            // Create directories
            sendProgress('📂 Creating directories...');
            await fs.promises.mkdir(venvsDir, { recursive: true });
            sendProgress('✅ Directories created successfully');
            
            // Check if Python is available
            sendProgress('🐍 Checking Python installation...');
            try {
                await new Promise((resolve, reject) => {
                    exec('python --version', (error, stdout, stderr) => {
                        if (error) {
                            reject(new Error('Python not found. Please install Python first.'));
                        } else {
                            sendProgress(`✅ Python found: ${stdout.trim()}`);
                            resolve();
                        }
                    });
                });
            } catch (pythonError) {
                sendProgress(`❌ Python check failed: ${pythonError.message}`, 'error');
                return { 
                    success: false, 
                    error: pythonError.message,
                    step: 'python-check'
                };
            }
            
            // Create virtual environment using system Python
            sendProgress('🔧 Creating virtual environment...');
            sendProgress('⏳ This may take a moment...');
            const createVenvCommand = `python -m venv "${venvDir}"`;
            const createResult = await executeTerminalCommandDirect(createVenvCommand, homeDir, sendProgress);
            
            if (!createResult.success) {
                sendProgress(`❌ Virtual environment creation failed: ${createResult.error}`, 'error');
                throw new Error(`Failed to create virtual environment: ${createResult.error}`);
            }
            
            sendProgress('✅ Virtual environment created successfully');
            
            // Verify Python executable exists
            const pythonPath = os.platform() === 'win32' 
                ? path.join(venvDir, 'Scripts', 'python.exe')
                : path.join(venvDir, 'bin', 'python');
                
            sendProgress(`🔍 Verifying Python executable at: ${pythonPath}`);
            if (!fs.existsSync(pythonPath)) {
                const errorMsg = `Python executable not found at: ${pythonPath}`;
                sendProgress(`❌ ${errorMsg}`, 'error');
                throw new Error(errorMsg);
            }
            sendProgress('✅ Python executable verified');
            
            // Install essential packages step by step with detailed logging
            sendProgress('📦 Starting package installation...');
            
            // Step 1: Upgrade pip
            sendProgress('⬆️ Upgrading pip...');
            const upgradeCommand = `"${pythonPath}" -m pip install --upgrade pip`;
            const upgradeResult = await executeTerminalCommandDirect(upgradeCommand, homeDir, sendProgress);
            
            if (upgradeResult.success) {
                sendProgress('✅ Pip upgraded successfully');
            } else {
                sendProgress('⚠️ Pip upgrade had issues, continuing anyway');
            }
            
            // Step 2: Install core packages one by one
            const packages = [
                { name: 'pillow', description: 'Image processing library' },
                { name: 'numpy', description: 'Mathematical computing library' },
                { name: 'matplotlib', description: 'Plotting library' },
                { name: 'manim', description: 'Mathematical animation engine' }
            ];
            
            let installedCount = 0;
            let failedPackages = [];
            
            for (let i = 0; i < packages.length; i++) {
                const pkg = packages[i];
                sendProgress(`📦 Installing ${pkg.name} (${i + 1}/${packages.length}) - ${pkg.description}...`);
                
                const installCommand = `"${pythonPath}" -m pip install ${pkg.name}`;
                const installResult = await executeTerminalCommandDirect(installCommand, homeDir, sendProgress);
                
                if (installResult.success) {
                    sendProgress(`✅ ${pkg.name} installed successfully`);
                    installedCount++;
                } else {
                    sendProgress(`❌ Failed to install ${pkg.name}: ${installResult.error}`, 'error');
                    failedPackages.push(pkg.name);
                }
                
                // Add small delay between installations
                await new Promise(resolve => setTimeout(resolve, 500));
            }
            
            // Final summary
            sendProgress('📊 Installation Summary:');
            sendProgress(`✅ Successfully installed: ${installedCount}/${packages.length} packages`);
            if (failedPackages.length > 0) {
                sendProgress(`❌ Failed packages: ${failedPackages.join(', ')}`);
            }
            
            // Test manim installation
            sendProgress('🧪 Testing manim installation...');
            const testCommand = `"${pythonPath}" -c "import manim; print('Manim version:', manim.__version__)"`;
            const testResult = await executeTerminalCommandDirect(testCommand, homeDir, sendProgress);
            
            if (testResult.success) {
                sendProgress('✅ Manim installation test passed');
                sendProgress(testResult.output);
            } else {
                sendProgress('⚠️ Manim test failed, but environment was created');
            }
            
            sendProgress('🎉 Virtual environment setup completed!');
            sendProgress('🚀 You can now start creating animations!');
            
            return { 
                success: true, 
                venvPath: venvDir,
                pythonPath: pythonPath,
                message: 'Virtual environment created successfully',
                installedPackages: installedCount,
                failedPackages: failedPackages,
                totalPackages: packages.length
            };
            
        } catch (error) {
            console.error('❌ Environment creation error:', error);
            sendProgress(`❌ Setup failed: ${error.message}`, 'error');
            return { 
                success: false, 
                error: error.message,
                step: 'environment-creation'
            };
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
            
            // Create virtual environment using system Python
            const createVenvCommand = `python -m venv "${venvDir}"`;
            const createResult = await executeTerminalCommandDirect(createVenvCommand, homeDir);
            
            if (!createResult.success) {
                throw new Error(`Failed to create virtual environment: ${createResult.error}`);
            }
            
            // Install manim using new environment Python
            const pythonPath = os.platform() === 'win32' 
                ? path.join(venvDir, 'Scripts', 'python.exe')
                : path.join(venvDir, 'bin', 'python');
            
            const installCommand = `"${pythonPath}" -m pip install manim[gui]`;
            const installResult = await executeTerminalCommandDirect(installCommand, homeDir);
            
            if (!installResult.success) {
                throw new Error(`Failed to install manim: ${installResult.error}`);
            }
            
            return { success: true };
            
        } catch (error) {
            console.error('Environment setup error:', error);
            return { success: false, error: error.message };
        }
    });

    // UPDATED: Python environment info with auto-creation
    ipcMain.handle('get-python-info', async () => {
        try {
            const pythonPath = path.join(os.homedir(), '.manim_studio', 'venvs', 'manim_studio_default', 'Scripts', 'python.exe');
            const venvPath = path.join(os.homedir(), '.manim_studio', 'venvs', 'manim_studio_default');
            
            const exists = await fs.promises.access(pythonPath).then(() => true).catch(() => false);
            const venvExists = await fs.promises.access(venvPath).then(() => true).catch(() => false);
            
            return { 
                success: true, 
                pythonPath, 
                venvPath,
                exists,
                venvExists,
                autoCreateAvailable: !exists // Can auto-create if it doesn't exist
            };
        } catch (error) {
            return { success: false, error: error.message };
        }
    });

    // Other utility handlers
    ipcMain.handle('get-app-paths', () => {
        return {
            home: os.homedir(),
            manimStudio: path.join(os.homedir(), '.manim_studio'),
            assets: path.join(os.homedir(), '.manim_studio', 'assets'),
            venv: path.join(os.homedir(), '.manim_studio', 'venvs')
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

    // Assets management
    ipcMain.handle('add-asset', async (event, options) => {
        try {
            const result = await dialog.showOpenDialog(mainWindow, {
                properties: ['openFile'],
                filters: options?.filters || [
                    { name: 'All Files', extensions: ['*'] }
                ]
            });
            
            if (result.canceled || !result.filePaths.length) {
                return { success: false, canceled: true };
            }
            
            const sourcePath = result.filePaths[0];
            const fileName = path.basename(sourcePath);
            const assetsDir = path.join(os.homedir(), '.manim_studio', 'assets');
            const destPath = path.join(assetsDir, fileName);
            
            // Create assets directory if it doesn't exist
            await fs.promises.mkdir(assetsDir, { recursive: true });
            
            // Copy file
            await fs.promises.copyFile(sourcePath, destPath);
            
            return { success: true, fileName, destPath };
        } catch (error) {
            return { success: false, error: error.message };
        }
    });

    ipcMain.handle('list-files', async (event, dirPath) => {
        try {
            const files = await fs.promises.readdir(dirPath);
            const result = await Promise.all(files.map(async (file) => {
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
            return { success: true, files: result };
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

    // Process management (kill process)
    ipcMain.handle('kill-process', async (event, pid) => {
        try {
            if (pid) {
                process.kill(pid);
                return { success: true };
            }
            return { success: false, error: 'No PID provided' };
        } catch (error) {
            return { success: false, error: error.message };
        }
    });

    console.log('✅ IPC handlers setup completed');
}

// ENHANCED: Smart terminal command execution that handles environment creation
async function executeTerminalCommandSmart(command, cwd = process.cwd()) {
    // Check if this is an environment creation command
    const isEnvCreation = command.includes('python -m venv') || command.includes('pip install');
    
    if (isEnvCreation) {
        // Use direct execution for environment creation (system Python)
        return executeTerminalCommandDirect(command, cwd);
    } else {
        // Use forced virtual environment for other commands
        return executeTerminalCommand(command, cwd);
    }
}

// ENHANCED: Direct terminal command execution with progress logging
async function executeTerminalCommandDirect(command, cwd = process.cwd(), progressCallback = null) {
    return new Promise((resolve) => {
        console.log(`🚀 Executing (Direct): ${command} in ${cwd}`);
        
        let output = '';
        let errorOutput = '';
        
        // Execute command directly without forcing virtual environment
        const process = spawn(command, [], {
            cwd: cwd,
            shell: true,
            stdio: ['pipe', 'pipe', 'pipe'],
            env: {
                ...require('process').env,
                // Don't force virtual environment for direct commands
            }
        });

        // Handle stdout
        process.stdout.on('data', (data) => {
            const text = data.toString();
            output += text;
            console.log('📤 stdout:', text.trim());
            
            // Send to progress callback if provided
            if (progressCallback && text.trim()) {
                progressCallback(`📤 ${text.trim()}`);
            }
            
            // Send real-time output to renderer
            if (mainWindow && !mainWindow.isDestroyed()) {
                mainWindow.webContents.send('terminal-output', {
                    type: 'stdout',
                    data: text
                });
            }
        });

        // Handle stderr
        process.stderr.on('data', (data) => {
            const text = data.toString();
            errorOutput += text;
            console.log('📤 stderr:', text.trim());
            
            // Send to progress callback if provided
            if (progressCallback && text.trim()) {
                progressCallback(`⚠️ ${text.trim()}`);
            }
            
            // Send real-time output to renderer
            if (mainWindow && !mainWindow.isDestroyed()) {
                mainWindow.webContents.send('terminal-output', {
                    type: 'stderr', 
                    data: text
                });
            }
        });

        // Handle process completion
        process.on('close', (code) => {
            console.log(`🏁 Process completed with code: ${code}`);
            
            if (progressCallback) {
                progressCallback(`🏁 Command completed with exit code: ${code}`);
            }
            
            const result = {
                success: code === 0,
                output: output.trim(),
                error: errorOutput.trim(),
                code: code,
                timestamp: new Date().toISOString(),
                command: command,
                workingDirectory: cwd,
                outputLength: output ? output.length : 0
            };
            
            resolve(result);
        });

        // Handle process errors
        process.on('error', (error) => {
            console.error('❌ Process error:', error);
            
            if (progressCallback) {
                progressCallback(`❌ Process error: ${error.message}`);
            }
            
            const result = {
                success: false,
                output: output,
                error: `Process error: ${error.message}`,
                code: -1,
                timestamp: new Date().toISOString(),
                command: command,
                workingDirectory: cwd,
                outputLength: output ? output.length : 0
            };
            
            resolve(result);
        });
        
        // Set timeout for long-running processes
        setTimeout(() => {
            if (!process.killed) {
                console.log('⏰ Process timeout, killing...');
                if (progressCallback) {
                    progressCallback('⏰ Command timed out after 5 minutes');
                }
                process.kill();
            }
        }, 300000); // 5 minutes timeout
    });
}

// EXISTING: Enhanced terminal command execution with proper Windows path handling (for normal commands)
async function executeTerminalCommand(command, cwd = process.cwd()) {
    return new Promise((resolve) => {
        console.log(`🚀 Executing (Forced VEnv): ${command} in ${cwd}`);
        
        let output = '';
        let errorOutput = '';
        
        // FORCE manim_studio_default environment for Manim operations
        const FORCED_VENV_PATH = path.join(os.homedir(), '.manim_studio', 'venvs', 'manim_studio_default');
        const FORCED_PYTHON_EXE = path.join(FORCED_VENV_PATH, 'Scripts', 'python.exe');
        
        console.log('🎯 FORCING virtual environment usage');
        console.log('📋 Original command:', command);
        console.log('📁 Working directory:', cwd);
        
        // ENFORCE: ONLY use our specific virtual environment Python for Manim commands
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
        
        // REPLACE any python/manim command with our specific virtual environment Python
        let modifiedCommand = command;

        if (command.includes('python') || command.match(/\bmanim\b/i)) {
            console.log('🔧 Modifying Python/Manim command to use virtual environment');

            // Replace any python references with venv python
            modifiedCommand = modifiedCommand.replace(/\bpython(\.exe)?\b/gi, `"${FORCED_PYTHON_EXE}"`);

            // Replace standalone manim commands (avoid "-m manim" already using python)
            if (!/-m\s+manim\b/i.test(command) && /\bmanim\b/i.test(command)) {
                modifiedCommand = modifiedCommand.replace(/(^|\s)manim\b/i, `$1"${FORCED_PYTHON_EXE}" -m manim`);
            }

            console.log('🎯 Modified command:', modifiedCommand);
        }
        
        // Execute with proper environment
        const process = spawn(modifiedCommand, [], {
            cwd: cwd,
            shell: true,
            stdio: ['pipe', 'pipe', 'pipe'],
            env: {
                ...require('process').env,
                PATH: path.join(FORCED_VENV_PATH, 'Scripts') + path.delimiter + require('process').env.PATH,
                VIRTUAL_ENV: FORCED_VENV_PATH,
                PYTHONPATH: FORCED_VENV_PATH
            }
        });

        // Handle stdout
        process.stdout.on('data', (data) => {
            const text = data.toString();
            output += text;
            console.log('📤 stdout:', text.trim());
            
            // Send real-time output to renderer
            if (mainWindow && !mainWindow.isDestroyed()) {
                mainWindow.webContents.send('terminal-output', {
                    type: 'stdout',
                    data: text
                });
            }
        });

        // Handle stderr
        process.stderr.on('data', (data) => {
            const text = data.toString();
            errorOutput += text;
            console.log('📤 stderr:', text.trim());
            
            // Send real-time output to renderer
            if (mainWindow && !mainWindow.isDestroyed()) {
                mainWindow.webContents.send('terminal-output', {
                    type: 'stderr', 
                    data: text
                });
            }
        });

        // Handle process completion
        process.on('close', (code) => {
            console.log(`🏁 Process completed with code: ${code}`);
            
            const result = {
                success: code === 0,
                output: output.trim(),
                error: errorOutput.trim(),
                code: code,
                timestamp: new Date().toISOString(),
                command: modifiedCommand,
                originalCommand: command,
                workingDirectory: cwd,
                outputLength: output ? output.length : 0
            };
            
            resolve(result);
        });

        // Handle process errors
        process.on('error', (error) => {
            console.error('❌ Process error:', error);
            
            const result = {
                success: false,
                output: output,
                error: `Process error: ${error.message}`,
                code: -1,
                timestamp: new Date().toISOString(),
                command: modifiedCommand,
                originalCommand: command,
                workingDirectory: cwd,
                outputLength: output ? output.length : 0
            };
            
            resolve(result);
        });
        
        // Set timeout for long-running processes
        setTimeout(() => {
            if (!process.killed) {
                console.log('⏰ Process timeout, killing...');
                process.kill();
            }
        }, 300000); // 5 minutes timeout
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