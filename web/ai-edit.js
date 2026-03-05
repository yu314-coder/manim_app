// ai-edit.js — AI Edit: dual provider (Claude Code + Codex), panel + window mode
// Dependencies: pywebview.api, xterm.js (window mode)
// In panel mode: also depends on editor, monaco, toast(), performAutosave()
(function initAIEdit() {
    'use strict';

    const isWindowMode = !!window._aiEditWindowMode;

    // ═══════════════════════════════════════════════════════════════════
    //  Shared state
    // ═══════════════════════════════════════════════════════════════════
    let currentProvider = 'claude';   // 'claude' or 'codex'
    let originalCode = '';
    let editedCode = '';
    let pollTimer = null;
    let isStreaming = false;
    let attachedImages = [];  // [{name, path, dataUrl?}]
    let currentModels = [];
    let selectedModel = '';

    // ─── Helpers ───
    function toast(msg, type) {
        if (typeof window.toast === 'function') window.toast(msg, type);
        else console.log(`[${type}] ${msg}`);
    }

    async function waitForApi() {
        for (let i = 0; i < 40; i++) {
            if (typeof pywebview !== 'undefined' && pywebview.api) return true;
            await new Promise(r => setTimeout(r, 250));
        }
        return false;
    }

    // ═══════════════════════════════════════════════════════════════════
    //  WINDOW MODE
    // ═══════════════════════════════════════════════════════════════════
    if (isWindowMode) {
        initWindowMode();
        return;
    }

    // ═══════════════════════════════════════════════════════════════════
    //  Enhanced streaming output renderer (panel mode)
    // ═══════════════════════════════════════════════════════════════════
    function esc(s) {
        const d = document.createElement('div');
        d.textContent = s;
        return d.innerHTML;
    }

    const TOOL_ICONS = {
        Write: 'fa-pen', Edit: 'fa-pen',
        Read: 'fa-eye',
        Bash: 'fa-terminal',
        Grep: 'fa-search', Glob: 'fa-search',
        WebFetch: 'fa-globe', WebSearch: 'fa-globe',
        NotebookEdit: 'fa-book',
    };

    function renderEnhancedOutput(text) {
        if (!text) return '';
        const lines = text.split('\n');
        let html = '';
        let inCodeBlock = false;

        for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed) {
                if (inCodeBlock) { html += '</div>'; inCodeBlock = false; }
                continue;
            }

            // Tool header: Write(scene.py), Read(scene.py), Bash(cmd), etc.
            const toolMatch = trimmed.match(/^(Write|Read|Edit|Bash|Grep|Glob|WebFetch|WebSearch|NotebookEdit)\((.+)\)$/);
            if (toolMatch) {
                if (inCodeBlock) { html += '</div>'; inCodeBlock = false; }
                const icon = TOOL_ICONS[toolMatch[1]] || 'fa-cog';
                html += `<div class="aip-tool-header"><i class="fas ${icon}"></i> ${toolMatch[1]}(<span class="aip-tool-file">${esc(toolMatch[2])}</span>)</div>`;
                continue;
            }

            // Tool result: "Wrote 24 lines to scene.py"
            if (/^(Wrote|Read|Edited|Created|Updated|Deleted)\b/i.test(trimmed)) {
                if (inCodeBlock) { html += '</div>'; inCodeBlock = false; }
                html += `<div class="aip-tool-result">${esc(trimmed)}</div>`;
                continue;
            }

            // Numbered code line: "  1  from manim import *"
            const codeMatch = line.match(/^(\s*)(\d+)\s(.*)$/);
            if (codeMatch) {
                if (!inCodeBlock) { html += '<div class="aip-code-block">'; inCodeBlock = true; }
                html += `<div class="aip-code-line"><span class="aip-line-num">${codeMatch[2]}</span><span class="aip-line-code">${esc(codeMatch[3])}</span></div>`;
                continue;
            }

            // Collapsed hint: "+14 lines (ctrl+o to expand)"
            if (/^\+\d+ lines/.test(trimmed)) {
                if (inCodeBlock) { html += '</div>'; inCodeBlock = false; }
                html += `<div class="aip-collapsed">${esc(trimmed)}</div>`;
                continue;
            }

            // Plain text
            if (inCodeBlock) { html += '</div>'; inCodeBlock = false; }
            html += `<div class="aip-tool-text">${esc(trimmed)}</div>`;
        }
        if (inCodeBlock) html += '</div>';
        return html;
    }

    // ═══════════════════════════════════════════════════════════════════
    //  PANEL MODE (existing sidebar in index.html)
    // ═══════════════════════════════════════════════════════════════════
    initPanelMode();

    // ─────────────────────────────────────────────────────────────────
    function initPanelMode() {
        const panel       = document.getElementById('aiEditPanel');
        const panelBtn    = document.getElementById('aiEditPanelBtn');
        const panelClose  = document.getElementById('aiEditPanelClose');
        const popoutBtn   = document.getElementById('aiEditPopoutBtn');
        const promptInput = document.getElementById('aiEditPrompt');
        const sendBtn     = document.getElementById('aiEditSendBtn');
        const modelBtn    = document.getElementById('aiEditModelBtn');
        const modelLabel  = document.getElementById('aiEditModelLabel');
        const modelDropdown = document.getElementById('aiEditModelDropdown');
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
        const providerToggle = document.getElementById('aiEditProviderToggle');
        const dropZone    = document.getElementById('aiEditDropZone');
        const imageInput  = document.getElementById('aiEditImageInput');
        const thumbGrid   = document.getElementById('aiEditThumbGrid');
        const autoApplyEl = document.getElementById('aiEditAutoApply');
        if (!panel || !editorEl) return;

        let diffEditorInstance = null;
        let panelVisible = false;

        // ── Auto-apply toggle: persist in localStorage ──
        if (autoApplyEl) {
            autoApplyEl.checked = localStorage.getItem('aiEditAutoApply') !== 'false';
            autoApplyEl.addEventListener('change', () => {
                localStorage.setItem('aiEditAutoApply', autoApplyEl.checked);
                // Visual feedback on the label
                const label = autoApplyEl.closest('label');
                if (label) label.style.opacity = autoApplyEl.checked ? '1' : '0.5';
            });
            // Set initial opacity
            const label = autoApplyEl.closest('label');
            if (label) label.style.opacity = autoApplyEl.checked ? '1' : '0.5';
        }

        // ── Provider toggle ──
        if (providerToggle) {
            providerToggle.querySelectorAll('.aip-prov').forEach(btn => {
                btn.addEventListener('click', () => {
                    providerToggle.querySelectorAll('.aip-prov').forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                    currentProvider = btn.dataset.provider;
                    loadModels();
                });
            });
        }

        // ── Search toggle button (globe icon) ──
        const searchBtn = document.getElementById('aiEditSearchBtn');
        if (searchBtn && searchToggle) {
            searchBtn.addEventListener('click', () => {
                searchToggle.checked = !searchToggle.checked;
                searchBtn.classList.toggle('active', searchToggle.checked);
            });
        }

        function updateSendBtnLabel() {
            // Icon-only send button — no label change needed
        }

        // ── Load models (dropdown) ──
        async function loadModels() {
            if (!await waitForApi()) return;
            try {
                const fn = currentProvider === 'claude' ? 'get_claude_models' : 'get_codex_models';
                if (!pywebview.api[fn]) return;
                const result = await pywebview.api[fn]();
                currentModels = result.models || [];
                selectedModel = '';
                renderModelDropdown();
            } catch (e) { console.log('[AI EDIT] Model load:', e); }
        }

        function renderModelDropdown() {
            if (!modelDropdown) return;
            modelDropdown.innerHTML = '';
            // Default option
            const defOpt = document.createElement('button');
            defOpt.className = 'aiw-model-option' + (selectedModel === '' ? ' active' : '');
            defOpt.textContent = 'Default';
            defOpt.addEventListener('click', () => selectModel('', 'Default'));
            modelDropdown.appendChild(defOpt);

            for (const m of currentModels) {
                const opt = document.createElement('button');
                opt.className = 'aiw-model-option' + (selectedModel === m.id ? ' active' : '');
                opt.textContent = m.display_name;
                opt.addEventListener('click', () => selectModel(m.id, m.display_name));
                modelDropdown.appendChild(opt);
            }
            // Update label
            if (modelLabel) {
                const sel = currentModels.find(m => m.id === selectedModel);
                modelLabel.textContent = sel ? sel.display_name : 'Default';
            }
        }

        function selectModel(id, name) {
            selectedModel = id;
            if (modelLabel) modelLabel.textContent = name;
            if (modelDropdown) {
                modelDropdown.classList.remove('show');
                modelBtn?.classList.remove('open');
                modelDropdown.querySelectorAll('.aiw-model-option').forEach(o =>
                    o.classList.toggle('active', o.textContent === name));
            }
        }

        // Toggle dropdown
        modelBtn?.addEventListener('click', (e) => {
            e.stopPropagation();
            const open = modelDropdown.classList.toggle('show');
            modelBtn.classList.toggle('open', open);
        });
        document.addEventListener('click', () => {
            modelDropdown?.classList.remove('show');
            modelBtn?.classList.remove('open');
        });

        loadModels();

        // ── Image upload (drop zone + file input) ──
        if (dropZone && imageInput) {
            dropZone.addEventListener('click', () => imageInput.click());
            dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('drag-over'); });
            dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
            dropZone.addEventListener('drop', e => {
                e.preventDefault();
                dropZone.classList.remove('drag-over');
                handleFiles(e.dataTransfer.files);
            });
            imageInput.addEventListener('change', () => {
                handleFiles(imageInput.files);
                imageInput.value = '';
            });
        }

        async function handleFiles(files) {
            if (!files) return;
            for (const file of files) {
                if (!file.type.startsWith('image/')) continue;
                const reader = new FileReader();
                reader.onload = async (e) => {
                    const dataUrl = e.target.result;
                    try {
                        const res = await pywebview.api.ai_edit_save_image(file.name, dataUrl);
                        if (res.status === 'success') {
                            attachedImages.push({ name: file.name, path: res.path, dataUrl });
                            renderThumbs();
                        }
                    } catch (err) { console.error('[AI EDIT] Image save:', err); }
                };
                reader.readAsDataURL(file);
            }
        }

        function renderThumbs() {
            if (!thumbGrid) return;
            thumbGrid.innerHTML = '';
            attachedImages.forEach((img, i) => {
                const div = document.createElement('div');
                div.className = 'ai-edit-thumb';
                div.innerHTML = `<img src="${img.dataUrl || ''}" alt="${img.name}">
                    <button class="ai-edit-thumb-remove" data-idx="${i}">&times;</button>`;
                thumbGrid.appendChild(div);
            });
            thumbGrid.querySelectorAll('.ai-edit-thumb-remove').forEach(btn =>
                btn.addEventListener('click', e => {
                    attachedImages.splice(parseInt(e.target.dataset.idx), 1);
                    renderThumbs();
                })
            );
        }

        // ── Toggle panel ──
        function togglePanel() {
            panelVisible = !panelVisible;
            panel.style.display = panelVisible ? 'flex' : 'none';
            if (panelVisible) setTimeout(() => promptInput.focus(), 50);
            if (typeof editor !== 'undefined' && editor) setTimeout(() => editor.layout(), 50);
        }

        function updateContextHint() {
            if (typeof editor === 'undefined' || !editor || !contextDiv || !contextText) return;
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

        function openAIEdit(prefillPrompt) {
            if (typeof editor === 'undefined' || !editor) return;
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

        function closePanel() {
            if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
            isStreaming = false;
            try { pywebview?.api?.ai_edit_cancel(); } catch(e) {}
            try { pywebview?.api?.ai_edit_claude_cancel(); } catch(e) {}
            destroyDiffEditor();
            resetSendBtn();
            diffActions.style.display = 'none';
            if (streamBox) streamBox.style.display = 'none';
            panelVisible = false;
            panel.style.display = 'none';
            attachedImages = [];
            if (thumbGrid) thumbGrid.innerHTML = '';
            if (typeof editor !== 'undefined' && editor) { editor.focus(); setTimeout(() => editor.layout(), 50); }
        }

        panelBtn?.addEventListener('click', togglePanel);
        panelClose?.addEventListener('click', closePanel);

        // ── Popout button → open separate window ──
        popoutBtn?.addEventListener('click', async () => {
            if (!await waitForApi()) return;
            try {
                await pywebview.api.open_ai_edit_window();
                closePanel();
            } catch (e) { console.error('[AI EDIT] Popout error:', e); }
        });

        // ── Diff editor ──
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
                theme: 'vs-dark', readOnly: false, originalEditable: false,
                renderSideBySide: true, automaticLayout: true,
                minimap: { enabled: false }, scrollBeyondLastLine: false,
                fontSize: editor.getOption(monaco.editor.EditorOption.fontSize),
            });
            diffEditorInstance.setModel({ original: origModel, modified: modModel });

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
            if (typeof editor !== 'undefined' && editor) editor.getDomNode().style.visibility = 'visible';
        }

        function resetSendBtn() {
            isStreaming = false;
            if (sendBtn) {
                sendBtn.disabled = false;
                sendBtn.classList.remove('cancel-mode');
                sendBtn.innerHTML = '<i class="fas fa-arrow-up"></i>';
            }
            if (statusText) statusText.style.display = 'none';
        }

        // ── Send / Cancel ──
        sendBtn?.addEventListener('click', async () => {
            if (isStreaming) {
                if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
                try {
                    if (currentProvider === 'claude') await pywebview.api.ai_edit_claude_cancel();
                    else await pywebview.api.ai_edit_cancel();
                } catch(e) {}
                resetSendBtn();
                if (streamBox) streamBox.style.display = 'none';
                toast('Cancelled', 'info');
                return;
            }

            const prompt = promptInput.value.trim();
            if (!prompt) { toast('Enter a prompt', 'warning'); promptInput.focus(); return; }

            originalCode = editor.getModel().getValue();
            isStreaming = true;
            sendBtn.innerHTML = '<i class="fas fa-stop"></i>';
            sendBtn.classList.add('cancel-mode');
            statusText.style.display = 'flex';
            diffActions.style.display = 'none';
            if (streamBox) streamBox.style.display = 'flex';
            if (streamOutput) streamOutput.textContent = '';
            const providerName = currentProvider === 'claude' ? 'Claude' : 'Codex';
            statusMsg.textContent = `Starting ${providerName}...`;

            try {
                const selection = editor.getSelection();
                let selectedCode = '', selStart = 0, selEnd = 0;
                if (selection && !selection.isEmpty()) {
                    selectedCode = editor.getModel().getValueInRange(selection);
                    selStart = selection.startLineNumber;
                    selEnd   = selection.endLineNumber;
                }

                const useSearch = searchToggle ? searchToggle.checked : false;
                const imagePaths = attachedImages.map(img => img.path);

                let res;
                if (currentProvider === 'claude') {
                    res = await pywebview.api.ai_edit_claude_start(
                        originalCode, prompt, selectedModel, useSearch,
                        selectedCode, selStart, selEnd, imagePaths);
                } else {
                    res = await pywebview.api.ai_edit_codex(
                        originalCode, prompt, selectedModel, useSearch,
                        selectedCode, selStart, selEnd, imagePaths);
                }

                if (res.status === 'error') {
                    statusMsg.textContent = res.message || 'Failed';
                    toast(res.message || 'AI edit failed', 'error');
                    resetSendBtn();
                    return;
                }

                statusMsg.textContent = `${providerName} is generating...`;
                const pollFn = currentProvider === 'claude' ? 'ai_edit_claude_poll' : 'ai_edit_poll';

                pollTimer = setInterval(async () => {
                    try {
                        const poll = await pywebview.api[pollFn]();
                        if (streamOutput) {
                            // Both Claude and Codex now provide filtered_output (full replace)
                            const clean = poll.filtered_output || '';
                            if (clean) streamOutput.innerHTML = renderEnhancedOutput(clean);
                            // Defer scroll to after browser layout
                            requestAnimationFrame(() => {
                                streamOutput.scrollTop = streamOutput.scrollHeight;
                            });
                        }
                        if (poll.status === 'streaming') {
                            statusMsg.textContent = `Generating... (${poll.chars || 0} chars)`;
                        }
                        if (poll.done) {
                            clearInterval(pollTimer); pollTimer = null;
                            if (poll.status === 'success' && poll.edited_code) {
                                editedCode = poll.edited_code;
                                if (streamBox) streamBox.style.display = 'none';
                                // Auto-apply or show diff
                                if (autoApplyEl && autoApplyEl.checked) {
                                    editor.setValue(editedCode);
                                    toast('Changes applied! Ctrl+Z to undo', 'success');
                                    if (typeof performAutosave === 'function') performAutosave();
                                } else {
                                    showDiffEditor(originalCode, editedCode);
                                    toast('Review the diff — Accept or Reject', 'info');
                                }
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

        // ── Accept / Reject ──
        acceptBtn?.addEventListener('click', () => {
            if (typeof editor === 'undefined' || !editor) return;
            let finalCode = editedCode;
            if (diffEditorInstance) {
                try { finalCode = diffEditorInstance.getModel().modified.getValue(); } catch(e) {}
            }
            destroyDiffEditor();
            diffActions.style.display = 'none';
            editor.setValue(finalCode);
            toast('Changes applied & saving...', 'success');
            editor.focus();
            if (typeof performAutosave === 'function') performAutosave();
        });

        rejectBtn?.addEventListener('click', () => {
            destroyDiffEditor();
            diffActions.style.display = 'none';
            toast('Changes discarded', 'info');
            promptInput.focus();
        });

        // ── Keyboard shortcuts + auto-grow ──
        promptInput?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendBtn?.click(); }
            if (e.key === 'Escape') closePanel();
        });
        promptInput?.addEventListener('input', () => {
            // Auto-grow textarea height
            promptInput.style.height = 'auto';
            promptInput.style.height = Math.min(promptInput.scrollHeight, 120) + 'px';
        });
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && panelVisible) closePanel();
        });

        // ── Register Monaco keybinding + selection listener ──
        const hookEditor = setInterval(() => {
            if (typeof editor !== 'undefined' && editor && typeof monaco !== 'undefined' && monaco) {
                clearInterval(hookEditor);
                editor.addAction({
                    id: 'ai-edit-code', label: 'Edit with AI',
                    keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyMod.Shift | monaco.KeyCode.KeyE],
                    contextMenuGroupId: '9_ai', contextMenuOrder: 1,
                    run: openAIEdit
                });
                editor.onDidChangeCursorSelection(() => {
                    if (panelVisible) updateContextHint();
                });
                console.log('[AI EDIT] Panel registered');
            }
        }, 500);

        // ── "Fix with AI" button ──
        const fixWithAIBtn = document.getElementById('fixWithAIBtn');
        fixWithAIBtn?.addEventListener('click', () => {
            if (typeof editor === 'undefined' || !editor) return;
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

        // ── Poll for pending AI code from window mode ──
        setInterval(async () => {
            if (typeof pywebview === 'undefined' || !pywebview?.api?.get_pending_ai_code) return;
            try {
                const res = await pywebview.api.get_pending_ai_code();
                if (res.status === 'success' && res.code && typeof editor !== 'undefined' && editor) {
                    editor.setValue(res.code);
                    toast('AI edit applied from window', 'success');
                    if (typeof performAutosave === 'function') performAutosave();
                }
            } catch(e) {}
        }, 1000);

        window.openAIEdit = openAIEdit;
        updateSendBtnLabel();
    }

    // ═══════════════════════════════════════════════════════════════════
    //  WINDOW MODE — standalone ai-edit-window.html
    // ═══════════════════════════════════════════════════════════════════
    function initWindowMode() {
        const closeBtn    = document.getElementById('aiwCloseBtn');
        const providerEl  = document.getElementById('aiwProviderToggle');
        const promptInput = document.getElementById('aiwPrompt');
        const modelBtn    = document.getElementById('aiwModelBtn');
        const modelLabel  = document.getElementById('aiwModelLabel');
        const modelDropdown = document.getElementById('aiwModelDropdown');
        const dropZone    = document.getElementById('aiwDropZone');
        const imageInput  = document.getElementById('aiwImageInput');
        const thumbGrid   = document.getElementById('aiwThumbGrid');
        const searchToggle= document.getElementById('aiwSearchToggle');
        const sendBtn     = document.getElementById('aiwSendBtn');
        const statusEl    = document.getElementById('aiwStatus');
        const statusMsg   = document.getElementById('aiwStatusMsg');
        const terminalEl  = document.getElementById('aiwTerminal');
        const diffBar     = document.getElementById('aiwDiffBar');
        const diffStats   = document.getElementById('aiwDiffStats');
        const acceptBtn   = document.getElementById('aiwAcceptBtn');
        const rejectBtn   = document.getElementById('aiwRejectBtn');

        let term = null;  // xterm.js Terminal instance

        // ── Initialize xterm.js terminal ──
        if (typeof Terminal !== 'undefined' && terminalEl) {
            term = new Terminal({
                cursorBlink: true,
                fontSize: 13,
                fontFamily: "'Consolas', 'Monaco', 'Courier New', monospace",
                theme: {
                    background: '#0d0d0d',
                    foreground: '#d4d4d4',
                    cursor: '#a78bfa',
                },
                convertEol: true,
                scrollback: 5000,
            });
            term.open(terminalEl);
            term.writeln('\x1b[90mReady. Select a provider and send a prompt.\x1b[0m');

            // ── Keyboard: copy/paste/select-all support ──
            term.attachCustomKeyEventHandler((ev) => {
                // Ctrl+Shift+C → always copy
                if (ev.ctrlKey && ev.shiftKey && ev.key === 'C') {
                    const sel = term.getSelection();
                    if (sel) navigator.clipboard.writeText(sel);
                    return false; // prevent terminal from handling
                }
                // Ctrl+C → copy if text selected, else send ^C to PTY
                if (ev.ctrlKey && !ev.shiftKey && ev.key === 'c' && ev.type === 'keydown') {
                    const sel = term.getSelection();
                    if (sel) {
                        navigator.clipboard.writeText(sel);
                        return false;
                    }
                    // No selection: let it pass through as ^C to PTY
                    return true;
                }
                // Ctrl+A → select all terminal text
                if (ev.ctrlKey && ev.key === 'a' && ev.type === 'keydown') {
                    term.selectAll();
                    return false;
                }
                // Ctrl+V → paste from clipboard
                if (ev.ctrlKey && ev.key === 'v' && ev.type === 'keydown') {
                    navigator.clipboard.readText().then(text => {
                        if (text && currentProvider === 'claude' && isStreaming) {
                            pywebview.api.ai_edit_claude_send(text).catch(() => {});
                        }
                    }).catch(() => {});
                    return false;
                }
                return true;
            });

            // Forward keyboard input to Claude PTY
            term.onData(async (data) => {
                if (currentProvider === 'claude' && isStreaming) {
                    try { await pywebview.api.ai_edit_claude_send(data); } catch(e) {}
                }
            });
        }

        // ── Close window (use pywebview destroy, not window.close) ──
        closeBtn?.addEventListener('click', async () => {
            cancelStreaming();
            try { await pywebview.api.close_ai_edit_window(); } catch(e) {}
        });

        // ── Provider toggle ──
        if (providerEl) {
            providerEl.querySelectorAll('.aiw-pill').forEach(btn => {
                btn.addEventListener('click', () => {
                    providerEl.querySelectorAll('.aiw-pill').forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                    currentProvider = btn.dataset.provider;
                    loadModels();
                    updateSendLabel();
                });
            });
        }

        function updateSendLabel() {
            if (!sendBtn || isStreaming) return;
            const label = currentProvider === 'claude' ? 'Send to Claude' : 'Send to Codex';
            sendBtn.innerHTML = `<i class="fas fa-paper-plane"></i> ${label}`;
        }

        // ── Models (dropdown) ──
        async function loadModels() {
            if (!await waitForApi()) return;
            try {
                const fn = currentProvider === 'claude' ? 'get_claude_models' : 'get_codex_models';
                if (!pywebview.api[fn]) return;
                const result = await pywebview.api[fn]();
                currentModels = result.models || [];
                selectedModel = '';
                renderModelDropdown();
            } catch (e) { console.log('[AI EDIT WIN] Model load:', e); }
        }

        function renderModelDropdown() {
            if (!modelDropdown) return;
            modelDropdown.innerHTML = '';
            const defOpt = document.createElement('button');
            defOpt.className = 'aiw-model-option' + (selectedModel === '' ? ' active' : '');
            defOpt.textContent = 'Default';
            defOpt.addEventListener('click', () => selectModel('', 'Default'));
            modelDropdown.appendChild(defOpt);

            for (const m of currentModels) {
                const opt = document.createElement('button');
                opt.className = 'aiw-model-option' + (selectedModel === m.id ? ' active' : '');
                opt.textContent = m.display_name;
                opt.addEventListener('click', () => selectModel(m.id, m.display_name));
                modelDropdown.appendChild(opt);
            }
            if (modelLabel) {
                const sel = currentModels.find(m => m.id === selectedModel);
                modelLabel.textContent = sel ? sel.display_name : 'Default';
            }
        }

        function selectModel(id, name) {
            selectedModel = id;
            if (modelLabel) modelLabel.textContent = name;
            if (modelDropdown) {
                modelDropdown.classList.remove('show');
                modelBtn?.classList.remove('open');
                modelDropdown.querySelectorAll('.aiw-model-option').forEach(o =>
                    o.classList.toggle('active', o.textContent === name));
            }
        }

        modelBtn?.addEventListener('click', (e) => {
            e.stopPropagation();
            const open = modelDropdown.classList.toggle('show');
            modelBtn.classList.toggle('open', open);
        });
        document.addEventListener('click', () => {
            modelDropdown?.classList.remove('show');
            modelBtn?.classList.remove('open');
        });

        // ── Image upload ──
        if (dropZone && imageInput) {
            dropZone.addEventListener('click', () => imageInput.click());
            dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('drag-over'); });
            dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
            dropZone.addEventListener('drop', e => {
                e.preventDefault();
                dropZone.classList.remove('drag-over');
                handleFiles(e.dataTransfer.files);
            });
            imageInput.addEventListener('change', () => {
                handleFiles(imageInput.files);
                imageInput.value = '';
            });
        }

        async function handleFiles(files) {
            if (!files) return;
            for (const file of files) {
                if (!file.type.startsWith('image/')) continue;
                const reader = new FileReader();
                reader.onload = async (e) => {
                    const dataUrl = e.target.result;
                    try {
                        const res = await pywebview.api.ai_edit_save_image(file.name, dataUrl);
                        if (res.status === 'success') {
                            attachedImages.push({ name: file.name, path: res.path, dataUrl });
                            renderThumbs();
                        }
                    } catch (err) { console.error('[AI EDIT WIN] Image save:', err); }
                };
                reader.readAsDataURL(file);
            }
        }

        function renderThumbs() {
            if (!thumbGrid) return;
            thumbGrid.innerHTML = '';
            attachedImages.forEach((img, i) => {
                const div = document.createElement('div');
                div.className = 'aiw-thumb';
                div.innerHTML = `<img src="${img.dataUrl || ''}" alt="${img.name}">
                    <button class="aiw-thumb-remove" data-idx="${i}">&times;</button>`;
                thumbGrid.appendChild(div);
            });
            thumbGrid.querySelectorAll('.aiw-thumb-remove').forEach(btn =>
                btn.addEventListener('click', e => {
                    attachedImages.splice(parseInt(e.target.dataset.idx), 1);
                    renderThumbs();
                })
            );
        }

        // ── Send / Cancel ──
        function cancelStreaming() {
            if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
            isStreaming = false;
            try {
                if (currentProvider === 'claude') pywebview?.api?.ai_edit_claude_cancel();
                else pywebview?.api?.ai_edit_cancel();
            } catch(e) {}
        }

        sendBtn?.addEventListener('click', async () => {
            if (isStreaming) {
                cancelStreaming();
                sendBtn.disabled = false;
                sendBtn.classList.remove('cancel-mode');
                updateSendLabel();
                if (statusEl) statusEl.style.display = 'none';
                toast('Cancelled', 'info');
                return;
            }

            const prompt = promptInput.value.trim();
            if (!prompt) { toast('Enter a prompt', 'warning'); promptInput?.focus(); return; }

            // Get code from main editor
            if (!await waitForApi()) { toast('API not ready', 'error'); return; }
            let codeRes;
            try { codeRes = await pywebview.api.get_editor_code(); } catch(e) {
                toast('Failed to get editor code', 'error'); return;
            }
            originalCode = (codeRes && codeRes.code) || '';

            isStreaming = true;
            sendBtn.innerHTML = '<i class="fas fa-stop"></i> Cancel';
            sendBtn.classList.add('cancel-mode');
            if (statusEl) statusEl.style.display = 'flex';
            if (diffBar) diffBar.style.display = 'none';
            const providerName = currentProvider === 'claude' ? 'Claude' : 'Codex';
            if (statusMsg) statusMsg.textContent = `Starting ${providerName}...`;

            // Clear terminal
            if (term) { term.clear(); term.writeln(`\x1b[90m[${providerName}] Sending prompt...\x1b[0m`); }

            try {
                const useSearch = searchToggle ? searchToggle.checked : false;
                const imagePaths = attachedImages.map(img => img.path);

                let res;
                if (currentProvider === 'claude') {
                    res = await pywebview.api.ai_edit_claude_start(
                        originalCode, prompt, selectedModel, useSearch,
                        '', 0, 0, imagePaths);
                } else {
                    res = await pywebview.api.ai_edit_codex(
                        originalCode, prompt, selectedModel, useSearch,
                        '', 0, 0, imagePaths);
                }

                if (res.status === 'error') {
                    if (statusMsg) statusMsg.textContent = res.message || 'Failed';
                    if (term) term.writeln(`\x1b[31m${res.message || 'Failed'}\x1b[0m`);
                    toast(res.message || 'AI edit failed', 'error');
                    resetWinSendBtn();
                    return;
                }

                if (statusMsg) statusMsg.textContent = `${providerName} is generating...`;

                // Poll for output
                const pollFn = currentProvider === 'claude' ? 'ai_edit_claude_poll' : 'ai_edit_poll';
                let lastLen = 0;  // used for Codex (cumulative); Claude uses incremental drain

                pollTimer = setInterval(async () => {
                    try {
                        const poll = await pywebview.api[pollFn]();
                        // Write output to terminal
                        if (poll.output && term) {
                            if (currentProvider === 'claude') {
                                // Claude poll drains buffer each call → write directly
                                term.write(poll.output);
                            } else {
                                // Codex poll returns cumulative → write delta
                                const newText = poll.output.substring(lastLen);
                                if (newText) {
                                    term.write(newText);
                                    lastLen = poll.output.length;
                                }
                            }
                        }
                        if (poll.status === 'streaming' && statusMsg) {
                            statusMsg.textContent = `Generating... (${poll.chars || 0} chars)`;
                        }
                        if (poll.done) {
                            clearInterval(pollTimer); pollTimer = null;
                            const winAutoApply = localStorage.getItem('aiEditAutoApply') !== 'false';
                            if (poll.status === 'success' && poll.edited_code) {
                                editedCode = poll.edited_code;
                                if (winAutoApply) {
                                    // Auto-apply: send to editor immediately
                                    try {
                                        await pywebview.api.set_editor_code(editedCode);
                                        if (term) term.writeln('\n\x1b[32m[Done] Changes auto-applied! Ctrl+Z to undo.\x1b[0m');
                                        toast('Changes applied! Ctrl+Z to undo', 'success');
                                    } catch(e) {
                                        if (term) term.writeln('\n\x1b[31m[Error] Failed to auto-apply.\x1b[0m');
                                        if (diffBar) diffBar.style.display = 'flex';
                                        if (diffStats) diffStats.textContent = 'Changes ready';
                                    }
                                } else {
                                    if (term) term.writeln('\n\x1b[32m[Done] Review changes below.\x1b[0m');
                                    if (diffBar) diffBar.style.display = 'flex';
                                    if (diffStats) diffStats.textContent = 'Changes ready';
                                    toast('Review changes — Accept or Reject', 'info');
                                }
                            } else {
                                if (statusMsg) statusMsg.textContent = poll.message || 'Failed';
                                if (term) term.writeln(`\n\x1b[31m${poll.message || 'Failed'}\x1b[0m`);
                                toast(poll.message || 'AI edit failed', 'error');
                            }
                            resetWinSendBtn();
                        }
                    } catch (e) { console.error('[AI EDIT WIN] Poll:', e); }
                }, currentProvider === 'claude' ? 100 : 300);

            } catch (err) {
                if (statusMsg) statusMsg.textContent = 'Error: ' + err.message;
                if (term) term.writeln(`\x1b[31mError: ${err.message}\x1b[0m`);
                toast('AI edit failed', 'error');
                resetWinSendBtn();
            }
        });

        function resetWinSendBtn() {
            isStreaming = false;
            if (sendBtn) {
                sendBtn.disabled = false;
                sendBtn.classList.remove('cancel-mode');
                updateSendLabel();
            }
            if (statusEl) statusEl.style.display = 'none';
        }

        // ── Accept / Reject ──
        acceptBtn?.addEventListener('click', async () => {
            if (!editedCode) return;
            try {
                await pywebview.api.set_editor_code(editedCode);
                toast('Changes sent to editor', 'success');
                if (diffBar) diffBar.style.display = 'none';
                if (term) term.writeln('\x1b[32m[Accepted] Code applied in main editor.\x1b[0m');
            } catch(e) {
                toast('Failed to apply changes', 'error');
            }
        });

        rejectBtn?.addEventListener('click', () => {
            if (diffBar) diffBar.style.display = 'none';
            toast('Changes discarded', 'info');
            if (term) term.writeln('\x1b[33m[Rejected] Changes discarded.\x1b[0m');
        });

        // ── Keyboard ──
        promptInput?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendBtn?.click(); }
        });

        // ── Init ──
        loadModels();
        updateSendLabel();
        promptInput?.focus();
    }

})();
