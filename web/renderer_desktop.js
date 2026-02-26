/**
 * Manim Studio - Desktop Renderer (PyWebView)
 * Native desktop app using PyWebView API instead of Electron IPC
 */

// App state
let currentFile = null;
let editor = null;
let isAppClosing = false; // Flag to prevent API calls during shutdown

const job = {
    running: false,
    type: null
};

// Terminal history
const terminalHistory = {
    commands: [],
    index: -1,
    maxSize: 50
};

// Auto-save state
let autosaveTimer = null;
let lastSavedCode = '';
let hasUnsavedChanges = false;
const AUTOSAVE_INTERVAL = 30000; // 30 seconds

// Preview blob URL tracking to prevent premature revocation
let currentPreviewBlobUrl = null;

// Render history tracking — records metadata when a render/preview starts
let _renderMeta = { startTime: 0, mode: '', quality: '', fps: 0, sceneName: '', format: '' };
let currentPreviewPath = null; // Track current preview path to avoid unnecessary reloads

// Initialize Monaco Editor using AMD require
function initializeEditor() {
    console.log('Initializing Monaco Editor...');

    // Check if AMD require is available
    if (typeof require === 'undefined') {
        console.error('AMD require is not available!');
        return;
    }

    // Use AMD require to load Monaco Editor
    require(['vs/editor/editor.main'], function() {
        console.log('Monaco Editor module loaded');
        console.log('monaco object:', typeof monaco);

        // Register Python + Manim completions & hover docs (zero-lag, client-side only)
        if (typeof window.registerManimCompletions === 'function') {
            window.registerManimCompletions(monaco);
        }

        const container = document.getElementById('monacoEditor');
        if (!container) {
            console.error('Monaco editor container not found!');
            return;
        }

        // Ensure container has size
        console.log('Container dimensions:', container.offsetWidth, 'x', container.offsetHeight);

        if (container.offsetWidth === 0 || container.offsetHeight === 0) {
            console.error('Container has zero size! Editor cannot render.');
            return;
        }

        // Default code template
        const defaultCode = `from manim import *

class MyScene(Scene):
    def construct(self):
        # Your animation code here
        text = Text("Hello, Manim!")
        self.play(Write(text))
        self.wait()
`;

        // Create Monaco Editor instance
        editor = monaco.editor.create(container, {
            value: defaultCode,
            language: 'python',
            theme: 'vs-dark',
            fontSize: 14,
            automaticLayout: true,
            readOnly: false,
            minimap: { enabled: true },
            scrollBeyondLastLine: false,
            lineNumbers: 'on',
            roundedSelection: false,
            scrollbar: {
                useShadows: false,
                verticalScrollbarSize: 10,
                horizontalScrollbarSize: 10
            },
            wordWrap: 'on',
            tabSize: 4,
            insertSpaces: true,
            renderWhitespace: 'selection',
            cursorBlinking: 'smooth',
            smoothScrolling: true,
            mouseWheelZoom: true,
            formatOnPaste: true,
            formatOnType: true,
            autoClosingBrackets: 'always',
            autoClosingQuotes: 'always',
            suggestOnTriggerCharacters: true,
            acceptSuggestionOnEnter: 'on',
            quickSuggestions: {
                other: true,
                comments: false,
                strings: false
            },
            // Text selection features
            selectionHighlight: true,               // Highlight text similar to selection
            occurrencesHighlight: true,             // Highlight occurrences of selected text
            selectOnLineNumbers: true,              // Click line numbers to select line
            dragAndDrop: true,                      // Enable drag and drop of text selections
            multiCursorModifier: 'alt',             // Use Alt key for multiple cursors
            renderLineHighlight: 'all',             // Highlight current line and selection
            selectionClipboard: true,               // Copy selection to clipboard on select
            // Enhanced IntelliSense
            suggest: {
                showWords: true,
                showMethods: true,
                showFunctions: true,
                showConstructors: true,
                showFields: true,
                showVariables: true,
                showClasses: true,
                showStructs: true,
                showInterfaces: true,
                showModules: true,
                showProperties: true,
                showEvents: true,
                showOperators: true,
                showUnits: true,
                showValues: true,
                showConstants: true,
                showEnums: true,
                showEnumMembers: true,
                showKeywords: true,
                showSnippets: true
            }
        });

        // Event listeners
        let errorCheckTimeout = null;
        editor.onDidChangeModelContent(() => {
            updateLineCount();
            // Mark as having unsaved changes
            const currentCode = getEditorValue();
            if (currentCode !== lastSavedCode) {
                updateSaveStatus('unsaved');
            }

            // Debounced error checking (wait 500ms after typing stops)
            if (errorCheckTimeout) {
                clearTimeout(errorCheckTimeout);
            }
            errorCheckTimeout = setTimeout(() => {
                checkCodeErrors();
            }, 500);

        });

        editor.onDidChangeCursorPosition(() => {
            updateCursor();
            updateSelection();
        });

        editor.onDidChangeCursorSelection(() => {
            updateSelection();
        });

        // Add keyboard shortcuts for selection
        editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyA, () => {
            // Select all text
            const model = editor.getModel();
            const lastLine = model.getLineCount();
            const lastColumn = model.getLineMaxColumn(lastLine);
            editor.setSelection(new monaco.Selection(1, 1, lastLine, lastColumn));
        });

        // Focus the editor
        setTimeout(() => {
            editor.focus();
        }, 100);

        updateLineCount();
        updateCursor();
        updateSelection();

        // Start LSP in background — zero lag, editor already works without it
        if (typeof window.initializeLsp === 'function') {
            window.initializeLsp(monaco, editor);
        }

        console.log('Monaco Editor initialized successfully');
        console.log('Editor is editable:', !editor.getOption(monaco.editor.EditorOption.readOnly));
        console.log('Editor value:', editor.getValue().substring(0, 50) + '...');
    }, function(err) {
        console.error('Failed to load Monaco Editor module:', err);
    });
}

// Helper functions
function delay(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

// Force refresh the UI by clearing and repopulating the DOM
async function forceRefreshAssetsUI() {
    console.log('[FORCE-REFRESH] Starting forced UI refresh');

    const container = document.getElementById('assetsGrid');
    if (!container) {
        console.error('[FORCE-REFRESH] assetsGrid container not found!');
        return;
    }

    // Step 1: Clear the DOM completely
    console.log('[FORCE-REFRESH] Clearing container');
    container.innerHTML = '';

    // Step 2: Force a reflow to ensure browser processes the clear
    void container.offsetHeight;

    // Step 3: Wait for browser to paint
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));

    // Step 4: Fetch fresh data and repopulate
    console.log('[FORCE-REFRESH] Fetching fresh assets');
    await refreshAssets(false);

    // Step 5: Force another paint
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));

    console.log('[FORCE-REFRESH] UI refresh complete');
}

// Retry refresh until files appear or max attempts reached
async function refreshAssetsWithRetry(initialDelayMs = 800, retryDelayMs = 500, maxAttempts = 2) {
    console.log(`[REFRESH-RETRY] Starting retry mechanism (initial delay: ${initialDelayMs}ms, retry delay: ${retryDelayMs}ms, ${maxAttempts} attempts)`);

    // Initial delay to let files be written to disk
    console.log(`[REFRESH-RETRY] Waiting ${initialDelayMs}ms for files to be written...`);
    await delay(initialDelayMs);

    for (let i = 0; i < maxAttempts; i++) {
        console.log(`[REFRESH-RETRY] Attempt ${i + 1}/${maxAttempts}`);

        // Force complete UI refresh
        await forceRefreshAssetsUI();

        console.log(`[REFRESH-RETRY] Refreshed, current count: ${allAssets.length}`);

        // Wait before next attempt (if not the last one)
        if (i < maxAttempts - 1) {
            await delay(retryDelayMs);
        }
    }

    console.log(`[REFRESH-RETRY] Completed ${maxAttempts} refresh attempts`);
    return true;
}

function getEditorValue() {
    return editor ? editor.getValue() : '';
}

function setEditorValue(value) {
    if (editor) {
        editor.setValue(value);
        updateLineCount();
        updateCursor();
    }
}

function focusEditor() {
    if (editor) editor.focus();
}

function updateLineCount() {
    const lineCount = editor ? editor.getModel().getLineCount() : 0;
    const elem = document.getElementById('linesCount');
    if (elem) elem.textContent = `Lines: ${lineCount}`;
}

function updateCursor() {
    if (!editor) return;
    const position = editor.getPosition();
    const elem = document.getElementById('cursorPosition');
    if (elem) elem.textContent = `Ln ${position.lineNumber}, Col ${position.column}`;
}

function updateSelection() {
    if (!editor) return;

    const selection = editor.getSelection();
    const selectedText = editor.getModel().getValueInRange(selection);

    // Update status bar with selection info
    const elem = document.getElementById('selectionInfo');
    if (elem) {
        if (selectedText && selectedText.length > 0) {
            const lines = selectedText.split('\n').length;
            const chars = selectedText.length;
            elem.textContent = ` (${chars} chars, ${lines} lines selected)`;
            elem.style.display = 'inline';
        } else {
            elem.textContent = '';
            elem.style.display = 'none';
        }
    }
}

function getSelectedText() {
    if (!editor) return '';
    const selection = editor.getSelection();
    return editor.getModel().getValueInRange(selection);
}

function updateCurrentFile(filename) {
    const elem = document.getElementById('currentFile');
    if (elem) {
        elem.textContent = filename || 'Untitled';
        elem.title = currentFile || '';
    }
}

function toast(message, type = 'info') {
    console.log(`[${type.toUpperCase()}] ${message}`);

    // Get or create toast container
    let container = document.getElementById('toastContainer');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toastContainer';
        document.body.appendChild(container);
    }

    // Icon mapping
    const icons = {
        success: '✓',
        error: '✕',
        warning: '⚠',
        info: 'ℹ'
    };

    // Create toast element
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;

    // Create icon
    const icon = document.createElement('div');
    icon.className = 'toast-icon';
    icon.textContent = icons[type] || icons.info;

    // Create message
    const messageEl = document.createElement('div');
    messageEl.className = 'toast-message';
    messageEl.textContent = message;

    // Create progress bar
    const progress = document.createElement('div');
    progress.className = 'toast-progress';

    // Assemble toast
    toast.appendChild(icon);
    toast.appendChild(messageEl);
    toast.appendChild(progress);

    // Add to container
    container.appendChild(toast);

    // Trigger show animation
    setTimeout(() => {
        toast.classList.add('show');
    }, 10);

    // Auto-dismiss after 3 seconds
    const dismissTimeout = setTimeout(() => {
        toast.classList.add('hiding');
        setTimeout(() => {
            toast.remove();
        }, 300);
    }, 3000);

    // Pause on hover
    toast.addEventListener('mouseenter', () => {
        clearTimeout(dismissTimeout);
        progress.style.animationPlayState = 'paused';
    });

    toast.addEventListener('mouseleave', () => {
        progress.style.animationPlayState = 'running';
        setTimeout(() => {
            toast.classList.add('hiding');
            setTimeout(() => {
                toast.remove();
            }, 300);
        }, 1000);
    });
}

// Toast with action button
function showToastWithAction(message, type = 'info', buttonText, buttonAction) {
    console.log('------------------------------------------------------------');
    console.log('[TOAST] showToastWithAction called');
    console.log(`[TOAST] Message: ${message}`);
    console.log(`[TOAST] Type: ${type}`);
    console.log(`[TOAST] Button text: ${buttonText}`);
    console.log('------------------------------------------------------------');

    // Get or create toast container
    let container = document.getElementById('toastContainer');
    if (!container) {
        console.log('[TOAST] Creating toast container...');
        container = document.createElement('div');
        container.id = 'toastContainer';
        document.body.appendChild(container);
        console.log('[TOAST] Toast container created');
    } else {
        console.log('[TOAST] Using existing toast container');
    }

    // Icon mapping
    const icons = {
        success: '✓',
        error: '✕',
        warning: '⚠',
        info: 'ℹ'
    };

    // Create toast element
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.style.minWidth = '300px';

    // Create icon
    const icon = document.createElement('div');
    icon.className = 'toast-icon';
    icon.textContent = icons[type] || icons.info;

    // Create message
    const messageEl = document.createElement('div');
    messageEl.className = 'toast-message';
    messageEl.textContent = message;

    // Create action button
    const actionBtn = document.createElement('button');
    actionBtn.textContent = buttonText;
    actionBtn.style.cssText = `
        background: rgba(255, 255, 255, 0.2);
        border: 1px solid rgba(255, 255, 255, 0.3);
        color: white;
        padding: 6px 12px;
        border-radius: 4px;
        cursor: pointer;
        font-size: 12px;
        font-weight: 600;
        margin-left: 8px;
        transition: all 0.2s;
    `;
    actionBtn.onmouseenter = () => {
        actionBtn.style.background = 'rgba(255, 255, 255, 0.3)';
    };
    actionBtn.onmouseleave = () => {
        actionBtn.style.background = 'rgba(255, 255, 255, 0.2)';
    };
    actionBtn.onclick = async () => {
        console.log('============================================================');
        console.log('[TOAST] Action button clicked!');
        console.log('============================================================');
        try {
            // Disable button and show loading state
            console.log('[TOAST] Disabling button and showing loading state...');
            actionBtn.disabled = true;
            actionBtn.textContent = 'Opening...';
            actionBtn.style.cursor = 'wait';

            // Execute the action and wait for it to complete
            console.log('[TOAST] Executing button action...');
            await buttonAction();
            console.log('[TOAST] Button action completed successfully');

            // Action succeeded - remove toast
            console.log('[TOAST] Removing toast...');
            toast.remove();
            console.log('[TOAST] Toast removed');
        } catch (err) {
            // Action failed - show error
            console.error('[TOAST] ✗ Action failed:', err);
            actionBtn.textContent = 'Failed';
            actionBtn.style.background = 'rgba(239, 68, 68, 0.3)';

            // Auto-remove after showing error briefly
            setTimeout(() => {
                toast.remove();
            }, 2000);
        }
    };
    console.log('[TOAST] Button onclick handler attached');

    // Create progress bar
    const progress = document.createElement('div');
    progress.className = 'toast-progress';

    // Assemble toast
    toast.appendChild(icon);
    toast.appendChild(messageEl);
    toast.appendChild(actionBtn);
    toast.appendChild(progress);

    // Add to container
    container.appendChild(toast);

    // Trigger show animation
    setTimeout(() => {
        toast.classList.add('show');
    }, 10);

    // Auto-dismiss after 5 seconds (longer for action toasts)
    const dismissTimeout = setTimeout(() => {
        toast.classList.add('hiding');
        setTimeout(() => {
            toast.remove();
        }, 300);
    }, 5000);

    // Pause on hover
    toast.addEventListener('mouseenter', () => {
        clearTimeout(dismissTimeout);
        progress.style.animationPlayState = 'paused';
    });

    toast.addEventListener('mouseleave', () => {
        progress.style.animationPlayState = 'running';
        setTimeout(() => {
            toast.classList.add('hiding');
            setTimeout(() => {
                toast.remove();
            }, 300);
        }, 1500);
    });

    console.log('[TOAST] ✓ Toast with action button created successfully');
    console.log('[TOAST] Toast will auto-dismiss in 5 seconds');
    console.log('------------------------------------------------------------');
}

// Console functions (for xterm.js terminal)
function appendConsole(text, type = 'info') {
    // Write to xterm.js terminal if available
    if (term) {
        // Add color based on type
        let color = '';
        if (type === 'error') {
            color = '\x1b[31m'; // Red
        } else if (type === 'success') {
            color = '\x1b[32m'; // Green
        } else if (type === 'warning') {
            color = '\x1b[33m'; // Yellow
        }
        const reset = color ? '\x1b[0m' : '';
        term.write(color + text + reset + '\r\n');
    } else {
        // Fallback to console.log
        console.log(`[CONSOLE ${type.toUpperCase()}]`, text);
    }
}

function clearConsole() {
    if (term) {
        term.clear();
    } else {
        console.log('[CONSOLE] Clear requested but terminal not available');
    }
}

function setTerminalStatus(text, type = 'info') {
    const status = document.getElementById('terminalStatus');
    if (status) {
        status.textContent = text;
        status.className = `terminal-status status-${type}`;
    }
}

function focusInput() {
    // Focus xterm.js terminal if available
    if (term) {
        term.focus();
    }
}

// File operations
async function newFile() {
    try {
        const res = await pywebview.api.new_file();
        if (res.status === 'success') {
            editor.setValue(res.code);
            currentFile = null;
            updateCurrentFile('Untitled');
            lastSavedCode = res.code;
            hasUnsavedChanges = false;
            updateSaveStatus('saved');
            toast('New file created', 'success');
        }
    } catch (err) {
        toast(`Error: ${err.message}`, 'error');
    }
}

async function openFile() {
    try {
        const res = await pywebview.api.open_file_dialog();
        if (res.status === 'success') {
            editor.setValue(res.code);
            currentFile = res.path;
            updateCurrentFile(res.filename);
            lastSavedCode = res.code;
            hasUnsavedChanges = false;
            updateSaveStatus('saved');
            toast(`Opened ${res.filename}`, 'success');
        }
    } catch (err) {
        toast(`Open failed: ${err.message}`, 'error');
    }
}

async function saveFile() {
    try {
        const code = getEditorValue();
        const res = await pywebview.api.save_file(code, currentFile);

        if (res.status === 'success') {
            currentFile = res.path;
            updateCurrentFile(res.filename);
            toast('File saved', 'success');
            lastSavedCode = code;
            hasUnsavedChanges = false;
            updateSaveStatus('saved');
        } else if (res.status === 'cancelled') {
            toast('Save cancelled', 'info');
        } else {
            toast(`Save failed: ${res.message}`, 'error');
        }
    } catch (err) {
        toast(`Save failed: ${err.message}`, 'error');
    }
}

async function saveFileAs() {
    try {
        const code = getEditorValue();
        const res = await pywebview.api.save_file_dialog(code);

        if (res.status === 'success') {
            currentFile = res.path;
            updateCurrentFile(res.filename);
            toast('File saved', 'success');
            lastSavedCode = code;
            hasUnsavedChanges = false;
            updateSaveStatus('saved');
        }
    } catch (err) {
        toast(`Save failed: ${err.message}`, 'error');
    }
}

// Auto-save functions
function updateSaveStatus(status) {
    const indicator = document.getElementById('autosaveIndicator');
    const statusText = document.getElementById('autosaveStatus');
    const icon = indicator.querySelector('i');

    // Remove all status classes
    indicator.classList.remove('saved', 'saving', 'unsaved');

    if (status === 'saved') {
        indicator.classList.add('saved');
        icon.className = 'fas fa-check-circle';
        statusText.textContent = 'Saved';
        hasUnsavedChanges = false;
    } else if (status === 'saving') {
        indicator.classList.add('saving');
        icon.className = 'fas fa-spinner';
        statusText.textContent = 'Saving...';
    } else if (status === 'unsaved') {
        indicator.classList.add('unsaved');
        icon.className = 'fas fa-exclamation-circle';
        statusText.textContent = 'Unsaved changes';
        hasUnsavedChanges = true;
    }
}

async function performAutosave() {
    if (!editor || isAppClosing) return;

    const code = getEditorValue();

    // Don't autosave if code hasn't changed
    if (code === lastSavedCode) {
        console.log('[AUTOSAVE] No changes detected, skipping autosave');
        return;
    }

    // Don't autosave empty code
    if (!code.trim()) {
        console.log('[AUTOSAVE] Empty code, skipping autosave');
        return;
    }

    console.log('[AUTOSAVE] Changes detected, performing autosave...');

    try {
        updateSaveStatus('saving');
        const result = await pywebview.api.autosave_code(code);

        if (result.status === 'success') {
            console.log('[AUTOSAVE] ✓ Auto-saved successfully at:', result.timestamp);
            updateSaveStatus('saved');
            lastSavedCode = code;
            hasUnsavedChanges = false;
        } else {
            console.error('[AUTOSAVE] ✗ Failed:', result.message);
            updateSaveStatus('unsaved');
        }
    } catch (err) {
        console.error('[AUTOSAVE] ✗ Error:', err);
        updateSaveStatus('unsaved');
    }
}

function startAutosave() {
    console.log('[AUTOSAVE] Starting auto-save timer (30 seconds)');

    // Clear existing timer
    if (autosaveTimer) {
        clearInterval(autosaveTimer);
    }

    // Start new timer
    autosaveTimer = setInterval(() => {
        performAutosave();
    }, AUTOSAVE_INTERVAL);
}

function stopAutosave() {
    console.log('[AUTOSAVE] Stopping auto-save timer');
    if (autosaveTimer) {
        clearInterval(autosaveTimer);
        autosaveTimer = null;
    }
}

async function checkForAutosaves() {
    try {
        const result = await pywebview.api.get_autosave_files();

        if (result.status === 'success' && result.files.length > 0) {
            showAutosaveRecoveryDialog(result.files);
        }
    } catch (err) {
        console.error('[AUTOSAVE] Error checking for autosaves:', err);
    }
}

function showAutosaveRecoveryDialog(autosaves) {
    // Get the most recent autosave
    const latest = autosaves[0];

    const modal = document.createElement('div');
    modal.className = 'modal-overlay active';
    modal.style.zIndex = '10000';

    modal.innerHTML = `
        <div class="modal-container" style="max-width: 500px;">
            <div class="modal-header">
                <h2>
                    <i class="fas fa-history"></i>
                    Recover Unsaved Work?
                </h2>
            </div>
            <div class="modal-body">
                <p style="margin: 0 0 16px 0; color: var(--text-secondary);">
                    An auto-saved version of your work was found. Would you like to recover it?
                </p>
                <div style="padding: 12px; background: var(--bg-secondary); border-radius: 6px; margin-bottom: 16px;">
                    <strong style="color: var(--text-primary);">Auto-saved:</strong>
                    <span style="color: var(--text-secondary); margin-left: 8px;">${formatTimestamp(latest.timestamp)}</span>
                    <br>
                    <strong style="color: var(--text-primary);">File:</strong>
                    <span style="color: var(--text-secondary); margin-left: 8px;">${latest.file_path || 'Untitled'}</span>
                </div>
                <p style="margin: 0; font-size: 13px; color: var(--text-secondary);">
                    <i class="fas fa-info-circle"></i> Found ${autosaves.length} auto-save(s)
                </p>
            </div>
            <div class="modal-footer">
                <button class="btn btn-secondary" id="discardAutosaveBtn">Discard</button>
                <button class="btn btn-primary" id="recoverAutosaveBtn">
                    <i class="fas fa-undo"></i> Recover
                </button>
            </div>
        </div>
    `;

    document.body.appendChild(modal);

    // Handle recover button
    document.getElementById('recoverAutosaveBtn').addEventListener('click', async () => {
        try {
            const result = await pywebview.api.load_autosave(latest.autosave_file);
            if (result.status === 'success') {
                setEditorValue(result.code);
                lastSavedCode = result.code;
                toast('Work recovered successfully', 'success');
                modal.remove();
            } else {
                toast('Failed to recover work', 'error');
            }
        } catch (err) {
            toast(`Recovery failed: ${err.message}`, 'error');
        }
    });

    // Handle discard button
    document.getElementById('discardAutosaveBtn').addEventListener('click', async () => {
        try {
            // Delete all autosaves
            for (const autosave of autosaves) {
                await pywebview.api.delete_autosave(autosave.autosave_file);
            }
            toast('Auto-saves discarded', 'info');
            modal.remove();
        } catch (err) {
            console.error('[AUTOSAVE] Error discarding:', err);
            modal.remove();
        }
    });
}

function formatTimestamp(timestamp) {
    // Format: YYYYMMDD_HHMMSS -> readable format
    const year = timestamp.substring(0, 4);
    const month = timestamp.substring(4, 6);
    const day = timestamp.substring(6, 8);
    const hour = timestamp.substring(9, 11);
    const minute = timestamp.substring(11, 13);
    const second = timestamp.substring(13, 15);

    return `${year}-${month}-${day} ${hour}:${minute}:${second}`;
}

// Code Error Checking Functions
let currentErrorDecorations = [];

async function checkCodeErrors() {
    if (!editor || !pywebview?.api) {
        console.log('[ERROR CHECK] Editor or API not ready');
        return;
    }

    const code = getEditorValue();
    console.log('[ERROR CHECK] Checking code, length:', code.length);

    try {
        const result = await pywebview.api.check_code_errors(code);
        console.log('[ERROR CHECK] Result:', result);

        if (result.status === 'success') {
            displayErrors(result.errors);
        }
    } catch (err) {
        console.error('[ERROR CHECK] Failed:', err);
    }
}

function displayErrors(errors) {
    const errorsList = document.getElementById('errorsList');
    const errorCount = document.getElementById('errorCount');
    const errorsPanel = document.getElementById('codeErrorsPanel');
    const monacoEditor = document.getElementById('monacoEditor');

    console.log('[ERROR DISPLAY] Displaying errors:', errors);

    if (!errorsList || !errorCount || !errorsPanel || !monacoEditor) {
        console.error('[ERROR DISPLAY] Error elements not found!');
        return;
    }

    if (!errors || errors.length === 0) {
        // No errors - hide panel and expand editor to full height
        errorsPanel.style.display = 'none';
        monacoEditor.style.height = '100%';

        // Clear Monaco decorations
        if (editor) {
            currentErrorDecorations = editor.deltaDecorations(currentErrorDecorations, []);
            editor.layout(); // Trigger layout recalculation
        }
        return;
    }

    // Errors found - show panel and adjust editor height
    errorsPanel.style.display = 'block';
    monacoEditor.style.height = 'calc(100% - 120px)';

    // Display errors
    errorCount.textContent = errors.length;
    errorsList.innerHTML = '';

    const decorations = [];

    errors.forEach((error, index) => {
        const errorItem = document.createElement('div');
        errorItem.className = `error-item ${error.type === 'warning' ? 'warning' : ''}`;

        errorItem.innerHTML = `
            <i class="fas ${error.type === 'warning' ? 'fa-exclamation-triangle' : 'fa-times-circle'} error-icon"></i>
            <div class="error-content">
                <div class="error-location">Line ${error.line}${error.column ? `, Column ${error.column}` : ''}</div>
                <div class="error-message">${escapeHtml(error.message)}</div>
            </div>
        `;

        // Click to jump to error line
        errorItem.addEventListener('click', () => {
            if (editor && error.line > 0) {
                editor.revealLineInCenter(error.line);
                editor.setPosition({ lineNumber: error.line, column: error.column || 1 });
                editor.focus();
            }
        });

        errorsList.appendChild(errorItem);

        // Add Monaco decoration for error line
        if (error.line > 0) {
            decorations.push({
                range: new monaco.Range(error.line, 1, error.line, 1),
                options: {
                    isWholeLine: true,
                    className: error.type === 'warning' ? 'warningLine' : 'errorLine',
                    glyphMarginClassName: error.type === 'warning' ? 'warningGlyph' : 'errorGlyph',
                    glyphMarginHoverMessage: { value: error.message }
                }
            });
        }
    });

    // Apply decorations to editor
    if (editor && decorations.length > 0) {
        currentErrorDecorations = editor.deltaDecorations(currentErrorDecorations, decorations);
    }

    // Trigger layout recalculation after showing panel
    if (editor) {
        editor.layout();
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function clearErrors() {
    const errorsPanel = document.getElementById('codeErrorsPanel');
    const monacoEditor = document.getElementById('monacoEditor');

    // Hide panel and expand editor to full height
    if (errorsPanel) {
        errorsPanel.style.display = 'none';
    }
    if (monacoEditor) {
        monacoEditor.style.height = '100%';
    }

    // Clear Monaco decorations
    if (editor) {
        currentErrorDecorations = editor.deltaDecorations(currentErrorDecorations, []);
        editor.layout(); // Trigger layout recalculation
    }
}

// Rendering functions
async function renderAnimation() {
    if (job.running) {
        toast('Another job is running', 'warning');
        return;
    }

    let quality = document.getElementById('qualitySelect').value;
    let fps = document.getElementById('fpsSelect').value;

    // Handle custom resolution
    if (quality === 'custom') {
        const width = parseInt(document.getElementById('customWidth').value, 10) || 1920;
        const height = parseInt(document.getElementById('customHeight').value, 10) || 1080;
        quality = `${width}x${height}`;
    }

    // Handle custom FPS
    if (fps === 'custom') {
        fps = parseInt(document.getElementById('customFps').value, 10) || 30;
    } else {
        fps = parseInt(fps, 10) || 30;
    }

    const code = getEditorValue();

    if (!code.trim()) {
        toast('No code to render', 'warning');
        return;
    }

    // Get GPU acceleration setting
    const gpuEnabled = typeof getGPUAccelerationSetting === 'function' ? getGPUAccelerationSetting() : false;
    console.log(`[RENDER] GPU acceleration: ${gpuEnabled}`);

    const format = document.getElementById('formatSelect')?.value || 'mp4';
    saveRenderSidebarSettings();

    // Track render metadata for history
    _renderMeta = { startTime: Date.now(), mode: 'render', quality: String(quality), fps, sceneName: '', format };

    setTerminalStatus('Rendering...', 'warning');
    try {
        const res = await pywebview.api.render_animation(code, quality, fps, gpuEnabled, format, null, null, null);

        if (res.status === 'error') {
            setTerminalStatus('Error', 'error');
            toast(`Render failed: ${res.message}`, 'error');
        }
    } catch (err) {
        setTerminalStatus('Error', 'error');
        toast(`Render error: ${err.message}`, 'error');
    }
}

async function quickPreview() {
    if (job.running) {
        toast('Another job is running', 'warning');
        return;
    }

    let quality = document.getElementById('previewQualitySelect').value;
    let fps = document.getElementById('previewFpsSelect').value;

    // Handle custom resolution
    if (quality === 'custom') {
        const width = parseInt(document.getElementById('previewCustomWidth').value, 10) || 1920;
        const height = parseInt(document.getElementById('previewCustomHeight').value, 10) || 1080;
        quality = `${width}x${height}`;
    }

    // Handle custom FPS
    if (fps === 'custom') {
        fps = parseInt(document.getElementById('previewCustomFps').value, 10) || 15;
    } else {
        fps = parseInt(fps, 10) || 15;
    }

    const code = getEditorValue();

    if (!code.trim()) {
        toast('No code to preview', 'warning');
        return;
    }

    // Get GPU acceleration setting
    const gpuEnabled = typeof getGPUAccelerationSetting === 'function' ? getGPUAccelerationSetting() : false;
    console.log('[PREVIEW] Calling quick_preview with params:', { code: code.substring(0, 50) + '...', quality, fps, gpuEnabled });

    saveRenderSidebarSettings();

    // Track preview metadata for history
    _renderMeta = { startTime: Date.now(), mode: 'preview', quality: String(quality), fps, sceneName: '', format: 'mp4' };

    // Just run the command in terminal - no UI messages
    try {
        const res = await pywebview.api.quick_preview(code, quality, fps, gpuEnabled, 'mp4', null);

        if (res.status === 'error') {
            toast(`Preview failed: ${res.message}`, 'error');
        }
    } catch (err) {
        toast(`Preview error: ${err.message}`, 'error');
        job.running = false;
        setTerminalStatus('Error', 'error');
    }
}

async function stopActiveRender() {
    if (!job.running) {
        toast('No render in progress', 'info');
        return;
    }

    setTerminalStatus('Stopping...', 'warning');

    try {
        const res = await pywebview.api.stop_render();

        if (res.status === 'success') {
            appendConsole('Render stopped', 'info');
            job.running = false;
            setTerminalStatus('Stopped', 'info');
        } else {
            appendConsole(`Stop failed: ${res.message}`, 'error');
        }
    } catch (err) {
        appendConsole(`Stop error: ${err.message}`, 'error');
    }
}

// Callbacks for render updates (called by Python)
window.updateRenderOutput = function(line) {
    appendConsole(line);
};

// Function to display media in preview panel - OPTIMIZED
async function showPreview(filePath, forceReload = false) {
    console.log('[PREVIEW] showPreview called with path:', filePath, 'forceReload:', forceReload);

    const previewVideo = document.getElementById('previewVideo');
    const previewImage = document.getElementById('previewImage');
    const placeholder = document.querySelector('.preview-placeholder');
    const filenameSpan = document.getElementById('previewFilename');

    if (!filePath) {
        if (placeholder) placeholder.style.display = 'flex';
        previewVideo.style.display = 'none';
        previewImage.style.display = 'none';
        currentPreviewPath = null;
        return;
    }

    // If we're already showing this exact file, skip reload to prevent flickering
    // UNLESS forceReload is true (e.g. after a new render with the same output path)
    if (currentPreviewPath === filePath && !forceReload) {
        console.log('[PREVIEW] Already showing this file, skipping reload to prevent vanishing');
        return;
    }

    currentPreviewPath = filePath;

    // IMPORTANT: Properly clear and unload old video to force complete reload
    console.log('[PREVIEW] Clearing old preview sources...');

    // Step 1: Pause current video
    previewVideo.pause();

    // Step 2: Remove src attribute completely (not just empty string)
    previewVideo.removeAttribute('src');

    // Step 3: Remove all child source elements if any
    while (previewVideo.firstChild) {
        previewVideo.removeChild(previewVideo.firstChild);
    }

    // Step 4: Trigger load to clear buffer
    previewVideo.load();

    // Clear image too
    previewImage.removeAttribute('src');

    // NOTE: Do NOT revoke currentPreviewBlobUrl here - we'll revoke it only when we create a NEW blob URL
    // This prevents the preview from vanishing if showPreview is called multiple times with the same file

    // Hide all first
    previewVideo.style.display = 'none';
    previewImage.style.display = 'none';
    if (placeholder) placeholder.style.display = 'none';

    // Get filename and extension
    const filename = filePath.split(/[/\\]/).pop();
    const ext = filename.split('.').pop().toLowerCase();
    filenameSpan.textContent = filename;

    console.log('[PREVIEW] Loading NEW preview from assets folder:', filename);
    console.log('[PREVIEW] File type:', ext);

    try {
        // For videos: use temp_assets HTTP path (no size limits, works in new windows)
        // For images: use base64 blob (small files, fast)
        const isVideo = ['mp4', 'mov', 'webm', 'avi'].includes(ext);

        let videoHttpUrl = null;  // HTTP-servable URL for videos
        let blobUrl = null;       // Blob URL for images
        let fileSize = 0;

        if (isVideo) {
            // Copy video to web/temp_assets and get a relative HTTP path
            console.log('[PREVIEW] Requesting HTTP-served path for video...');
            const result = await pywebview.api.get_asset_as_data_url(filePath);

            if (result.status !== 'success' || !result.dataUrl) {
                filenameSpan.textContent = `Error: ${result.message || 'Failed to load'}`;
                if (placeholder) placeholder.style.display = 'flex';
                return;
            }

            videoHttpUrl = result.dataUrl;  // e.g. "temp_assets/MyScene.mp4"
            fileSize = result.size || 0;
            console.log('[PREVIEW] Video HTTP path:', videoHttpUrl);
            console.log('[PREVIEW] File size:', fileSize, 'bytes');
        } else {
            // Images: use base64 → blob (small, fast)
            console.log('[PREVIEW] Requesting file bytes from backend...');
            const result = await pywebview.api.get_asset_as_bytes(filePath);

            console.log('[PREVIEW] Backend response:', result.status);

            if (result.status !== 'success' || !result.data) {
                filenameSpan.textContent = `Error: ${result.message || 'Failed to load'}`;
                if (placeholder) placeholder.style.display = 'flex';
                return;
            }

            console.log('[PREVIEW] Converting base64 to Blob...');
            const binaryString = atob(result.data);
            const bytes = new Uint8Array(binaryString.length);
            for (let i = 0; i < binaryString.length; i++) {
                bytes[i] = binaryString.charCodeAt(i);
            }
            const blob = new Blob([bytes], { type: result.mimeType });
            fileSize = blob.size;

            // Revoke old blob URL if it exists
            if (currentPreviewBlobUrl) {
                URL.revokeObjectURL(currentPreviewBlobUrl);
                currentPreviewBlobUrl = null;
            }

            blobUrl = URL.createObjectURL(blob);
            currentPreviewBlobUrl = blobUrl;
            console.log('[PREVIEW] Created Blob URL:', blobUrl, 'size:', blob.size);
        }

        // Video formats
        if (ext === 'mp4' || ext === 'mov' || ext === 'webm' || ext === 'avi') {
            console.log('[PREVIEW] Displaying NEW video with HTTP URL:', videoHttpUrl);

            // Set up event handlers before setting src
            previewVideo.onerror = (e) => {
                console.error('========== VIDEO LOAD ERROR ==========');
                console.error('[PREVIEW] Error loading video:', filename);
                console.error('[PREVIEW] Video src that failed:', previewVideo.src);
                console.error('[PREVIEW] Video error code:', previewVideo.error ? previewVideo.error.code : 'unknown');
                console.error('[PREVIEW] Video error message:', previewVideo.error ? previewVideo.error.message : 'unknown');
                console.error('[PREVIEW] Video networkState:', previewVideo.networkState);
                console.error('[PREVIEW] Video readyState:', previewVideo.readyState);

                const errorMessages = {
                    1: 'MEDIA_ERR_ABORTED - Fetching aborted by user',
                    2: 'MEDIA_ERR_NETWORK - Network error',
                    3: 'MEDIA_ERR_DECODE - Decoding error',
                    4: 'MEDIA_ERR_SRC_NOT_SUPPORTED - Format not supported'
                };
                const errorCode = previewVideo.error ? previewVideo.error.code : 0;
                console.error('[PREVIEW] Error meaning:', errorMessages[errorCode] || 'Unknown error');
                console.error('======================================');

                filenameSpan.textContent = `Error loading ${filename}`;
            };

            previewVideo.onloadeddata = () => {
                console.log('[PREVIEW] Video loaded:', filename);
                console.log('[PREVIEW] Video duration:', previewVideo.duration, 'seconds');
                console.log('[PREVIEW] Video dimensions:', previewVideo.videoWidth, 'x', previewVideo.videoHeight);
            };

            previewVideo.oncanplay = () => {
                console.log('[PREVIEW] Video can play:', filename);
            };

            // Use HTTP URL served from temp_assets (no size limits, works in fullscreen windows)
            console.log('[PREVIEW] ========== SETTING VIDEO SOURCE ==========');
            console.log('[PREVIEW] Source type: HTTP URL (temp_assets)');
            console.log('[PREVIEW] HTTP URL:', videoHttpUrl);
            console.log('[PREVIEW] File size:', fileSize, 'bytes');
            console.log('[PREVIEW] =======================================');

            // Add cache-busting parameter to force reload
            const cacheBuster = Date.now();
            const videoUrl = videoHttpUrl.includes('?')
                ? `${videoHttpUrl}&_=${cacheBuster}`
                : `${videoHttpUrl}?_=${cacheBuster}`;

            previewVideo.src = videoUrl;

            // Show video element
            previewVideo.style.display = 'block';

            // Trigger load() to load the new source
            previewVideo.load();

            // Attempt autoplay
            previewVideo.play().catch(() => {
                console.log('[PREVIEW] Autoplay prevented (user interaction required)');
            });

            console.log('[PREVIEW] Preview box updated with new video');
        }
        // Image formats
        else if (ext === 'png' || ext === 'jpg' || ext === 'jpeg' || ext === 'gif' || ext === 'webp') {
            console.log('[PREVIEW] Displaying NEW image with Blob URL');

            // Set up event handlers before setting src
            previewImage.onload = () => {
                console.log('[PREVIEW] Image loaded successfully:', filename);
                filenameSpan.textContent = filename;
            };

            previewImage.onerror = () => {
                console.error('[PREVIEW] Error loading image:', filename);
                filenameSpan.textContent = `Error loading ${filename}`;
            };

            console.log('[PREVIEW] Setting image source from Blob URL, size:', fileSize, 'bytes');
            previewImage.src = blobUrl;

            // Show image element
            previewImage.style.display = 'block';

            console.log('[PREVIEW] Preview box updated with new image');
        }
        else {
            filenameSpan.textContent = `Unsupported: ${ext}`;
            if (placeholder) placeholder.style.display = 'flex';
        }

    } catch (error) {
        console.error('[PREVIEW] Error in showPreview:', error);
        filenameSpan.textContent = `Error: ${error.message}`;
        if (placeholder) placeholder.style.display = 'flex';
        // Clear current path on error so retry will work
        currentPreviewPath = null;
    }
}

// Save rendered file from assets to user's chosen location
async function saveRenderedFile(sourcePath, suggestedName) {
    console.log('[SAVE] Calling save_rendered_file...');
    console.log('   Source:', sourcePath);
    console.log('   Suggested name:', suggestedName);

    try {
        const result = await pywebview.api.save_rendered_file(sourcePath, suggestedName);

        if (result.status === 'success') {
            console.log('============================================================');
            console.log('[SAVE] File saved successfully!');
            console.log('[SAVE] Saved to:', result.path);

            // Extract folder path from saved file path
            const savedPath = result.path;
            const lastSlash = Math.max(savedPath.lastIndexOf('/'), savedPath.lastIndexOf('\\'));
            const folderPath = savedPath.substring(0, lastSlash);

            console.log('[SAVE] Extracted folder path:', folderPath);
            console.log('[SAVE] About to call showToastWithAction...');

            // Show toast with "Open Folder" button
            showToastWithAction('File saved successfully!', 'success', 'Open Folder', async () => {
                console.log('============================================================');
                console.log('[SAVE] *** BUTTON CLICKED - Opening folder ***');
                console.log('[SAVE] Folder path:', folderPath);
                console.log('============================================================');
                try {
                    console.log('[SAVE] Calling pywebview.api.open_folder...');
                    const openResult = await pywebview.api.open_folder(folderPath);
                    console.log('[SAVE] open_folder result:', openResult);
                    if (openResult.status === 'success') {
                        console.log('[SAVE] ✓ Folder opened successfully');
                    } else {
                        console.error('[SAVE] ✗ open_folder returned error:', openResult.message);
                        toast(`Error: ${openResult.message}`, 'error');
                    }
                } catch (err) {
                    console.error('[SAVE] ✗ Exception calling open_folder:', err);
                    toast(`Error: ${err.message}`, 'error');
                }
                console.log('============================================================');
            });

            console.log('[SAVE] Toast created successfully');
            console.log('============================================================');

            // Only refresh assets if the file was from assets folder, not render folder
            // (render folder is already cleared after save)
            if (!sourcePath.includes('render')) {
                refreshAssets();
            }
        } else if (result.status === 'cancelled') {
            console.log('[SAVE] User cancelled save dialog');
            toast('Save cancelled', 'info');
        } else {
            console.error('[SAVE] Save failed:', result.message);
            toast(`Save failed: ${result.message}`, 'error');
        }
    } catch (error) {
        console.error('[SAVE] Error calling save_rendered_file:', error);
        toast('Error saving file', 'error');
    }
}

// Show save dialog for completed render
window.showRenderSaveDialog = function(renderFilePath) {
    console.log('💾 Showing save dialog for render:', renderFilePath);

    // Extract filename from path for suggested name
    const pathParts = renderFilePath.split(/[\\\/]/);
    const filename = pathParts[pathParts.length - 1];

    // Show save dialog
    saveRenderedFile(renderFilePath, filename);
};

// Modified to accept autoSave parameter and trigger save dialog automatically
window.renderCompleted = function(outputPath, autoSave = false, suggestedName = 'MyScene.mp4') {
    console.log('🎉 Render completed!');
    console.log('📂 Output path received:', outputPath);
    console.log('📂 AutoSave:', autoSave);
    console.log('📂 Suggested name:', suggestedName);

    appendConsole('─'.repeat(60), 'info');
    appendConsole('✓ Render completed successfully!', 'success');

    // Show file location in terminal
    if (outputPath) {
        const filename = outputPath.split(/[/\\]/).pop();
        const folderPath = outputPath.substring(0, outputPath.lastIndexOf(/[/\\]/.exec(outputPath)[0]));
        appendConsole(`📁 Rendered as: ${filename}`, 'success');
        appendConsole(`📂 Location: ${outputPath}`, 'info');
        appendConsole(`💡 File saved in render folder`, 'info');
    }

    appendConsole('─'.repeat(60), 'info');
    job.running = false;
    setTerminalStatus('Ready', 'success');
    toast('Render completed!', 'success');

    // Record in render history
    _recordRenderHistory(outputPath, 'render');

    // Auto-show in main preview box and switch to workspace tab
    if (outputPath) {
        console.log('🎬 Auto-loading preview...');
        showPreview(outputPath, true);  // forceReload=true — new render, same path, new content

        // Auto-switch to workspace tab to show the preview
        const workspaceTab = document.querySelector('.tab-pill[data-tab="workspace"]');
        if (workspaceTab) {
            console.log('🔄 Switching to workspace tab...');
            workspaceTab.click();
        }

        // If autoSave is enabled, show save dialog after a short delay
        if (autoSave) {
            console.log('[AUTO-SAVE] Will show save dialog in 500ms...');
            setTimeout(() => {
                console.log('[AUTO-SAVE] Showing save dialog now...');
                saveRenderedFile(outputPath, suggestedName);
            }, 500);
        }
    } else {
        console.warn('⚠️ No output path provided to renderCompleted');
    }
};

window.renderFailed = function(error) {
    appendConsole('─'.repeat(60), 'info');
    appendConsole(`✗ Render failed: ${error}`, 'error');
    appendConsole('─'.repeat(60), 'info');
    job.running = false;
    setTerminalStatus('Error', 'error');
};

window.previewCompleted = function(outputPath) {
    console.log('🎉 Preview completed!');
    console.log('📂 Output path received:', outputPath);
    console.log('📁 File is now in assets folder for display');

    appendConsole('─'.repeat(60), 'info');
    appendConsole('✓ Preview completed! File ready in preview box.', 'success');

    // Show file locations in terminal
    if (outputPath) {
        const filename = outputPath.split(/[/\\]/).pop();
        const ext = filename.split('.').pop().toLowerCase();
        appendConsole(`📁 Preview saved as: ${filename}`, 'success');
        appendConsole(`📂 Location: ${outputPath}`, 'info');
        appendConsole(`💡 Also available at: ~/.manim_studio/preview/latest_preview.${ext}`, 'info');
    }

    appendConsole('─'.repeat(60), 'info');
    job.running = false;
    setTerminalStatus('Ready', 'success');

    // Record in render history
    _recordRenderHistory(outputPath, 'preview');

    // Auto-show in main preview box and switch to workspace tab
    if (outputPath) {
        console.log('🎬 Auto-loading preview from assets folder...');
        console.log('   Path:', outputPath);

        // Load preview using get_asset_as_data_url for HTTP URL
        showPreview(outputPath, true);  // forceReload=true — new preview, same path, new content

        // Auto-switch to workspace tab to show the preview
        const workspaceTab = document.querySelector('.tab-pill[data-tab="workspace"]');
        if (workspaceTab) {
            console.log('🔄 Switching to workspace tab to show preview...');
            workspaceTab.click();
        }

        // Show toast with file location info
        const filename = outputPath.split(/[/\\]/).pop();
        toast(`Preview ready! Saved as: ${filename}`, 'success');

        console.log('✅ Preview loaded in preview box (files kept permanently)');
    } else {
        console.warn('⚠️ No output path provided to previewCompleted');
        appendConsole('Warning: No preview file found', 'warning');
    }
};

window.previewFailed = function(error) {
    appendConsole('─'.repeat(60), 'info');
    appendConsole(`✗ Preview failed: ${error}`, 'error');
    appendConsole('─'.repeat(60), 'info');
    job.running = false;
    setTerminalStatus('Error', 'error');
};

// ── Render History helpers ──────────────────────────────────────────────────

/** Save a completed render/preview to the persistent history via the backend. */
function _recordRenderHistory(outputPath, mode) {
    if (!outputPath) return;
    const durationMs = _renderMeta.startTime ? Date.now() - _renderMeta.startTime : 0;
    const filename = outputPath.split(/[/\\]/).pop();
    const entry = {
        scene_name:       _renderMeta.sceneName || filename.replace(/\.[^.]+$/, ''),
        quality:          _renderMeta.quality || '?',
        fps:              _renderMeta.fps || 0,
        format:           _renderMeta.format || 'mp4',
        mode:             mode || _renderMeta.mode || 'render',
        output_path:      outputPath,
        filename:         filename,
        timestamp:        new Date().toISOString(),
        duration_seconds: Math.round(durationMs / 1000),
    };
    pywebview.api.add_render_history(entry).catch(e => console.warn('[HISTORY]', e));
}

/** Play a video in the history tab's own embedded player. */
let _historyPlayerId = 0;  // Monotonic counter to cancel stale loads
async function playInHistoryPlayer(filePath, displayName) {
    const player   = document.getElementById('historyPlayer');
    const video    = document.getElementById('historyPlayerVideo');
    const nameSpan = document.getElementById('historyPlayerName');
    const closeBtn = document.getElementById('historyPlayerClose');
    if (!player || !video) return;

    // Bump request ID — any older in-flight loads become stale
    const thisId = ++_historyPlayerId;

    // Show the player and update title immediately
    player.classList.add('visible');
    nameSpan.textContent = displayName || filePath.split(/[/\\]/).pop();

    // Clear active highlight on all rows (caller will re-add to the clicked row)
    document.querySelectorAll('.history-entry.active').forEach(el => el.classList.remove('active'));

    // Pause + clear previous video
    video.pause();
    video.removeAttribute('src');
    video.load();

    // Get an HTTP-served path for the video (copies to web/temp_assets/)
    try {
        const result = await pywebview.api.get_asset_as_data_url(filePath);

        // If the user clicked a different entry while we were loading, bail out
        if (thisId !== _historyPlayerId) return;

        if (result.status !== 'success' || !result.dataUrl) {
            nameSpan.textContent = 'Error loading video';
            return;
        }

        const cacheBuster = Date.now();
        const videoUrl = result.dataUrl.includes('?')
            ? `${result.dataUrl}&_=${cacheBuster}`
            : `${result.dataUrl}?_=${cacheBuster}`;

        video.src = videoUrl;
        video.load();
        video.play().catch(() => {});
    } catch (err) {
        if (thisId !== _historyPlayerId) return;  // stale
        console.error('[HISTORY PLAYER] Error:', err);
        nameSpan.textContent = 'Error: ' + err.message;
    }

    // Wire close button (only once)
    if (!closeBtn._wired) {
        closeBtn.addEventListener('click', () => {
            _historyPlayerId++;  // Cancel any in-flight load
            video.pause();
            video.removeAttribute('src');
            video.load();
            player.classList.remove('visible');
            document.querySelectorAll('.history-entry.active').forEach(el => el.classList.remove('active'));
        });
        closeBtn._wired = true;
    }
}

/** Refresh the render history list UI. Called when the History tab is opened. */
async function refreshRenderHistory() {
    const list = document.getElementById('historyList');
    if (!list) return;

    list.innerHTML = '<div class="history-empty"><i class="fas fa-spinner fa-spin"></i><div>Loading...</div></div>';

    try {
        const res = await pywebview.api.get_render_history();
        const entries = (res && res.entries) || [];

        if (entries.length === 0) {
            list.innerHTML =
                '<div class="history-empty">' +
                    '<i class="fas fa-clock-rotate-left"></i>' +
                    '<div>No render history yet</div>' +
                    '<div style="font-size:13px;opacity:0.7">Completed renders and previews will appear here</div>' +
                '</div>';
            return;
        }

        list.innerHTML = '';
        for (const entry of entries) {
            list.appendChild(_buildHistoryRow(entry));
        }
    } catch (e) {
        console.warn('[HISTORY] Failed to load:', e);
        list.innerHTML = '<div class="history-empty"><i class="fas fa-exclamation-triangle"></i><div>Failed to load history</div></div>';
    }
}

/** Build a single history row DOM element. */
function _buildHistoryRow(entry) {
    const row = document.createElement('div');
    row.className = 'history-entry' + (entry.file_exists === false ? ' missing-file' : '');

    const isRender = entry.mode === 'render';
    const iconClass = isRender ? 'render' : 'preview';
    const iconFa    = isRender ? 'fa-film' : 'fa-eye';

    // Format timestamp
    let timeStr = '';
    try {
        const d = new Date(entry.timestamp);
        timeStr = d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) +
                  ' ' + d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
    } catch (_) { timeStr = entry.timestamp || ''; }

    // Duration
    const dur = entry.duration_seconds;
    const durStr = dur >= 60 ? Math.floor(dur / 60) + 'm ' + (dur % 60) + 's' : dur + 's';

    row.innerHTML =
        '<div class="history-icon ' + iconClass + '"><i class="fas ' + iconFa + '"></i></div>' +
        '<div class="history-info">' +
            '<div class="history-scene">' + _escHtml(entry.scene_name || entry.filename || '?') + '</div>' +
            '<div class="history-meta">' +
                '<span><i class="fas fa-tag"></i> ' + _escHtml(entry.mode) + '</span>' +
                '<span><i class="fas fa-expand"></i> ' + _escHtml(entry.quality) + '</span>' +
                '<span><i class="fas fa-gauge-high"></i> ' + entry.fps + ' fps</span>' +
                (dur ? '<span><i class="fas fa-stopwatch"></i> ' + durStr + '</span>' : '') +
                '<span><i class="fas fa-calendar"></i> ' + timeStr + '</span>' +
                (entry.file_exists === false ? '<span style="color:#ef4444"><i class="fas fa-triangle-exclamation"></i> file missing</span>' : '') +
            '</div>' +
        '</div>' +
        '<div class="history-entry-actions">' +
            (entry.file_exists !== false
                ? '<button class="history-entry-btn" title="Open in preview"><i class="fas fa-play"></i></button>'
                : '') +
            '<button class="history-entry-btn delete" title="Remove from history"><i class="fas fa-xmark"></i></button>' +
        '</div>';

    // Wire up buttons — use specific selectors to avoid index confusion
    const playBtn = entry.file_exists !== false
        ? row.querySelector('.history-entry-btn:not(.delete)')
        : null;
    const deleteBtn = row.querySelector('.history-entry-btn.delete');

    const entryName = entry.scene_name || entry.filename || 'Video';

    if (playBtn) {
        playBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            // Play in the history tab's own player (not workspace preview)
            playInHistoryPlayer(entry.output_path, entryName);
            row.classList.add('active');
        });
    }
    if (deleteBtn) {
        deleteBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            _deleteHistoryEntry(entry.timestamp, row);
        });
    }

    // Clicking the row itself also plays in history player
    if (entry.file_exists !== false) {
        row.addEventListener('click', () => {
            document.querySelectorAll('.history-entry.active').forEach(el => el.classList.remove('active'));
            playInHistoryPlayer(entry.output_path, entryName);
            row.classList.add('active');
        });
    }

    return row;
}

async function _deleteHistoryEntry(timestamp, rowEl) {
    try {
        await pywebview.api.delete_render_history_entry(timestamp);
        rowEl.style.transition = 'opacity 0.25s, transform 0.25s';
        rowEl.style.opacity = '0';
        rowEl.style.transform = 'translateX(30px)';
        setTimeout(() => { rowEl.remove(); _checkHistoryEmpty(); }, 260);
    } catch (e) { console.warn('[HISTORY]', e); }
}

async function clearRenderHistory() {
    if (!confirm('Clear all render history?')) return;
    try {
        await pywebview.api.clear_render_history();
        refreshRenderHistory();
    } catch (e) { console.warn('[HISTORY]', e); }
}

function _checkHistoryEmpty() {
    const list = document.getElementById('historyList');
    if (list && list.children.length === 0) {
        list.innerHTML =
            '<div class="history-empty">' +
                '<i class="fas fa-clock-rotate-left"></i>' +
                '<div>No render history yet</div>' +
                '<div style="font-size:13px;opacity:0.7">Completed renders and previews will appear here</div>' +
            '</div>';
    }
}

function _escHtml(s) {
    const el = document.createElement('span');
    el.textContent = s;
    return el.innerHTML;
}

// CACHE BUSTER - Version 2025-01-25-v9
// ASSETS WORKFLOW: Render → Move to assets → Auto-save dialog → User chooses location
console.log('[RENDERER] Loaded renderer_desktop.js - Version 2025-01-25-v9 - ASSETS WORKFLOW');
console.log('[RENDERER] Render: Move to assets -> Auto-save dialog -> User saves to location');

// Assets management
// Helper function to get file type icon
function getFileTypeIcon(fileName) {
    const ext = fileName.split('.').pop().toLowerCase();
    const iconMap = {
        'mp4': 'fa-file-video',
        'mov': 'fa-file-video',
        'webm': 'fa-file-video',
        'avi': 'fa-file-video',
        'png': 'fa-file-image',
        'jpg': 'fa-file-image',
        'jpeg': 'fa-file-image',
        'gif': 'fa-file-image',
        'svg': 'fa-file-image'
    };
    return iconMap[ext] || 'fa-file';
}

// Helper function to get file type badge
function getFileTypeBadge(fileName) {
    const ext = fileName.split('.').pop().toLowerCase();
    if (['mp4', 'mov', 'webm', 'avi'].includes(ext)) {
        return { text: 'VIDEO', class: 'video' };
    } else if (['png', 'jpg', 'jpeg', 'gif', 'svg'].includes(ext)) {
        return { text: 'IMAGE', class: 'image' };
    }
    return { text: ext.toUpperCase(), class: '' };
}

// Helper function to format date
function formatDate(timestamp) {
    if (!timestamp) return 'Unknown';
    const date = new Date(timestamp * 1000);
    const now = new Date();
    const diffTime = Math.abs(now - date);
    const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));

    if (diffDays === 0) {
        return 'Today';
    } else if (diffDays === 1) {
        return 'Yesterday';
    } else if (diffDays < 7) {
        return `${diffDays} days ago`;
    } else {
        return date.toLocaleDateString();
    }
}

// Global state for assets
let allAssets = [];
let currentFilter = 'all';
let searchQuery = '';
let currentAsset = null; // Currently selected asset for modal

async function refreshAssets(preserveOnEmpty = false) {
    console.log('============================================');
    console.log('📦 REFRESHING ASSETS...');
    console.log(`[ASSETS] preserveOnEmpty: ${preserveOnEmpty}`);
    console.log('============================================');

    try {
        console.log('[ASSETS] Checking pywebview API...');
        if (typeof pywebview === 'undefined' || !pywebview.api) {
            console.error('[ASSETS] ✗ PyWebView API not available!');
            return;
        }
        console.log('[ASSETS] ✓ PyWebView API available');

        console.log('[ASSETS] Calling list_media_files()...');
        const res = await pywebview.api.list_media_files();
        console.log('[ASSETS] Response:', res);

        if (!res.files || res.files.length === 0) {
            console.log('[ASSETS] No files found in response');
            // Only clear the UI if we're not preserving on empty
            if (!preserveOnEmpty) {
                console.log('[ASSETS] Clearing UI (preserveOnEmpty=false)');
                allAssets = [];
                displayAssets([]);
            } else {
                console.log('[ASSETS] Keeping existing UI (preserveOnEmpty=true)');
            }
            return;
        }

        allAssets = res.files;
        console.log(`[ASSETS] ✅ Found ${allAssets.length} assets:`, allAssets.map(f => f.name));
        console.log('[ASSETS] About to call displayAssets() with', allAssets.length, 'files');
        console.log('[ASSETS] allAssets array:', allAssets);
        displayAssets(allAssets);
        console.log('[ASSETS] displayAssets() call completed');
    } catch (err) {
        console.error('[ASSETS] ❌ Failed to refresh assets:', err);
        console.error('[ASSETS] Error stack:', err.stack);
        // On error during drag-drop, preserve the UI
        if (preserveOnEmpty) {
            console.log('[ASSETS] Error occurred but preserving UI');
        }
    }
}

// COMPLETELY REWRITTEN displayAssets() - Using pure innerHTML for better compatibility
function displayAssets(files) {
    try {
        console.log('============================================');
        console.log('[ASSETS] displayAssets() START');
        console.log('[ASSETS] Files parameter:', files);
        console.log('[ASSETS] Files type:', typeof files);
        console.log('[ASSETS] Files is array?', Array.isArray(files));
        console.log('[ASSETS] Files length:', files ? files.length : 'null/undefined');
        console.log('============================================');

        const container = document.getElementById('assetsGrid');

        if (!container) {
            console.error('[ASSETS] ❌ CRITICAL: assetsGrid element not found!');
            alert('ERROR: Assets container not found in DOM!');
            return;
        }

        console.log('[ASSETS] ✓ Container found, ID:', container.id);
        console.log('[ASSETS] Container display style:', window.getComputedStyle(container).display);
        console.log('[ASSETS] Container visibility:', window.getComputedStyle(container).visibility);

        // Empty state
        if (!files || files.length === 0) {
            console.log('[ASSETS] No files - showing empty state');
            container.innerHTML = `
                <div class="empty-state" style="padding: 40px; text-align: center;">
                    <i class="fas fa-box-open" style="font-size: 48px; color: #666; margin-bottom: 16px;"></i>
                    <p style="color: #999; font-size: 16px;">No assets yet. Render something!</p>
                </div>
            `;
            updateAssetsCount(0);
            return;
        }

        // Apply filters
        let filteredFiles = files;

        if (searchQuery) {
            filteredFiles = filteredFiles.filter(file =>
                file.name.toLowerCase().includes(searchQuery.toLowerCase())
            );
        }

        if (currentFilter !== 'all') {
            filteredFiles = filteredFiles.filter(file => {
                const ext = file.name.split('.').pop().toLowerCase();
                if (currentFilter === 'video') {
                    return ['mp4', 'mov', 'webm', 'avi'].includes(ext);
                } else if (currentFilter === 'image') {
                    return ['png', 'jpg', 'jpeg', 'gif', 'svg'].includes(ext);
                }
                return true;
            });
        }

        if (filteredFiles.length === 0) {
            console.log('[ASSETS] No files match filters');
            container.innerHTML = `
                <div class="empty-state" style="padding: 40px; text-align: center;">
                    <i class="fas fa-filter" style="font-size: 48px; color: #666; margin-bottom: 16px;"></i>
                    <p style="color: #999; font-size: 16px;">No assets match your filters</p>
                </div>
            `;
            updateAssetsCount(0);
            return;
        }

        updateAssetsCount(filteredFiles.length);

        // Build HTML string for ALL assets at once
        console.log('[ASSETS] Building HTML for', filteredFiles.length, 'files...');
        let assetsHTML = '';

        filteredFiles.forEach((file, index) => {
            console.log(`[ASSETS] [${index + 1}/${filteredFiles.length}] ${file.name}`);

            const ext = file.name.split('.').pop().toLowerCase();
            const isVideo = ['mp4', 'mov', 'webm', 'avi'].includes(ext);
            const isImage = ['png', 'jpg', 'jpeg', 'gif', 'svg'].includes(ext);

            const badge = getFileTypeBadge(file.name);
            const icon = getFileTypeIcon(file.name);

            // Convert Windows path to web path
            const webPath = file.path.replace(/\\/g, '/');

            // Build thumbnail
            let thumbnailHTML = '';
            if (isVideo) {
                thumbnailHTML = `<video src="${webPath}" muted style="width: 100%; height: 100%; object-fit: cover;"></video>`;
            } else if (isImage) {
                thumbnailHTML = `<img src="${webPath}" alt="${file.name}" style="width: 100%; height: 100%; object-fit: cover;">`;
            } else {
                thumbnailHTML = `<i class="fas ${icon}" style="font-size: 48px; color: var(--accent-primary);"></i>`;
            }

            // Build complete asset card HTML
            assetsHTML += `
            <div class="asset-item" onclick="openAssetByIndex(${index})" style="
                background: var(--bg-secondary);
                border: 1px solid var(--border-color);
                border-radius: 8px;
                padding: 12px;
                cursor: pointer;
                transition: all 0.2s ease;
            " onmouseover="this.style.borderColor='var(--accent-primary)'" onmouseout="this.style.borderColor='var(--border-color)'">
                <div class="asset-thumbnail" style="
                    width: 100%;
                    height: 150px;
                    background: var(--bg-primary);
                    border-radius: 6px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    overflow: hidden;
                    margin-bottom: 12px;
                ">
                    ${thumbnailHTML}
                </div>
                <div class="asset-info">
                    <div class="asset-name" title="${file.name}" style="
                        font-weight: 500;
                        color: var(--text-primary);
                        margin-bottom: 8px;
                        overflow: hidden;
                        text-overflow: ellipsis;
                        white-space: nowrap;
                    ">${file.name}</div>
                    <div class="asset-meta" style="
                        display: flex;
                        flex-wrap: wrap;
                        gap: 8px;
                        font-size: 12px;
                        color: var(--text-secondary);
                    ">
                        <span class="asset-type-badge ${badge.class}" style="
                            background: var(--accent-primary);
                            color: white;
                            padding: 2px 8px;
                            border-radius: 4px;
                            font-weight: 500;
                        ">${badge.text}</span>
                        <span class="asset-size">
                            <i class="fas fa-hdd"></i> ${formatBytes(file.size)}
                        </span>
                        <span class="asset-date">
                            <i class="fas fa-clock"></i> ${formatDate(file.mtime)}
                        </span>
                    </div>
                </div>
            </div>
        `;
        });

        // Set ALL HTML at once (much faster and more reliable than appendChild)
        console.log('[ASSETS] Setting container innerHTML...');
        console.log('[ASSETS] HTML length:', assetsHTML.length, 'characters');
        container.innerHTML = assetsHTML;

        console.log('[ASSETS] ============================================');
        console.log('[ASSETS] ✅ COMPLETE - Displayed', filteredFiles.length, 'assets');
        console.log('[ASSETS] Container children:', container.children.length);
        console.log('[ASSETS] Container innerHTML length:', container.innerHTML.length);
        console.log('[ASSETS] First child element:', container.firstChild);
        console.log('[ASSETS] ============================================');

    } catch (error) {
        console.error('[ASSETS] ❌❌❌ EXCEPTION IN displayAssets():', error);
        console.error('[ASSETS] Error message:', error.message);
        console.error('[ASSETS] Error stack:', error.stack);
        alert(`CRITICAL ERROR in displayAssets(): ${error.message}`);
    }
}

// Helper function to open asset by index (since we're using inline onclick)
window.openAssetByIndex = function(index) {
    const file = allAssets[index];
    if (file) {
        console.log('📺 Asset clicked:', file.name);
        openAssetModal(file);
    }
};

// Open asset preview modal
function openAssetModal(file) {
    currentAsset = file;
    const modal = document.getElementById('assetPreviewModal');
    const video = document.getElementById('assetModalVideo');
    const image = document.getElementById('assetModalImage');

    // Hide both
    video.style.display = 'none';
    image.style.display = 'none';

    // Convert path to file:// URL
    let webPath = file.path.replace(/\\/g, '/');
    if (!webPath.startsWith('file://') && !webPath.startsWith('http')) {
        webPath = 'file:///' + webPath;
    }

    const ext = file.name.split('.').pop().toLowerCase();

    // Show appropriate media
    if (ext === 'mp4' || ext === 'mov' || ext === 'webm') {
        video.src = webPath;
        video.style.display = 'block';
        video.load();
    } else if (ext === 'png' || ext === 'jpg' || ext === 'jpeg' || ext === 'gif') {
        image.src = webPath;
        image.style.display = 'block';
    }

    // Set details
    document.getElementById('assetDetailName').textContent = file.name;
    document.getElementById('assetDetailSize').textContent = formatBytes(file.size);
    document.getElementById('assetDetailType').textContent = ext.toUpperCase();
    document.getElementById('assetDetailDate').textContent = formatDate(file.mtime);
    document.getElementById('assetDetailPath').textContent = file.path;

    // Show modal
    modal.style.display = 'flex';
}

// Close asset modal
function closeAssetModal() {
    const modal = document.getElementById('assetPreviewModal');
    const video = document.getElementById('assetModalVideo');

    // Stop video if playing
    if (video) {
        video.pause();
        video.src = '';
    }

    modal.style.display = 'none';
    currentAsset = null;
}

// Open asset in main preview box
function openInMainPreview() {
    if (currentAsset) {
        // Close modal
        closeAssetModal();

        // Show in main preview
        showPreview(currentAsset.path);

        // Switch to workspace tab
        const workspaceTab = document.querySelector('.tab-pill[data-tab="workspace"]');
        if (workspaceTab) workspaceTab.click();
    }
}

// Update assets count display
function updateAssetsCount(count) {
    const countElement = document.getElementById('assetsCount');
    if (countElement) {
        countElement.textContent = `${count} ${count === 1 ? 'item' : 'items'}`;
    }
}

// Setup assets search
function setupAssetsSearch() {
    const searchInput = document.getElementById('assetsSearchInput');
    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            searchQuery = e.target.value;
            displayAssets(allAssets);
        });
    }
}

// Setup assets filters
function setupAssetsFilters() {
    const filterButtons = document.querySelectorAll('.filter-btn');
    filterButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            // Remove active class from all
            filterButtons.forEach(b => b.classList.remove('active'));
            // Add active to clicked
            btn.classList.add('active');
            // Update filter
            currentFilter = btn.getAttribute('data-filter');
            displayAssets(allAssets);
        });
    });
}

// Setup asset modal handlers
function setupAssetModal() {
    // Close button
    document.getElementById('closeAssetPreview')?.addEventListener('click', closeAssetModal);

    // Click outside to close
    document.getElementById('assetPreviewModal')?.addEventListener('click', (e) => {
        if (e.target.id === 'assetPreviewModal') {
            closeAssetModal();
        }
    });

    // Open in main preview button
    document.getElementById('openInMainPreview')?.addEventListener('click', openInMainPreview);

    // Open in explorer button
    document.getElementById('openInExplorer')?.addEventListener('click', () => {
        if (currentAsset) {
            openMediaFolder();
        }
    });

    // ESC key to close
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            const modal = document.getElementById('assetPreviewModal');
            if (modal && modal.style.display === 'flex') {
                closeAssetModal();
            }
        }
    });
}

async function openMediaFolder() {
    try {
        await pywebview.api.open_media_folder();
    } catch (err) {
        toast(`Error: ${err.message}`, 'error');
    }
}

async function playMedia(filePath) {
    try {
        await pywebview.api.play_media(filePath);
    } catch (err) {
        toast(`Error: ${err.message}`, 'error');
    }
}

function formatBytes(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

// Terminal command execution
// Terminal output polling for persistent cmd.exe session with xterm.js
let terminalPollInterval = null;
let term = null; // xterm.js Terminal instance

async function startTerminalPolling() {
    if (terminalPollInterval) return; // Already polling

    console.log('[TERMINAL] Starting PTY output polling for xterm.js...');

    // Adaptive polling: faster when active, slower when idle
    let consecutiveEmptyPolls = 0;
    let currentPollInterval = 50; // Start at 50ms (20 calls/sec max)
    const MIN_INTERVAL = 50;      // Fastest: 50ms when active
    const MAX_INTERVAL = 500;     // Slowest: 500ms when idle
    const EMPTY_POLLS_THRESHOLD = 10; // After 10 empty polls, slow down

    // Throttle scroll operations using requestAnimationFrame
    let scrollPending = false;
    let autoFollowOutput = true;
    let viewportTrackingAttached = false;
    let isDraggingScrollbar = false;
    const getTerminalViewport = () => document.querySelector('#terminalContainer .xterm-viewport');
    const isNearBottom = () => {
        const viewport = getTerminalViewport();
        if (!viewport) return true;
        const distanceFromBottom = viewport.scrollHeight - (viewport.scrollTop + viewport.clientHeight);
        return distanceFromBottom <= 24;
    };
    const attachViewportTracking = () => {
        if (viewportTrackingAttached) return;

        const viewport = getTerminalViewport();
        if (!viewport) return;

        const disableAutoFollow = () => {
            autoFollowOutput = false;
        };

        // As soon as user interacts with scroll area, stop auto-follow.
        viewport.addEventListener('wheel', disableAutoFollow, { passive: true });
        viewport.addEventListener('touchstart', disableAutoFollow, { passive: true });
        viewport.addEventListener('pointerdown', (event) => {
            const rect = viewport.getBoundingClientRect();
            const scrollbarHitArea = 24;
            if (event.clientX >= rect.right - scrollbarHitArea) {
                isDraggingScrollbar = true;
                autoFollowOutput = false;
            }
        }, { passive: true });
        window.addEventListener('pointerup', () => {
            isDraggingScrollbar = false;
        }, { passive: true });
        window.addEventListener('pointercancel', () => {
            isDraggingScrollbar = false;
        }, { passive: true });

        viewport.addEventListener('scroll', () => {
            // Disable auto-follow when user scrolls up; restore when user returns to bottom.
            autoFollowOutput = isNearBottom();
        }, { passive: true });

        viewportTrackingAttached = true;
    };

    const scheduleScroll = () => {
        if (!scrollPending) {
            scrollPending = true;
            requestAnimationFrame(() => {
                if (term && typeof term.scrollToBottom === 'function') {
                    term.scrollToBottom();
                }
                // Fallback scroll method
                const viewport = getTerminalViewport();
                if (viewport) {
                    viewport.scrollTop = viewport.scrollHeight;
                }
                autoFollowOutput = true;
                scrollPending = false;
            });
        }
    };

    const poll = async () => {
        try {
            attachViewportTracking();

            const res = await pywebview.api.get_terminal_output();
            if (res.status === 'success' && res.output && term) {
                if (res.output.length > 0) {
                    // Preserve user scroll position if they scrolled up.
                    const shouldAutoScroll = autoFollowOutput && !isDraggingScrollbar;

                    // Got output - write it
                    term.write(res.output);

                    // Schedule scroll (throttled with RAF) only when following output
                    if (shouldAutoScroll) {
                        scheduleScroll();
                    }

                    // Reset to fast polling when we have output
                    consecutiveEmptyPolls = 0;
                    if (currentPollInterval !== MIN_INTERVAL) {
                        currentPollInterval = MIN_INTERVAL;
                        clearInterval(terminalPollInterval);
                        terminalPollInterval = setInterval(poll, currentPollInterval);
                    }
                } else {
                    // No output - slow down polling gradually
                    consecutiveEmptyPolls++;
                    if (consecutiveEmptyPolls >= EMPTY_POLLS_THRESHOLD && currentPollInterval < MAX_INTERVAL) {
                        currentPollInterval = Math.min(currentPollInterval + 10, MAX_INTERVAL);
                        clearInterval(terminalPollInterval);
                        terminalPollInterval = setInterval(poll, currentPollInterval);
                        console.log(`[TERMINAL] Slowing poll to ${currentPollInterval}ms (idle)`);
                    }
                }
            }
        } catch (err) {
            console.error('[TERMINAL] Poll error:', err);
        }
    };

    // Start polling
    terminalPollInterval = setInterval(poll, currentPollInterval);
}

async function executeCommand(command) {
    console.log('🔧 executeCommand() called with:', command);
    if (!command.trim()) {
        console.log('Empty command, ignoring');
        return;
    }

    // Handle special UI-only commands
    if (command === 'clear') {
        clearConsole();
        setTerminalStatus(job.running ? 'Busy...' : 'Ready', job.running ? 'warning' : 'info');
        focusInput();
        return;
    }

    if (command === 'help') {
        appendConsole('=== Manim Studio Terminal ===', 'info');
        appendConsole('This is a real cmd.exe session!', 'info');
        appendConsole('', 'info');
        appendConsole('Special commands:', 'info');
        appendConsole('  clear - clear console display', 'info');
        appendConsole('  help - show this help', 'info');
        appendConsole('', 'info');
        appendConsole('All other commands run in persistent cmd.exe:', 'info');
        appendConsole('  pip install <package> - uses venv pip automatically', 'info');
        appendConsole('  claude - use Claude Code AI (if installed)', 'info');
        appendConsole('  dir, cd, echo, etc. - normal cmd.exe commands', 'info');
        setTerminalStatus(job.running ? 'Busy...' : 'Ready', job.running ? 'warning' : 'info');
        focusInput();
        return;
    }

    // Show command like a real terminal
    appendConsole(`> ${command}`, 'command');
    setTerminalStatus('Running...', 'warning');

    try {
        console.log('[TERMINAL] Sending command to persistent cmd.exe...');
        const res = await pywebview.api.execute_command(command);

        // Output is handled by polling (get_terminal_output), just check for errors
        if (res.status === 'error' && res.message) {
            appendConsole(res.message, 'error');
            setTerminalStatus('Error', 'error');
        } else {
            setTerminalStatus('Ready', 'success');

            // Refresh system info after pip commands
            if (command.startsWith('pip ')) {
                setTimeout(() => loadSystemInfo(), 1500);
            }
        }
    } catch (err) {
        appendConsole(`Error: ${err.message}`, 'error');
        setTerminalStatus('Error', 'error');
    } finally {
        focusInput();
    }
}

// System info
async function loadSystemInfo() {
    console.log('📊 loadSystemInfo() called');
    try {
        console.log('Calling pywebview.api.get_system_info()...');
        const info = await pywebview.api.get_system_info();
        console.log('System info received:', info);

        // Set all system info fields
        document.getElementById('pythonVersion').textContent = info.python_version ? info.python_version.split('\n')[0] : 'Unknown';
        document.getElementById('manimVersion').textContent = info.manim_version || 'Not installed';
        document.getElementById('platform').textContent = info.platform || 'Unknown';
        document.getElementById('baseDir').textContent = info.base_dir || '-';
        document.getElementById('mediaDir').textContent = info.media_dir || '-';
        document.getElementById('venvPath').textContent = info.venv_path || 'Not in virtual environment';
        document.getElementById('pythonExe').textContent = info.python_exe || '-';

        // Set status indicators
        const venvStatus = document.getElementById('venvStatus');
        if (info.venv_path) {
            venvStatus.textContent = 'Active';
            venvStatus.className = 'status-badge success';
        } else {
            venvStatus.textContent = 'Not Active';
            venvStatus.className = 'status-badge warning';
        }

        const manimStatus = document.getElementById('manimStatus');
        if (info.manim_installed) {
            manimStatus.textContent = 'Installed';
            manimStatus.className = 'status-badge success';
        } else {
            manimStatus.textContent = 'Not Installed';
            manimStatus.className = 'status-badge error';
        }

        // Check LaTeX status
        checkLatexStatus();

        console.log('✅ System info loaded successfully');
    } catch (err) {
        console.error('❌ System info error:', err);
    }
}

// Check LaTeX availability
async function checkLatexStatus() {
    try {
        console.log('🔍 Checking LaTeX status...');
        const result = await pywebview.api.check_prerequisites();

        const latexStatusElement = document.getElementById('latexStatus');
        const latexCard = document.getElementById('latexStatusCard');
        const latexStatusBtn = document.getElementById('latexStatusBtn');

        if (result.status === 'success' && result.results.latex.installed) {
            // LaTeX found
            const variant = result.results.latex.variant || 'Installed';

            // Update system panel
            latexStatusElement.innerHTML = `
                <span class="status-indicator found"></span>
                <span style="flex: 1;">✓ ${variant}</span>
            `;
            latexCard.className = 'info-card success';

            // Update header button
            latexStatusBtn.className = 'status-btn found';
            latexStatusBtn.title = `LaTeX Status - ${variant}`;
            latexStatusBtn.innerHTML = `
                <span class="status-dot found"></span>
                <span class="status-text">LaTeX ✓</span>
            `;

            console.log('✅ LaTeX found:', variant);
        } else {
            // LaTeX not found

            // Update system panel
            latexStatusElement.innerHTML = `
                <span class="status-indicator missing"></span>
                <span style="flex: 1;">✗ Not Found - <a href="#" onclick="window.open('https://miktex.org/download'); return false;" style="color: var(--accent-warning); text-decoration: underline;">Install MiKTeX</a></span>
            `;
            latexCard.className = 'info-card warning';

            // Update header button
            latexStatusBtn.className = 'status-btn missing';
            latexStatusBtn.title = 'LaTeX Status - Not Found (Click to download MiKTeX)';
            latexStatusBtn.innerHTML = `
                <span class="status-dot missing"></span>
                <span class="status-text">LaTeX ✗</span>
            `;

            console.log('⚠️ LaTeX not found');
        }
    } catch (err) {
        console.error('❌ LaTeX check error:', err);
        const latexStatusElement = document.getElementById('latexStatus');
        const latexStatusBtn = document.getElementById('latexStatusBtn');

        latexStatusElement.innerHTML = `
            <span class="status-indicator missing"></span>
            <span style="flex: 1;">Error checking</span>
        `;

        latexStatusBtn.className = 'status-btn missing';
        latexStatusBtn.title = 'LaTeX Status - Error checking';
        latexStatusBtn.innerHTML = `
            <span class="status-dot missing"></span>
            <span class="status-text">LaTeX ?</span>
        `;
    }
}

// Settings
async function loadSettings() {
    try {
        const settings = await pywebview.api.get_settings();

        document.getElementById('qualitySelect').value = settings.quality || '720p';
        document.getElementById('fpsSelect').value = settings.fps || 30;

        const formatEl = document.getElementById('formatSelect');
        formatEl.value = settings.format || 'mp4';
        // Guard: if the saved value doesn't match any option the select goes blank — reset to default
        if (!formatEl.value) formatEl.value = 'mp4';

        if (editor && settings.font_size) {
            editor.updateOptions({ fontSize: settings.font_size });
        }
    } catch (err) {
        console.error('Failed to load settings:', err);
    }
}

async function saveSettings() {
    try {
        const settings = {
            quality: document.getElementById('qualitySelect').value,
            fps: parseInt(document.getElementById('fpsSelect').value),
            format: document.getElementById('formatSelect').value,
            font_size: editor ? editor.getOption(monaco.editor.EditorOption.fontSize) : 14
        };

        await pywebview.api.update_settings(settings);
    } catch (err) {
        console.error('Failed to save settings:', err);
    }
}

// ─── Render sidebar settings persistence (Fix 9) ───────────────────────────

const RENDER_SETTINGS_KEY = 'manim-render-sidebar';

function saveRenderSidebarSettings() {
    const s = {
        renderQuality: document.getElementById('qualitySelect')?.value,
        renderFps: document.getElementById('fpsSelect')?.value,
        renderFormat: document.getElementById('formatSelect')?.value,
        renderCustomWidth: document.getElementById('customWidth')?.value,
        renderCustomHeight: document.getElementById('customHeight')?.value,
        renderCustomFps: document.getElementById('customFps')?.value,
        previewQuality: document.getElementById('previewQualitySelect')?.value,
        previewFps: document.getElementById('previewFpsSelect')?.value,
        previewCustomWidth: document.getElementById('previewCustomWidth')?.value,
        previewCustomHeight: document.getElementById('previewCustomHeight')?.value,
        previewCustomFps: document.getElementById('previewCustomFps')?.value,
    };
    try {
        localStorage.setItem(RENDER_SETTINGS_KEY, JSON.stringify(s));
    } catch (e) {
        console.warn('[SETTINGS] localStorage write failed:', e);
    }
}

function loadRenderSidebarSettings() {
    try {
        const raw = localStorage.getItem(RENDER_SETTINGS_KEY);
        if (!raw) return;
        const s = JSON.parse(raw);

        const set = (id, val) => { if (val !== undefined && val !== null && document.getElementById(id)) document.getElementById(id).value = val; };

        set('qualitySelect', s.renderQuality);
        set('fpsSelect', s.renderFps);
        set('formatSelect', s.renderFormat);
        set('customWidth', s.renderCustomWidth);
        set('customHeight', s.renderCustomHeight);
        set('customFps', s.renderCustomFps);
        set('previewQualitySelect', s.previewQuality);
        set('previewFpsSelect', s.previewFps);
        set('previewCustomWidth', s.previewCustomWidth);
        set('previewCustomHeight', s.previewCustomHeight);
        set('previewCustomFps', s.previewCustomFps);

        // Show/hide custom resolution divs based on restored values
        const q = document.getElementById('qualitySelect');
        if (q) document.getElementById('customResolutionDiv').style.display = q.value === 'custom' ? 'block' : 'none';
        const f = document.getElementById('fpsSelect');
        if (f) document.getElementById('customFpsDiv').style.display = f.value === 'custom' ? 'block' : 'none';
        const pq = document.getElementById('previewQualitySelect');
        if (pq) document.getElementById('previewCustomResolutionDiv').style.display = pq.value === 'custom' ? 'block' : 'none';
        const pf = document.getElementById('previewFpsSelect');
        if (pf) document.getElementById('previewCustomFpsDiv').style.display = pf.value === 'custom' ? 'block' : 'none';
    } catch (err) {
        console.error('[SETTINGS] Failed to load render sidebar settings:', err);
    }
}

// ─── App version (Fix 4) ────────────────────────────────────────────────────

async function loadAppVersion() {
    try {
        const res = await pywebview.api.get_app_version();
        const ver = `v${res.version}`;
        const el = document.getElementById('appVersion');
        if (el) el.textContent = ver;
        // Update help modal version if it's already in the DOM
        const helpVer = document.getElementById('helpModalVersion');
        if (helpVer) helpVer.textContent = ver;
        // Also update when modals are loaded later
        window.addEventListener('modalsReady', () => {
            const hv = document.getElementById('helpModalVersion');
            if (hv) hv.textContent = ver;
        }, { once: true });
    } catch (err) {
        console.error('[VERSION] Failed to load app version:', err);
    }
}


// Event listeners
document.addEventListener('DOMContentLoaded', () => {
    // Initialize editor (doesn't require PyWebView API)
    initializeEditor();
});

// Detect app closing to prevent API calls during shutdown
window.addEventListener('beforeunload', () => {
    console.log('[SHUTDOWN] App is closing, setting isAppClosing flag');

    // Trigger autosave before closing if there are unsaved changes
    // This is a backup in case the periodic autosave didn't catch the latest changes
    try {
        const code = getEditorValue();
        if (code && code !== lastSavedCode && code.trim()) {
            console.log('[SHUTDOWN] Unsaved changes detected, performing final autosave...');
            // Use synchronous call to ensure it completes before window closes
            if (typeof pywebview !== 'undefined' && pywebview.api) {
                pywebview.api.autosave_code(code);
                console.log('[SHUTDOWN] Final autosave completed');
            }
        } else {
            console.log('[SHUTDOWN] No unsaved changes, skipping final autosave');
        }
    } catch (err) {
        console.error('[SHUTDOWN] Error during autosave:', err);
    }

    isAppClosing = true;
});

// Wait for PyWebView to be ready before using API
window.addEventListener('pywebviewready', () => {
    console.log('============================================');
    console.log('✅ PyWebView ready event fired!');
    console.log('============================================');
    console.log('pywebview object:', typeof pywebview);
    console.log('pywebview.api:', typeof pywebview?.api);

    if (typeof pywebview !== 'undefined' && pywebview.api) {
        console.log('✓ PyWebView API is available');
        console.log('Available API methods:', Object.keys(pywebview.api));
    } else {
        console.error('✗ PyWebView API is NOT available!');
    }

    // Load initial data (requires PyWebView API)
    console.log('============================================');
    console.log('Loading initial data...');
    console.log('============================================');

    console.log('[INIT] 0. Loading app version...');
    loadAppVersion();

    console.log('[INIT] 0.5. Restoring render sidebar settings...');
    loadRenderSidebarSettings();

    console.log('[INIT] 1. Loading settings...');
    loadSettings();

    console.log('[INIT] 2. Loading system info...');
    loadSystemInfo();

    console.log('[INIT] 2.5. Checking LaTeX status for header button...');
    checkLatexStatus();

    console.log('[INIT] 3. Refreshing assets...');
    refreshAssets();

    console.log('[INIT] 4. Starting auto-save...');
    startAutosave();

    console.log('[INIT] 5. Checking for unsaved work (delayed)...');
    // Delay autosave check to ensure app is fully loaded
    setTimeout(() => {
        checkForAutosaves();
    }, 2000);  // Wait 2 seconds for app to fully initialize

    console.log('[INIT] 5.5. Checking for missing required packages (delayed)...');
    setTimeout(() => {
        checkMissingRequiredPackages();
    }, 5000);  // Run after autosave check, non-blocking

    console.log('[INIT] 6. Will initialize terminal when ready...');
    // Terminal initialization happens below (after Terminal constructor is loaded)

    // Auto-refresh system info every 1 minute (60000ms)
    setInterval(() => {
        // Only refresh if system tab is active to avoid unnecessary API calls
        const systemPanel = document.getElementById('system-panel');
        if (systemPanel && systemPanel.classList.contains('active')) {
            console.log('🔄 Auto-refreshing system info...');
            loadSystemInfo();
        }
    }, 60000); // 60 seconds

    // Setup assets functionality
    setupAssetsSearch();
    setupAssetsFilters();
    setupAssetModal();

    // Tab switching functionality
    const tabPills = document.querySelectorAll('.tab-pill');
    const tabPanels = document.querySelectorAll('.tab-panel');

    tabPills.forEach(pill => {
        pill.addEventListener('click', () => {
            const tabName = pill.getAttribute('data-tab');
            console.log(`[TAB] Switching to tab: ${tabName}`);

            // Remove active class from all pills and panels
            tabPills.forEach(p => p.classList.remove('active'));
            tabPanels.forEach(panel => panel.classList.remove('active'));

            // Add active class to clicked pill and corresponding panel
            pill.classList.add('active');
            document.getElementById(`${tabName}-panel`)?.classList.add('active');

            // Refresh assets when assets tab is clicked
            if (tabName === 'assets') {
                console.log('[TAB] Assets tab selected, refreshing assets...');
                refreshAssets();
            }

            // Refresh history when history tab is clicked
            if (tabName === 'history') {
                refreshRenderHistory();
            }

            // Handle performance monitoring based on active tab
            handlePerformanceMonitoring();

            console.log(`Switched to ${tabName} tab`);
        });
    });

    // LaTeX status button click handler
    document.getElementById('latexStatusBtn')?.addEventListener('click', async () => {
        const result = await pywebview.api.check_prerequisites();
        if (result.status === 'success' && !result.results.latex.installed) {
            // If LaTeX is not installed, open download page
            window.open('https://miktex.org/download');
        } else {
            // If LaTeX is installed, switch to system tab to show details
            document.querySelectorAll('.tab-pill').forEach(p => p.classList.remove('active'));
            document.querySelectorAll('.tab-panel').forEach(panel => panel.classList.remove('active'));
            document.querySelector('[data-tab="system"]')?.classList.add('active');
            document.getElementById('system-panel')?.classList.add('active');
        }
    });

    // Button event listeners
    document.getElementById('newFileBtn')?.addEventListener('click', newFile);
    document.getElementById('openFileBtn')?.addEventListener('click', openFile);
    document.getElementById('saveFileBtn')?.addEventListener('click', saveFile);
    document.getElementById('saveAsBtn')?.addEventListener('click', saveFileAs);
    document.getElementById('renderBtn')?.addEventListener('click', renderAnimation);
    document.getElementById('previewBtn')?.addEventListener('click', quickPreview);
    document.getElementById('stopBtn')?.addEventListener('click', stopActiveRender);
    document.getElementById('refreshAssetsBtn')?.addEventListener('click', refreshAssets);
    document.getElementById('clearErrorsBtn')?.addEventListener('click', clearErrors);
    document.getElementById('openAssetsFolderBtn')?.addEventListener('click', openMediaFolder);
    document.getElementById('openMediaFolderBtn')?.addEventListener('click', openMediaFolder);
    document.getElementById('refreshSystemBtn')?.addEventListener('click', loadSystemInfo);
    document.getElementById('settingsBtn')?.addEventListener('click', () => {
        document.getElementById('settingsModal')?.classList.add('show');
    });

    // Modal close functionality
    document.querySelectorAll('.close-btn, [data-modal]').forEach(btn => {
        btn.addEventListener('click', () => {
            const modalId = btn.getAttribute('data-modal');
            if (modalId) {
                document.getElementById(modalId)?.classList.remove('show');
            }
        });
    });

    // Copy console output button - copies all terminal content
    document.getElementById('copyOutputBtn')?.addEventListener('click', () => {
        if (term) {
            try {
                // Get all visible lines from the terminal buffer
                const buffer = term.buffer.active;
                let text = '';

                // Read all lines from the buffer
                for (let i = 0; i < buffer.length; i++) {
                    const line = buffer.getLine(i);
                    if (line) {
                        text += line.translateToString(true) + '\n';
                    }
                }

                // Copy to clipboard
                navigator.clipboard.writeText(text).then(() => {
                    toast('Copied', 'success');
                    console.log('[TERMINAL] Copied', text.split('\n').length, 'lines to clipboard');
                }).catch(err => {
                    toast('Copy failed', 'error');
                    console.error('[TERMINAL] Copy failed:', err);
                });
            } catch (err) {
                console.error('[TERMINAL] Error copying terminal content:', err);
                toast('Copy failed', 'error');
            }
        } else {
            toast('Terminal not ready', 'warning');
        }
    });

    // Clear console button - reset terminal to original state
    document.getElementById('clearOutputBtn')?.addEventListener('click', async () => {
        if (term) {
            // Clear the terminal screen
            term.clear();

            // Send cls command to PTY to reset cmd.exe
            try {
                await pywebview.api.send_terminal_command('cls\r\n');
                toast('Cleared', 'success');
            } catch (err) {
                console.error('[TERMINAL] Error clearing:', err);
                toast('Clear failed', 'error');
            }
        } else {
            toast('Not ready', 'warning');
        }
    });

    // Initialize xterm.js terminal emulator
    function initializeTerminal() {
        console.log('[TERMINAL] Initializing xterm.js terminal...');

        const terminalContainer = document.getElementById('terminalContainer');
        if (!terminalContainer) {
            console.error('❌ Terminal container not found!');
            return;
        }

        // Check if Terminal constructor is available (try both window.Terminal and global Terminal)
        const TerminalConstructor = window.Terminal || (typeof Terminal !== 'undefined' ? Terminal : null);

        if (!TerminalConstructor) {
            console.error('❌ xterm.js Terminal constructor not available!');
            terminalContainer.innerHTML = '<div style="color: #ff6b6b; padding: 20px; font-family: monospace;">Error: xterm.js library not loaded<br>Terminal constructor not found</div>';
            return;
        }

        console.log('✅ Terminal constructor found, creating instance...');

        try {
            // Create terminal instance with performance-optimized settings
            term = new TerminalConstructor({
                cursorBlink: true,
                cursorStyle: 'block',
                fontSize: 14,
                fontFamily: 'Consolas, "Courier New", monospace',
                lineHeight: 1.2,
                letterSpacing: 0,
                windowsMode: true, // Enable Windows-specific PTY handling
                theme: {
                    background: '#0c0c0c',
                    foreground: '#cccccc',
                    cursor: '#ffffff',
                    cursorAccent: '#000000',
                    selection: 'rgba(255, 255, 255, 0.3)',
                    black: '#0c0c0c',
                    red: '#c50f1f',
                    green: '#13a10e',
                    yellow: '#c19c00',
                    blue: '#0037da',
                    magenta: '#881798',
                    cyan: '#3a96dd',
                    white: '#cccccc',
                    brightBlack: '#767676',
                    brightRed: '#e74856',
                    brightGreen: '#16c60c',
                    brightYellow: '#f9f1a5',
                    brightBlue: '#3b78ff',
                    brightMagenta: '#b4009e',
                    brightCyan: '#61d6d6',
                    brightWhite: '#f2f2f2'
                },
                allowTransparency: false,
                scrollback: 5000, // Reduced from 10000 for better performance
                fastScrollModifier: 'shift',
                fastScrollSensitivity: 5,
                cols: 120,  // Match PTY width for proper progress bar display
                rows: 30,   // Match PTY height
                // Performance optimizations
                rendererType: 'canvas', // Use canvas renderer for better performance
                disableStdin: false,
                convertEol: false, // Keep false to preserve \r for progress bars
                screenReaderMode: false, // Disable for performance
                macOptionIsMeta: true,
                rightClickSelectsWord: true
            });

            // Open terminal in container
            term.open(terminalContainer);
            console.log('✅ Terminal opened in container');

            // Focus terminal so it can receive input immediately
            term.focus();

            // Calculate terminal size based on container - auto-sizing like HTML
            function calculateTerminalSize() {
                // Get actual container dimensions
                const rect = terminalContainer.getBoundingClientRect();
                const width = rect.width - 20; // Account for padding
                const height = rect.height - 20;

                // Get actual character dimensions from xterm's render service
                let charWidth = 9;
                let charHeight = 17;

                try {
                    const core = term._core;
                    if (core && core._renderService && core._renderService.dimensions) {
                        charWidth = core._renderService.dimensions.css.cell.width || 9;
                        charHeight = core._renderService.dimensions.css.cell.height || 17;
                    }
                } catch (e) {
                    // Use defaults if can't access internal API
                }

                // Calculate columns and rows to fill the space
                const cols = Math.max(10, Math.floor(width / charWidth));
                const rows = Math.max(5, Math.floor(height / charHeight));

                return { cols, rows };
            }

            // Wait for terminal to render, then calculate and apply proper size
            setTimeout(() => {
                const size = calculateTerminalSize();
                console.log(`[TERMINAL] Initial auto-size: ${size.cols}x${size.rows} (container: ${terminalContainer.clientWidth}x${terminalContainer.clientHeight})`);

                if (size.cols > 0 && size.rows > 0) {
                    term.resize(size.cols, size.rows);
                    lastCols = size.cols;
                    lastRows = size.rows;

                    // Notify backend of terminal size (skip if app is closing)
                    if (!isAppClosing) {
                        pywebview.api.resize_terminal(size.cols, size.rows).catch(err => {
                            // Ignore errors if app is closing
                            if (!isAppClosing) {
                                console.error('[TERMINAL] Error resizing PTY:', err);
                            }
                        });
                    }
                }
            }, 200);

            // Force another resize after a bit to ensure proper sizing
            setTimeout(() => {
                const size = calculateTerminalSize();
                if (size.cols > 0 && size.rows > 0 && (size.cols !== lastCols || size.rows !== lastRows)) {
                    console.log(`[TERMINAL] Secondary auto-size adjustment: ${size.cols}x${size.rows}`);
                    term.resize(size.cols, size.rows);
                    if (!isAppClosing) {
                        pywebview.api.resize_terminal(size.cols, size.rows).catch(() => {});
                    }
                    lastCols = size.cols;
                    lastRows = size.rows;
                }
            }, 500);

            // Send user input to PTY backend
            term.onData(async (data) => {
                try {
                    await pywebview.api.send_terminal_command(data);
                } catch (err) {
                    console.error('[TERMINAL] Error sending data:', err);
                }
            });

            // Enable copy/paste support
            term.attachCustomKeyEventHandler((event) => {
                // Ctrl+Shift+C - Copy (when text is selected)
                if (event.ctrlKey && event.shiftKey && event.key === 'C' && term.hasSelection()) {
                    const selection = term.getSelection();
                    navigator.clipboard.writeText(selection).catch(err => {
                        console.error('[TERMINAL] Copy failed:', err);
                    });
                    return false; // Prevent default
                }

                // Ctrl+Shift+V - Paste
                if (event.ctrlKey && event.shiftKey && event.key === 'V' && event.type === 'keydown') {
                    navigator.clipboard.readText().then(text => {
                        if (text) {
                            pywebview.api.send_terminal_command(text);
                        }
                    }).catch(err => {
                        console.error('[TERMINAL] Paste failed:', err);
                    });
                    return false; // Prevent default
                }

                return true; // Allow other keys
            });

            // Selection-based copy (when user selects text and releases mouse)
            term.onSelectionChange(() => {
                if (term.hasSelection()) {
                    const selection = term.getSelection();
                    if (selection) {
                        navigator.clipboard.writeText(selection).catch(err => {
                            console.log('[TERMINAL] Auto-copy failed:', err);
                        });
                    }
                }
            });

            // Right-click context menu for paste
            terminalContainer.addEventListener('contextmenu', (e) => {
                e.preventDefault();
                navigator.clipboard.readText().then(text => {
                    if (text) {
                        pywebview.api.send_terminal_command(text);
                    }
                }).catch(err => {
                    console.error('[TERMINAL] Paste failed:', err);
                });
            });

            // Handle terminal resize - auto-size on container changes
            let lastCols = 10;
            let lastRows = 5;
            let resizeTimeout = null;
            let lastResizeTime = 0;

            const resizeObserver = new ResizeObserver(() => {
                if (term && terminalContainer) {
                    // Debounce resize to avoid too many updates
                    if (resizeTimeout) {
                        clearTimeout(resizeTimeout);
                    }

                    resizeTimeout = setTimeout(() => {
                        // Throttle resize operations - minimum 250ms between resizes
                        const now = Date.now();
                        if (now - lastResizeTime < 250) {
                            return;
                        }

                        const size = calculateTerminalSize();

                        // Only resize if dimensions actually changed significantly
                        if (size.cols > 0 && size.rows > 0 && (size.cols !== lastCols || size.rows !== lastRows)) {
                            console.log(`[TERMINAL] Auto-resizing from ${lastCols}x${lastRows} to ${size.cols}x${size.rows}`);

                            // Use requestAnimationFrame for smooth resize
                            requestAnimationFrame(() => {
                                term.resize(size.cols, size.rows);
                            });

                            // Notify backend PTY of new size (skip if app is closing)
                            if (!isAppClosing) {
                                pywebview.api.resize_terminal(size.cols, size.rows).catch(err => {
                                    // Ignore errors if app is closing
                                    if (!isAppClosing) {
                                        console.error('[TERMINAL] Error resizing PTY:', err);
                                    }
                                });
                            }

                            lastCols = size.cols;
                            lastRows = size.rows;
                            lastResizeTime = now;
                        }
                    }, 150); // Wait 150ms for resize to settle (increased from 100ms)
                }
            });
            resizeObserver.observe(terminalContainer);

            // Also listen to window resize for better responsiveness
            window.addEventListener('resize', () => {
                if (resizeTimeout) {
                    clearTimeout(resizeTimeout);
                }
                resizeTimeout = setTimeout(() => {
                    const size = calculateTerminalSize();
                    if (size.cols > 0 && size.rows > 0 && term) {
                        term.resize(size.cols, size.rows);
                        if (!isAppClosing) {
                            pywebview.api.resize_terminal(size.cols, size.rows).catch(() => {});
                        }
                        lastCols = size.cols;
                        lastRows = size.rows;
                    }
                }, 100);
            });

            console.log('✅ xterm.js terminal fully initialized and ready');

            // Now start polling for PTY output
            console.log('[TERMINAL] Starting PTY output polling...');
            startTerminalPolling();
        } catch (err) {
            console.error('❌ Error initializing terminal:', err);
            terminalContainer.innerHTML = `<div style="color: #ff6b6b; padding: 20px; font-family: monospace;">Error initializing terminal:<br>${err.message}</div>`;
        }
    }

    // Try to initialize terminal - check multiple times to handle async script loading
    let terminalInitialized = false;

    function tryInitTerminal() {
        if (terminalInitialized) {
            console.log('[TERMINAL] Already initialized, skipping...');
            return;
        }

        const TerminalConstructor = window.Terminal || (typeof Terminal !== 'undefined' ? Terminal : null);

        if (TerminalConstructor) {
            console.log('[TERMINAL] Terminal constructor found, initializing...');
            terminalInitialized = true;
            initializeTerminal();
        } else {
            console.log('[TERMINAL] Terminal constructor not yet available, will retry...');
        }
    }

    // Try immediately
    tryInitTerminal();

    // If not found, retry after script loads
    if (!terminalInitialized) {
        setTimeout(tryInitTerminal, 500);
    }

    // Render Quality select - show/hide custom resolution
    document.getElementById('qualitySelect')?.addEventListener('change', (event) => {
        const customResDiv = document.getElementById('customResolutionDiv');
        if (customResDiv) {
            if (event.target.value === 'custom') {
                customResDiv.style.display = 'block';
            } else {
                customResDiv.style.display = 'none';
            }
        }
        saveSettings();
    });

    // Render FPS select - show/hide custom FPS
    document.getElementById('fpsSelect')?.addEventListener('change', (event) => {
        const customFpsDiv = document.getElementById('customFpsDiv');
        if (customFpsDiv) {
            if (event.target.value === 'custom') {
                customFpsDiv.style.display = 'block';
            } else {
                customFpsDiv.style.display = 'none';
            }
        }
        saveSettings();
    });

    // Preview Quality select - show/hide custom resolution
    document.getElementById('previewQualitySelect')?.addEventListener('change', (event) => {
        const customResDiv = document.getElementById('previewCustomResolutionDiv');
        if (customResDiv) {
            if (event.target.value === 'custom') {
                customResDiv.style.display = 'block';
            } else {
                customResDiv.style.display = 'none';
            }
        }
        saveSettings();
    });

    // Preview FPS select - show/hide custom FPS
    document.getElementById('previewFpsSelect')?.addEventListener('change', (event) => {
        const customFpsDiv = document.getElementById('previewCustomFpsDiv');
        if (customFpsDiv) {
            if (event.target.value === 'custom') {
                customFpsDiv.style.display = 'block';
            } else {
                customFpsDiv.style.display = 'none';
            }
        }
        saveSettings();
    });

    // Save settings on changes
    document.getElementById('formatSelect')?.addEventListener('change', saveSettings);
    document.getElementById('customWidth')?.addEventListener('change', saveSettings);
    document.getElementById('customHeight')?.addEventListener('change', saveSettings);
    document.getElementById('customFps')?.addEventListener('change', saveSettings);
    document.getElementById('previewCustomWidth')?.addEventListener('change', saveSettings);
    document.getElementById('previewCustomHeight')?.addEventListener('change', saveSettings);
    document.getElementById('previewCustomFps')?.addEventListener('change', saveSettings);

    // Persist sidebar settings to localStorage on every change
    ['qualitySelect','fpsSelect','formatSelect','customWidth','customHeight','customFps',
     'previewQualitySelect','previewFpsSelect','previewCustomWidth','previewCustomHeight','previewCustomFps'
    ].forEach(id => document.getElementById(id)?.addEventListener('change', saveRenderSidebarSettings));

    // Font size control
    document.getElementById('fontSizeSelect')?.addEventListener('change', (event) => {
        const fontSize = parseInt(event.target.value, 10) || 14;
        if (editor) {
            editor.updateOptions({ fontSize: fontSize });
            saveSettings();
        }
    });

    // Initial status
    setTerminalStatus('Ready', 'success');
    appendConsole('Manim Studio Desktop - Ready', 'success');
    appendConsole('Type "help" for available commands', 'info');

    console.log('Manim Studio Desktop initialized');
});

// ============================================================================
// NOTIFICATION HELPER
// ============================================================================

function showNotification(title, message, type = 'info') {
    // Use console for debugging
    console.log(`[NOTIFICATION] ${type}: ${title} - ${message}`);

    // Show desktop notification if available
    if ('Notification' in window && Notification.permission === 'granted') {
        new Notification(title, {
            body: message,
            icon: type === 'success' ? '✓' : type === 'error' ? '✗' : 'ℹ'
        });
    }

    // Also show a toast-style notification in the UI
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
        <div class="toast-icon">
            ${type === 'success' ? '<i class="fas fa-check-circle"></i>' :
              type === 'error' ? '<i class="fas fa-exclamation-circle"></i>' :
              '<i class="fas fa-info-circle"></i>'}
        </div>
        <div class="toast-content">
            <div class="toast-title">${title}</div>
            <div class="toast-message">${message}</div>
        </div>
    `;

    document.body.appendChild(toast);

    // Animate in
    setTimeout(() => toast.classList.add('show'), 10);

    // Remove after 4 seconds
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// Request notification permission on load
if ('Notification' in window && Notification.permission === 'default') {
    Notification.requestPermission();
}

// ============================================================================
// ASSETS UPLOAD AND DRAG-DROP
// ============================================================================

window.uploadAssets = async function() {
    try {
        const result = await pywebview.api.select_files_to_upload();

        if (result.status === 'success' && result.file_paths.length > 0) {
            const uploadResult = await pywebview.api.upload_assets(result.file_paths);

            if (uploadResult.status === 'success') {
                showNotification('Upload Complete', uploadResult.message, 'success');
                refreshAssets();
            } else if (uploadResult.status === 'partial') {
                showNotification('Upload Partial', uploadResult.message, 'info');
                refreshAssets();
            } else {
                showNotification('Upload Failed', uploadResult.message, 'error');
            }
        }
    } catch (error) {
        console.error('[UPLOAD ERROR]', error);
        showNotification('Upload Error', error.message, 'error');
    }
}

// Setup drag and drop for assets
document.addEventListener('DOMContentLoaded', () => {
    const dropzone = document.getElementById('assetsDropzone');

    if (dropzone) {
        // Prevent default drag behaviors on dropzone only
        dropzone.addEventListener('dragenter', (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropzone.classList.add('dragover');
        }, false);

        dropzone.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropzone.classList.add('dragover');
        }, false);

        dropzone.addEventListener('dragleave', (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropzone.classList.remove('dragover');
        }, false);

        // Handle dropped files
        dropzone.addEventListener('drop', (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropzone.classList.remove('dragover');
            handleDrop(e);
        }, false);

        // Prevent browser from opening dropped files outside the dropzone
        document.body.addEventListener('dragover', (e) => {
            // Only prevent if not over the dropzone
            if (e.target !== dropzone && !dropzone.contains(e.target)) {
                e.preventDefault();
            }
        }, false);

        document.body.addEventListener('drop', (e) => {
            // Only prevent if not over the dropzone
            if (e.target !== dropzone && !dropzone.contains(e.target)) {
                e.preventDefault();
            }
        }, false);
    }
});

async function handleDrop(e) {
    const dt = e.dataTransfer;
    const files = dt.files;

    if (files.length > 0) {
        console.log(`[DRAG-DROP] ${files.length} files dropped`);

        // Try to get file paths (works in some environments like Electron/PyWebView)
        const filePaths = [];
        let hasFilePaths = false;

        for (let i = 0; i < files.length; i++) {
            const file = files[i];
            console.log('[DRAG-DROP] File:', file.name, 'Path:', file.path, 'Type:', file.type);

            // Check if we have actual file system paths
            if (file.path && file.path !== file.name) {
                filePaths.push(file.path);
                hasFilePaths = true;
            }
        }

        if (hasFilePaths && filePaths.length > 0) {
            // We have file paths - use the backend upload method
            console.log('[DRAG-DROP] Using file paths:', filePaths);
            try {
                const uploadResult = await pywebview.api.upload_assets(filePaths);

                if (uploadResult.status === 'success') {
                    showNotification('Upload Complete', uploadResult.message, 'success');
                    console.log('[DRAG-DROP] Upload successful, calling loadAssets()...');
                    // Call the same function as the refresh button
                    if (window.loadAssets) {
                        await window.loadAssets();
                    }
                } else if (uploadResult.status === 'partial') {
                    showNotification('Upload Partial', uploadResult.message, 'info');
                    console.log('[DRAG-DROP] Upload partial, calling loadAssets()...');
                    // Call the same function as the refresh button
                    if (window.loadAssets) {
                        await window.loadAssets();
                    }
                } else {
                    showNotification('Upload Failed', uploadResult.message, 'error');
                }
            } catch (error) {
                console.error('[DRAG-DROP ERROR]', error);
                showNotification('Upload Error', error.message, 'error');
            }
        } else {
            // No file paths available - need to read file contents and upload
            console.log('[DRAG-DROP] No file paths - reading file contents');

            try {
                const uploadPromises = [];

                for (let i = 0; i < files.length; i++) {
                    const file = files[i];
                    uploadPromises.push(uploadFileContent(file));
                }

                const results = await Promise.all(uploadPromises);
                const successCount = results.filter(r => r === true).length;
                const failCount = results.length - successCount;

                if (successCount > 0 && failCount === 0) {
                    showNotification('Upload Complete', `Successfully uploaded ${successCount} file(s)`, 'success');
                    console.log('[DRAG-DROP] Upload successful, calling loadAssets()...');
                    // Call the same function as the refresh button
                    if (window.loadAssets) {
                        await window.loadAssets();
                    }
                } else if (successCount > 0 && failCount > 0) {
                    showNotification('Upload Partial', `Uploaded ${successCount} file(s), ${failCount} failed`, 'info');
                    console.log('[DRAG-DROP] Upload partial, calling loadAssets()...');
                    // Call the same function as the refresh button
                    if (window.loadAssets) {
                        await window.loadAssets();
                    }
                } else {
                    showNotification('Upload Failed', 'All uploads failed', 'error');
                }
            } catch (error) {
                console.error('[DRAG-DROP ERROR]', error);
                showNotification('Upload Error', error.message, 'error');
            }
        }
    }
}

async function uploadFileContent(file) {
    return new Promise((resolve) => {
        const reader = new FileReader();

        reader.onload = async function(e) {
            try {
                const base64Content = e.target.result.split(',')[1]; // Remove data URL prefix
                const result = await pywebview.api.upload_file_content(file.name, base64Content);

                if (result.status === 'success') {
                    console.log(`[UPLOAD] Successfully uploaded ${file.name}`);
                    resolve(true);
                } else {
                    console.error(`[UPLOAD] Failed to upload ${file.name}:`, result.message);
                    resolve(false);
                }
            } catch (error) {
                console.error(`[UPLOAD ERROR] ${file.name}:`, error);
                resolve(false);
            }
        };

        reader.onerror = function() {
            console.error(`[UPLOAD ERROR] Failed to read ${file.name}`);
            resolve(false);
        };

        reader.readAsDataURL(file);
    });
}

// ============================================================================
// PACKAGE MANAGEMENT FUNCTIONS
// ============================================================================

let cachedUpdates = null; // Cache updates to avoid checking every time

async function refreshPackages(checkUpdates = false) {
    console.log('[VENV] Refreshing package list...');
    const packagesList = document.getElementById('packagesList');

    // Show loading
    packagesList.innerHTML = `
        <div class="venv-loading">
            <i class="fas fa-spinner fa-spin"></i> Loading packages...
        </div>
    `;

    try {
        // Get installed packages
        const packagesResult = await pywebview.api.get_installed_packages();

        // Only check for updates if explicitly requested
        let updatesResult = { status: 'success', updates: cachedUpdates || [] };
        if (checkUpdates) {
            updatesResult = await pywebview.api.check_package_updates();
            cachedUpdates = updatesResult.updates || [];
        }

        console.log('[VENV] Package list result:', packagesResult);
        console.log('[VENV] Updates result:', updatesResult);

        if (packagesResult.status === 'success' && packagesResult.packages && packagesResult.packages.length > 0) {
            // Create a map of packages with updates (including safety info)
            const updatesMap = {};
            if (updatesResult.status === 'success' && updatesResult.updates) {
                updatesResult.updates.forEach(update => {
                    updatesMap[update.name] = {
                        latest: update.latest_version,
                        current: update.version,
                        safe_to_update: update.safe_to_update !== false,  // Default to true if not specified
                        warning: update.warning || null,
                        is_critical: update.is_critical || false
                    };
                });
            }

            // Build package list HTML
            let html = '';
            packagesResult.packages.forEach(pkg => {
                const isCritical = ['pip', 'setuptools', 'wheel', 'manim', 'manim-fonts'].includes(pkg.name.toLowerCase());
                const hasUpdate = updatesMap[pkg.name];

                html += `
                    <div class="package-item ${hasUpdate ? 'has-update' : ''} ${hasUpdate && !hasUpdate.safe_to_update ? 'has-warning' : ''}">
                        <div class="package-info">
                            <div class="package-name">
                                ${pkg.name}
                                ${hasUpdate && hasUpdate.is_critical ? '<span style="color: #ef4444; margin-left: 6px;" title="Critical for Manim"><i class="fas fa-exclamation-triangle"></i></span>' : ''}
                                ${hasUpdate ? '<span class="package-update-badge"><i class="fas fa-arrow-up"></i> Update available</span>' : ''}
                            </div>
                            <div class="package-version">
                                v${pkg.version}
                                ${hasUpdate ? `<span class="package-latest"> → v${hasUpdate.latest}</span>` : ''}
                            </div>
                            ${hasUpdate && hasUpdate.warning ? `
                                <div style="margin-top: 6px; padding: 6px 10px; background: rgba(239, 68, 68, 0.1); border-left: 3px solid #ef4444; border-radius: 4px; font-size: 12px; color: #ef4444;">
                                    ${hasUpdate.warning}
                                </div>
                            ` : ''}
                        </div>
                        <div class="package-actions">
                            ${hasUpdate ? `
                                <button
                                    class="package-btn package-btn-update ${!hasUpdate.safe_to_update ? 'package-btn-warning' : ''}"
                                    onclick="updatePackage('${pkg.name}', ${!hasUpdate.safe_to_update})"
                                    title="${!hasUpdate.safe_to_update ? 'Warning: May affect Manim compatibility' : 'Update to latest version'}"
                                >
                                    <i class="fas ${!hasUpdate.safe_to_update ? 'fa-exclamation-triangle' : 'fa-arrow-up'}"></i> Update
                                </button>
                            ` : ''}
                            <button
                                class="package-btn package-btn-uninstall"
                                onclick="uninstallPackage('${pkg.name}')"
                                ${isCritical ? 'disabled title="Cannot uninstall critical package"' : ''}
                            >
                                <i class="fas fa-trash"></i> Uninstall
                            </button>
                        </div>
                    </div>
                `;
            });
            packagesList.innerHTML = html;
        } else if (packagesResult.status === 'error') {
            packagesList.innerHTML = `
                <div class="venv-empty">
                    <i class="fas fa-exclamation-triangle"></i>
                    <p>${packagesResult.message || 'Failed to load packages'}</p>
                </div>
            `;
        } else {
            packagesList.innerHTML = `
                <div class="venv-empty">
                    <i class="fas fa-box-open"></i>
                    <p>No packages installed</p>
                </div>
            `;
        }
    } catch (error) {
        console.error('[VENV ERROR]', error);
        packagesList.innerHTML = `
            <div class="venv-empty">
                <i class="fas fa-exclamation-circle"></i>
                <p>Error loading packages: ${error.message}</p>
            </div>
        `;
    }
}

async function installPackage() {
    const input = document.getElementById('packageNameInput');
    const packageName = input.value.trim();

    if (!packageName) {
        showNotification('Input Required', 'Please enter a package name', 'error');
        return;
    }

    console.log(`[VENV] Checking dependencies for: ${packageName}`);

    // Disable install button and show checking status
    const installBtn = document.querySelector('.venv-btn-primary');
    const originalHTML = installBtn.innerHTML;
    installBtn.disabled = true;
    installBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Checking...';

    try {
        // First, check for dependencies and conflicts
        const checkResult = await pywebview.api.check_package_dependencies(packageName);
        console.log('[VENV] Dependency check result:', checkResult);

        if (checkResult.status === 'error') {
            showNotification('Check Failed', checkResult.message, 'error');
            installBtn.disabled = false;
            installBtn.innerHTML = originalHTML;
            return;
        }

        // If there are conflicts with critical packages, show warning
        if (checkResult.has_conflicts) {
            const conflictNames = checkResult.conflicts.map(c => c.name).join(', ');
            const message = `⚠️ WARNING: This package will modify critical Manim dependencies:\n\n${conflictNames}\n\nThis may break Manim functionality. Do you want to continue?`;

            if (!confirm(message)) {
                showNotification('Installation Cancelled', 'Installation cancelled by user', 'info');
                installBtn.disabled = false;
                installBtn.innerHTML = originalHTML;
                return;
            }
        }

        // If there are warnings, show them
        if (checkResult.warnings && checkResult.warnings.length > 0) {
            const warningMsg = `⚠️ Warnings:\n${checkResult.warnings.join('\n')}\n\nContinue with installation?`;
            if (!confirm(warningMsg)) {
                showNotification('Installation Cancelled', 'Installation cancelled by user', 'info');
                installBtn.disabled = false;
                installBtn.innerHTML = originalHTML;
                return;
            }
        }

        // Show dependencies that will be installed
        if (checkResult.dependencies && checkResult.dependencies.length > 1) {
            const depList = checkResult.dependencies.map(d => `${d.name} ${d.version}`).join(', ');
            console.log(`[VENV] Will install: ${depList}`);
        }

        // Proceed with installation
        installBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Installing...';
        console.log(`[VENV] Installing package: ${packageName}`);

        const result = await pywebview.api.install_package(packageName);
        console.log('[VENV] Install result:', result);

        if (result.status === 'success') {
            input.value = ''; // Clear input
            showNotification('Package Installed', `Successfully installed ${packageName}`, 'success');
            // Refresh without checking updates (faster)
            await refreshPackages(false);
        } else {
            showNotification('Installation Failed', result.message, 'error');
        }
    } catch (error) {
        console.error('[VENV ERROR]', error);
        showNotification('Installation Error', error.message, 'error');
    } finally {
        // Re-enable install button
        installBtn.disabled = false;
        installBtn.innerHTML = originalHTML;
    }
}

async function updatePackage(packageName, hasWarning = false) {
    console.log(`[VENV] Updating package: ${packageName}, hasWarning: ${hasWarning}`);

    // If there's a warning, show confirmation dialog
    if (hasWarning) {
        const message = `⚠️ WARNING: Updating ${packageName} may affect Manim compatibility.\n\nThis update could potentially break Manim functionality.\n\nDo you want to continue?`;
        if (!confirm(message)) {
            console.log('[VENV] Update cancelled by user');
            showNotification('Update Cancelled', 'Update cancelled by user', 'info');
            return;
        }
    }

    // Find and disable the update button for this package
    const buttons = document.querySelectorAll('.package-btn-update');
    let targetButton = null;
    buttons.forEach(btn => {
        if (btn.getAttribute('onclick').includes(packageName)) {
            targetButton = btn;
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Updating...';
        }
    });

    try {
        const result = await pywebview.api.update_package(packageName);
        console.log('[VENV] Update result:', result);

        if (result.status === 'success') {
            showNotification('Package Updated', `Successfully updated ${packageName}`, 'success');
            // Refresh and check for more updates (in case dependencies were updated)
            await refreshPackages(true);
        } else {
            showNotification('Update Failed', result.message, 'error');
            if (targetButton) {
                targetButton.disabled = false;
                const icon = hasWarning ? 'fa-exclamation-triangle' : 'fa-arrow-up';
                targetButton.innerHTML = `<i class="fas ${icon}"></i> Update`;
            }
        }
    } catch (error) {
        console.error('[VENV ERROR]', error);
        showNotification('Update Error', error.message, 'error');
        if (targetButton) {
            targetButton.disabled = false;
            targetButton.innerHTML = '<i class="fas fa-arrow-up"></i> Update';
        }
    }
}

async function uninstallPackage(packageName) {
    if (!confirm(`Are you sure you want to uninstall ${packageName}?`)) {
        return;
    }

    console.log(`[VENV] Uninstalling package: ${packageName}`);

    // Find and disable the uninstall button for this package
    const buttons = document.querySelectorAll('.package-btn-uninstall');
    let targetButton = null;
    buttons.forEach(btn => {
        if (btn.getAttribute('onclick').includes(packageName)) {
            targetButton = btn;
            btn.disabled = true;
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Removing...';
        }
    });

    try {
        const result = await pywebview.api.uninstall_package(packageName);
        console.log('[VENV] Uninstall result:', result);

        if (result.status === 'success') {
            showNotification('Package Removed', `Successfully uninstalled ${packageName}`, 'success');
            // Refresh without checking updates (faster)
            await refreshPackages(false);
        } else {
            showNotification('Uninstall Failed', result.message, 'error');
            if (targetButton) {
                targetButton.disabled = false;
                targetButton.innerHTML = '<i class="fas fa-trash"></i> Uninstall';
            }
        }
    } catch (error) {
        console.error('[VENV ERROR]', error);
        showNotification('Uninstall Error', error.message, 'error');
        if (targetButton) {
            targetButton.disabled = false;
            targetButton.innerHTML = '<i class="fas fa-trash"></i> Uninstall';
        }
    }
}

// Auto-refresh packages when venv tab is opened (first time only)
let venvTabLoaded = false;
document.addEventListener('DOMContentLoaded', () => {
    const tabPills = document.querySelectorAll('.tab-pill');
    tabPills.forEach(pill => {
        pill.addEventListener('click', () => {
            const tabName = pill.getAttribute('data-tab');
            if (tabName === 'venv' && !venvTabLoaded) {
                // Load packages list only (no update check) when tab is first opened
                venvTabLoaded = true;
                refreshPackages(false);
            }
        });
    });
});

// ============================================================================
// MISSING REQUIRED PACKAGES CHECK + INSTALL MODAL
// ============================================================================

async function checkMissingRequiredPackages() {
    try {
        const result = await pywebview.api.check_missing_required_packages();
        if (result.status === 'success' && result.missing.length > 0) {
            showMissingPackagesModal(result.missing);
        }
    } catch (e) {
        console.warn('[VENV] check_missing_required_packages error:', e);
    }
}

function showMissingPackagesModal(missingPackages) {
    // Prevent duplicate modals
    if (document.getElementById('missingPkgModal')) return;

    const pkgList = missingPackages.map(p =>
        `<div style="display:flex;align-items:center;gap:8px;padding:8px 12px;background:#1e2433;border-radius:6px;margin-bottom:6px;">
            <span style="color:#f87171;font-size:16px;">⚠</span>
            <span style="color:#e2e8f0;font-family:monospace;font-size:13px;">${p}</span>
        </div>`
    ).join('');

    const modal = document.createElement('div');
    modal.id = 'missingPkgModal';
    modal.style.cssText = `
        position:fixed;top:0;left:0;width:100%;height:100%;
        background:rgba(0,0,0,0.65);z-index:99999;
        display:flex;align-items:center;justify-content:center;
        animation:fadeIn 0.2s ease;
    `;

    modal.innerHTML = `
        <div id="missingPkgBox" style="
            background:#16191f;border:1px solid #2d3748;border-radius:14px;
            width:520px;max-width:95vw;padding:28px;
            box-shadow:0 24px 60px rgba(0,0,0,0.6);
            animation:slideInUp 0.25s ease;
        ">
            <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;">
                <span style="font-size:28px;">📦</span>
                <div>
                    <div style="color:#f1f5f9;font-size:17px;font-weight:700;">Missing Required Packages</div>
                    <div style="color:#94a3b8;font-size:13px;margin-top:2px;">The following packages need to be installed:</div>
                </div>
            </div>

            <div id="missingPkgList" style="margin-bottom:18px;">
                ${pkgList}
            </div>

            <div style="color:#94a3b8;font-size:12px;margin-bottom:20px;line-height:1.6;">
                These packages enable features like <strong style="color:#a78bfa;">IntelliSense / code intelligence</strong>
                in the editor. You can install them now or later from the <strong style="color:#60a5fa;">Packages tab</strong>.
            </div>

            <!-- Terminal output box (hidden until install starts) -->
            <div id="missingPkgTerminal" style="display:none;margin-bottom:16px;">
                <div style="background:#0d1117;border:1px solid #2d3748;border-radius:8px;overflow:hidden;">
                    <div style="background:#1e2433;padding:6px 14px;display:flex;align-items:center;gap:8px;border-bottom:1px solid #2d3748;">
                        <span style="width:10px;height:10px;border-radius:50%;background:#fc5c65;display:inline-block;"></span>
                        <span style="width:10px;height:10px;border-radius:50%;background:#fed330;display:inline-block;"></span>
                        <span style="width:10px;height:10px;border-radius:50%;background:#26de81;display:inline-block;"></span>
                        <span style="color:#718096;font-size:11px;margin-left:6px;font-family:system-ui;">Installation Console</span>
                    </div>
                    <div id="missingPkgLog" style="
                        padding:12px;max-height:220px;overflow-y:auto;
                        font-family:Consolas,Monaco,'Courier New',monospace;
                        font-size:12px;line-height:1.7;color:#a8dadc;
                        white-space:pre-wrap;word-break:break-all;
                    "></div>
                </div>
            </div>

            <!-- Buttons -->
            <div id="missingPkgBtns" style="display:flex;gap:12px;">
                <button id="missingPkgSkip" style="
                    flex:1;padding:11px;border:1px solid #374151;border-radius:8px;
                    background:transparent;color:#94a3b8;font-size:14px;font-weight:600;
                    cursor:pointer;transition:all 0.2s;
                " onmouseover="this.style.background='#1e2433'" onmouseout="this.style.background='transparent'">
                    Skip for now
                </button>
                <button id="missingPkgInstall" style="
                    flex:2;padding:11px;border:none;border-radius:8px;
                    background:linear-gradient(135deg,#667eea,#764ba2);
                    color:white;font-size:14px;font-weight:700;
                    cursor:pointer;transition:all 0.2s;
                " onmouseover="this.style.opacity='0.9'" onmouseout="this.style.opacity='1'">
                    Install Now
                </button>
            </div>

            <!-- Close button (shown after install completes) -->
            <div id="missingPkgClose" style="display:none;">
                <button style="
                    width:100%;padding:11px;border:none;border-radius:8px;
                    background:linear-gradient(135deg,#48bb78,#38a169);
                    color:white;font-size:14px;font-weight:700;cursor:pointer;
                " onclick="document.getElementById('missingPkgModal').remove()">
                    Close
                </button>
            </div>
        </div>
        <style>
            @keyframes slideInUp {
                from { opacity:0; transform:translateY(20px); }
                to   { opacity:1; transform:translateY(0); }
            }
        </style>
    `;

    document.body.appendChild(modal);

    // Skip button
    document.getElementById('missingPkgSkip').addEventListener('click', () => {
        modal.remove();
        // Pre-fill the package search in the venv tab so user can easily find & install
        const pkgInput = document.getElementById('packageNameInput');
        if (pkgInput) pkgInput.value = missingPackages[0];
    });

    // Install button
    document.getElementById('missingPkgInstall').addEventListener('click', async () => {
        const installBtn = document.getElementById('missingPkgInstall');
        const skipBtn    = document.getElementById('missingPkgSkip');
        const terminal   = document.getElementById('missingPkgTerminal');
        const btns       = document.getElementById('missingPkgBtns');

        // Swap UI to terminal mode
        installBtn.disabled = true;
        skipBtn.disabled    = true;
        installBtn.innerHTML = '<span style="display:inline-block;width:14px;height:14px;border:2px solid rgba(255,255,255,0.3);border-top-color:white;border-radius:50%;animation:spin 0.7s linear infinite;margin-right:8px;vertical-align:middle;"></span> Installing...';
        terminal.style.display = 'block';

        try {
            await pywebview.api.install_missing_required_packages(missingPackages);
            // Actual completion handled by window.onMissingPkgDone callback below
        } catch (e) {
            _appendMissingPkgLog('[ERROR] ' + e.message);
            _finishMissingPkgInstall(false);
        }
    });
}

function _appendMissingPkgLog(line) {
    const log = document.getElementById('missingPkgLog');
    if (!log) return;
    const el = document.createElement('div');
    if (line.startsWith('[ERROR]') || line.startsWith('ERROR')) {
        el.style.color = '#fc5c65';
    } else if (line.startsWith('[SUCCESS]') || line.includes('Successfully installed')) {
        el.style.color = '#48bb78';
        el.style.fontWeight = '600';
    } else if (line.startsWith('>>>')) {
        el.style.color = '#a78bfa';
        el.style.fontWeight = '600';
    }
    el.textContent = line;
    log.appendChild(el);
    log.scrollTop = log.scrollHeight;
}

function _finishMissingPkgInstall(success) {
    const btns      = document.getElementById('missingPkgBtns');
    const closeDiv  = document.getElementById('missingPkgClose');
    const pkgList   = document.getElementById('missingPkgList');

    if (btns)     btns.style.display     = 'none';
    if (closeDiv) closeDiv.style.display = 'block';

    if (success) {
        if (pkgList) pkgList.innerHTML = `
            <div style="display:flex;align-items:center;gap:10px;padding:10px 14px;
                        background:#0d2a1a;border:1px solid #48bb78;border-radius:8px;">
                <span style="color:#48bb78;font-size:20px;">✓</span>
                <span style="color:#48bb78;font-weight:600;">All packages installed successfully!</span>
            </div>`;
        _appendMissingPkgLog('[SUCCESS] Installation complete. IntelliSense will activate shortly.');
    } else {
        _appendMissingPkgLog('[ERROR] Installation failed. You can retry from the Packages tab.');
    }
}

// Python calls these via evaluate_js
window.onMissingPkgLog  = (line) => _appendMissingPkgLog(line);
window.onMissingPkgDone = (success) => _finishMissingPkgInstall(success);

// ═══════════════════════════════════════════════════════════════════════
// Feature: Find & Replace Button
// ═══════════════════════════════════════════════════════════════════════
document.getElementById('findReplaceBtn')?.addEventListener('click', () => {
    if (editor) {
        editor.getAction('editor.action.startFindReplaceAction').run();
        editor.focus();
    }
});

// ═══════════════════════════════════════════════════════════════════════
// Feature: Keyboard Shortcuts Map
// ═══════════════════════════════════════════════════════════════════════
(function initShortcutMap() {
    const modal = document.getElementById('shortcutMapModal');
    const closeBtn = document.getElementById('closeShortcutMap');
    const searchInput = document.getElementById('shortcutSearch');
    const openBtn = document.getElementById('shortcutMapBtn');

    function openShortcutMap() {
        if (!modal) return;
        modal.style.display = 'flex';
        setTimeout(() => searchInput?.focus(), 50);
    }
    function closeShortcutMap() {
        if (!modal) return;
        modal.style.display = 'none';
        if (searchInput) searchInput.value = '';
        filterShortcuts('');
    }

    openBtn?.addEventListener('click', openShortcutMap);
    closeBtn?.addEventListener('click', closeShortcutMap);
    modal?.addEventListener('click', (e) => {
        if (e.target === modal) closeShortcutMap();
    });

    // Search/filter
    function filterShortcuts(query) {
        const rows = document.querySelectorAll('.shortcut-row');
        const groups = document.querySelectorAll('.shortcut-group');
        const q = query.toLowerCase().trim();

        rows.forEach(row => {
            const text = row.textContent.toLowerCase();
            row.classList.toggle('hidden', q && !text.includes(q));
        });

        // Hide groups with no visible rows
        groups.forEach(group => {
            const visibleRows = group.querySelectorAll('.shortcut-row:not(.hidden)');
            group.style.display = visibleRows.length === 0 ? 'none' : '';
        });
    }

    searchInput?.addEventListener('input', (e) => filterShortcuts(e.target.value));

    // Global keyboard shortcut: Ctrl+/ (outside Monaco to avoid conflict with toggle comment)
    document.addEventListener('keydown', (e) => {
        // Ctrl+/ when not focused in editor
        if (e.ctrlKey && e.key === '/' && document.activeElement?.id !== 'monacoEditor') {
            // If modal is open, close it; otherwise open it
            if (modal && modal.style.display === 'flex') {
                closeShortcutMap();
            } else {
                openShortcutMap();
            }
        }
        // ESC to close
        if (e.key === 'Escape' && modal && modal.style.display === 'flex') {
            closeShortcutMap();
        }
    });
})();

// ═══════════════════════════════════════════════════════════════════════
// Feature: Scene Outline
// ═══════════════════════════════════════════════════════════════════════
(function initSceneOutline() {
    const panel = document.getElementById('sceneOutlinePanel');
    const tree = document.getElementById('outlineTree');
    const openBtn = document.getElementById('sceneOutlineBtn');
    const closeBtn = document.getElementById('closeOutlineBtn');

    let outlineVisible = false;
    let outlineDebounce = null;

    function toggleOutline() {
        outlineVisible = !outlineVisible;
        if (panel) panel.style.display = outlineVisible ? 'flex' : 'none';
        if (outlineVisible) refreshOutline();
        // Re-layout Monaco editor
        if (editor) setTimeout(() => editor.layout(), 50);
    }

    openBtn?.addEventListener('click', toggleOutline);
    closeBtn?.addEventListener('click', () => {
        outlineVisible = false;
        if (panel) panel.style.display = 'none';
        if (editor) setTimeout(() => editor.layout(), 50);
    });

    // Ctrl+Shift+O to toggle outline
    document.addEventListener('keydown', (e) => {
        if (e.ctrlKey && e.shiftKey && e.key === 'O') {
            e.preventDefault();
            toggleOutline();
        }
    });

    // Parse code to build outline tree
    function parseOutline(code) {
        const lines = code.split('\n');
        const scenes = [];
        let currentScene = null;
        let currentMethod = null;

        for (let i = 0; i < lines.length; i++) {
            const line = lines[i];

            // Detect class definitions (Scene subclasses)
            const classMatch = line.match(/^class\s+(\w+)\s*\(([^)]*)\)\s*:/);
            if (classMatch) {
                currentScene = {
                    name: classMatch[1],
                    parent: classMatch[2].trim(),
                    line: i + 1,
                    methods: []
                };
                scenes.push(currentScene);
                currentMethod = null;
                continue;
            }

            if (!currentScene) continue;

            // Detect method definitions (indented under class)
            const methodMatch = line.match(/^    def\s+(\w+)\s*\(/);
            if (methodMatch) {
                currentMethod = {
                    name: methodMatch[1],
                    line: i + 1,
                    mobjects: []
                };
                currentScene.methods.push(currentMethod);
                continue;
            }

            // Detect Mobject assignments within methods
            if (currentMethod) {
                const mobjectMatch = line.match(/^\s{8}(\w+)\s*=\s*([\w.]+)\s*\(/);
                if (mobjectMatch) {
                    currentMethod.mobjects.push({
                        name: mobjectMatch[1],
                        type: mobjectMatch[2],
                        line: i + 1
                    });
                }
            }
        }
        return scenes;
    }

    function renderOutline(scenes) {
        if (!tree) return;

        if (scenes.length === 0) {
            tree.innerHTML = '<div class="outline-empty"><i class="fas fa-code"></i> No scenes found</div>';
            return;
        }

        let html = '';
        for (const scene of scenes) {
            html += `<div class="outline-scene">`;
            html += `<div class="outline-scene-header" data-line="${scene.line}">
                        <i class="fas fa-chevron-down"></i>
                        <span class="outline-scene-icon"><i class="fas fa-cube"></i></span>
                        ${escapeHtml(scene.name)}
                        <span style="color:var(--text-secondary);font-size:10px;margin-left:auto;">${escapeHtml(scene.parent)}</span>
                     </div>`;
            html += `<div class="outline-children">`;

            for (const method of scene.methods) {
                html += `<div class="outline-method" data-line="${method.line}">
                            <i class="fas fa-cogs"></i>
                            ${escapeHtml(method.name)}()
                         </div>`;
                for (const mob of method.mobjects) {
                    html += `<div class="outline-mobject" data-line="${mob.line}">
                                <i class="fas fa-circle"></i>
                                ${escapeHtml(mob.name)} <span style="color:var(--text-secondary)">${escapeHtml(mob.type)}</span>
                             </div>`;
                }
            }

            html += `</div></div>`;
        }
        tree.innerHTML = html;

        // Click handlers for navigation
        tree.querySelectorAll('[data-line]').forEach(el => {
            el.addEventListener('click', (e) => {
                const line = parseInt(el.dataset.line);
                if (editor && line) {
                    editor.revealLineInCenter(line);
                    editor.setPosition({ lineNumber: line, column: 1 });
                    editor.focus();
                }
            });
        });

        // Collapsible scene headers
        tree.querySelectorAll('.outline-scene-header').forEach(header => {
            header.addEventListener('dblclick', (e) => {
                e.stopPropagation();
                header.classList.toggle('collapsed');
                const children = header.nextElementSibling;
                if (children) children.classList.toggle('hidden');
            });
        });
    }

    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    function refreshOutline() {
        if (!outlineVisible || !editor) return;
        const code = editor.getValue();
        const scenes = parseOutline(code);
        renderOutline(scenes);
    }

    // Refresh outline when code changes (debounced)
    function scheduleOutlineRefresh() {
        if (!outlineVisible) return;
        if (outlineDebounce) clearTimeout(outlineDebounce);
        outlineDebounce = setTimeout(refreshOutline, 1000);
    }

    // Hook into editor content changes
    const origInit = window.initializeEditor;
    const hookEditorChanges = setInterval(() => {
        if (editor) {
            clearInterval(hookEditorChanges);
            editor.onDidChangeModelContent(() => {
                scheduleOutlineRefresh();
            });
        }
    }, 500);

    // Expose for external use
    window.refreshSceneOutline = refreshOutline;
})();

// ═══════════════════════════════════════════════════════════════════════
// Feature: Bracket Pair Colorizer
// ═══════════════════════════════════════════════════════════════════════
(function initBracketColorizer() {
    // Monaco 0.33+ has built-in bracket pair colorization
    const hookEditor = setInterval(() => {
        if (editor && monaco) {
            clearInterval(hookEditor);
            // Enable bracket pair colorization and guides
            editor.updateOptions({
                'bracketPairColorization.enabled': true,
                bracketPairColorization: { enabled: true, independentColorPoolPerBracketType: true },
                guides: {
                    bracketPairs: true,
                    bracketPairsHorizontal: 'active',
                    highlightActiveBracketPair: true,
                    indentation: true,
                    highlightActiveIndentation: true
                },
                matchBrackets: 'always'
            });

            // Define custom bracket colors via CSS injection
            const style = document.createElement('style');
            style.textContent = `
                .bracket-highlighting-0 { color: #ffd700 !important; }
                .bracket-highlighting-1 { color: #da70d6 !important; }
                .bracket-highlighting-2 { color: #179fff !important; }
                .bracket-highlighting-3 { color: #00c853 !important; }
                .bracket-highlighting-4 { color: #ff6b6b !important; }
                .bracket-highlighting-5 { color: #ff9100 !important; }
            `;
            document.head.appendChild(style);
            console.log('[BRACKETS] Bracket pair colorization enabled');
        }
    }, 500);
})();

// ═══════════════════════════════════════════════════════════════════════
// Feature: Auto-Import Fixer for Manim classes
// ═══════════════════════════════════════════════════════════════════════
(function initAutoImportFixer() {
    const MANIM_CLASSES = new Set([
        // Mobjects
        'Circle', 'Square', 'Rectangle', 'Triangle', 'Polygon', 'RegularPolygon',
        'Line', 'Arrow', 'DoubleArrow', 'DashedLine', 'TangentLine', 'Vector',
        'Dot', 'SmallDot', 'Point', 'Annulus', 'AnnularSector', 'Sector', 'Arc',
        'Ellipse', 'Star', 'RoundedRectangle',
        'Text', 'Tex', 'MathTex', 'Title', 'BulletedList', 'Paragraph',
        'MarkupText', 'Code',
        'Axes', 'NumberPlane', 'ComplexPlane', 'NumberLine', 'BarChart',
        'Table', 'MobjectTable', 'IntegerTable', 'DecimalTable',
        'VGroup', 'Group', 'SurroundingRectangle', 'BackgroundRectangle',
        'Brace', 'BraceBetweenPoints', 'BraceLabel',
        'ImageMobject', 'SVGMobject',
        'ThreeDScene', 'Surface', 'Sphere', 'Cube', 'Cylinder', 'Cone',
        'Torus', 'Prism', 'Arrow3D', 'Line3D', 'Dot3D',
        'ThreeDAxes',
        // Animations
        'Create', 'Write', 'DrawBorderThenFill', 'FadeIn', 'FadeOut',
        'GrowFromCenter', 'GrowFromEdge', 'GrowFromPoint', 'GrowArrow',
        'Transform', 'ReplacementTransform', 'TransformFromCopy',
        'MoveToTarget', 'ApplyMethod',
        'Rotate', 'SpinInFromNothing', 'ShrinkToCenter',
        'Indicate', 'Flash', 'ShowPassingFlash', 'Wiggle', 'Circumscribe',
        'FocusOn', 'ApplyWave',
        'AnimationGroup', 'Succession', 'LaggedStart', 'LaggedStartMap',
        'Uncreate', 'Unwrite', 'ShowCreation',
        // Camera / Scenes
        'Scene', 'MovingCameraScene', 'ZoomedScene', 'VectorScene',
        'LinearTransformationScene',
        // Constants/Utils
        'UP', 'DOWN', 'LEFT', 'RIGHT', 'ORIGIN', 'UL', 'UR', 'DL', 'DR',
        'PI', 'TAU', 'DEGREES',
        'RED', 'BLUE', 'GREEN', 'YELLOW', 'WHITE', 'BLACK', 'ORANGE', 'PURPLE',
        'PINK', 'TEAL', 'GOLD', 'MAROON', 'GREY', 'GRAY',
        'rate_functions', 'linear', 'smooth', 'rush_into', 'rush_from',
        'ValueTracker', 'DecimalNumber', 'Integer', 'Variable',
        'always_redraw', 'always',
    ]);

    let autoImportDebounce = null;

    const hookEditor = setInterval(() => {
        if (editor && monaco) {
            clearInterval(hookEditor);

            // Register a code action provider for quick fixes
            monaco.languages.registerCodeActionProvider('python', {
                provideCodeActions(model, range, context) {
                    const code = model.getValue();
                    const lines = code.split('\n');

                    // Check if 'from manim import *' already exists
                    const hasWildcardImport = lines.some(l => /^\s*from\s+manim\s+import\s+\*/.test(l));
                    if (hasWildcardImport) return { actions: [], dispose() {} };

                    // Collect existing specific imports
                    const existingImports = new Set();
                    lines.forEach(l => {
                        const m = l.match(/^\s*from\s+manim(?:\.\w+)*\s+import\s+(.+)/);
                        if (m) m[1].split(',').forEach(name => existingImports.add(name.trim()));
                    });

                    // Scan code for used Manim classes that aren't imported
                    const missingImports = new Set();
                    for (let i = 0; i < lines.length; i++) {
                        // Skip import lines and comments
                        if (/^\s*(from|import)\s/.test(lines[i]) || /^\s*#/.test(lines[i])) continue;
                        const words = lines[i].match(/\b[A-Z]\w+\b/g);
                        if (words) {
                            words.forEach(w => {
                                if (MANIM_CLASSES.has(w) && !existingImports.has(w)) {
                                    missingImports.add(w);
                                }
                            });
                        }
                    }

                    if (missingImports.size === 0) return { actions: [], dispose() {} };

                    const actions = [];

                    // Option 1: Add wildcard import
                    actions.push({
                        title: `Add 'from manim import *'`,
                        kind: 'quickfix',
                        diagnostics: [],
                        edit: {
                            edits: [{
                                resource: model.uri,
                                textEdit: {
                                    range: new monaco.Range(1, 1, 1, 1),
                                    text: 'from manim import *\n'
                                },
                                versionId: model.getVersionId()
                            }]
                        },
                        isPreferred: true
                    });

                    // Option 2: Add specific imports
                    const sortedMissing = [...missingImports].sort();
                    actions.push({
                        title: `Import: ${sortedMissing.join(', ')} from manim`,
                        kind: 'quickfix',
                        diagnostics: [],
                        edit: {
                            edits: [{
                                resource: model.uri,
                                textEdit: {
                                    range: new monaco.Range(1, 1, 1, 1),
                                    text: `from manim import ${sortedMissing.join(', ')}\n`
                                },
                                versionId: model.getVersionId()
                            }]
                        }
                    });

                    return { actions, dispose() {} };
                }
            });

            // Also show a toast notification when missing imports detected
            editor.onDidChangeModelContent(() => {
                if (autoImportDebounce) clearTimeout(autoImportDebounce);
                autoImportDebounce = setTimeout(() => {
                    const code = editor.getValue();
                    const lines = code.split('\n');
                    const hasImport = lines.some(l => /^\s*from\s+manim\s+import/.test(l));
                    if (hasImport) return;

                    // Check if any Manim class is used
                    const usesManim = lines.some(l => {
                        if (/^\s*(from|import|#)/.test(l)) return false;
                        const words = l.match(/\b[A-Z]\w+\b/g);
                        return words && words.some(w => MANIM_CLASSES.has(w));
                    });

                    if (usesManim && !document.getElementById('autoImportToast')) {
                        const toastEl = document.createElement('div');
                        toastEl.id = 'autoImportToast';
                        toastEl.style.cssText = `
                            position:fixed; bottom:60px; right:20px; z-index:10000;
                            background:var(--bg-secondary); border:1px solid var(--border-color);
                            border-left:4px solid #f59e0b; border-radius:8px;
                            padding:10px 14px; box-shadow:0 4px 12px rgba(0,0,0,0.3);
                            display:flex; align-items:center; gap:10px; font-size:13px;
                            color:var(--text-primary); max-width:380px;
                        `;
                        toastEl.innerHTML = `
                            <i class="fas fa-lightbulb" style="color:#f59e0b;font-size:16px;"></i>
                            <span>Missing Manim import detected</span>
                            <button id="autoImportFixBtn" style="
                                background:#f59e0b;color:#000;border:none;border-radius:4px;
                                padding:4px 10px;font-size:12px;font-weight:600;cursor:pointer;
                                white-space:nowrap;
                            ">Fix</button>
                            <button onclick="this.parentElement.remove()" style="
                                background:none;border:none;color:var(--text-secondary);
                                cursor:pointer;font-size:14px;padding:2px 6px;
                            "><i class='fas fa-times'></i></button>
                        `;
                        document.body.appendChild(toastEl);
                        document.getElementById('autoImportFixBtn').addEventListener('click', () => {
                            const model = editor.getModel();
                            model.pushEditOperations([], [{
                                range: new monaco.Range(1, 1, 1, 1),
                                text: 'from manim import *\n'
                            }], () => null);
                            toastEl.remove();
                            toast('Added: from manim import *', 'success');
                        });
                        // Auto-dismiss after 8 seconds
                        setTimeout(() => toastEl?.remove(), 8000);
                    }
                }, 2000);
            });

            console.log('[AUTO-IMPORT] Auto-import fixer initialized');
        }
    }, 500);
})();

// ═══════════════════════════════════════════════════════════════════════
// Feature: Zen Mode (F11)
// ═══════════════════════════════════════════════════════════════════════
(function initZenMode() {
    let zenActive = false;

    function toggleZen() {
        zenActive = !zenActive;
        document.body.classList.toggle('zen-mode', zenActive);
        if (editor) {
            setTimeout(() => editor.layout(), 100);
            editor.focus();
        }
        if (zenActive) {
            toast('Zen Mode — press F11 or Esc to exit', 'info');
        }
    }

    document.addEventListener('keydown', (e) => {
        if (e.key === 'F11') {
            e.preventDefault();
            toggleZen();
        }
        if (e.key === 'Escape' && zenActive) {
            toggleZen();
        }
    });

    window.toggleZenMode = toggleZen;
    console.log('[ZEN] Zen mode initialized (F11)');
})();

// ═══════════════════════════════════════════════════════════════════════
// Feature: Quick Screenshot (Preview Frame Capture)
// ═══════════════════════════════════════════════════════════════════════
(function initScreenshot() {
    document.getElementById('screenshotBtn')?.addEventListener('click', async () => {
        const video = document.getElementById('previewVideo');
        const img = document.getElementById('previewImage');

        let canvas, suggestedName;

        if (video && video.style.display !== 'none' && video.src) {
            // Capture current video frame
            canvas = document.createElement('canvas');
            canvas.width = video.videoWidth || video.clientWidth;
            canvas.height = video.videoHeight || video.clientHeight;
            if (canvas.width === 0 || canvas.height === 0) {
                toast('Video not ready — wait for it to load', 'warning');
                return;
            }
            canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
            suggestedName = 'manim_frame_' + new Date().toISOString().slice(0, 19).replace(/[T:]/g, '-') + '.png';
        } else if (img && img.style.display !== 'none' && img.src) {
            // Capture displayed image
            canvas = document.createElement('canvas');
            canvas.width = img.naturalWidth || img.clientWidth;
            canvas.height = img.naturalHeight || img.clientHeight;
            if (canvas.width === 0 || canvas.height === 0) {
                toast('Image not loaded yet', 'warning');
                return;
            }
            canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
            suggestedName = 'manim_screenshot_' + new Date().toISOString().slice(0, 19).replace(/[T:]/g, '-') + '.png';
        } else {
            toast('No preview to screenshot', 'warning');
            return;
        }

        // Convert canvas to base64 PNG (strip data:image/png;base64, prefix)
        const dataUrl = canvas.toDataURL('image/png');
        const base64Data = dataUrl.split(',')[1];

        if (!base64Data) {
            toast('Failed to capture frame', 'error');
            return;
        }

        // Call Python backend to show native Save As dialog
        try {
            const res = await pywebview.api.save_screenshot(base64Data, suggestedName);
            if (res.status === 'success') {
                toast(`Screenshot saved: ${res.filename}`, 'success');
            } else if (res.status === 'cancelled') {
                toast('Screenshot save cancelled', 'info');
            } else {
                toast(`Screenshot failed: ${res.message}`, 'error');
            }
        } catch (err) {
            toast(`Screenshot failed: ${err.message}`, 'error');
        }
    });
    console.log('[SCREENSHOT] Quick screenshot initialized (native Save As dialog)');
})();

// ═══════════════════════════════════════════════════════════════════════
// Feature: Editor Bookmarks (Ctrl+B toggle, Ctrl+Up/Down navigate)
// ═══════════════════════════════════════════════════════════════════════
(function initBookmarks() {
    let bookmarks = []; // Array of line numbers
    let bookmarkDecorations = [];

    function refreshDecorations() {
        if (!editor) return;
        const decorations = bookmarks.map(line => ({
            range: new monaco.Range(line, 1, line, 1),
            options: {
                isWholeLine: true,
                className: 'bookmark-line',
                glyphMarginClassName: 'bookmark-glyph',
                glyphMarginHoverMessage: { value: '**Bookmark** — Ctrl+Up/Down to navigate' }
            }
        }));
        bookmarkDecorations = editor.deltaDecorations(bookmarkDecorations, decorations);
    }

    function toggleBookmark() {
        if (!editor) return;
        const line = editor.getPosition().lineNumber;
        const idx = bookmarks.indexOf(line);
        if (idx >= 0) {
            bookmarks.splice(idx, 1);
        } else {
            bookmarks.push(line);
            bookmarks.sort((a, b) => a - b);
        }
        refreshDecorations();
    }

    function jumpToBookmark(direction) {
        if (!editor || bookmarks.length === 0) return;
        const currentLine = editor.getPosition().lineNumber;

        let target;
        if (direction === 'next') {
            target = bookmarks.find(b => b > currentLine) || bookmarks[0];
        } else {
            target = [...bookmarks].reverse().find(b => b < currentLine) || bookmarks[bookmarks.length - 1];
        }

        if (target) {
            editor.revealLineInCenter(target);
            editor.setPosition({ lineNumber: target, column: 1 });
            editor.focus();
        }
    }

    const hookEditor = setInterval(() => {
        if (editor && monaco) {
            clearInterval(hookEditor);

            // Ctrl+B: Toggle bookmark
            editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyB, toggleBookmark);

            // Ctrl+Up: Previous bookmark
            editor.addCommand(
                monaco.KeyMod.CtrlCmd | monaco.KeyCode.UpArrow,
                () => jumpToBookmark('prev')
            );

            // Ctrl+Down: Next bookmark
            editor.addCommand(
                monaco.KeyMod.CtrlCmd | monaco.KeyCode.DownArrow,
                () => jumpToBookmark('next')
            );

            // Clean up bookmarks when lines are deleted
            editor.onDidChangeModelContent((e) => {
                if (bookmarks.length === 0) return;
                const lineCount = editor.getModel().getLineCount();
                bookmarks = bookmarks.filter(b => b <= lineCount);
                refreshDecorations();
            });

            console.log('[BOOKMARKS] Editor bookmarks initialized (Ctrl+B, Ctrl+Up/Down)');
        }
    }, 500);

    window.toggleBookmark = toggleBookmark;
    window.getBookmarks = () => [...bookmarks];
})();

// ═══════════════════════════════════════════════════════════════════════
// Feature: Drag & Drop File Open
// ═══════════════════════════════════════════════════════════════════════
(function initDragDrop() {
    const editorContainer = document.getElementById('monacoEditor');
    if (!editorContainer) return;

    const parentBody = editorContainer.closest('.workspace-body');

    let overlay = null;

    function showOverlay() {
        if (overlay) return;
        overlay = document.createElement('div');
        overlay.className = 'dragdrop-overlay';
        overlay.innerHTML = '<span><i class="fas fa-file-import"></i> Drop .py file to open</span>';
        (parentBody || editorContainer).appendChild(overlay);
    }

    function hideOverlay() {
        if (overlay) {
            overlay.remove();
            overlay = null;
        }
    }

    // Use the workspace-body or body as drag target
    const dropTarget = parentBody || document.body;

    dropTarget.addEventListener('dragenter', (e) => {
        e.preventDefault();
        if (e.dataTransfer.types.includes('Files')) showOverlay();
    });

    dropTarget.addEventListener('dragover', (e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'copy';
    });

    dropTarget.addEventListener('dragleave', (e) => {
        // Only hide if leaving the container entirely
        if (!dropTarget.contains(e.relatedTarget)) hideOverlay();
    });

    dropTarget.addEventListener('drop', async (e) => {
        e.preventDefault();
        hideOverlay();

        const files = e.dataTransfer.files;
        if (!files || files.length === 0) return;

        const file = files[0];
        if (!file.name.endsWith('.py') && !file.name.endsWith('.pyw') && !file.name.endsWith('.txt')) {
            toast('Only .py files can be opened in the editor', 'warning');
            return;
        }

        // Read file content using FileReader
        const reader = new FileReader();
        reader.onload = (ev) => {
            const content = ev.target.result;
            if (editor) {
                editor.setValue(content);
                currentFile = null; // Dropped file doesn't have a persistent path via pywebview
                updateCurrentFile(file.name);
                lastSavedCode = content;
                hasUnsavedChanges = false;
                updateSaveStatus('saved');
                toast(`Opened ${file.name} (drag & drop)`, 'success');
            }
        };
        reader.onerror = () => toast('Failed to read dropped file', 'error');
        reader.readAsText(file);
    });

    console.log('[DRAGDROP] Drag-and-drop file open initialized');
})();

// ═══════════════════════════════════════════════════════════════════════
// Feature: Command Palette (Ctrl+Shift+P)
// ═══════════════════════════════════════════════════════════════════════
(function initCommandPalette() {
    const overlay = document.getElementById('commandPalette');
    const input = document.getElementById('commandPaletteInput');
    const results = document.getElementById('commandPaletteResults');
    if (!overlay || !input || !results) return;

    let activeIndex = 0;

    // Command registry
    const commands = [
        { id: 'new-file',        icon: 'fa-file',            label: 'New File',              shortcut: 'Ctrl+N',          action: () => typeof newFile === 'function' && newFile() },
        { id: 'open-file',       icon: 'fa-folder-open',     label: 'Open File',             shortcut: 'Ctrl+O',          action: () => typeof openFile === 'function' && openFile() },
        { id: 'save-file',       icon: 'fa-save',            label: 'Save File',             shortcut: 'Ctrl+S',          action: () => typeof saveFile === 'function' && saveFile() },
        { id: 'save-as',         icon: 'fa-save',            label: 'Save File As...',       shortcut: 'Ctrl+Shift+S',    action: () => typeof saveFileAs === 'function' && saveFileAs() },
        { id: 'render',          icon: 'fa-play',            label: 'Render Animation',      shortcut: 'F5',              action: () => typeof renderAnimation === 'function' && renderAnimation() },
        { id: 'preview',         icon: 'fa-eye',             label: 'Quick Preview',         shortcut: 'F6',              action: () => typeof quickPreview === 'function' && quickPreview() },
        { id: 'stop',            icon: 'fa-stop',            label: 'Stop Render',           shortcut: 'Esc',             action: () => typeof stopRender === 'function' && stopRender() },
        { id: 'find',            icon: 'fa-search',          label: 'Find',                  shortcut: 'Ctrl+F',          action: () => editor?.getAction('editor.action.startFindReplaceAction')?.run() },
        { id: 'find-replace',    icon: 'fa-exchange-alt',    label: 'Find & Replace',        shortcut: 'Ctrl+H',          action: () => editor?.getAction('editor.action.startFindReplaceAction')?.run() },
        { id: 'goto-line',       icon: 'fa-hashtag',         label: 'Go to Line...',         shortcut: 'Ctrl+G',          action: () => editor?.getAction('editor.action.gotoLine')?.run() },
        { id: 'zen-mode',        icon: 'fa-expand',          label: 'Toggle Zen Mode',       shortcut: 'F11',             action: () => typeof toggleZenMode === 'function' && toggleZenMode() },
        { id: 'toggle-comment',  icon: 'fa-comment',         label: 'Toggle Line Comment',   shortcut: 'Ctrl+/',          action: () => editor?.getAction('editor.action.commentLine')?.run() },
        { id: 'format-doc',      icon: 'fa-indent',          label: 'Format Document',       shortcut: 'Shift+Alt+F',     action: () => editor?.getAction('editor.action.formatDocument')?.run() },
        { id: 'shortcuts',       icon: 'fa-keyboard',        label: 'Keyboard Shortcuts',    shortcut: '',                action: () => { const m = document.getElementById('shortcutMapModal'); if (m) m.style.display = 'flex'; } },
        { id: 'outline',         icon: 'fa-sitemap',         label: 'Toggle Scene Outline',  shortcut: 'Ctrl+Shift+O',    action: () => document.getElementById('sceneOutlineBtn')?.click() },
        { id: 'bookmark',        icon: 'fa-bookmark',        label: 'Toggle Bookmark',       shortcut: 'Ctrl+B',          action: () => typeof toggleBookmark === 'function' && toggleBookmark() },
        { id: 'select-all',      icon: 'fa-object-group',    label: 'Select All',            shortcut: 'Ctrl+A',          action: () => editor?.getAction('editor.action.selectAll')?.run() },
        { id: 'toggle-minimap',  icon: 'fa-map',             label: 'Toggle Minimap',        shortcut: '',                action: () => { if (editor) { const cur = editor.getOption(monaco.editor.EditorOption.minimap); editor.updateOptions({ minimap: { enabled: !cur.enabled } }); } } },
        { id: 'toggle-wordwrap', icon: 'fa-align-left',      label: 'Toggle Word Wrap',      shortcut: '',                action: () => { if (editor) { const cur = editor.getOption(monaco.editor.EditorOption.wordWrap); editor.updateOptions({ wordWrap: cur === 'on' ? 'off' : 'on' }); } } },
        { id: 'screenshot',      icon: 'fa-camera',          label: 'Screenshot Preview',    shortcut: '',                action: () => document.getElementById('screenshotBtn')?.click() },
        { id: 'theme',           icon: 'fa-moon',            label: 'Toggle Theme',          shortcut: '',                action: () => document.getElementById('themeBtn')?.click() },
        { id: 'settings',        icon: 'fa-cog',             label: 'Open Settings',         shortcut: '',                action: () => document.getElementById('settingsBtn')?.click() },
        { id: 'colors',          icon: 'fa-palette',         label: 'Open Color Picker',     shortcut: '',                action: () => document.querySelector('.action-btn[onclick*="color" i], #colorPickerBtn, .action-btn:has(.fa-palette)')?.click() },
        { id: 'clear-terminal',  icon: 'fa-eraser',          label: 'Clear Terminal',        shortcut: '',                action: () => document.getElementById('clearTermBtn')?.click() },
        { id: 'ai-edit',         icon: 'fa-wand-magic-sparkles', label: 'Edit with AI (Claude)', shortcut: 'Ctrl+Shift+E', action: () => typeof openAIEdit === 'function' && openAIEdit() },
        { id: 'manim-docs',      icon: 'fa-book',            label: 'Manim Docs Lookup',     shortcut: 'Ctrl+Shift+D',    action: () => typeof openManimDocs === 'function' && openManimDocs() },
    ];

    function openPalette() {
        overlay.style.display = 'flex';
        input.value = '';
        activeIndex = 0;
        renderCommands('');
        setTimeout(() => input.focus(), 50);
    }

    function closePalette() {
        overlay.style.display = 'none';
        input.value = '';
        if (editor) editor.focus();
    }

    function renderCommands(query) {
        const q = query.toLowerCase().trim();
        const filtered = q
            ? commands.filter(c => c.label.toLowerCase().includes(q) || c.id.includes(q))
            : commands;

        if (filtered.length === 0) {
            results.innerHTML = '<div class="cmd-empty">No matching commands</div>';
            return;
        }

        activeIndex = Math.min(activeIndex, filtered.length - 1);

        results.innerHTML = filtered.map((cmd, i) => `
            <div class="cmd-item ${i === activeIndex ? 'active' : ''}" data-idx="${i}">
                <i class="fas ${cmd.icon}"></i>
                <span class="cmd-label">${highlight(cmd.label, q)}</span>
                ${cmd.shortcut ? `<span class="cmd-shortcut">${cmd.shortcut}</span>` : ''}
            </div>
        `).join('');

        // Click handlers
        results.querySelectorAll('.cmd-item').forEach((el, i) => {
            el.addEventListener('click', () => {
                closePalette();
                filtered[i].action();
            });
            el.addEventListener('mouseenter', () => {
                activeIndex = i;
                results.querySelectorAll('.cmd-item').forEach((e, j) =>
                    e.classList.toggle('active', j === i));
            });
        });
    }

    function highlight(text, query) {
        if (!query) return text;
        const idx = text.toLowerCase().indexOf(query);
        if (idx < 0) return text;
        return text.slice(0, idx) + '<b style="color:var(--accent-primary)">' + text.slice(idx, idx + query.length) + '</b>' + text.slice(idx + query.length);
    }

    // Input handling
    input.addEventListener('input', () => {
        activeIndex = 0;
        renderCommands(input.value);
    });

    input.addEventListener('keydown', (e) => {
        const items = results.querySelectorAll('.cmd-item');
        const q = input.value.toLowerCase().trim();
        const filtered = q
            ? commands.filter(c => c.label.toLowerCase().includes(q) || c.id.includes(q))
            : commands;

        if (e.key === 'ArrowDown') {
            e.preventDefault();
            activeIndex = (activeIndex + 1) % Math.max(filtered.length, 1);
            items.forEach((el, i) => el.classList.toggle('active', i === activeIndex));
            items[activeIndex]?.scrollIntoView({ block: 'nearest' });
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            activeIndex = (activeIndex - 1 + filtered.length) % Math.max(filtered.length, 1);
            items.forEach((el, i) => el.classList.toggle('active', i === activeIndex));
            items[activeIndex]?.scrollIntoView({ block: 'nearest' });
        } else if (e.key === 'Enter') {
            e.preventDefault();
            if (filtered[activeIndex]) {
                closePalette();
                filtered[activeIndex].action();
            }
        } else if (e.key === 'Escape') {
            closePalette();
        }
    });

    // Close on overlay click
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) closePalette();
    });

    // Global shortcut: Ctrl+Shift+P
    document.addEventListener('keydown', (e) => {
        if (e.ctrlKey && e.shiftKey && e.key === 'P') {
            e.preventDefault();
            if (overlay.style.display === 'flex') closePalette();
            else openPalette();
        }
    });

    window.openCommandPalette = openPalette;
    console.log('[CMD PALETTE] Command palette initialized (Ctrl+Shift+P)');
})();

// ═══════════════════════════════════════════════════════════════════════
// Feature: AI Code Edit — Side Panel (like Scene Outline)
// ═══════════════════════════════════════════════════════════════════════
(function initAIEdit() {
    const panel       = document.getElementById('aiEditPanel');
    const panelBtn    = document.getElementById('aiEditPanelBtn');
    const panelClose  = document.getElementById('aiEditPanelClose');
    const promptInput = document.getElementById('aiEditPrompt');
    const sendBtn     = document.getElementById('aiEditSendBtn');
    const modelSelect = document.getElementById('aiEditModelSelect');
    const providerSel = document.getElementById('aiEditProviderSelect');
    const searchSection = document.getElementById('aiEditSearchSection');
    const searchToggle  = document.getElementById('aiEditSearchToggle');
    const statusText  = document.getElementById('aiEditStatusText');
    const statusMsg   = document.getElementById('aiEditStatusMsg');
    const diffActions = document.getElementById('aiDiffActions');
    const diffStats   = document.getElementById('aiDiffStats');
    const acceptBtn   = document.getElementById('aiDiffAccept');
    const rejectBtn   = document.getElementById('aiDiffReject');
    const streamBox   = document.getElementById('aiEditStreamBox');
    const streamOutput= document.getElementById('aiEditStreamOutput');
    const contextDiv  = document.getElementById('aiEditContext');
    const contextText = document.getElementById('aiEditContextText');
    const editorEl    = document.getElementById('monacoEditor');
    if (!panel || !editorEl) return;

    let originalCode = '';
    let editedCode = '';
    let diffEditorInstance = null;
    let pollTimer = null;
    let panelVisible = false;
    let isStreaming = false;
    let currentProvider = 'claude';  // 'claude' or 'codex'

    // ── Provider switch logic ──
    function getProvider() { return providerSel ? providerSel.value : 'claude'; }

    function onProviderChange() {
        currentProvider = getProvider();
        const isCodex = currentProvider === 'codex';
        // Update web search hint per provider
        const searchHint = document.getElementById('aiEditSearchHint');
        if (searchHint) searchHint.textContent = isCodex ? '(live results)' : '(WebSearch tool)';
        // Reload models for the new provider
        loadModelsForProvider(currentProvider);
        // Persist choice
        try { localStorage.setItem('ai_edit_provider', currentProvider); } catch(e) {}
    }

    // Restore saved provider
    try {
        const saved = localStorage.getItem('ai_edit_provider');
        if (saved && providerSel) {
            providerSel.value = saved;
            currentProvider = saved;
        }
    } catch(e) {}
    providerSel?.addEventListener('change', onProviderChange);

    // ── Fetch available models per provider ──
    async function loadModelsForProvider(provider) {
        try {
            if (typeof pywebview === 'undefined' || !pywebview.api) {
                await new Promise(r => setTimeout(r, 2000));
            }
            if (typeof pywebview === 'undefined' || !pywebview.api) return;

            let models = [];
            let currentModel = '';

            if (provider === 'codex') {
                if (pywebview.api.get_codex_models) {
                    const result = await pywebview.api.get_codex_models();
                    models = result.models || [];
                }
            } else {
                if (pywebview.api.get_claude_models) {
                    const result = await pywebview.api.get_claude_models();
                    models = result.models || [];
                    currentModel = result.current_model || '';
                }
            }

            if (modelSelect) {
                while (modelSelect.options.length > 1) modelSelect.remove(1);
                for (const m of models) {
                    const opt = document.createElement('option');
                    opt.value = m.id;
                    opt.textContent = m.display_name;
                    modelSelect.appendChild(opt);
                }
            }
            if (currentModel && modelSelect) {
                for (const opt of modelSelect.options) {
                    if (opt.value === currentModel || opt.value.includes(currentModel) || currentModel.includes(opt.value)) {
                        opt.selected = true; break;
                    }
                }
            }
        } catch (e) { console.log('[AI EDIT] Model load:', e); }
    }

    // Initial load
    (async function() {
        onProviderChange();  // sets API key visibility + loads models
    })();

    // ── Toggle the AI Edit panel (like outline toggle) ──
    function togglePanel() {
        panelVisible = !panelVisible;
        panel.style.display = panelVisible ? 'flex' : 'none';
        if (panelVisible) setTimeout(() => promptInput.focus(), 50);
        // Re-layout Monaco editor after panel toggle
        if (editor) setTimeout(() => editor.layout(), 50);
    }

    // ── Update context indicator based on editor selection ──
    function updateContextHint() {
        if (!editor || !contextDiv || !contextText) return;
        const sel = editor.getSelection();
        if (sel && !sel.isEmpty()) {
            const lines = sel.endLineNumber - sel.startLineNumber + 1;
            contextText.textContent = `Selected: lines ${sel.startLineNumber}-${sel.endLineNumber} (${lines} lines)`;
            contextDiv.classList.add('has-selection');
        } else {
            contextText.textContent = 'Editing whole file';
            contextDiv.classList.remove('has-selection');
        }
    }

    // ── Open panel (with optional prefill prompt) ──
    function openAIEdit(prefillPrompt) {
        if (!editor) return;
        originalCode = editor.getModel().getValue();
        if (typeof prefillPrompt === 'string') promptInput.value = prefillPrompt;
        statusText.style.display = 'none';
        diffActions.style.display = 'none';
        if (streamBox) streamBox.style.display = 'none';
        if (!panelVisible) {
            panelVisible = true;
            panel.style.display = 'flex';
            if (editor) setTimeout(() => editor.layout(), 50);
        }
        updateContextHint();
        setTimeout(() => promptInput.focus(), 50);
    }

    // ── Close panel completely ──
    function closePanel() {
        if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
        isStreaming = false;
        try { pywebview?.api?.ai_edit_cancel(); } catch(e) {}
        destroyDiffEditor();
        resetSendBtn();
        diffActions.style.display = 'none';
        if (streamBox) streamBox.style.display = 'none';
        panelVisible = false;
        panel.style.display = 'none';
        // Re-layout Monaco editor
        if (editor) { editor.focus(); setTimeout(() => editor.layout(), 50); }
    }

    // ── Button handlers for open/close ──
    panelBtn?.addEventListener('click', togglePanel);
    panelClose?.addEventListener('click', closePanel);

    // ── Create Monaco DiffEditor over the normal editor ──
    function showDiffEditor(original, modified) {
        let container = document.getElementById('aiDiffContainer');
        if (!container) {
            container = document.createElement('div');
            container.id = 'aiDiffContainer';
            container.style.cssText = 'position:absolute;inset:0;z-index:50;';
            editorEl.style.position = 'relative';
            editorEl.appendChild(container);
        }
        container.style.display = 'block';
        editor.getDomNode().style.visibility = 'hidden';

        const origModel = monaco.editor.createModel(original, 'python');
        const modModel  = monaco.editor.createModel(modified, 'python');

        diffEditorInstance = monaco.editor.createDiffEditor(container, {
            theme: 'vs-dark',
            readOnly: false,
            originalEditable: false,
            renderSideBySide: true,
            automaticLayout: true,
            minimap: { enabled: false },
            scrollBeyondLastLine: false,
            fontSize: editor.getOption(monaco.editor.EditorOption.fontSize),
        });
        diffEditorInstance.setModel({ original: origModel, modified: modModel });

        // Count changes for stats
        setTimeout(() => {
            try {
                const changes = diffEditorInstance.getLineChanges() || [];
                let added = 0, removed = 0;
                for (const c of changes) {
                    removed += Math.max(0, c.originalEndLineNumber - c.originalStartLineNumber + 1);
                    added   += Math.max(0, c.modifiedEndLineNumber - c.modifiedStartLineNumber + 1);
                }
                if (diffStats) diffStats.textContent = `+${added} / -${removed} lines`;
            } catch(e) {}
        }, 300);

        // Show diff review actions in panel
        diffActions.style.display = 'flex';
    }

    function destroyDiffEditor() {
        if (diffEditorInstance) {
            try {
                const origModel = diffEditorInstance.getModel()?.original;
                const modModel  = diffEditorInstance.getModel()?.modified;
                diffEditorInstance.dispose();
                if (origModel) origModel.dispose();
                if (modModel) modModel.dispose();
            } catch(e) {}
            diffEditorInstance = null;
        }
        const container = document.getElementById('aiDiffContainer');
        if (container) container.style.display = 'none';
        if (editor) editor.getDomNode().style.visibility = 'visible';
    }

    // ── Reset send button to default state ──
    function resetSendBtn() {
        isStreaming = false;
        sendBtn.disabled = false;
        const label = getProvider() === 'codex' ? 'Send to Codex' : 'Send to Claude';
        sendBtn.innerHTML = `<i class="fas fa-paper-plane"></i> ${label}`;
        sendBtn.classList.remove('cancel-mode');
        statusText.style.display = 'none';
    }

    // ── Send / Cancel button (toggles based on isStreaming) ──
    sendBtn?.addEventListener('click', async () => {
        if (isStreaming) {
            if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
            try { await pywebview.api.ai_edit_cancel(); } catch(e) {}
            resetSendBtn();
            if (streamBox) streamBox.style.display = 'none';
            toast('Cancelled', 'info');
            return;
        }

        const prompt = promptInput.value.trim();
        if (!prompt) { toast('Enter a prompt', 'warning'); promptInput.focus(); return; }

        originalCode = editor.getModel().getValue();
        isStreaming = true;
        sendBtn.innerHTML = '<i class="fas fa-stop"></i> Cancel';
        sendBtn.classList.add('cancel-mode');
        statusText.style.display = 'flex';
        diffActions.style.display = 'none';
        if (streamBox) streamBox.style.display = 'flex';
        if (streamOutput) streamOutput.textContent = '';

        const provider = getProvider();
        const providerLabel = provider === 'codex' ? 'Codex' : 'Claude Code';
        statusMsg.textContent = `Starting ${providerLabel}...`;

        try {
            const chosenModel = modelSelect ? modelSelect.value : '';

            // Get selection info (VS Code Copilot style — selected code vs whole file)
            const selection = editor.getSelection();
            let selectedCode = '';
            let selStart = 0, selEnd = 0;
            if (selection && !selection.isEmpty()) {
                selectedCode = editor.getModel().getValueInRange(selection);
                selStart = selection.startLineNumber;
                selEnd   = selection.endLineNumber;
            }

            let res;
            const useSearch = searchToggle ? searchToggle.checked : false;
            if (provider === 'codex') {
                res = await pywebview.api.ai_edit_codex(
                    originalCode, prompt, chosenModel, useSearch,
                    selectedCode, selStart, selEnd
                );
            } else {
                res = await pywebview.api.ai_edit_code(
                    originalCode, prompt, chosenModel, useSearch,
                    selectedCode, selStart, selEnd
                );
            }

            if (res.status === 'error') {
                statusMsg.textContent = res.message || 'Failed';
                toast(res.message || 'AI edit failed', 'error');
                resetSendBtn();
                return;
            }

            statusMsg.textContent = `${providerLabel} is generating...`;

            // Both providers use the same poll — Codex CLI also edits files in workspace
            const pollFn = pywebview.api.ai_edit_poll;

            pollTimer = setInterval(async () => {
                try {
                    const poll = await pollFn();
                    if (poll.output && streamOutput) {
                        streamOutput.textContent = poll.output;
                        streamOutput.scrollTop = streamOutput.scrollHeight;
                    }
                    if (poll.status === 'streaming') {
                        statusMsg.textContent = `Generating... (${poll.chars || 0} chars)`;
                    }
                    if (poll.done) {
                        clearInterval(pollTimer); pollTimer = null;
                        if (poll.status === 'success' && poll.edited_code) {
                            editedCode = poll.edited_code;
                            if (streamBox) streamBox.style.display = 'none';
                            showDiffEditor(originalCode, editedCode);
                            toast('Review the diff — Accept or Reject', 'info');
                        } else {
                            statusMsg.textContent = poll.message || 'Failed';
                            toast(poll.message || 'AI edit failed', 'error');
                        }
                        resetSendBtn();
                    }
                } catch (e) { console.error('[AI EDIT] Poll:', e); }
            }, 300);

        } catch (err) {
            statusMsg.textContent = 'Error: ' + err.message;
            toast('AI edit failed', 'error');
            resetSendBtn();
        }
    });

    // ── Accept: apply modified code from diff editor, then auto-save ──
    acceptBtn?.addEventListener('click', () => {
        if (!editor) return;
        let finalCode = editedCode;
        if (diffEditorInstance) {
            try {
                finalCode = diffEditorInstance.getModel().modified.getValue();
            } catch(e) {}
        }
        destroyDiffEditor();
        diffActions.style.display = 'none';
        editor.setValue(finalCode);
        toast('Changes applied & saving...', 'success');
        editor.focus();
        // Auto-save immediately so the AI-edited code is persisted
        if (typeof performAutosave === 'function') {
            performAutosave();
        }
    });

    // ── Reject: discard changes, keep panel open for retry ──
    rejectBtn?.addEventListener('click', () => {
        destroyDiffEditor();
        diffActions.style.display = 'none';
        toast('Changes discarded', 'info');
        promptInput.focus();
    });

    // ── Keyboard shortcuts ──
    promptInput?.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendBtn?.click(); }
        if (e.key === 'Escape') closePanel();
    });

    // Global Escape to close panel
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && panelVisible) closePanel();
    });

    // ── Register Monaco context menu action + keybinding + selection listener ──
    const hookEditor = setInterval(() => {
        if (editor && monaco) {
            clearInterval(hookEditor);
            editor.addAction({
                id: 'ai-edit-code',
                label: 'Edit with AI',
                keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyMod.Shift | monaco.KeyCode.KeyE],
                contextMenuGroupId: '9_ai',
                contextMenuOrder: 1,
                run: openAIEdit
            });
            // Update context hint when selection changes (only when panel is visible)
            editor.onDidChangeCursorSelection(() => {
                if (panelVisible) updateContextHint();
            });
            console.log('[AI EDIT] Panel registered');
        }
    }, 500);

    // ── "Fix with AI" button in error panel ──
    const fixWithAIBtn = document.getElementById('fixWithAIBtn');
    fixWithAIBtn?.addEventListener('click', () => {
        if (!editor) return;
        const errorItems = document.querySelectorAll('#errorsList .error-item');
        if (!errorItems || errorItems.length === 0) { toast('No errors to fix', 'info'); return; }
        const msgs = [];
        errorItems.forEach(item => {
            const loc = item.querySelector('.error-location')?.textContent || '';
            const msg = item.querySelector('.error-message')?.textContent || '';
            if (msg) msgs.push(`${loc}: ${msg}`);
        });
        openAIEdit('Fix the following code errors:\n' + msgs.join('\n'));
    });

    window.openAIEdit = openAIEdit;
})();

// ═══════════════════════════════════════════════════════════════════════
// Feature: Manim Docs Lookup Panel
// ═══════════════════════════════════════════════════════════════════════
(function initManimDocs() {
    const panel     = document.getElementById('manimDocsPanel');
    const closeBtn  = document.getElementById('docsCloseBtn');
    const searchInp = document.getElementById('docsSearchInput');
    const body      = document.getElementById('docsBody');
    if (!panel) return;

    // Comprehensive Manim docs database
    const MANIM_DOCS = {
        // ── Mobjects ──
        Circle:       { cat: 'Mobject', sig: 'Circle(radius=1.0, color=WHITE, fill_opacity=0, **kwargs)', desc: 'A circle. Set fill_opacity=1 for a solid disc.', params: [{n:'radius',d:'float, default 1.0 — Radius in scene units'},{n:'color',d:'Color, default WHITE — Stroke/fill color'},{n:'fill_opacity',d:'float, default 0 — 0=outline, 1=solid'}], ex: 'Circle(radius=2, color=BLUE)\nCircle(fill_color=RED, fill_opacity=1)' },
        Square:       { cat: 'Mobject', sig: 'Square(side_length=2.0, color=WHITE, **kwargs)', desc: 'A square with equal side lengths.', params: [{n:'side_length',d:'float, default 2.0 — Length of each side'}], ex: 'Square(side_length=3, color=GREEN)\nSquare().set_fill(BLUE, opacity=0.5)' },
        Rectangle:    { cat: 'Mobject', sig: 'Rectangle(width=4.0, height=2.0, color=WHITE, **kwargs)', desc: 'A rectangle with configurable dimensions.', params: [{n:'width',d:'float, default 4.0'},{n:'height',d:'float, default 2.0'},{n:'color',d:'Color, default WHITE'}], ex: 'Rectangle(width=6, height=3, color=YELLOW)' },
        Triangle:     { cat: 'Mobject', sig: 'Triangle(**kwargs)', desc: 'An equilateral triangle pointing upward.', params: [], ex: 'Triangle(color=RED, fill_opacity=1)' },
        Line:         { cat: 'Mobject', sig: 'Line(start=LEFT, end=RIGHT, **kwargs)', desc: 'A straight line between two points.', params: [{n:'start',d:'point — Starting position'},{n:'end',d:'point — Ending position'}], ex: 'Line(LEFT, RIGHT, color=BLUE)\nLine(ORIGIN, UP*2)' },
        Arrow:        { cat: 'Mobject', sig: 'Arrow(start=LEFT, end=RIGHT, **kwargs)', desc: 'A line with an arrowhead at the end.', params: [{n:'start',d:'point — Tail position'},{n:'end',d:'point — Head position'},{n:'buff',d:'float — Gap from endpoints'}], ex: 'Arrow(LEFT, RIGHT, color=YELLOW)\nArrow(ORIGIN, UP*2, buff=0)' },
        Dot:          { cat: 'Mobject', sig: 'Dot(point=ORIGIN, radius=0.08, color=WHITE, **kwargs)', desc: 'A small solid dot placed at a point.', params: [{n:'point',d:'np.array — Center position'},{n:'radius',d:'float, default 0.08'}], ex: 'Dot(RIGHT*2, color=RED)\nDot(ORIGIN, radius=0.15)' },
        Text:         { cat: 'Mobject', sig: 'Text(text, font_size=48, color=WHITE, font="")', desc: 'Pango-rendered text (no LaTeX). Supports font selection.', params: [{n:'text',d:'str — The text to display'},{n:'font_size',d:'int, default 48'},{n:'color',d:'Color, default WHITE'},{n:'font',d:'str — Font family name'}], ex: 'Text("Hello!", font_size=72, color=BLUE)\nText("Code", font="Consolas")' },
        MathTex:      { cat: 'Mobject', sig: 'MathTex(*strings, **kwargs)', desc: 'LaTeX math mode. Strings are joined and wrapped in $$.', params: [{n:'*strings',d:'str — LaTeX expressions'}], ex: 'MathTex(r"E = mc^2")\nMathTex(r"\\int_0^1 x^2 dx")' },
        Tex:          { cat: 'Mobject', sig: 'Tex(*strings, **kwargs)', desc: 'LaTeX text mode for prose with occasional math.', params: [{n:'*strings',d:'str — LaTeX text strings'}], ex: 'Tex("Hello ", "$x^2$", " World")' },
        Axes:         { cat: 'Mobject', sig: 'Axes(x_range=[-1,1,1], y_range=[-1,1,1], x_length=12, y_length=6)', desc: 'A pair of axes for plotting functions.', params: [{n:'x_range',d:'[min, max, step]'},{n:'y_range',d:'[min, max, step]'},{n:'x_length',d:'float — Width in scene units'},{n:'y_length',d:'float — Height in scene units'}], ex: 'ax = Axes(x_range=[-3,3,1], y_range=[-2,2,1])\ngraph = ax.plot(lambda x: x**2, color=BLUE)' },
        NumberPlane:  { cat: 'Mobject', sig: 'NumberPlane(**kwargs)', desc: 'Full coordinate plane with labeled axes and grid.', params: [{n:'x_range',d:'[min, max, step]'},{n:'y_range',d:'[min, max, step]'}], ex: 'plane = NumberPlane()\nself.add(plane)' },
        VGroup:       { cat: 'Mobject', sig: 'VGroup(*mobjects)', desc: 'Group of VMobjects that can be transformed together.', params: [{n:'*mobjects',d:'VMobject — Objects to group'}], ex: 'g = VGroup(Circle(), Square()).arrange(RIGHT)\nself.play(Create(g))' },
        SurroundingRectangle: { cat: 'Mobject', sig: 'SurroundingRectangle(mobject, buff=0.2, color=YELLOW)', desc: 'A tight rectangle that fits around a mobject.', params: [{n:'mobject',d:'Mobject — Target to surround'},{n:'buff',d:'float — Padding around target'},{n:'color',d:'Color'}], ex: 'rect = SurroundingRectangle(text, color=RED)' },
        Brace:        { cat: 'Mobject', sig: 'Brace(mobject, direction=DOWN)', desc: 'A curly brace. Use get_tip() to position a label.', params: [{n:'mobject',d:'Mobject — Target'},{n:'direction',d:'vector — Direction brace points'}], ex: 'brace = Brace(square, DOWN)\nlabel = brace.get_tex("x^2")' },
        ValueTracker: { cat: 'Mobject', sig: 'ValueTracker(value=0)', desc: 'Holds a numeric value. Use for smooth value animations.', params: [{n:'value',d:'float — Initial value'}], ex: 't = ValueTracker(0)\nnum = always_redraw(lambda: DecimalNumber(t.get_value()))\nself.play(t.animate.set_value(10), run_time=3)' },
        // ── Animations ──
        Create:       { cat: 'Animation', sig: 'Create(mobject)', desc: 'Animate drawing the outline and fill of a mobject.', params: [{n:'mobject',d:'Mobject — Object to create'}], ex: 'self.play(Create(circle))' },
        Write:        { cat: 'Animation', sig: 'Write(mobject)', desc: 'Animate writing text or path stroke by stroke.', params: [{n:'mobject',d:'Mobject — Text or path to write'}], ex: 'self.play(Write(Text("Hello")))' },
        FadeIn:       { cat: 'Animation', sig: 'FadeIn(mobject, shift=ORIGIN, scale=1)', desc: 'Fade into view with optional directional shift.', params: [{n:'mobject',d:'Mobject'},{n:'shift',d:'vector — Direction to slide from'},{n:'scale',d:'float — Starting scale'}], ex: 'self.play(FadeIn(text, shift=UP))\nself.play(FadeIn(circle, scale=0.5))' },
        FadeOut:      { cat: 'Animation', sig: 'FadeOut(mobject, shift=ORIGIN)', desc: 'Fade out with optional directional shift.', params: [{n:'mobject',d:'Mobject'},{n:'shift',d:'vector — Direction to slide out'}], ex: 'self.play(FadeOut(text, shift=DOWN))' },
        Transform:    { cat: 'Animation', sig: 'Transform(source, target)', desc: 'Morph source into target. Source object stays in scene.', params: [{n:'source',d:'Mobject — Original'},{n:'target',d:'Mobject — Target shape'}], ex: 'self.play(Transform(circle, square))' },
        ReplacementTransform: { cat: 'Animation', sig: 'ReplacementTransform(source, target)', desc: 'Morph source into target, replacing source in scene.', params: [{n:'source',d:'Mobject'},{n:'target',d:'Mobject'}], ex: 'self.play(ReplacementTransform(circle, square))' },
        Indicate:     { cat: 'Animation', sig: 'Indicate(mobject, color=YELLOW, scale_factor=1.2)', desc: 'Briefly scale up and change color to draw attention.', params: [{n:'mobject',d:'Mobject'},{n:'color',d:'Color, default YELLOW'},{n:'scale_factor',d:'float, default 1.2'}], ex: 'self.play(Indicate(text))' },
        Flash:        { cat: 'Animation', sig: 'Flash(point, color=YELLOW, num_lines=12)', desc: 'Radial flash lines at a point.', params: [{n:'point',d:'point or Mobject'},{n:'color',d:'Color'},{n:'num_lines',d:'int — Number of rays'}], ex: 'self.play(Flash(ORIGIN, color=RED))' },
        Circumscribe: { cat: 'Animation', sig: 'Circumscribe(mobject, shape=Rectangle)', desc: 'Draw a shape around the mobject then fade it.', params: [{n:'mobject',d:'Mobject'},{n:'shape',d:'class — Rectangle or Circle'}], ex: 'self.play(Circumscribe(equation))' },
        GrowFromCenter: { cat: 'Animation', sig: 'GrowFromCenter(mobject)', desc: 'Scale up from zero at the center.', params: [{n:'mobject',d:'Mobject'}], ex: 'self.play(GrowFromCenter(circle))' },
        Rotate:       { cat: 'Animation', sig: 'Rotate(mobject, angle=TAU, axis=OUT)', desc: 'Rotate a mobject by the given angle.', params: [{n:'mobject',d:'Mobject'},{n:'angle',d:'float — Radians (TAU=full rotation)'},{n:'axis',d:'vector — Rotation axis'}], ex: 'self.play(Rotate(square, angle=PI/2))\nself.play(Rotate(cube, angle=TAU, axis=UP))' },
        AnimationGroup: { cat: 'Animation', sig: 'AnimationGroup(*animations, lag_ratio=0)', desc: 'Run multiple animations simultaneously.', params: [{n:'*animations',d:'Animation'},{n:'lag_ratio',d:'float — Stagger between 0 and 1'}], ex: 'self.play(AnimationGroup(\n    Create(c1), Create(c2), lag_ratio=0.3\n))' },
        LaggedStart:  { cat: 'Animation', sig: 'LaggedStart(*animations, lag_ratio=0.05)', desc: 'Start each animation slightly after the previous.', params: [{n:'*animations',d:'Animation'},{n:'lag_ratio',d:'float — Delay between starts'}], ex: 'circles = [Circle() for _ in range(5)]\nself.play(LaggedStart(*[Create(c) for c in circles]))' },
        Succession:   { cat: 'Animation', sig: 'Succession(*animations)', desc: 'Run animations one after another in sequence.', params: [{n:'*animations',d:'Animation'}], ex: 'self.play(Succession(\n    Create(circle), FadeOut(circle)\n))' },
        // ── Scene Methods ──
        play:         { cat: 'Scene Method', sig: 'self.play(*animations, run_time=1, rate_func=smooth)', desc: 'Play one or more animations.', params: [{n:'*animations',d:'Animation — Animations to play'},{n:'run_time',d:'float — Duration in seconds'},{n:'rate_func',d:'function — Easing (smooth, linear, rush_into)'}], ex: 'self.play(Create(circle), run_time=2)\nself.play(Transform(a, b), rate_func=linear)' },
        wait:         { cat: 'Scene Method', sig: 'self.wait(duration=1)', desc: 'Pause the animation for a duration.', params: [{n:'duration',d:'float — Seconds to wait'}], ex: 'self.wait(2)' },
        add:          { cat: 'Scene Method', sig: 'self.add(*mobjects)', desc: 'Add mobjects to the scene without animation.', params: [{n:'*mobjects',d:'Mobject'}], ex: 'self.add(circle, text)' },
        remove:       { cat: 'Scene Method', sig: 'self.remove(*mobjects)', desc: 'Remove mobjects from the scene without animation.', params: [{n:'*mobjects',d:'Mobject'}], ex: 'self.remove(circle)' },
    };

    const allNames = Object.keys(MANIM_DOCS).sort();

    function openDocsPanel() { panel.classList.add('open'); }
    function closeDocsPanel() { panel.classList.remove('open'); if (editor) editor.focus(); }

    closeBtn?.addEventListener('click', closeDocsPanel);

    function showDocFor(name) {
        // Case-insensitive lookup: try exact, then Title Case, then scan all keys
        let doc = MANIM_DOCS[name];
        let resolvedName = name;
        if (!doc) {
            const titleCase = name.charAt(0).toUpperCase() + name.slice(1);
            if (MANIM_DOCS[titleCase]) { doc = MANIM_DOCS[titleCase]; resolvedName = titleCase; }
        }
        if (!doc) {
            const lower = name.toLowerCase();
            const found = allNames.find(n => n.toLowerCase() === lower);
            if (found) { doc = MANIM_DOCS[found]; resolvedName = found; }
        }
        if (!doc) {
            // No exact match — show browse list filtered by the query
            body.innerHTML = `<div style="color:var(--text-secondary);font-size:13px;padding:8px 0;margin-bottom:8px;">No exact match for <b>${escapeH(name)}</b>. Showing related results:</div>`;
            const q = name.toLowerCase();
            const matches = allNames.filter(n => n.toLowerCase().includes(q) || (MANIM_DOCS[n]?.cat || '').toLowerCase().includes(q));
            if (matches.length > 0) {
                body.innerHTML += matches.map(n => {
                    const d = MANIM_DOCS[n];
                    return `<div class="docs-browse-item" data-name="${escapeAttr(n)}"><span class="item-name">${escapeH(n)}</span><span class="item-type">${escapeH(d?.cat || '')}</span></div>`;
                }).join('');
                body.querySelectorAll('.docs-browse-item').forEach(el => {
                    el.addEventListener('click', () => showDocFor(el.dataset.name));
                });
            } else {
                showBrowseList('');
            }
            openDocsPanel();
            return;
        }
        name = resolvedName;

        let html = '';
        html += `<div class="docs-class-name">${escapeH(name)}</div>`;
        html += `<div style="font-size:11px;color:var(--text-secondary);margin-bottom:8px;">${escapeH(doc.cat)}</div>`;
        html += `<div class="docs-signature">${escapeH(doc.sig)}</div>`;
        html += `<div class="docs-description">${escapeH(doc.desc)}</div>`;

        if (doc.params && doc.params.length > 0) {
            html += `<div class="docs-params-title">Parameters</div>`;
            for (const p of doc.params) {
                html += `<div class="docs-param"><span class="docs-param-name">${escapeH(p.n)}</span><div class="docs-param-desc">${escapeH(p.d)}</div></div>`;
            }
        }

        if (doc.ex) {
            html += `<div class="docs-example-title">Example</div>`;
            html += `<div class="docs-example" data-code="${escapeAttr(doc.ex)}">${escapeH(doc.ex)}</div>`;
        }

        body.innerHTML = html;

        // Click example to insert into editor
        body.querySelectorAll('.docs-example').forEach(el => {
            el.addEventListener('click', () => {
                if (!editor) return;
                const code = el.dataset.code;
                editor.trigger('docs', 'type', { text: code });
                editor.focus();
                toast('Code inserted', 'success');
            });
        });

        openDocsPanel();
    }

    function showBrowseList(query) {
        const q = query.toLowerCase().trim();
        const matches = q
            ? allNames.filter(n => n.toLowerCase().includes(q) || (MANIM_DOCS[n]?.cat || '').toLowerCase().includes(q))
            : allNames;

        if (matches.length === 0) {
            body.innerHTML = '<div class="docs-empty">No results</div>';
            return;
        }

        body.innerHTML = matches.map(name => {
            const doc = MANIM_DOCS[name];
            return `<div class="docs-browse-item" data-name="${escapeAttr(name)}">
                <span class="item-name">${escapeH(name)}</span>
                <span class="item-type">${escapeH(doc?.cat || '')}</span>
            </div>`;
        }).join('');

        body.querySelectorAll('.docs-browse-item').forEach(el => {
            el.addEventListener('click', () => showDocFor(el.dataset.name));
        });
    }

    // Search input
    searchInp?.addEventListener('input', (e) => {
        const q = e.target.value.trim();
        if (q.length > 0) {
            showBrowseList(q);
        } else {
            body.innerHTML = '<div class="docs-empty"><i class="fas fa-book-open"></i>Right-click a Manim class in the editor<br>and select <b>Lookup Manim Docs</b><br><br>Or search above to browse</div>';
        }
    });

    // If input is focused and empty, show full list
    searchInp?.addEventListener('focus', () => {
        if (!searchInp.value.trim()) showBrowseList('');
    });

    function escapeH(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
    function escapeAttr(s) { return String(s).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

    // Register Monaco context menu action
    const hookEditor = setInterval(() => {
        if (editor && monaco) {
            clearInterval(hookEditor);
            editor.addAction({
                id: 'lookup-manim-docs',
                label: 'Lookup Manim Docs',
                keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyMod.Shift | monaco.KeyCode.KeyD],
                contextMenuGroupId: '9_ai',
                contextMenuOrder: 2,
                run: () => {
                    const word = editor.getModel().getWordAtPosition(editor.getPosition());
                    if (word && word.word) {
                        searchInp.value = word.word;
                        showDocFor(word.word);
                    } else {
                        openDocsPanel();
                        searchInp.focus();
                    }
                }
            });
            console.log('[DOCS] Manim docs context menu action registered');
        }
    }, 500);

    window.openManimDocs = (name) => { if (name) showDocFor(name); else openDocsPanel(); };
})();
