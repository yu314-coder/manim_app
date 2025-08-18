const { contextBridge, ipcRenderer } = require('electron');

// Expose secure APIs to renderer process via contextBridge
contextBridge.exposeInMainWorld('electronAPI', {
    // File operations
    async openFile(options = {}) {
        try {
            const result = await ipcRenderer.invoke('show-open-dialog', options);
            if (!result.canceled && result.filePaths.length > 0) {
                const filePath = result.filePaths[0];
                const loadResult = await ipcRenderer.invoke('load-file', filePath);
                if (loadResult.success) {
                    return { 
                        success: true, 
                        content: loadResult.content, 
                        filePath: filePath,
                        fileName: require('path').basename(filePath)
                    };
                } else {
                    return { success: false, error: loadResult.error };
                }
            }
            return { success: false, error: 'Open canceled' };
        } catch (error) {
            return { success: false, error: error.message };
        }
    },

    async saveFile(filePath, content) {
        try {
            const result = await ipcRenderer.invoke('save-file', filePath, content);
            return result;
        } catch (error) {
            return { success: false, error: error.message };
        }
    },

    async saveFileAs(content, options = {}) {
        try {
            const result = await ipcRenderer.invoke('show-save-dialog', options);
            if (!result.canceled) {
                const saveResult = await ipcRenderer.invoke('save-file', result.filePath, content);
                if (saveResult.success) {
                    return { 
                        success: true, 
                        filePath: result.filePath,
                        fileName: require('path').basename(result.filePath)
                    };
                } else {
                    return { success: false, error: saveResult.error };
                }
            }
            return { success: false, error: 'Save canceled' };
        } catch (error) {
            return { success: false, error: error.message };
        }
    },

    // Terminal operations
    async executeCommand(command, cwd) {
        try {
            const result = await ipcRenderer.invoke('execute-terminal-command', command, cwd);
            return result;
        } catch (error) {
            return { success: false, error: error.message };
        }
    },

    // Window management
    async openVenvManager() {
        try {
            await ipcRenderer.invoke('open-venv-manager');
            return { success: true };
        } catch (error) {
            return { success: false, error: error.message };
        }
    },

    async openAssetsManager() {
        try {
            await ipcRenderer.invoke('open-assets-manager');
            return { success: true };
        } catch (error) {
            return { success: false, error: error.message };
        }
    },

    // Workspace operations
    async readWorkspaceFiles(dirPath) {
        try {
            const result = await ipcRenderer.invoke('read-workspace-files', dirPath);
            return result;
        } catch (error) {
            return { success: false, error: error.message };
        }
    },

    // System paths
    async getAppPaths() {
        try {
            const paths = await ipcRenderer.invoke('get-app-paths');
            return { success: true, paths };
        } catch (error) {
            return { success: false, error: error.message };
        }
    },

    // Python environment info
    async getPythonInfo() {
        try {
            const result = await ipcRenderer.invoke('get-python-info');
            return result;
        } catch (error) {
            return { success: false, error: error.message };
        }
    },

    // Environment management
    async checkEnvironment() {
        try {
            const result = await ipcRenderer.invoke('check-environment');
            return result;
        } catch (error) {
            return { success: false, error: error.message };
        }
    },

    async setupEnvironment() {
        try {
            const result = await ipcRenderer.invoke('setup-environment');
            return result;
        } catch (error) {
            return { success: false, error: error.message };
        }
    },

    // Language server communication for Monaco IntelliSense
    async requestLanguageServer(request) {
        try {
            const result = await ipcRenderer.invoke('request-language-server', request);
            return result;
        } catch (error) {
            return { success: false, error: error.message };
        }
    },

    // IPC event listeners for real-time updates
    onProcessOutput(callback) {
        const listener = (event, data) => callback(data);
        ipcRenderer.on('process-output', listener);
        return () => ipcRenderer.removeListener('process-output', listener);
    },

    onProcessComplete(callback) {
        const listener = (event, data) => callback(data);
        ipcRenderer.on('process-complete', listener);
        return () => ipcRenderer.removeListener('process-complete', listener);
    },

    onProcessStarted(callback) {
        const listener = (event, data) => callback(data);
        ipcRenderer.on('process-started', listener);
        return () => ipcRenderer.removeListener('process-started', listener);
    },

    // Utility functions exposed securely
    utils: {
        basename: (filePath) => require('path').basename(filePath),
        dirname: (filePath) => require('path').dirname(filePath),
        extname: (filePath) => require('path').extname(filePath),
        join: (...paths) => require('path').join(...paths)
    }
});

// Expose a minimal console API for debugging (optional)
contextBridge.exposeInMainWorld('electronConsole', {
    log: (...args) => console.log('[Renderer]', ...args),
    error: (...args) => console.error('[Renderer]', ...args),
    warn: (...args) => console.warn('[Renderer]', ...args)
});

// Expose version info
contextBridge.exposeInMainWorld('electronInfo', {
    platform: process.platform,
    arch: process.arch,
    versions: {
        node: process.versions.node,
        electron: process.versions.electron,
        chrome: process.versions.chrome
    }
});