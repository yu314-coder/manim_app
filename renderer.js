// Fixed Renderer.js for Assets and VEnv Window Management + Terminal Override
const { ipcRenderer } = require('electron');
const fs = require('fs');
const path = require('path');
const os = require('os');

console.log('🔧 Renderer.js loaded for window management');

// FORCE manim_studio_default environment for ALL operations - NEVER use system Python
const FORCED_VENV_PATH = path.join(os.homedir(), '.manim_studio', 'venvs', 'manim_studio_default');
const FORCED_PYTHON_EXE = path.join(FORCED_VENV_PATH, 'Scripts', 'python.exe');

// Enhanced terminal command execution with FORCED virtual environment usage
if (typeof window !== 'undefined') {
    // Store original IPC invoke for fallback
    const originalInvoke = ipcRenderer.invoke;
    
    // FORCE: Override ALL terminal commands to use ONLY the verified virtual environment
    ipcRenderer.invoke = function(channel, ...args) {
        if (channel === 'execute-terminal-command') {
            console.log('🎯 Renderer: FORCING virtual environment usage');
            
            const [command, cwd] = args;
            console.log('📋 Original command:', command);
            console.log('📁 Working directory:', cwd);
            
            // ENFORCE: ONLY use our specific virtual environment Python - NO FALLBACKS
            if (!fs.existsSync(FORCED_PYTHON_EXE)) {
                console.error('❌ CRITICAL: Virtual environment not found at:', FORCED_PYTHON_EXE);
                return Promise.resolve({
                    success: false,
                    output: '',
                    error: `Virtual environment not found at: ${FORCED_PYTHON_EXE}. Please set up the environment first.`,
                    code: -1
                });
            }
            
            let modifiedCommand = command;
            
            // ENFORCE: Replace any python calls with our SPECIFIC python executable
            if (command.includes('python')) {
                // Replace ALL python variations with our forced path
                modifiedCommand = modifiedCommand.replace(/\bpython\s+/g, `"${FORCED_PYTHON_EXE}" `);
                modifiedCommand = modifiedCommand.replace(/\bpython$/g, `"${FORCED_PYTHON_EXE}"`);
                modifiedCommand = modifiedCommand.replace(/\bpython\.exe\s+/g, `"${FORCED_PYTHON_EXE}" `);
                modifiedCommand = modifiedCommand.replace(/\bpython\.exe$/g, `"${FORCED_PYTHON_EXE}"`);
                
                // Handle cases where python is at the beginning
                if (modifiedCommand.startsWith('python ')) {
                    modifiedCommand = modifiedCommand.replace(/^python /, `"${FORCED_PYTHON_EXE}" `);
                }
                if (modifiedCommand === 'python') {
                    modifiedCommand = `"${FORCED_PYTHON_EXE}"`;
                }
            }
            
            console.log('🔄 ENFORCED command:', modifiedCommand);
            console.log('✅ Using FORCED virtual environment:', FORCED_VENV_PATH);
            
            return originalInvoke.call(this, channel, modifiedCommand, cwd);
        }
        return originalInvoke.call(this, channel, ...args);
    };
    
    // Enhanced global function to execute terminal commands with FORCED environment
    window.executeTerminalCommand = async function(command, workingDir = null) {
        try {
            console.log('🚀 Executing terminal command with FORCED environment:', command);
            console.log('📁 Working directory:', workingDir);
            
            // ENFORCE: Check virtual environment before executing
            if (!fs.existsSync(FORCED_PYTHON_EXE)) {
                const warnMsg = `Virtual environment not found at: ${FORCED_PYTHON_EXE}. Attempting automatic setup...`;
                console.warn('⚠️', warnMsg);
                if (window.addTerminalLine) {
                    window.addTerminalLine(`⚠️ ${warnMsg}`, 'warning');
                }
                if (window.electronAPI && window.electronAPI.autoCreateEnvironment) {
                    const setup = await window.electronAPI.autoCreateEnvironment();
                    if (!setup || !setup.success) {
                        const err = (setup && setup.error) ? setup.error : 'Automatic environment setup failed';
                        if (window.addTerminalLine) {
                            window.addTerminalLine(`❌ ${err}`, 'error');
                        }
                        return {
                            success: false,
                            output: '',
                            error: err,
                            code: -1,
                            timestamp: new Date().toISOString()
                        };
                    }
                    if (window.addTerminalLine) {
                        window.addTerminalLine('✅ Virtual environment installed', 'success');
                    }
                } else {
                    const err = 'Environment setup API not available';
                    if (window.addTerminalLine) {
                        window.addTerminalLine(`❌ ${err}`, 'error');
                    }
                    return {
                        success: false,
                        output: '',
                        error: err,
                        code: -1,
                        timestamp: new Date().toISOString()
                    };
                }
            }
            if (!fs.existsSync(FORCED_PYTHON_EXE)) {
                const err = `Virtual environment setup failed to create: ${FORCED_PYTHON_EXE}`;
                if (window.addTerminalLine) {
                    window.addTerminalLine(`❌ ${err}`, 'error');
                }
                return {
                    success: false,
                    output: '',
                    error: err,
                    code: -1,
                    timestamp: new Date().toISOString()
                };
            }
            
            // Show command start in UI
            if (window.addTerminalLine) {
                window.addTerminalLine(`🔧 Executing: ${command}`, 'info');
                window.addTerminalLine(`✅ Using FORCED environment: ${FORCED_VENV_PATH}`, 'success');
            }
            
            const result = await ipcRenderer.invoke('execute-terminal-command', command, workingDir);
            
            console.log('✅ Command execution result:', result);
            
            // Show completion status in UI
            if (window.addTerminalLine) {
                if (result.success) {
                    window.addTerminalLine(`✅ Command completed successfully (exit code: ${result.code})`, 'success');
                } else {
                    window.addTerminalLine(`❌ Command failed (exit code: ${result.code})`, 'error');
                    if (result.error) {
                        window.addTerminalLine(`Error details: ${result.error}`, 'error');
                    }
                }
            }
            
            return result;
        } catch (error) {
            console.error('❌ Terminal command error:', error);
            
            // Show error in UI
            if (window.addTerminalLine) {
                window.addTerminalLine(`❌ Command execution error: ${error.message}`, 'error');
            }
            
            return {
                success: false,
                output: '',
                error: error.message,
                code: -1,
                timestamp: new Date().toISOString()
            };
        }
    };
}

// Global functions for window management
window.openAssetsWindow = function() {
    console.log('🎨 Opening Assets Manager');
    ipcRenderer.invoke('open-assets-manager');
};

window.openVenvWindow = function() {
    console.log('🐍 Opening VEnv Manager');
    ipcRenderer.invoke('open-venv-manager');
};

// Force environment display override
function forceUpdateEnvironmentDisplay() {
    const displays = document.querySelectorAll('[id*="env"], [class*="env"], [id*="venv"], [class*="venv"]');
    displays.forEach(element => {
        if (element.textContent && element.textContent.includes('venv')) {
            element.textContent = element.textContent.replace(/\([^)]*\)/, '(manim_studio_default)');
            if (fs.existsSync(FORCED_PYTHON_EXE)) {
                element.style.color = '#4ec9b0';
            } else {
                element.style.color = '#f44747';
            }
        }
    });
}

// Override terminal prompt display
function forceTerminalPromptUpdate() {
    const prompts = document.querySelectorAll('.terminal-prompt, [class*="prompt"]');
    prompts.forEach(prompt => {
        if (prompt.textContent && prompt.textContent.includes('>')) {
            const currentPath = prompt.textContent.split('>')[0];
            const workingDir = currentPath.replace(/\([^)]*\)/, '').trim();
            prompt.textContent = `(manim_studio_default) ${workingDir}>`;
        }
    });
}

// Force environment status for header
function updateHeaderEnvironmentStatus() {
    let envDisplay = document.getElementById('env-display');
    if (envDisplay) {
        if (fs.existsSync(FORCED_PYTHON_EXE)) {
            envDisplay.innerHTML = '🟢 manim_studio_default';
            envDisplay.style.color = '#4ec9b0';
        } else {
            envDisplay.innerHTML = '🔴 manim_studio_default';
            envDisplay.style.color = '#f44747';
        }
    }
}

// For assets.html window
if (window.location.pathname.includes('assets.html')) {
    console.log('🎨 Assets window renderer loaded');
    
    // Assets window notification system
    window.showNotification = function(message, type = 'info') {
        const notification = document.createElement('div');
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: ${type === 'error' ? '#c5282f' : type === 'success' ? '#16825d' : '#0e639c'};
            color: white;
            padding: 12px 20px;
            border-radius: 6px;
            z-index: 1000;
            font-size: 13px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            max-width: 400px;
        `;
        notification.textContent = message;
        document.body.appendChild(notification);
        
        setTimeout(() => {
            if (document.body.contains(notification)) {
                document.body.removeChild(notification);
            }
        }, 3000);
    };
}

// For venv.html window
if (window.location.pathname.includes('venv.html')) {
    console.log('🐍 VEnv window renderer loaded');
    
    let packages = [];
    let isLoading = false;
    
    document.addEventListener('DOMContentLoaded', () => {
        loadVenvWindow();
        setupVenvEventListeners();
        
        // Force display to show manim_studio_default
        setInterval(forceUpdateEnvironmentDisplay, 1000);
    });
    
    function loadVenvWindow() {
        try {
            loadPackages();
            updateVenvStatus();
        } catch (error) {
            console.error('Error loading venv window:', error);
            showVenvError('Failed to load virtual environment data');
        }
    }
    
    function setupVenvEventListeners() {
        // Search functionality
        const searchInput = document.getElementById('search-input');
        if (searchInput) {
            searchInput.addEventListener('input', filterPackages);
        }
        
        // Install package on Enter
        const installInput = document.getElementById('install-input');
        if (installInput) {
            installInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    installPackage();
                }
            });
        }
    }
    
    function showVenvError(message) {
        console.error('VEnv Error:', message);
        if (window.showNotification) {
            window.showNotification(message, 'error');
        }
    }
    
    // VEnv window notification system
    window.showNotification = function(message, type = 'info') {
        const notification = document.createElement('div');
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: ${type === 'error' ? '#c5282f' : type === 'success' ? '#16825d' : '#0e639c'};
            color: white;
            padding: 12px 20px;
            border-radius: 6px;
            z-index: 1000;
            font-size: 13px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            max-width: 400px;
        `;
        notification.textContent = message;
        document.body.appendChild(notification);
        
        setTimeout(() => {
            if (document.body.contains(notification)) {
                document.body.removeChild(notification);
            }
        }, 3000);
    };
}

// For main index.html window - force environment display updates
if (window.location.pathname.includes('index.html') || window.location.pathname === '/') {
    console.log('🏠 Main window renderer - forcing environment display');
    
    document.addEventListener('DOMContentLoaded', () => {
        // Continuously force the environment display to show manim_studio_default
        setInterval(() => {
            forceUpdateEnvironmentDisplay();
            forceTerminalPromptUpdate();
            updateHeaderEnvironmentStatus();
        }, 500);
        
        // Note: Terminal listeners are now handled in index.html to prevent conflicts
        console.log('✅ Main window renderer environment overrides active');
    });
    
        // Listen for real-time terminal output from main process with better handling
        ipcRenderer.on('terminal-output', (event, data) => {
            console.log('📤 Real-time terminal output received:', data);
            
            if (data.data && data.data.trim()) {
                // Clean up the output and add it to terminal
                const cleanedOutput = data.data.trim();
                const outputType = data.type === 'stderr' ? 'error' : 'info';
                
                // Add to terminal if function exists
                if (window.addTerminalLine) {
                    window.addTerminalLine(cleanedOutput, outputType);
                } else {
                    // Fallback: try to add directly to terminal output
                    const terminalOutput = document.getElementById('terminal-output');
                    if (terminalOutput) {
                        const line = document.createElement('div');
                        line.className = `terminal-line ${outputType}`;
                        line.textContent = `[${new Date().toLocaleTimeString()}] ${cleanedOutput}`;
                        terminalOutput.appendChild(line);
                        terminalOutput.scrollTop = terminalOutput.scrollHeight;
                    }
                }
            }
        });
        
        // Listen for process completion with enhanced feedback
        ipcRenderer.on('process-complete', (event, result) => {
            console.log('🏁 Process completed with enhanced result:', result);
            
            if (window.addTerminalLine) {
                if (result.success) {
                    window.addTerminalLine(`✅ Process completed successfully (exit code: ${result.code})`, 'success');
                } else {
                    window.addTerminalLine(`❌ Process failed (exit code: ${result.code})`, 'error');
                    if (result.error) {
                        // Split error into lines and add each one
                        const errorLines = result.error.split('\n').filter(line => line.trim());
                        errorLines.forEach(line => {
                            window.addTerminalLine(line.trim(), 'error');
                        });
                    }
                }
            }
            
            // Update UI buttons and status based on completion
            updateUIAfterProcessComplete(result);
        });
        
        console.log('✅ Enhanced terminal listeners setup completed');
    }
    
    function updateUIAfterProcessComplete(result) {
        // Reset preview button
        const previewBtn = document.getElementById('preview-btn') || 
                          document.querySelector('[onclick*="quickPreview"]') ||
                          document.querySelector('button[onclick*="Preview"]');
        if (previewBtn) {
            previewBtn.textContent = previewBtn.textContent.includes('Preview') ? 
                                   (previewBtn.textContent.includes('⚡') ? '⚡ Preview' : '🎥 Preview') : 
                                   previewBtn.textContent.replace(/⏳.*/, '⚡ Preview');
            previewBtn.disabled = false;
        }
        
        // Reset render button
        const renderBtn = document.getElementById('render-btn') || 
                         document.querySelector('[onclick*="renderAnimation"]') ||
                         document.querySelector('button[onclick*="Render"]');
        if (renderBtn) {
            renderBtn.textContent = renderBtn.textContent.includes('Render') ? 
                                  (renderBtn.textContent.includes('🎬') ? '🎬 Render' : '🚀 Render') : 
                                  renderBtn.textContent.replace(/⏳.*/, '🎬 Render');
            renderBtn.disabled = false;
        }
        
        // Update status if function exists
        if (window.showStatus) {
            if (result.success) {
                window.showStatus('✅ Operation completed successfully', 'success');
            } else {
                window.showStatus(`❌ Operation failed (Code: ${result.code})`, 'error');
            }
        }
        
        // Reset global process running flag if it exists
        if (typeof window.isProcessRunning !== 'undefined') {
            window.isProcessRunning = false;
        }
    }
}

// General utility functions
function formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

// Enhanced file operations with better error handling
window.saveFileToSystem = async function(content, defaultPath = 'animation.py') {
    try {
        const { dialog } = require('@electron/remote');
        const result = await dialog.showSaveDialog({
            defaultPath: defaultPath,
            filters: [
                { name: 'Python Files', extensions: ['py'] },
                { name: 'All Files', extensions: ['*'] }
            ]
        });
        
        if (!result.canceled) {
            const saveResult = await ipcRenderer.invoke('save-file', result.filePath, content);
            if (saveResult.success) {
                console.log('✅ File saved successfully:', result.filePath);
                if (window.addTerminalLine) {
                    window.addTerminalLine(`💾 File saved: ${path.basename(result.filePath)}`, 'success');
                }
                return { success: true, filePath: result.filePath };
            } else {
                console.error('❌ Save failed:', saveResult.error);
                if (window.addTerminalLine) {
                    window.addTerminalLine(`❌ Save failed: ${saveResult.error}`, 'error');
                }
                return { success: false, error: saveResult.error };
            }
        }
        return { success: false, error: 'Save canceled by user' };
    } catch (error) {
        console.error('❌ Save file error:', error);
        if (window.addTerminalLine) {
            window.addTerminalLine(`❌ Save error: ${error.message}`, 'error');
        }
        return { success: false, error: error.message };
    }
};

window.loadFileFromSystem = async function() {
    try {
        const { dialog } = require('@electron/remote');
        const result = await dialog.showOpenDialog({
            filters: [
                { name: 'Python Files', extensions: ['py'] },
                { name: 'All Files', extensions: ['*'] }
            ],
            properties: ['openFile']
        });
        
        if (!result.canceled && result.filePaths.length > 0) {
            const filePath = result.filePaths[0];
            const loadResult = await ipcRenderer.invoke('load-file', filePath);
            if (loadResult.success) {
                console.log('✅ File loaded successfully:', filePath);
                if (window.addTerminalLine) {
                    window.addTerminalLine(`📂 File loaded: ${path.basename(filePath)}`, 'success');
                }
                return { success: true, content: loadResult.content, filePath: filePath };
            } else {
                console.error('❌ Load failed:', loadResult.error);
                if (window.addTerminalLine) {
                    window.addTerminalLine(`❌ Load failed: ${loadResult.error}`, 'error');
                }
                return { success: false, error: loadResult.error };
            }
        }
        return { success: false, error: 'Load canceled by user' };
    } catch (error) {
        console.error('❌ Load file error:', error);
        if (window.addTerminalLine) {
            window.addTerminalLine(`❌ Load error: ${error.message}`, 'error');
        }
        return { success: false, error: error.message };
    }
};

// Enhanced app paths utility
window.getAppPaths = async function() {
    try {
        const paths = await ipcRenderer.invoke('get-app-paths');
        console.log('📁 App paths retrieved:', paths);
        return paths;
    } catch (error) {
        console.error('❌ Error getting app paths:', error);
        return {
            home: os.homedir(),
            temp: os.tmpdir(),
            cwd: process.cwd(),
            manimStudio: path.join(os.homedir(), '.manim_studio'),
            assets: path.join(os.homedir(), '.manim_studio', 'assets'),
            venvs: path.join(os.homedir(), '.manim_studio', 'venvs')
        };
    }
};

// Enhanced directory creation utility
window.ensureDirectory = function(dirPath) {
    try {
        if (!fs.existsSync(dirPath)) {
            fs.mkdirSync(dirPath, { recursive: true });
            console.log('📁 Created directory:', dirPath);
            if (window.addTerminalLine) {
                window.addTerminalLine(`📁 Created directory: ${dirPath}`, 'info');
            }
        }
        return true;
    } catch (error) {
        console.error('❌ Error creating directory:', error);
        if (window.addTerminalLine) {
            window.addTerminalLine(`❌ Error creating directory: ${error.message}`, 'error');
        }
        return false;
    }
};

// Event listeners for keyboard shortcuts
document.addEventListener('keydown', (e) => {
    if (e.ctrlKey) {
        switch (e.key) {
            case 'f':
                e.preventDefault();
                const searchInput = document.getElementById('search-input');
                if (searchInput) searchInput.focus();
                break;
            case 'r':
                e.preventDefault();
                if (window.location.pathname.includes('venv.html')) {
                    if (window.refreshPackages) window.refreshPackages();
                } else if (window.location.pathname.includes('assets.html')) {
                    if (window.refreshAssets) window.refreshAssets();
                }
                break;
            case 'i':
                e.preventDefault();
                if (window.location.pathname.includes('venv.html')) {
                    const installInput = document.getElementById('install-input');
                    if (installInput) installInput.focus();
                } else if (window.location.pathname.includes('assets.html')) {
                    if (window.importAssets) window.importAssets();
                }
                break;
        }
    }
    
    // Enter key in install input
    if (e.key === 'Enter' && e.target.id === 'install-input') {
        if (window.installPackage) window.installPackage();
    }
});

console.log('✅ Renderer.js fully loaded with enhanced terminal command handling');