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
        const newChatBtn  = document.getElementById('aiEditNewChatBtn');
        const historyBtn  = document.getElementById('aiEditHistoryBtn');
        const historyDrop = document.getElementById('aiEditHistoryDropdown');
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
        const agentUI = document.getElementById('aiAgentUI');
        const agentLog = document.getElementById('aiAgentLog');
        const agentShots = document.getElementById('aiAgentScreenshots');
        const agentChip = document.getElementById('aiAgentChip');
        const agentChipClose = document.getElementById('aiAgentChipClose');
        const agentToggleBtn = document.getElementById('aiAgentToggle');
        let agentMode = false;

        function setAgentMode(on) {
            agentMode = on;
            if (agentChip) agentChip.style.display = on ? 'inline-flex' : 'none';
            if (agentToggleBtn) agentToggleBtn.classList.toggle('active', on);
            if (agentUI) agentUI.style.display = on ? 'block' : 'none';
            if (promptInput) promptInput.placeholder = on
                ? 'Describe your animation...' : 'Ask anything';
        }

        if (agentToggleBtn) {
            agentToggleBtn.addEventListener('click', () => setAgentMode(!agentMode));
        }
        if (agentChipClose) {
            agentChipClose.addEventListener('click', () => setAgentMode(false));
        }

        if (providerToggle) {
            providerToggle.querySelectorAll('.aip-prov').forEach(btn => {
                btn.addEventListener('click', () => {
                    providerToggle.querySelectorAll('.aip-prov').forEach(b => {
                        b.classList.remove('active');
                        b.setAttribute('aria-checked', 'false');
                    });
                    btn.classList.add('active');
                    btn.setAttribute('aria-checked', 'true');
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

            const tierIcons = {
                premium:    { icon: 'fa-gem',              color: '#c084fc', label: 'Premium' },
                standard:   { icon: 'fa-bolt',             color: '#60a5fa', label: 'Standard' },
                economy:    { icon: 'fa-feather',          color: '#34d399', label: 'Fast' },
                discovered: { icon: 'fa-magnifying-glass', color: '#f59e0b', label: 'Discovered (auto-detected from Claude CLI history)' },
            };

            // Default option
            const defOpt = document.createElement('button');
            defOpt.className = 'aim-option' + (selectedModel === '' ? ' active' : '');
            defOpt.setAttribute('role', 'option');
            defOpt.setAttribute('aria-label', 'Auto - best model selected per task type');
            defOpt.setAttribute('data-testid', 'model-option-auto');
            defOpt.innerHTML = `
                <div class="aim-option-main">
                    <i class="fas fa-magic aim-option-icon" style="color:#94a3b8"></i>
                    <span class="aim-option-name">Auto</span>
                    <span class="aim-option-badge" style="background:rgba(148,163,184,0.15);color:#94a3b8">default</span>
                </div>
                <div class="aim-option-desc">Best model selected per task type</div>
            `;
            defOpt.addEventListener('click', () => selectModel('', 'Auto'));
            modelDropdown.appendChild(defOpt);

            // Group by tier
            const grouped = {};
            for (const m of currentModels) {
                const tier = m.tier || 'standard';
                if (!grouped[tier]) grouped[tier] = [];
                grouped[tier].push(m);
            }

            for (const tier of ['premium', 'standard', 'economy', 'discovered']) {
                const models = grouped[tier];
                if (!models || !models.length) continue;
                const t = tierIcons[tier] || tierIcons.standard;

                const sep = document.createElement('div');
                sep.className = 'aim-tier-sep';
                sep.innerHTML = `<i class="fas ${t.icon}" style="color:${t.color}"></i> ${t.label}`;
                modelDropdown.appendChild(sep);

                for (const m of models) {
                    const opt = document.createElement('button');
                    opt.className = 'aim-option' + (selectedModel === m.id ? ' active' : '');
                    opt.setAttribute('role', 'option');
                    opt.setAttribute('aria-label', `${m.display_name} - ${m.cost || ''} ${tier} tier`);
                    opt.setAttribute('data-testid', `model-option-${m.id}`);

                    const costStr = m.cost || '';
                    const thinkBadge = m.thinking === 'adaptive'
                        ? '<span class="aim-option-badge" style="background:rgba(168,85,247,0.15);color:#a855f7">adaptive</span>'
                        : '';
                    const recTags = (m.recommended_for || []).slice(0, 2).map(r =>
                        `<span class="aim-rec-tag">${r}</span>`
                    ).join('');

                    opt.innerHTML = `
                        <div class="aim-option-main">
                            <i class="fas ${t.icon} aim-option-icon" style="color:${t.color}"></i>
                            <span class="aim-option-name">${m.display_name}</span>
                            ${thinkBadge}
                        </div>
                        <div class="aim-option-meta">
                            ${costStr ? `<span class="aim-cost">${costStr}</span>` : ''}
                            ${recTags}
                        </div>
                    `;
                    opt.addEventListener('click', () => selectModel(m.id, m.display_name));
                    modelDropdown.appendChild(opt);
                }
            }

            // Update label
            if (modelLabel) {
                const sel = currentModels.find(m => m.id === selectedModel);
                modelLabel.textContent = sel ? sel.display_name : 'Auto';
            }
        }

        function selectModel(id, name) {
            selectedModel = id;
            if (modelLabel) modelLabel.textContent = name;
            if (modelDropdown) {
                modelDropdown.classList.remove('show');
                modelBtn?.classList.remove('open');
                modelDropdown.querySelectorAll('.aim-option').forEach(o =>
                    o.classList.toggle('active', false));
                // Find and mark active
                const opts = modelDropdown.querySelectorAll('.aim-option');
                for (const o of opts) {
                    const n = o.querySelector('.aim-option-name');
                    if (n && n.textContent === name) { o.classList.add('active'); break; }
                }
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
                const isImage = file.type.startsWith('image/');
                const isPdf = file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf');
                if (!isImage && !isPdf) continue;
                const reader = new FileReader();
                reader.onload = async (e) => {
                    const dataUrl = e.target.result;
                    try {
                        const res = await pywebview.api.ai_edit_save_image(file.name, dataUrl);
                        if (res.status === 'success') {
                            attachedImages.push({ name: file.name, path: res.path, dataUrl: isImage ? dataUrl : null, isPdf });
                            renderThumbs();
                        }
                    } catch (err) { console.error('[AI EDIT] File save:', err); }
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
                const preview = img.isPdf
                    ? `<div class="ai-edit-thumb-pdf"><i class="fas fa-file-pdf"></i><span>${img.name}</span></div>`
                    : `<img src="${img.dataUrl || ''}" alt="${img.name}">`;
                div.innerHTML = `${preview}
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

        // ── New Chat button ──
        newChatBtn?.addEventListener('click', async () => {
            if (!await waitForApi()) return;
            try { await pywebview.api.ai_edit_new_chat(); } catch(e) {}
            if (streamOutput) streamOutput.innerHTML = '';
            toast('New chat started', 'info');
        });

        // ── Chat History button ──
        historyBtn?.addEventListener('click', async (e) => {
            e.stopPropagation();
            if (historyDrop?.classList.contains('show')) {
                historyDrop.classList.remove('show');
                return;
            }
            if (!await waitForApi()) return;
            try {
                const res = await pywebview.api.ai_edit_list_sessions();
                if (!res || !res.sessions || res.sessions.length === 0) {
                    historyDrop.innerHTML = '<div class="aip-hist-empty">No chat history yet</div>';
                } else {
                    historyDrop.innerHTML = res.sessions.map(s => {
                        const date = s.updated_at ? new Date(s.updated_at).toLocaleDateString(undefined, {month:'short', day:'numeric'}) : '';
                        const cost = s.total_cost_usd ? `$${s.total_cost_usd.toFixed(2)}` : '';
                        const meta = [s.turn_count + ' turns', cost, date].filter(Boolean).join(' · ');
                        const prompt = s.last_prompt || 'No messages';
                        return `<div class="aip-hist-item" data-sid="${s.session_id}">
                            <div class="aip-hist-top">
                                <span class="aip-hist-file">${esc(s.file_name || 'untitled')}</span>
                                <span class="aip-hist-meta">${esc(meta)}</span>
                                <button class="aip-hist-del" data-del="${s.session_id}" title="Delete">&times;</button>
                            </div>
                            <span class="aip-hist-prompt">${esc(prompt)}</span>
                        </div>`;
                    }).join('');
                }
                historyDrop.classList.add('show');
            } catch (err) { console.error('[AI EDIT] History error:', err); }
        });

        // History dropdown: click to resume, X to delete
        historyDrop?.addEventListener('click', async (e) => {
            e.stopPropagation();
            const delBtn = e.target.closest('.aip-hist-del');
            if (delBtn) {
                const sid = delBtn.dataset.del;
                try { await pywebview.api.ai_edit_delete_session(sid); } catch(err) {}
                delBtn.closest('.aip-hist-item')?.remove();
                if (!historyDrop.querySelector('.aip-hist-item')) {
                    historyDrop.innerHTML = '<div class="aip-hist-empty">No chat history yet</div>';
                }
                return;
            }
            const item = e.target.closest('.aip-hist-item');
            if (!item) return;
            const sid = item.dataset.sid;
            historyDrop.classList.remove('show');
            try {
                const res = await pywebview.api.ai_edit_resume_session(sid);
                if (res.status === 'ok' && res.session) {
                    // Render previous turns in the output area
                    if (streamOutput) {
                        streamOutput.innerHTML = '';
                        for (const turn of (res.session.turns || [])) {
                            const sep = document.createElement('div');
                            sep.className = 'ai-chat-separator';
                            sep.innerHTML = `<div class="ai-chat-user-msg"><i class="fas fa-user"></i> ${esc(turn.prompt || '')}</div>`;
                            streamOutput.appendChild(sep);
                            if (turn.response) {
                                const resp = document.createElement('div');
                                resp.className = 'ai-chat-response';
                                resp.textContent = turn.response;
                                streamOutput.appendChild(resp);
                            }
                        }
                        streamOutput.scrollTop = streamOutput.scrollHeight;
                    }
                    toast(`Resumed session (${res.session.turns?.length || 0} turns)`, 'info');
                }
            } catch (err) { console.error('[AI EDIT] Resume error:', err); }
        });

        // Close history dropdown when clicking elsewhere
        document.addEventListener('click', () => historyDrop?.classList.remove('show'));

        // ══════════════════════════════════════════════════════════════
        // F-09: Style Memory modal
        // ══════════════════════════════════════════════════════════════
        const memoryBtn    = document.getElementById('aiEditMemoryBtn');
        const memoryModal  = document.getElementById('aiEditMemoryModal');
        const memoryEditor = document.getElementById('aiEditMemoryEditor');
        const memoryPath   = document.getElementById('aiEditMemoryPath');
        const memoryProps  = document.getElementById('aiEditMemoryProposals');
        const memorySave   = document.getElementById('aiEditMemorySave');
        const memoryRefresh = document.getElementById('aiEditMemoryRefresh');
        const memoryStatus = document.getElementById('aiEditMemoryStatus');
        const memoryDot    = document.getElementById('aiEditMemoryDot');

        function setMemoryStatus(msg, kind) {
            if (!memoryStatus) return;
            memoryStatus.textContent = msg || '';
            memoryStatus.style.color = kind === 'error' ? '#f87171'
                : kind === 'ok' ? '#86efac'
                : 'var(--text-secondary)';
        }

        function renderProposal(p) {
            const wrap = document.createElement('div');
            wrap.className = 'aip-memory-prop';
            wrap.dataset.pid = p.id;
            wrap.setAttribute('role', 'listitem');
            wrap.innerHTML = `
                <div class="aip-memory-prop-trigger">trigger: ${esc(p.trigger || '')}</div>
                <div class="aip-memory-prop-rule">${esc(p.suggested_rule || p.correction_text || '')}</div>
                <div class="aip-memory-prop-actions">
                    <button class="aip-memory-prop-btn" data-action="dismiss">Dismiss</button>
                    <button class="aip-memory-prop-btn accept" data-action="accept">Add to memory</button>
                </div>`;
            return wrap;
        }

        async function loadMemory() {
            if (!await waitForApi()) return;
            try {
                const res = await pywebview.api.ai_edit_get_memory();
                if (!res || res.status !== 'ok') {
                    setMemoryStatus(res?.message || 'Failed to load memory', 'error');
                    return;
                }
                if (memoryEditor) memoryEditor.value = res.style_md || '';
                if (memoryPath) memoryPath.textContent = res.path || '';
                if (memoryProps) {
                    memoryProps.innerHTML = '';
                    const proposals = res.proposals || [];
                    if (proposals.length === 0) {
                        memoryProps.innerHTML = '<div class="aip-memory-empty">No proposals yet. Correct the AI in a chat and a proposal will appear here.</div>';
                    } else {
                        proposals.forEach(p => memoryProps.appendChild(renderProposal(p)));
                    }
                }
                updateMemoryDot(res.proposals?.length || 0);
                setMemoryStatus('Loaded', 'ok');
            } catch (err) {
                console.error('[AI EDIT] Memory load error:', err);
                setMemoryStatus(String(err), 'error');
            }
        }

        function updateMemoryDot(count) {
            if (!memoryDot) return;
            memoryDot.style.display = count > 0 ? 'block' : 'none';
            memoryDot.title = count > 0 ? `${count} pending proposal${count > 1 ? 's' : ''}` : '';
        }

        async function refreshProposalBadge() {
            if (!await waitForApi()) return;
            try {
                const res = await pywebview.api.ai_edit_list_memory_proposals();
                if (res?.status === 'ok') updateMemoryDot((res.proposals || []).length);
            } catch (e) { /* silent */ }
        }

        // Hide the preview video element completely while the memory
        // modal is open. Pausing alone still leaves the last frame
        // composited on its own GPU layer, which Chromium can paint OVER
        // the modal regardless of z-index — that's the "video overlay
        // bug" the user kept hitting. visibility:hidden removes the
        // element from the compositor entirely.
        let _videoStateForMemory = null;  // { wasPlaying, prevVisibility, prevDisplay }
        function _hidePreviewForMemory() {
            const v = document.getElementById('previewVideo');
            if (!v) return;
            _videoStateForMemory = {
                wasPlaying: !v.paused && !v.ended,
                prevVisibility: v.style.visibility || '',
                prevDisplay: v.style.display || '',
            };
            try { v.pause(); } catch (e) {}
            // visibility:hidden keeps layout (so the placeholder space
            // stays the same) but removes the compositor layer.
            v.style.visibility = 'hidden';
        }
        function _restorePreviewAfterMemory() {
            if (!_videoStateForMemory) return;
            const v = document.getElementById('previewVideo');
            const state = _videoStateForMemory;
            _videoStateForMemory = null;
            if (!v) return;
            v.style.visibility = state.prevVisibility;
            v.style.display = state.prevDisplay;
            if (state.wasPlaying) v.play().catch(() => {});
        }

        memoryBtn?.addEventListener('click', async (e) => {
            e.stopPropagation();
            if (!memoryModal) return;
            _hidePreviewForMemory();
            memoryModal.hidden = false;
            await loadMemory();
            memoryEditor?.focus();
        });

        memoryModal?.addEventListener('click', (e) => {
            if (e.target.closest('[data-memory-close]')) {
                memoryModal.hidden = true;
                _restorePreviewAfterMemory();
            }
        });

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && memoryModal && !memoryModal.hidden) {
                memoryModal.hidden = true;
                _restorePreviewAfterMemory();
            }
        });

        memorySave?.addEventListener('click', async () => {
            if (!await waitForApi()) return;
            memorySave.disabled = true;
            setMemoryStatus('Saving…');
            try {
                const res = await pywebview.api.ai_edit_save_memory(memoryEditor?.value || '');
                if (res?.status === 'ok') {
                    setMemoryStatus('Saved ✓', 'ok');
                    if (typeof toast === 'function') toast('Style memory saved', 'success');
                } else {
                    setMemoryStatus(res?.message || 'Save failed', 'error');
                }
            } catch (err) {
                setMemoryStatus(String(err), 'error');
            } finally {
                memorySave.disabled = false;
            }
        });

        memoryRefresh?.addEventListener('click', loadMemory);

        // Proposal accept / dismiss
        memoryProps?.addEventListener('click', async (e) => {
            const btn = e.target.closest('.aip-memory-prop-btn');
            if (!btn) return;
            const card = btn.closest('.aip-memory-prop');
            const pid = card?.dataset.pid;
            if (!pid || !await waitForApi()) return;
            const action = btn.dataset.action;
            try {
                if (action === 'accept') {
                    const res = await pywebview.api.ai_edit_accept_memory_proposal(pid);
                    if (res?.status === 'ok') {
                        card.remove();
                        await loadMemory();
                        if (typeof toast === 'function') toast('Rule added to memory', 'success');
                    } else {
                        setMemoryStatus(res?.message || 'Accept failed', 'error');
                    }
                } else if (action === 'dismiss') {
                    const res = await pywebview.api.ai_edit_dismiss_memory_proposal(pid);
                    if (res?.status === 'ok') {
                        card.remove();
                        await refreshProposalBadge();
                        if (!memoryProps.querySelector('.aip-memory-prop')) {
                            memoryProps.innerHTML = '<div class="aip-memory-empty">No proposals yet. Correct the AI in a chat and a proposal will appear here.</div>';
                        }
                    }
                }
            } catch (err) {
                setMemoryStatus(String(err), 'error');
            }
        });

        // Expose for the streaming-done hook (resetSendBtn).
        window._aiEditRefreshMemoryBadge = refreshProposalBadge;

        // Poll once on panel init so the badge reflects any stale proposals.
        refreshProposalBadge();

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
            if (typeof updateAppState === 'function') updateAppState({ ai: 'none' });
            if (sendBtn) {
                sendBtn.disabled = false;
                sendBtn.classList.remove('cancel-mode');
                sendBtn.innerHTML = '<i class="fas fa-arrow-up"></i>';
            }
            if (statusText) statusText.style.display = 'none';
            // F-09: a turn just ended — check whether a memory proposal was
            // staged by the backend and light up the brain-icon dot.
            if (typeof window._aiEditRefreshMemoryBadge === 'function') {
                setTimeout(() => window._aiEditRefreshMemoryBadge(), 300);
            }
        }

        // ── Send / Cancel ──
        sendBtn?.addEventListener('click', async () => {
            if (isStreaming) {
                if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
                try {
                    if (agentActive) await pywebview.api.ai_agent_cancel();
                    else if (currentProvider === 'claude') await pywebview.api.ai_edit_claude_cancel();
                    else await pywebview.api.ai_edit_cancel();
                } catch(e) {}
                resetSendBtn();
                if (streamBox) streamBox.style.display = 'none';
                toast('Cancelled', 'info');
                return;
            }

            const prompt = promptInput.value.trim();
            if (!prompt) { toast('Enter a prompt', 'warning'); promptInput.focus(); return; }

            // ── Agent mode ──
            if (agentMode) {
                await startAgent(prompt);
                return;
            }

            originalCode = editor.getModel().getValue();
            isStreaming = true;
            if (typeof updateAppState === 'function') updateAppState({ ai: 'streaming' });
            sendBtn.innerHTML = '<i class="fas fa-stop"></i>';
            sendBtn.classList.add('cancel-mode');
            statusText.style.display = 'flex';
            diffActions.style.display = 'none';
            if (streamBox) streamBox.style.display = 'flex';
            // Insert chat separator instead of clearing output
            if (streamOutput) {
                const sep = document.createElement('div');
                sep.className = 'ai-chat-separator';
                const truncPrompt = prompt.length > 80 ? prompt.substring(0, 80) + '...' : prompt;
                sep.innerHTML = `<div class="ai-chat-user-msg"><i class="fas fa-user"></i> ${esc(truncPrompt)}</div>`;
                streamOutput.appendChild(sep);
                requestAnimationFrame(() => { streamOutput.scrollTop = streamOutput.scrollHeight; });
            }
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

                // Create a response container for this message's output
                let responseContainer = null;
                if (streamOutput) {
                    responseContainer = document.createElement('div');
                    responseContainer.className = 'ai-chat-response';
                    streamOutput.appendChild(responseContainer);
                }

                pollTimer = setInterval(async () => {
                    try {
                        const poll = await pywebview.api[pollFn]();
                        if (responseContainer) {
                            const clean = poll.filtered_output || '';
                            if (clean) responseContainer.innerHTML = renderEnhancedOutput(clean);
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
                                // Keep streamBox visible for chat history
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

        // ══════════════════════════════════════════════════════════════
        //  AGENT MODE — autonomous generate → render → fix loop
        // ══════════════════════════════════════════════════════════════

        let agentPollTimer = null;
        let lastAgentActionId = 0;
        let agentActive = false;

        const STEP_ICONS = {
            generating: 'fa-brain',
            rendering: 'fa-play',
            capturing: 'fa-camera',
            analyzing: 'fa-search',
            fixing: 'fa-wrench',
            done: 'fa-check-circle',
            error: 'fa-times-circle',
        };

        // Expose so agent-trigger redirect can call it from outside IIFE
        window.startAIAgent = function(desc, model) {
            if (model) selectedModel = model;
            startAgent(desc);
        };

        async function startAgent(description) {
            if (!await waitForApi()) return;
            isStreaming = true;
            agentActive = true;
            sendBtn.innerHTML = '<i class="fas fa-stop"></i>';
            sendBtn.classList.add('cancel-mode');
            statusText.style.display = 'flex';
            statusMsg.textContent = 'Starting agent...';
            if (agentLog) agentLog.innerHTML = '';
            if (agentShots) agentShots.innerHTML = '';
            if (streamBox) { streamBox.style.display = 'flex'; }
            if (streamOutput) streamOutput.innerHTML = '';

            try {
                const imagePaths = attachedImages.map(img => img.path);
                const currentCode = await pywebview.api.get_code();
                const res = await pywebview.api.ai_agent_start(description, 5, selectedModel, currentProvider, imagePaths, currentCode);
                if (res.status === 'error') {
                    toast(res.message, 'error');
                    resetSendBtn(); agentActive = false;
                    return;
                }
                lastAgentActionId = 0;
                agentPollTimer = setInterval(pollAgent, 400);
            } catch (e) {
                toast('Agent start failed: ' + e.message, 'error');
                resetSendBtn(); agentActive = false;
            }
        }

        async function pollAgent() {
            if (!agentActive) { clearInterval(agentPollTimer); return; }
            try {
                const st = await pywebview.api.ai_agent_poll();
                statusMsg.textContent = st.message || st.step;
                renderAgentLog(st.history || []);

                // Show live stream output from agent edit subprocess
                if (st.stream_output && streamOutput) {
                    streamOutput.innerHTML = renderEnhancedOutput(st.stream_output);
                    requestAnimationFrame(() => {
                        streamOutput.scrollTop = streamOutput.scrollHeight;
                        // Also scroll parent panel
                        const panel = streamOutput.closest('.aip-body, .aip-stream-box');
                        if (panel) panel.scrollTop = panel.scrollHeight;
                    });
                }

                // Execute actions from agent backend
                const act = st.action;
                if (act && act._id && act._id !== lastAgentActionId) {
                    lastAgentActionId = act._id;
                    await executeAgentAction(act, st.ui_action);
                }

                // Done / error
                if (!st.active && (st.step === 'done' || st.step === 'error' || st.step === 'idle')) {
                    clearInterval(agentPollTimer); agentPollTimer = null;
                    agentActive = false;
                    resetSendBtn();
                    if (st.step === 'done') toast('Agent finished!', 'success');
                    else if (st.step === 'error') toast('Agent error: ' + st.message, 'error');
                }
            } catch (e) { console.error('[AGENT POLL]', e); }
        }

        function renderAgentLog(history) {
            if (!agentLog) return;
            agentLog.innerHTML = '';
            history.forEach((h, i) => {
                const isLast = i === history.length - 1;
                const icon = STEP_ICONS[h.step] || 'fa-circle';
                const cls = isLast ? (h.step === 'error' ? 'error' : 'active')
                                   : (h.step === 'done' ? 'done' : '');
                const spin = isLast && !['done','error'].includes(h.step) ? ' fa-spin' : '';
                const el = document.createElement('div');
                el.className = 'aip-agent-step ' + cls;
                el.innerHTML = `<i class="fas ${isLast && spin ? 'fa-circle-notch' + spin : icon}"></i> ${esc(h.message)}`;
                agentLog.appendChild(el);
            });
            agentLog.scrollTop = agentLog.scrollHeight;
        }

        async function executeAgentAction(action, uiAction) {
            // Visual cursor animation
            if (uiAction && uiAction.type === 'click_button' && uiAction.target) {
                await showAgentCursor(uiAction.target, uiAction.label || '');
            }

            if (action.type === 'set_code_and_preview') {
                // Set code in editor
                if (typeof editor !== 'undefined' && editor) {
                    editor.setValue(action.code);
                }
                // ── Wait for any in-flight preview/render to finish ──
                // Before this fix, the agent fired quickPreview() while a
                // previous render was still running. quickPreview's
                // `if (job.running) return` guard silently rejected the
                // call, so monitorPreviewForAgent ended up listening for
                // a preview that never started — agent hung forever.
                // Now we explicitly poll until the previous job finishes
                // (or we hit a 5-minute safety cap).
                if (typeof job !== 'undefined' && job) {
                    let waited = 0;
                    const POLL_MS = 200;
                    const MAX_WAIT_MS = 5 * 60 * 1000;
                    while (job.running && waited < MAX_WAIT_MS) {
                        await new Promise(r => setTimeout(r, POLL_MS));
                        waited += POLL_MS;
                    }
                    if (job.running) {
                        console.warn('[AGENT] Previous job still running after 5min — forcing through anyway');
                    } else if (waited > 0) {
                        console.log(`[AGENT] Waited ${waited}ms for previous job to finish before agent preview`);
                    }
                }
                // Install completion hooks BEFORE triggering preview so
                // we don't miss a fast finish.
                monitorPreviewForAgent();
                if (typeof quickPreview === 'function') {
                    // Await the preview kick-off; quickPreview itself
                    // returns once the API call is dispatched (the actual
                    // render completes later via the watcher → previewCompleted
                    // hook the monitor installed above).
                    try { await quickPreview(); }
                    catch (e) { console.error('[AGENT] quickPreview error:', e); }
                }
            }

            if (action.type === 'capture_screenshots') {
                const count = action.count || 8;
                const shots = await captureVideoScreenshots(count);
                renderScreenshotThumbs(shots);
                // Send back to agent WITH image data so AI can actually see them
                try {
                    await pywebview.api.ai_agent_feedback({
                        type: 'screenshots',
                        screenshots: shots.map(s => ({
                            time: s.time,
                            dataUrl: s.dataUrl
                        }))
                    });
                } catch (e) { console.error('[AGENT] screenshot feedback:', e); }
            }
        }

        // ── Visual cursor that "clicks" a button ──
        async function showAgentCursor(targetId, label) {
            const target = document.getElementById(targetId);
            if (!target) return;

            const cursor = document.createElement('div');
            cursor.className = 'agent-cursor';
            cursor.innerHTML = '<i class="fas fa-mouse-pointer"></i>';
            document.body.appendChild(cursor);

            // Start from center of screen
            cursor.style.left = (window.innerWidth / 2) + 'px';
            cursor.style.top = (window.innerHeight / 2) + 'px';

            await new Promise(r => requestAnimationFrame(r));

            // Animate to target
            const rect = target.getBoundingClientRect();
            cursor.style.left = (rect.left + rect.width / 2) + 'px';
            cursor.style.top = (rect.top + rect.height / 2) + 'px';

            await new Promise(r => setTimeout(r, 550));

            // Click effect
            cursor.classList.add('click');
            target.classList.add('agent-target-glow');

            await new Promise(r => setTimeout(r, 400));
            target.classList.remove('agent-target-glow');
            cursor.remove();
        }

        // ── Monitor preview/render completion for agent feedback ──
        function monitorPreviewForAgent() {
            const origComplete = window.previewCompleted;
            const origFailed = window.previewFailed;
            const origRenderComplete = window.renderCompleted;
            const origRenderFailed = window.renderFailed;

            // 10-minute defensive timeout: if neither completion nor
            // failure callback fires (e.g. manim hung, watcher crashed),
            // force a render_error so the agent can break out of its
            // wait loop and try to recover or stop cleanly.
            let settled = false;
            const SAFETY_MS = 10 * 60 * 1000;
            const safetyTimer = setTimeout(() => {
                if (settled) return;
                settled = true;
                cleanup();
                console.warn('[AGENT] preview/render safety timeout fired — sending render_error to unblock');
                try {
                    pywebview.api.ai_agent_feedback({
                        type: 'render_error',
                        error: 'Preview/render did not complete within 10 minutes (safety timeout). Possible causes: hung manim subprocess, missed completion event, or stuck PTY.'
                    });
                } catch (e) {}
            }, SAFETY_MS);

            function cleanup() {
                window.previewCompleted = origComplete;
                window.previewFailed = origFailed;
                window.renderCompleted = origRenderComplete;
                window.renderFailed = origRenderFailed;
                clearTimeout(safetyTimer);
            }

            window.previewCompleted = function(outputPath) {
                if (settled) return; settled = true;
                cleanup();
                if (origComplete) origComplete(outputPath);
                try {
                    pywebview.api.ai_agent_feedback({ type: 'render_success', path: outputPath });
                } catch (e) {}
            };
            window.previewFailed = function(error) {
                if (settled) return; settled = true;
                cleanup();
                if (origFailed) origFailed(error);
                try {
                    pywebview.api.ai_agent_feedback({ type: 'render_error', error: error });
                } catch (e) {}
            };
            window.renderCompleted = function(outputPath, autoSave, suggestedName) {
                if (settled) return; settled = true;
                cleanup();
                if (origRenderComplete) origRenderComplete(outputPath, autoSave, suggestedName);
                try {
                    pywebview.api.ai_agent_feedback({ type: 'render_success', path: outputPath });
                } catch (e) {}
            };
            window.renderFailed = function(error) {
                if (settled) return; settled = true;
                cleanup();
                if (origRenderFailed) origRenderFailed(error);
                try {
                    pywebview.api.ai_agent_feedback({ type: 'render_error', error: error });
                } catch (e) {}
            };

            // (Old 10-min safety timer removed — replaced by the
            // settled-flag safetyTimer at the top of this function which
            // properly clears itself on success/failure and avoids a
            // double-fire if both completion and the timer race.)
        }

        // ── Capture screenshots from preview video ──
        // fps=1: capture 1 frame per second of video for thorough review
        async function captureVideoScreenshots(count) {
            const video = document.getElementById('previewVideo');
            if (!video || !video.duration || video.duration === Infinity || video.readyState < 2) {
                await new Promise(r => setTimeout(r, 1500));
                if (!video || !video.duration || video.duration === Infinity) return [];
            }

            const canvas = document.createElement('canvas');
            canvas.width = Math.min(video.videoWidth || 640, 640);
            canvas.height = Math.min(video.videoHeight || 360, 360);
            const ctx = canvas.getContext('2d');
            const duration = video.duration;
            const frames = [];

            // 1 frame per second, capped at 30 to avoid huge payloads
            const actualCount = Math.min(Math.max(Math.floor(duration), 1), 30);

            for (let i = 0; i < actualCount; i++) {
                const t = (duration / (actualCount + 1)) * (i + 1);
                video.currentTime = t;
                await new Promise(r => {
                    const onSeeked = () => { video.removeEventListener('seeked', onSeeked); r(); };
                    video.addEventListener('seeked', onSeeked);
                });
                ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
                frames.push({
                    time: t.toFixed(2),
                    dataUrl: canvas.toDataURL('image/jpeg', 0.6)
                });
            }
            video.currentTime = 0;
            return frames;
        }

        function renderScreenshotThumbs(shots) {
            if (!agentShots) return;
            agentShots.innerHTML = '';
            shots.forEach(s => {
                const img = document.createElement('img');
                img.src = s.dataUrl;
                img.title = `Frame at ${s.time}s`;
                img.addEventListener('click', () => {
                    const video = document.getElementById('previewVideo');
                    if (video) { video.currentTime = parseFloat(s.time); video.play(); }
                });
                agentShots.appendChild(img);
            });
        }

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

            const tierIcons = {
                premium:    { icon: 'fa-gem',              color: '#c084fc', label: 'Premium' },
                standard:   { icon: 'fa-bolt',             color: '#60a5fa', label: 'Standard' },
                economy:    { icon: 'fa-feather',          color: '#34d399', label: 'Fast' },
                discovered: { icon: 'fa-magnifying-glass', color: '#f59e0b', label: 'Discovered (auto-detected from Claude CLI history)' },
            };

            const defOpt = document.createElement('button');
            defOpt.className = 'aim-option' + (selectedModel === '' ? ' active' : '');
            defOpt.innerHTML = `
                <div class="aim-option-main">
                    <i class="fas fa-magic aim-option-icon" style="color:#94a3b8"></i>
                    <span class="aim-option-name">Auto</span>
                    <span class="aim-option-badge" style="background:rgba(148,163,184,0.15);color:#94a3b8">default</span>
                </div>
                <div class="aim-option-desc">Best model selected per task type</div>
            `;
            defOpt.addEventListener('click', () => selectModel('', 'Auto'));
            modelDropdown.appendChild(defOpt);

            const grouped = {};
            for (const m of currentModels) {
                const tier = m.tier || 'standard';
                if (!grouped[tier]) grouped[tier] = [];
                grouped[tier].push(m);
            }

            for (const tier of ['premium', 'standard', 'economy', 'discovered']) {
                const models = grouped[tier];
                if (!models || !models.length) continue;
                const t = tierIcons[tier] || tierIcons.standard;
                const sep = document.createElement('div');
                sep.className = 'aim-tier-sep';
                sep.innerHTML = `<i class="fas ${t.icon}" style="color:${t.color}"></i> ${t.label}`;
                modelDropdown.appendChild(sep);
                for (const m of models) {
                    const opt = document.createElement('button');
                    opt.className = 'aim-option' + (selectedModel === m.id ? ' active' : '');
                    const costStr = m.cost || '';
                    const thinkBadge = m.thinking === 'adaptive'
                        ? '<span class="aim-option-badge" style="background:rgba(168,85,247,0.15);color:#a855f7">adaptive</span>'
                        : '';
                    opt.innerHTML = `
                        <div class="aim-option-main">
                            <i class="fas ${t.icon} aim-option-icon" style="color:${t.color}"></i>
                            <span class="aim-option-name">${m.display_name || m.display}</span>
                            ${thinkBadge}
                        </div>
                        ${costStr ? `<div class="aim-option-meta"><span class="aim-cost">${costStr}</span></div>` : ''}
                    `;
                    opt.addEventListener('click', () => selectModel(m.id, m.display_name || m.display));
                    modelDropdown.appendChild(opt);
                }
            }

            // Models without tier (Codex extras)
            const noTier = currentModels.filter(m => !m.tier);
            for (const m of noTier) {
                const opt = document.createElement('button');
                opt.className = 'aim-option' + (selectedModel === m.id ? ' active' : '');
                opt.innerHTML = `<div class="aim-option-main"><span class="aim-option-name">${m.display_name || m.id}</span></div>`;
                opt.addEventListener('click', () => selectModel(m.id, m.display_name || m.id));
                modelDropdown.appendChild(opt);
            }

            if (modelLabel) {
                const sel = currentModels.find(m => m.id === selectedModel);
                modelLabel.textContent = sel ? (sel.display_name || sel.display) : 'Auto';
            }
        }

        function selectModel(id, name) {
            selectedModel = id;
            if (modelLabel) modelLabel.textContent = name;
            if (modelDropdown) {
                modelDropdown.classList.remove('show');
                modelBtn?.classList.remove('open');
                modelDropdown.querySelectorAll('.aim-option').forEach(o =>
                    o.classList.toggle('active', false));
                const opts = modelDropdown.querySelectorAll('.aim-option');
                for (const o of opts) {
                    const n = o.querySelector('.aim-option-name');
                    if (n && n.textContent === name) { o.classList.add('active'); break; }
                }
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
                const isImage = file.type.startsWith('image/');
                const isPdf = file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf');
                if (!isImage && !isPdf) continue;
                const reader = new FileReader();
                reader.onload = async (e) => {
                    const dataUrl = e.target.result;
                    try {
                        const res = await pywebview.api.ai_edit_save_image(file.name, dataUrl);
                        if (res.status === 'success') {
                            attachedImages.push({ name: file.name, path: res.path, dataUrl: isImage ? dataUrl : null, isPdf });
                            renderThumbs();
                        }
                    } catch (err) { console.error('[AI EDIT WIN] File save:', err); }
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
                const preview = img.isPdf
                    ? `<div class="aiw-thumb-pdf"><i class="fas fa-file-pdf"></i><span>${img.name}</span></div>`
                    : `<img src="${img.dataUrl || ''}" alt="${img.name}">`;
                div.innerHTML = `${preview}
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
