// ai-edit.js — AI Edit Panel (Claude Code + OpenAI Codex)
// Dependencies: editor, monaco, pywebview, toast(), performAutosave()
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
