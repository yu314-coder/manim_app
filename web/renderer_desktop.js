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
            setEditorValue(res.code);
            currentFile = null;
            updateCurrentFile('Untitled');
            toast('New file created', 'success');
            focusEditor();
        }
    } catch (err) {
        toast(`Error: ${err.message}`, 'error');
    }
}

async function openFile() {
    try {
        const res = await pywebview.api.open_file_dialog();
        if (res.status === 'success') {
            setEditorValue(res.code);
            currentFile = res.path;
            updateCurrentFile(res.filename);
            updateLineCount();
            updateCursor();
            focusEditor();
            toast(`Opened ${res.filename}`, 'success');
        }
    } catch (err) {
        toast(`Open failed: ${err.message}`, 'error');
    }
}

async function saveFile() {
    try {
        console.log('[SAVE] saveFile() called');
        const code = getEditorValue();
        console.log(`[SAVE] Current file path: ${currentFile}`);
        console.log(`[SAVE] Calling pywebview.api.save_file()`);
        const res = await pywebview.api.save_file(code, currentFile);
        console.log('[SAVE] API response:', res);

        if (res.status === 'success') {
            currentFile = res.path;
            updateCurrentFile(res.filename);
            toast('File saved', 'success');
            // Update save status
            lastSavedCode = code;
            updateSaveStatus('saved');
        } else if (res.status === 'cancelled') {
            console.log('[SAVE] Save cancelled by user');
            toast('Save cancelled', 'info');
        } else {
            console.log('[SAVE] Save failed:', res.message);
            toast(`Save failed: ${res.message}`, 'error');
        }
    } catch (err) {
        console.error('[SAVE] Exception:', err);
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
            // Update save status
            lastSavedCode = code;
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

    // Just run the command in terminal - no UI messages
    try {
        const res = await pywebview.api.render_animation(code, quality, fps, gpuEnabled);

        if (res.status === 'error') {
            toast(`Render failed: ${res.message}`, 'error');
        }
    } catch (err) {
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

    // Just run the command in terminal - no UI messages
    try {
        const res = await pywebview.api.quick_preview(code, quality, fps, gpuEnabled);

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
async function showPreview(filePath) {
    console.log('[PREVIEW] showPreview called with path:', filePath);

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

    // If we're already showing this exact file, don't reload it (prevents vanishing)
    if (currentPreviewPath === filePath) {
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
        // Get file as bytes from backend and convert to Blob
        console.log('[PREVIEW] Requesting file bytes from backend...');
        const result = await pywebview.api.get_asset_as_bytes(filePath);

        console.log('[PREVIEW] Backend response:', result.status);

        if (result.status !== 'success' || !result.data) {
            filenameSpan.textContent = `Error: ${result.message || 'Failed to load'}`;
            if (placeholder) placeholder.style.display = 'flex';
            return;
        }

        // Convert base64 to Blob
        console.log('[PREVIEW] Converting base64 to Blob...');
        console.log('[PREVIEW] Base64 data length:', result.data.length, 'chars');
        console.log('[PREVIEW] Expected file size:', result.size, 'bytes');

        const binaryString = atob(result.data);
        console.log('[PREVIEW] Decoded binary string length:', binaryString.length, 'bytes');

        const bytes = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) {
            bytes[i] = binaryString.charCodeAt(i);
        }
        console.log('[PREVIEW] Created byte array length:', bytes.length);

        const blob = new Blob([bytes], { type: result.mimeType });

        // Revoke old blob URL if it exists (before creating new one)
        if (currentPreviewBlobUrl) {
            console.log('[PREVIEW] Revoking old blob URL:', currentPreviewBlobUrl);
            URL.revokeObjectURL(currentPreviewBlobUrl);
            currentPreviewBlobUrl = null;
        }

        const blobUrl = URL.createObjectURL(blob);
        currentPreviewBlobUrl = blobUrl; // Track the new blob URL

        console.log('[PREVIEW] Created Blob, size:', blob.size, 'bytes');
        console.log('[PREVIEW] Created Blob URL:', blobUrl);
        console.log('[PREVIEW] Blob type:', blob.type);

        // Video formats
        if (ext === 'mp4' || ext === 'mov' || ext === 'webm' || ext === 'avi') {
            console.log('[PREVIEW] Displaying NEW video with Blob URL:', blobUrl);

            // Set up event handlers before setting src
            previewVideo.onerror = (e) => {
                console.error('========== VIDEO LOAD ERROR ==========');
                console.error('[PREVIEW] Error loading video:', filename);
                console.error('[PREVIEW] Error event:', e);
                console.error('[PREVIEW] Video src that failed:', previewVideo.src);
                console.error('[PREVIEW] Video currentSrc:', previewVideo.currentSrc);
                console.error('[PREVIEW] Video error code:', previewVideo.error ? previewVideo.error.code : 'unknown');
                console.error('[PREVIEW] Video error message:', previewVideo.error ? previewVideo.error.message : 'unknown');
                console.error('[PREVIEW] Video networkState:', previewVideo.networkState);
                console.error('[PREVIEW] Video readyState:', previewVideo.readyState);

                // Error codes: 1=ABORTED, 2=NETWORK, 3=DECODE, 4=SRC_NOT_SUPPORTED
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
                console.log('========== VIDEO LOADED SUCCESSFULLY ==========');
                console.log('[PREVIEW] ✅ Video loaded:', filename);
                console.log('[PREVIEW] Video duration:', previewVideo.duration, 'seconds');
                console.log('[PREVIEW] Video dimensions:', previewVideo.videoWidth, 'x', previewVideo.videoHeight);
                console.log('[PREVIEW] Video readyState:', previewVideo.readyState);
                console.log('==============================================');
            };

            previewVideo.onloadstart = () => {
                console.log('[PREVIEW] 🔄 Video load started:', filename);
            };

            previewVideo.onprogress = () => {
                console.log('[PREVIEW] 📊 Video loading progress...');
            };

            previewVideo.oncanplay = () => {
                console.log('[PREVIEW] ▶️ Video can play:', filename);
            };

            // Use Blob URL from converted bytes
            console.log('[PREVIEW] ========== SETTING VIDEO SOURCE ==========');
            console.log('[PREVIEW] Source type: Blob URL');
            console.log('[PREVIEW] Blob URL:', blobUrl);
            console.log('[PREVIEW] File size:', result.size, 'bytes');
            console.log('[PREVIEW] MIME type:', result.mimeType);
            console.log('[PREVIEW] =======================================');

            previewVideo.src = blobUrl;

            // Show video element
            previewVideo.style.display = 'block';

            // Trigger load() to load the new source
            previewVideo.load();

            // Attempt autoplay
            previewVideo.play().catch(() => {
                console.log('[PREVIEW] Autoplay prevented (user interaction required)');
            });

            console.log('[PREVIEW] ✅ Preview box updated with new video');
        }
        // Image formats
        else if (ext === 'png' || ext === 'jpg' || ext === 'jpeg' || ext === 'gif' || ext === 'webp') {
            console.log('[PREVIEW] Displaying NEW image with HTTP URL:', result.dataUrl.substring(0, 50) + '...');

            // Set up event handlers before setting src
            previewImage.onload = () => {
                console.log('[PREVIEW] ✅ NEW image loaded successfully:', filename);
                filenameSpan.textContent = filename;
            };

            previewImage.onerror = () => {
                console.error('[PREVIEW] Error loading image:', filename);
                filenameSpan.textContent = `Error loading ${filename}`;
            };

            // Use relative path directly (PyWebView can access web directory files)
            console.log('[PREVIEW] Setting image source:', result.dataUrl);

            // Add cache-busting parameter
            const cacheBuster = Date.now();
            const imageUrl = result.dataUrl.includes('?')
                ? `${result.dataUrl}&_=${cacheBuster}`
                : `${result.dataUrl}?_=${cacheBuster}`;

            console.log('[PREVIEW] Final image URL:', imageUrl);
            previewImage.src = imageUrl;

            // Show image element
            previewImage.style.display = 'block';

            console.log('[PREVIEW] ✅ Preview box updated with new image');
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

    // Auto-show in main preview box and switch to workspace tab
    if (outputPath) {
        console.log('🎬 Auto-loading preview...');
        showPreview(outputPath);

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

    // Auto-show in main preview box and switch to workspace tab
    if (outputPath) {
        console.log('🎬 Auto-loading preview from assets folder...');
        console.log('   Path:', outputPath);

        // Load preview using get_asset_as_data_url for HTTP URL
        showPreview(outputPath);

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

// CACHE BUSTER - Version 2025-01-25-v9
// ASSETS WORKFLOW: Render → Move to assets → Auto-save dialog → User chooses location
console.log('[RENDERER] Loaded renderer_desktop.js - Version 2025-01-25-v9 - ASSETS WORKFLOW');
console.log('[RENDERER] ✅ Render: Move to assets → Auto-save dialog → User saves to location');

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
    let currentPollInterval = 20; // Start fast
    const MIN_INTERVAL = 20;      // Fastest: 20ms when active
    const MAX_INTERVAL = 100;     // Slowest: 100ms when idle
    const EMPTY_POLLS_THRESHOLD = 10; // After 10 empty polls, slow down

    // Throttle scroll operations using requestAnimationFrame
    let scrollPending = false;
    const scheduleScroll = () => {
        if (!scrollPending) {
            scrollPending = true;
            requestAnimationFrame(() => {
                if (term && typeof term.scrollToBottom === 'function') {
                    term.scrollToBottom();
                }
                // Fallback scroll method
                const viewport = document.querySelector('.xterm-viewport');
                if (viewport) {
                    viewport.scrollTop = viewport.scrollHeight;
                }
                scrollPending = false;
            });
        }
    };

    const poll = async () => {
        try {
            const res = await pywebview.api.get_terminal_output();
            if (res.status === 'success' && res.output && term) {
                if (res.output.length > 0) {
                    // Got output - write it
                    term.write(res.output);

                    // Schedule scroll (throttled with RAF)
                    scheduleScroll();

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
        document.getElementById('formatSelect').value = settings.format || 'MP4 Video';

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
