// Manim Studio Desktop UI - Main JavaScript
// Uses Eel to communicate with Python backend

// State
let currentFile = null;
let editor = null;
let settings = {
    quality: '720p',
    fps: 30,
    format: 'mp4',
    theme: 'monokai',
    intellisense: true,
    autoPreview: false
};

// Toast notification helper
function showToast(message, type = 'info') {
    const bgColors = {
        success: 'linear-gradient(to right, #16a085, #1abc9c)',
        error: 'linear-gradient(to right, #e74c3c, #c0392b)',
        warning: 'linear-gradient(to right, #f39c12, #e67e22)',
        info: 'linear-gradient(to right, #3498db, #2980b9)'
    };

    Toastify({
        text: message,
        duration: 3000,
        gravity: "top",
        position: "right",
        style: {
            background: bgColors[type] || bgColors.info
        }
    }).showToast();
}

// Initialize CodeMirror editor
function initializeEditor() {
    const textarea = document.getElementById('codeEditor');

    editor = CodeMirror.fromTextArea(textarea, {
        mode: 'python',
        theme: settings.theme,
        lineNumbers: true,
        autoCloseBrackets: true,
        matchBrackets: true,
        indentUnit: 4,
        indentWithTabs: false,
        lineWrapping: false,
        extraKeys: {
            'Ctrl-Space': 'autocomplete',
            'Ctrl-S': () => { saveFile(); return false; },
            'Ctrl-N': () => { newFile(); return false; },
            'Ctrl-O': () => { openFile(); return false; },
            'F5': () => { renderAnimation(); return false; },
            'F6': () => { quickPreview(); return false; }
        }
    });

    // Load initial code
    eel.get_code()(function(result) {
        if (result && result.code) {
            editor.setValue(result.code);
        } else {
            // Set default content
            editor.setValue(`from manim import *

class MyScene(Scene):
    def construct(self):
        # Your animation code here
        text = Text("Hello, Manim!")
        self.play(Write(text))
        self.wait()
`);
        }
    });

    // Update status bar on cursor activity
    editor.on('cursorActivity', updateCursorPosition);
    editor.on('change', updateLineCount);

    updateLineCount();
}

// Navigation
function switchPanel(panelId) {
    // Hide all panels
    document.querySelectorAll('.panel').forEach(panel => {
        panel.classList.remove('active');
    });

    // Remove active state from all nav items
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.remove('active');
    });

    // Show selected panel
    const panel = document.getElementById(`${panelId}-panel`);
    if (panel) {
        panel.classList.add('active');
    }

    // Add active state to clicked nav item
    const navItem = document.querySelector(`[data-panel="${panelId}"]`);
    if (navItem) {
        navItem.classList.add('active');
    }
}

// File Operations
async function newFile() {
    eel.new_file()(function(data) {
        if (data.status === 'success') {
            editor.setValue(data.code);
            currentFile = null;
            updateCurrentFile('Untitled');
            addOutput('Created new file', 'info');
            showToast('New file created', 'success');
        }
    });
}

function openFile() {
    // Use native file dialog
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.py';
    input.onchange = (e) => {
        const file = e.target.files[0];
        if (!file) return;

        const reader = new FileReader();
        reader.onload = (event) => {
            const content = event.target.result;
            editor.setValue(content);
            currentFile = file.path || file.name;
            updateCurrentFile(file.name);
            addOutput(`Opened ${file.name}`, 'success');
            showToast(`Opened ${file.name}`, 'success');
        };
        reader.readAsText(file);
    };
    input.click();
}

async function saveFile() {
    if (!currentFile) {
        saveFileAs();
        return;
    }

    const code = editor.getValue();

    eel.save_file(currentFile, code)(function(data) {
        if (data.status === 'success') {
            addOutput(`Saved ${currentFile}`, 'success');
            showToast('File saved successfully', 'success');

            if (settings.autoPreview) {
                quickPreview();
            }
        } else {
            addOutput(`Error saving file: ${data.message}`, 'error');
            showToast(`Error: ${data.message}`, 'error');
        }
    });
}

function saveFileAs() {
    const filename = prompt('Enter filename:', 'scene.py');
    if (filename) {
        currentFile = filename;
        saveFile();
    }
}

// Render Operations
async function renderAnimation() {
    const code = editor.getValue();
    const quality = document.getElementById('qualitySelect').value;
    const fps = parseInt(document.getElementById('fpsSelect').value);

    setStatus('Rendering...', 'rendering');
    addOutput('Starting render...', 'info');
    showProgress();
    showStopButton();

    eel.render_animation(code, quality, fps)(function(data) {
        if (data.status === 'success') {
            addOutput('Render started successfully', 'success');
            showToast('Render started', 'info');
        } else {
            addOutput(`Render error: ${data.message}`, 'error');
            showToast(`Error: ${data.message}`, 'error');
            setStatus('Ready', 'ready');
            hideProgress();
            hideStopButton();
        }
    });
}

async function quickPreview() {
    const code = editor.getValue();

    setStatus('Previewing...', 'rendering');
    addOutput('Starting preview...', 'info');
    showToast('Starting preview...', 'info');

    eel.quick_preview(code)(function(data) {
        if (data.status === 'success') {
            addOutput('Preview started', 'success');
        } else {
            addOutput(`Preview error: ${data.message}`, 'error');
            showToast(`Error: ${data.message}`, 'error');
            setStatus('Ready', 'ready');
        }
    });
}

async function stopRender() {
    eel.stop_render()(function(data) {
        if (data.status === 'success') {
            addOutput('Render stopped', 'warning');
            showToast('Render stopped', 'warning');
            setStatus('Ready', 'ready');
            hideProgress();
            hideStopButton();
        }
    });
}

// Python callbacks for render updates
eel.expose(update_render_output);
function update_render_output(line) {
    addOutput(line, 'info');
}

eel.expose(render_completed);
function render_completed() {
    addOutput('Render completed successfully!', 'success');
    showToast('Render completed!', 'success');
    setStatus('Ready', 'ready');
    hideProgress();
    hideStopButton();
    loadMediaList();
}

eel.expose(render_failed);
function render_failed(error) {
    addOutput(`Render failed: ${error}`, 'error');
    showToast(`Render failed: ${error}`, 'error');
    setStatus('Ready', 'ready');
    hideProgress();
    hideStopButton();
}

eel.expose(preview_completed);
function preview_completed() {
    addOutput('Preview completed', 'success');
    showToast('Preview completed', 'success');
    setStatus('Ready', 'ready');
    loadMediaList();
}

eel.expose(preview_failed);
function preview_failed(error) {
    addOutput(`Preview failed: ${error}`, 'error');
    showToast(`Preview failed`, 'error');
    setStatus('Ready', 'ready');
}

// Media Operations
async function loadMediaList() {
    eel.list_media_files()(function(data) {
        const mediaList = document.getElementById('mediaList');

        if (data.files.length === 0) {
            mediaList.innerHTML = `
                <div class="empty-state">
                    <i class="fas fa-film"></i>
                    <p>No rendered media yet. Render an animation to see it here.</p>
                </div>
            `;
            return;
        }

        mediaList.innerHTML = data.files.map(file => `
            <div class="media-item" onclick="playMedia('${file.path.replace(/\\/g, '\\\\')}')">
                <div class="media-item-info">
                    <h4>${file.name}</h4>
                    <p>${formatFileSize(file.size)} • ${new Date(file.modified * 1000).toLocaleString()}</p>
                </div>
                <button class="icon-btn small">
                    <i class="fas fa-play"></i>
                </button>
            </div>
        `).join('');
    });
}

function playMedia(path) {
    // Open with default system player
    eel.execute_command(`start "" "${path}"`);
}

function openMediaFolder() {
    eel.open_media_folder()(function(data) {
        if (data.status === 'success') {
            showToast('Opened media folder', 'success');
        } else {
            showToast(`Error: ${data.message}`, 'error');
        }
    });
}

// Terminal Operations
async function executeCommand(command) {
    eel.execute_command(command)(function(data) {
        if (data.status === 'success') {
            addTerminalOutput(`$ ${command}`);
            if (data.stdout) addTerminalOutput(data.stdout);
            if (data.stderr) addTerminalOutput(data.stderr, 'error');
        } else {
            addTerminalOutput(`Error: ${data.message}`, 'error');
        }
    });
}

function addTerminalOutput(text, type = 'normal') {
    const output = document.getElementById('terminalOutput');
    const line = document.createElement('div');
    line.textContent = text;
    if (type === 'error') line.style.color = '#f00';
    output.appendChild(line);
    output.scrollTop = output.scrollHeight;
}

function clearTerminal() {
    document.getElementById('terminalOutput').innerHTML = '';
}

// System Info
async function loadSystemInfo() {
    eel.get_system_info()(function(info) {
        document.getElementById('pythonVersion').textContent = info.python_version.split('\n')[0];
        document.getElementById('manimVersion').textContent = info.manim_version;
        document.getElementById('platform').textContent = info.platform;
        document.getElementById('baseDir').textContent = info.base_dir;
        document.getElementById('mediaDir').textContent = info.media_dir;
    });
}

// Settings
async function loadSettings() {
    eel.get_settings()(function(data) {
        settings = { ...settings, ...data };
        applySettings();
    });
}

async function saveSettings() {
    eel.update_settings(settings)(function(data) {
        if (data.status === 'success') {
            addOutput('Settings saved', 'success');
            showToast('Settings saved', 'success');
            applySettings();
        }
    });
}

function applySettings() {
    document.getElementById('qualitySelect').value = settings.quality;
    document.getElementById('fpsSelect').value = settings.fps;
    document.getElementById('formatSelect').value = settings.format;

    if (editor) {
        editor.setOption('theme', settings.theme);
    }

    // Update theme icon
    const themeBtn = document.getElementById('themeBtn').querySelector('i');
    if (settings.theme === 'default') {
        themeBtn.className = 'fas fa-sun';
    } else {
        themeBtn.className = 'fas fa-moon';
    }
}

// UI Helpers
function setStatus(text, state) {
    const statusText = document.getElementById('statusText');
    const statusIndicator = document.getElementById('statusIndicator');

    statusText.textContent = text;

    statusIndicator.className = 'fas fa-circle';
    if (state === 'rendering') {
        statusIndicator.classList.add('rendering');
    }
}

function updateCurrentFile(filename) {
    const fileSpan = document.querySelector('#currentFile span');
    fileSpan.textContent = filename;
}

function updateCursorPosition() {
    const cursor = editor.getCursor();
    const cursorPos = document.getElementById('cursorPosition');
    cursorPos.textContent = `Ln ${cursor.line + 1}, Col ${cursor.ch + 1}`;
}

function updateLineCount() {
    const lineCount = document.getElementById('linesCount');
    lineCount.textContent = `Lines: ${editor.lineCount()}`;
}

function addOutput(message, type = 'info') {
    const output = document.getElementById('outputConsole');
    const line = document.createElement('div');
    line.className = 'output-line';

    const timestamp = new Date().toLocaleTimeString();
    let icon = 'ℹ️';

    if (type === 'success') icon = '✅';
    else if (type === 'error') icon = '❌';
    else if (type === 'warning') icon = '⚠️';

    line.innerHTML = `<span style="color: var(--text-secondary)">[${timestamp}]</span> ${icon} ${message}`;
    output.appendChild(line);
    output.scrollTop = output.scrollHeight;

    // Limit output lines to 500
    while (output.children.length > 500) {
        output.removeChild(output.firstChild);
    }
}

function clearOutput() {
    document.getElementById('outputConsole').innerHTML = '<div class="output-line">Ready to render...</div>';
}

function showProgress() {
    document.getElementById('progressSection').style.display = 'block';
}

function hideProgress() {
    document.getElementById('progressSection').style.display = 'none';
}

function showStopButton() {
    document.getElementById('stopBtn').style.display = 'flex';
    document.getElementById('renderBtn').style.display = 'none';
}

function hideStopButton() {
    document.getElementById('stopBtn').style.display = 'none';
    document.getElementById('renderBtn').style.display = 'flex';
}

function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

// Modal
function openModal(modalId) {
    document.getElementById(modalId).classList.add('active');
}

function closeModal(modalId) {
    document.getElementById(modalId).classList.remove('active');
}

// Event Listeners
function setupEventListeners() {
    // Navigation
    document.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', () => {
            const panel = item.dataset.panel;
            switchPanel(panel);

            // Load data when switching to certain panels
            if (panel === 'media') loadMediaList();
            if (panel === 'system') loadSystemInfo();
        });
    });

    // Header buttons
    document.getElementById('newFileBtn').addEventListener('click', newFile);
    document.getElementById('openFileBtn').addEventListener('click', openFile);
    document.getElementById('saveFileBtn').addEventListener('click', saveFile);
    document.getElementById('renderBtn').addEventListener('click', renderAnimation);
    document.getElementById('previewBtn').addEventListener('click', quickPreview);
    document.getElementById('stopBtn').addEventListener('click', stopRender);
    document.getElementById('settingsBtn').addEventListener('click', () => openModal('settingsModal'));
    document.getElementById('helpBtn').addEventListener('click', () => {
        eel.execute_command('start https://docs.manim.community/');
    });

    // Theme toggle
    document.getElementById('themeBtn').addEventListener('click', () => {
        if (settings.theme === 'monokai') {
            settings.theme = 'default';
        } else {
            settings.theme = 'monokai';
        }
        applySettings();
        eel.update_settings(settings);
    });

    // Panel actions
    document.getElementById('formatCodeBtn')?.addEventListener('click', () => {
        showToast('Code formatting not yet implemented', 'info');
    });

    document.getElementById('fontSizeSelect')?.addEventListener('change', (e) => {
        editor.getWrapperElement().style.fontSize = e.target.value + 'px';
    });

    document.getElementById('refreshMediaBtn')?.addEventListener('click', loadMediaList);
    document.getElementById('openMediaFolderBtn')?.addEventListener('click', openMediaFolder);
    document.getElementById('clearOutputBtn')?.addEventListener('click', clearOutput);
    document.getElementById('clearTerminalBtn')?.addEventListener('click', clearTerminal);
    document.getElementById('refreshSystemBtn')?.addEventListener('click', loadSystemInfo);

    // Terminal input
    document.getElementById('terminalInput')?.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            const input = e.target;
            const command = input.value.trim();
            if (command) {
                executeCommand(command);
                input.value = '';
            }
        }
    });

    // Settings
    document.getElementById('saveSettingsBtn')?.addEventListener('click', () => {
        settings.intellisense = document.getElementById('intellisenseToggle').checked;
        settings.autoPreview = document.getElementById('autoPreviewToggle').checked;
        settings.theme = document.getElementById('themeSelect').value;

        saveSettings();
        closeModal('settingsModal');
    });

    // Quality/FPS/Format changes
    document.getElementById('qualitySelect').addEventListener('change', (e) => {
        settings.quality = e.target.value;
        eel.update_settings(settings);
    });

    document.getElementById('fpsSelect').addEventListener('change', (e) => {
        settings.fps = parseInt(e.target.value);
        eel.update_settings(settings);
    });

    document.getElementById('formatSelect').addEventListener('change', (e) => {
        settings.format = e.target.value;
        eel.update_settings(settings);
    });

    // Modal close buttons
    document.querySelectorAll('.close-btn, .btn[data-modal]').forEach(btn => {
        btn.addEventListener('click', () => {
            const modalId = btn.dataset.modal;
            if (modalId) closeModal(modalId);
        });
    });

    // Close modals on background click
    document.querySelectorAll('.modal').forEach(modal => {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.classList.remove('active');
            }
        });
    });
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    initializeEditor();
    setupEventListeners();
    loadSettings();
    loadSystemInfo();
    setStatus('Ready', 'ready');
    addOutput('Manim Studio Desktop UI ready', 'success');
    showToast('Manim Studio ready!', 'success');
});
