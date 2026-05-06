// Advanced features (F-03 Visual Diff, F-08 Sketches, F-04 Inspector,
// F-01 Timeline, F-12 Render Farm).
//
// One file to keep the dock-and-modal plumbing together. Each section is
// scoped via an IIFE so the sections can't leak state into each other.

(function () {
    'use strict';

    // ── Shared helpers ───────────────────────────────────────────────
    function escHtml(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }
    function toastOr(msg, kind) {
        if (typeof window.showToast === 'function') window.showToast(msg, kind);
        else if (typeof window.toast === 'function') window.toast(msg, kind);
        else console.log(`[toast ${kind || ''}] ${msg}`);
    }
    async function waitApi(ms = 15000) {
        // Bumped from 5s to 15s — pywebview.api can be slow to bind on
        // first launch (cold dep checker, terminal init). 15s is well
        // under the user-visible timeout but plenty for normal cases.
        const start = Date.now();
        while (!window.pywebview?.api) {
            if (Date.now() - start > ms) return false;
            await new Promise(r => setTimeout(r, 50));
        }
        return true;
    }

    // Generic close-on-backdrop & ESC for any .feat-modal on page
    document.addEventListener('click', (e) => {
        if (e.target.closest('[data-feat-close]')) {
            const modal = e.target.closest('.feat-modal');
            if (modal) modal.hidden = true;
        }
    });
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            document.querySelectorAll('.feat-modal:not([hidden])').forEach(m => { m.hidden = true; });
        }
    });

    // Default flag values used if the backend API isn't reachable in time.
    // Mirrors app.py defaults — keeps the UI usable even if the dep
    // checker is starving the main thread on cold launch.
    const DEFAULT_FLAGS = {
        visual_diff: true,
        render_farm: true,
        ai_sketch:   true,
        inspector:   false,
        timeline:    false,
    };

    // Fetch feature flags once on load so all sections can gate themselves.
    const flagsReady = (async () => {
        if (!await waitApi()) {
            console.warn('[features.js] pywebview.api not ready in 15s — using DEFAULT_FLAGS');
            return { ...DEFAULT_FLAGS };
        }
        try {
            const res = await window.pywebview.api.get_feature_flags();
            const f = (res && res.status === 'ok') ? (res.features || {}) : {};
            console.log('[features.js] feature flags loaded:', f);
            // Merge over defaults so missing keys in saved settings don't
            // accidentally hide default-on features.
            return { ...DEFAULT_FLAGS, ...f };
        } catch (e) {
            console.warn('[features.js] get_feature_flags failed, using defaults:', e);
            return { ...DEFAULT_FLAGS };
        }
    })();

    // ── Top-toolbar launchers ────────────────────────────────────────
    // Wire each feature launcher button. Buttons are ALWAYS visible
    // (HTML has no display:none) — the flag check happens at click time
    // so the user can discover features even when their flag is off,
    // and toggling a flag in settings takes effect immediately.
    async function freshFlags() {
        try {
            if (!await waitApi(2000)) return null;
            const res = await window.pywebview.api.get_feature_flags();
            if (res && res.status === 'ok') {
                return { ...DEFAULT_FLAGS, ...(res.features || {}) };
            }
        } catch (e) { console.warn('[features.js] freshFlags failed:', e); }
        return null;
    }
    // Expose so other code paths can re-check without bypassing defaults.
    window._featGetFlags = freshFlags;

    // (Earlier "hide Timeline until preview completes" logic removed —
    // user clarified they want the button always discoverable. The
    // dock just opens immediately on click; preview-sync is attached
    // when openTimeline runs, and gracefully no-ops if no video is
    // currently loaded.)

    flagsReady.then(initialFlags => {
        // All experimental toolbar launchers (Sketch / Inspector /
        // Timeline) removed per user request 2026-05-05. Their backend
        // Python modules remain on disk and reachable via pywebview.api
        // for future re-introduction, but no UI surfaces them. Keeping
        // the launcher loop infrastructure makes it trivial to put them
        // back later — just append to this array.
        const launchers = [];
        for (const l of launchers) {
            const el = document.getElementById(l.id);
            if (!el) {
                console.warn(`[features.js] launcher element not found: #${l.id}`);
                continue;
            }
            el.style.display = '';
            if (!initialFlags[l.flag]) el.classList.add('feat-disabled');

            el.addEventListener('click', async () => {
                console.log(`[features.js] launcher clicked: #${l.id}`);
                // Open the modal/dock IMMEDIATELY (synchronously) so the
                // user sees something happen on every click — never block
                // visible feedback on async flag/API checks.
                const target = document.getElementById(l.modalId);
                if (target) {
                    target.hidden = false;
                    target.style.display = '';
                    console.log(`[features.js] unhid #${l.modalId}`);
                } else {
                    console.error(`[features.js] modal/dock #${l.modalId} missing`);
                }
                // Then run the feature's own opener (which does
                // post-open setup like loading data, focusing inputs,
                // attaching event listeners).
                const fn = window[l.openName];
                if (typeof fn === 'function') {
                    try { fn(); }
                    catch (e) { console.error('[features.js] open fn error:', e); }
                } else {
                    console.warn(`[features.js] window.${l.openName} missing — dock unhidden but no model loaded`);
                }
                // Async flag check: if the feature is disabled, surface a
                // toast pointing the user to Settings, but don't undo the
                // open (user can still see the empty dock and read the
                // toast).
                try {
                    const live = await freshFlags() || initialFlags;
                    console.log(`[features.js] flags after click: live=${live[l.flag]} initial=${initialFlags[l.flag]}`);
                    el.classList.toggle('feat-disabled', !live[l.flag]);
                    if (!live[l.flag]) {
                        toastOr(`${l.label} is disabled — enable it in Settings → Experimental Features for full functionality.`, 'info');
                    }
                } catch (e) { console.warn('[features.js] flag check failed:', e); }
            });
            console.log(`[features.js] launcher wired: #${l.id} initial flag=${initialFlags[l.flag]}; window.${l.openName}=${typeof window[l.openName]}`);
        }
        // (F-12 Render Farm toggle removed by user request 2026-05-06.)
        // Make sure the legacy global is falsy so any leftover farm-routing
        // checks in renderer_desktop.js take the standard render path.
        window._featFarmEnabled = false;
    });

    // ══════════════════════════════════════════════════════════════
    // F-03  Visual Diff
    // ══════════════════════════════════════════════════════════════
    (function visualDiff() {
        const btn       = document.getElementById('diffReviewBtn');
        const badge     = document.getElementById('diffReviewBadge');
        const modal     = document.getElementById('diffReviewModal');
        const listEl    = document.getElementById('diffReviewList');
        const scrubber  = document.getElementById('diffReviewScrubber');
        const frameLbl  = document.getElementById('diffReviewFrameLabel');
        const stripEl   = document.getElementById('diffReviewStrip');
        const statsEl   = document.getElementById('diffReviewStats');
        const subtitle  = document.getElementById('diffReviewSubtitle');
        const baseImg   = document.getElementById('diffReviewBaseImg');
        const curImg    = document.getElementById('diffReviewCurImg');
        const acceptBtn = document.getElementById('diffReviewAccept');
        const revertBtn = document.getElementById('diffReviewRevert');
        const blockBtn  = document.getElementById('diffReviewBlock');

        if (!btn || !modal) return;

        let state = {
            current: null,   // meta object for active render
            diff: null,      // {drift_per_frame, flagged, …}
            frame: 0,
            renders: [],
        };

        async function loadList() {
            if (!await waitApi()) return;
            try {
                const res = await window.pywebview.api.visual_diff_list(40);
                state.renders = (res && res.status === 'ok') ? (res.renders || []) : [];
                renderList();
            } catch (e) { console.warn('[F-03] list error', e); }
        }
        function renderList() {
            if (!listEl) return;
            listEl.innerHTML = state.renders.map(r => {
                const isCur = state.current && r.render_id === state.current.render_id;
                const base = r.is_baseline ? '<span class="badge-baseline">baseline</span>' : '';
                const date = r.created_at ? r.created_at.slice(5, 16).replace('T', ' ') : '';
                return `<div class="feat-diff-list-item ${isCur ? 'active' : ''}" role="listitem" data-rid="${escHtml(r.render_id)}">
                    <div class="t">${escHtml(r.render_id.slice(0, 8))}${base}</div>
                    <div class="m">${escHtml(date)} · ${r.frame_count || 0}f · ${escHtml(r.status || 'pending')}</div>
                </div>`;
            }).join('') || '<div class="feat-inspector-empty">No renders recorded yet.</div>';
        }

        listEl?.addEventListener('click', async (e) => {
            const item = e.target.closest('.feat-diff-list-item');
            if (!item) return;
            const rid = item.dataset.rid;
            const meta = state.renders.find(r => r.render_id === rid);
            if (!meta) return;
            await openRender(meta);
        });

        async function openRender(meta, diff) {
            state.current = meta;
            renderList();
            if (!diff) {
                const res = await window.pywebview.api.visual_diff_fetch(meta.render_id);
                diff = (res && res.status === 'ok') ? res.diff : null;
            }
            state.diff = diff;
            updateSubtitle();
            renderStrip();
            const total = diff?.total_frames || (meta.frame_count || 0);
            scrubber.max = Math.max(0, total - 1);
            state.frame = (diff?.flagged?.[0] ?? 0) || 0;
            scrubber.value = state.frame;
            await updateFrame();
        }

        function updateSubtitle() {
            if (!subtitle || !state.diff) { return; }
            const d = state.diff;
            if (!d.baseline_id) {
                subtitle.textContent = 'No baseline yet — first render is auto-accepted.';
            } else if (d.auto_accepted) {
                subtitle.textContent = `Auto-accepted · drift ${((d.mean_drift || 0) * 100).toFixed(2)}%.`;
            } else {
                subtitle.textContent = `${d.flagged_count} flagged of ${d.total_frames} · mean drift ${((d.mean_drift || 0) * 100).toFixed(2)}% (threshold ${((d.threshold || 0) * 100).toFixed(1)}%).`;
            }
            if (statsEl) statsEl.textContent = subtitle.textContent;
        }

        function renderStrip() {
            if (!stripEl || !state.diff) return;
            const drift = state.diff.drift_per_frame || [];
            const flagged = new Set(state.diff.flagged || []);
            const max = 50;   // cap cells for legibility
            const step = Math.max(1, Math.ceil(drift.length / max));
            let html = '';
            for (let i = 0; i < drift.length; i += step) {
                const d = drift[i] || 0;
                const cls = (flagged.has(i) ? 'flagged ' : '') + (i === state.frame ? 'cur' : '');
                const alpha = Math.min(1, 0.2 + d * 8);
                const bg = flagged.has(i) ? '' : `background:rgba(34,197,94,${alpha.toFixed(2)});`;
                html += `<div class="feat-diff-cell ${cls}" data-f="${i}" style="${bg}" title="frame ${i} drift ${(d * 100).toFixed(2)}%"></div>`;
            }
            stripEl.innerHTML = html;
        }

        stripEl?.addEventListener('click', (e) => {
            const cell = e.target.closest('.feat-diff-cell');
            if (!cell) return;
            state.frame = parseInt(cell.dataset.f, 10) || 0;
            scrubber.value = state.frame;
            updateFrame();
        });
        scrubber?.addEventListener('input', () => {
            state.frame = parseInt(scrubber.value, 10) || 0;
            updateFrame();
        });

        async function updateFrame() {
            if (!state.current) return;
            if (frameLbl) frameLbl.textContent = `${state.frame} / ${state.diff?.total_frames || 0}`;
            renderStrip();
            // Fetch thumbs
            try {
                const curRes = await window.pywebview.api.visual_diff_thumb(
                    state.current.render_id, state.frame);
                if (curImg && curRes?.url) curImg.src = curRes.url;
            } catch (e) {}
            if (state.diff?.baseline_id) {
                try {
                    const baseRes = await window.pywebview.api.visual_diff_thumb(
                        state.diff.baseline_id, state.frame);
                    if (baseImg && baseRes?.url) baseImg.src = baseRes.url;
                } catch (e) {}
            } else if (baseImg) {
                baseImg.removeAttribute('src');
            }
        }

        async function action(kind) {
            if (!state.current) return;
            const fn = window.pywebview.api[`visual_diff_${kind}`];
            if (!fn) return;
            try {
                const res = await fn(state.current.render_id);
                if (res?.status === 'ok') {
                    toastOr(`Render ${kind}ed`, 'success');
                    await loadList();
                    updateButtonBadge();
                } else {
                    toastOr(`Failed: ${res?.message || 'unknown'}`, 'error');
                }
            } catch (e) { toastOr(String(e), 'error'); }
        }
        acceptBtn?.addEventListener('click', () => action('accept'));
        revertBtn?.addEventListener('click', () => action('revert'));
        blockBtn ?.addEventListener('click', () => action('block'));

        // Keyboard shortcuts while modal is open
        document.addEventListener('keydown', (e) => {
            if (modal.hidden) return;
            if (e.key === 'j' || e.key === 'J') { jumpFlagged(1); e.preventDefault(); }
            else if (e.key === 'k' || e.key === 'K') { jumpFlagged(-1); e.preventDefault(); }
            else if (e.key === 'a' || e.key === 'A') { action('accept'); e.preventDefault(); }
            else if (e.key === 'r' || e.key === 'R') { action('revert'); e.preventDefault(); }
            else if (e.key === 'b' || e.key === 'B') { action('block'); e.preventDefault(); }
        });
        function jumpFlagged(dir) {
            const flagged = state.diff?.flagged || [];
            if (!flagged.length) return;
            let idx = flagged.findIndex(f => f > state.frame);
            if (dir < 0) {
                const reversed = [...flagged].reverse();
                const rIdx = reversed.findIndex(f => f < state.frame);
                if (rIdx >= 0) state.frame = reversed[rIdx];
            } else {
                if (idx >= 0) state.frame = flagged[idx];
                else state.frame = flagged[0];
            }
            scrubber.value = state.frame;
            updateFrame();
        }

        btn.addEventListener('click', async () => {
            modal.hidden = false;
            await loadList();
            if (state.renders[0]) await openRender(state.renders[0]);
        });

        function updateButtonBadge() {
            const flaggedCount = state.diff?.flagged_count || 0;
            const hasHistory = state.renders?.length > 0;
            if (!btn) return;
            btn.style.display = hasHistory ? '' : 'none';
            if (badge) {
                if (flaggedCount > 0 && state.current?.status === 'pending') {
                    badge.style.display = '';
                    badge.textContent = flaggedCount;
                } else {
                    badge.style.display = 'none';
                }
            }
        }

        // Invoked from renderCompleted: hash frames, diff, maybe open review.
        window._visualDiffAfterRender = async function (outputPath) {
            const flags = await flagsReady;
            if (!flags.visual_diff) return;
            if (!await waitApi()) return;
            try {
                const res = await window.pywebview.api.visual_diff_record(outputPath);
                if (!res || res.status !== 'ok') return;
                await loadList();
                const meta = state.renders.find(r => r.render_id === res.render_id);
                state.current = meta || null;
                state.diff = res.diff;
                updateButtonBadge();
                const d = res.diff || {};
                if (d.auto_accepted) {
                    // Silent success.
                } else if (d.flagged_count > 0) {
                    toastOr(`Visual drift: ${d.flagged_count} frames flagged — click the compare icon to review`, 'warning');
                }
            } catch (e) { console.warn('[F-03] record error', e); }
        };

        // Show the button once we know we have history at all
        (async () => {
            const flags = await flagsReady;
            if (!flags.visual_diff) return;
            await loadList();
            updateButtonBadge();
        })();
    })();

    // ══════════════════════════════════════════════════════════════
    // F-08  AI Sketches
    // ══════════════════════════════════════════════════════════════
    (function sketches() {
        const modal = document.getElementById('sketchModal');
        const grid  = document.getElementById('sketchGrid');
        const promptEl = document.getElementById('sketchPrompt');
        const goBtn = document.getElementById('sketchGenerate');
        const statusEl = document.getElementById('sketchStatus');
        const logEl = document.getElementById('sketchLog');
        const logWrap = document.getElementById('sketchLogWrap');
        if (!modal || !grid) return;

        function appendLog(lines) {
            if (!logEl || !Array.isArray(lines)) return;
            // Replace contents — backend always sends the cumulative tail.
            logEl.textContent = lines.join('\n');
            logEl.scrollTop = logEl.scrollHeight;
        }

        function renderCards(cards) {
            grid.innerHTML = cards.map((c, i) => {
                const letter = String.fromCharCode(65 + i);  // A, B, C
                const ready = !!c.video;
                return `
                <div class="feat-sketch-card" data-idx="${i}" role="listitem">
                    <div class="feat-sketch-card-label">Variant ${letter}</div>
                    ${ready
                        ? `<video src="${escHtml(c.video)}" autoplay loop muted playsinline></video>`
                        : `<div class="feat-sketch-placeholder">${escHtml(c.placeholder || 'Rendering…')}</div>`}
                    <div class="feat-sketch-actions">
                        <button class="feat-btn primary" data-action="fork" title="Save this variant as a new .py file next to your current file" ${ready ? '' : 'disabled'}>
                            <i class="fas fa-floppy-disk"></i> Use this
                        </button>
                        <button class="feat-btn" data-action="refine" title="Open this variant's code in AI Edit for further iteration" ${ready ? '' : 'disabled'}>
                            <i class="fas fa-pen-to-square"></i> Edit with AI
                        </button>
                        <button class="feat-btn" data-action="reroll" title="Generate a different version for just this slot">
                            <i class="fas fa-rotate"></i> Try again
                        </button>
                    </div>
                </div>`;
            }).join('');
        }

        async function generate() {
            const flags = await flagsReady;
            if (!flags.ai_sketch) { toastOr('Sketch mode disabled in settings', 'warning'); return; }
            const prompt = (promptEl?.value || '').trim();
            if (!prompt) { toastOr('Enter a sketch prompt first', 'warning'); return; }
            if (!await waitApi()) return;
            goBtn.disabled = true;
            statusEl.textContent = 'Calling Claude…';
            renderCards([
                { placeholder: 'Variant A — pending' },
                { placeholder: 'Variant B — pending' },
                { placeholder: 'Variant C — pending' },
            ]);

            // Kick off the (now async) backend job.
            let started;
            try {
                started = await window.pywebview.api.sketch_generate(prompt);
            } catch (e) {
                statusEl.textContent = String(e);
                goBtn.disabled = false;
                return;
            }
            if (started?.status !== 'started') {
                statusEl.textContent = started?.message || 'Failed to start';
                goBtn.disabled = false;
                return;
            }

            // Poll for progress every 500ms. Stop on done/error.
            let dots = 0;
            const elapsed = Date.now();
            // Auto-open the live log so the user sees streaming progress
            if (logWrap && !logWrap.open) logWrap.open = true;
            const tick = async () => {
                try {
                    const s = await window.pywebview.api.sketch_status();
                    if (!s) return;
                    dots = (dots + 1) % 4;
                    const dur = ((Date.now() - elapsed) / 1000).toFixed(0);
                    statusEl.textContent = `${s.message || ''} ${'.'.repeat(dots)} (${dur}s)`;
                    if (Array.isArray(s.cards) && s.cards.length) {
                        renderCards(s.cards);
                    }
                    if (Array.isArray(s.log)) appendLog(s.log);
                    if (s.step === 'done' || s.step === 'error' || !s.active) {
                        clearInterval(poll);
                        goBtn.disabled = false;
                        if (s.step === 'error') {
                            statusEl.textContent = `Error: ${s.message || 'unknown'}`;
                        } else {
                            const ready = (s.cards || []).filter(c => c.video).length;
                            statusEl.textContent = `${ready}/3 variants ready (${dur}s)`;
                        }
                    }
                } catch (e) {
                    /* keep polling — transient errors during pywebview bridge churn */
                }
            };
            const poll = setInterval(tick, 500);
            tick();   // immediate first poll so the user sees progress fast
        }
        goBtn?.addEventListener('click', generate);
        promptEl?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') { e.preventDefault(); generate(); }
        });
        grid?.addEventListener('click', async (e) => {
            const btn = e.target.closest('button[data-action]');
            if (!btn) return;
            const card = btn.closest('.feat-sketch-card');
            const idx = parseInt(card?.dataset.idx, 10);
            const action = btn.dataset.action;
            if (!await waitApi()) return;
            try {
                if (action === 'fork') {
                    const res = await window.pywebview.api.sketch_fork(idx);
                    if (res?.status === 'ok') {
                        toastOr(`Forked: ${res.file}`, 'success');
                        modal.hidden = true;
                    }
                } else if (action === 'reroll') {
                    btn.disabled = true;
                    const res = await window.pywebview.api.sketch_reroll(idx, (promptEl?.value || '').trim());
                    if (res?.status === 'ok' && res.card) {
                        const cards = Array.from(grid.children).map((el) => {
                            const v = el.querySelector('video');
                            return v ? { video: v.src } : { placeholder: 'pending' };
                        });
                        cards[idx] = res.card;
                        renderCards(cards);
                    }
                    btn.disabled = false;
                } else if (action === 'refine') {
                    toastOr('Refine: open AI Edit and paste the forked code to iterate.', 'info');
                }
            } catch (e) { toastOr(String(e), 'error'); }
        });

        // Expose an opener. Flag gating is done by the launcher click
        // handler — by the time we get here the user has already passed
        // the gate, so just open the modal.
        window.openSketchModal = async () => {
            modal.hidden = false;
            promptEl?.focus();
        };
    })();

    // ══════════════════════════════════════════════════════════════
    // F-04  Inspector (experimental)
    // ══════════════════════════════════════════════════════════════
    (function inspector() {
        const panel = document.getElementById('inspectorPanel');
        const title = document.getElementById('inspectorTitle');
        const bound = document.getElementById('inspectorBound');
        const body  = document.getElementById('inspectorBody');
        const srcEl = document.getElementById('inspectorSrc');
        const closeBtn = document.getElementById('inspectorClose');
        if (!panel) return;

        let currentObject = null;

        closeBtn?.addEventListener('click', () => { panel.hidden = true; });

        // Alt-click a preview element to inspect. We look for the preview
        // video — when Alt is held and the user clicks, we ask the backend
        // to resolve the click into a mobject's source range.
        document.addEventListener('click', async (e) => {
            if (!e.altKey) return;
            const target = e.target.closest('#previewVideo, #previewImage, [data-testid="preview-video"]');
            if (!target) return;
            const flags = await flagsReady;
            if (!flags.inspector) return;
            // For v1 we don't have preview instrumentation yet — so the user
            // picks a mobject by name via a prompt. The AST machinery is
            // fully wired; only the click-to-bbox pipeline is TODO.
            const name = prompt('Inspector: mobject name (e.g. "self.c1") — click-to-bbox coming soon:');
            if (!name) return;
            await loadObject(name);
            panel.hidden = false;
        }, true);

        async function loadObject(objectPath) {
            if (!await waitApi()) return;
            let code = '';
            try {
                if (typeof getEditorValue === 'function') code = getEditorValue();
                else if (typeof editor !== 'undefined' && editor?.getValue) code = editor.getValue();
            } catch (e) {}
            try {
                const res = await window.pywebview.api.inspector_resolve(objectPath, code || null);
                if (!res || res.status !== 'ok') {
                    if (title) title.textContent = `Not found: ${objectPath}`;
                    if (body) body.innerHTML = `<div class="feat-inspector-empty">${escHtml(res?.message || 'Could not resolve object')}</div>`;
                    if (bound) bound.classList.remove('active');
                    currentObject = null;
                    return;
                }
                currentObject = res;
                if (title) title.textContent = `${res.kind || 'mobject'} — ${objectPath}${res.scratch ? ' (scratch)' : ''}`;
                if (bound) bound.classList.add('active');
                renderKwargs(res.kwargs || []);
                if (srcEl) srcEl.textContent = res.source_excerpt || '';
                if (res.scratch && res.hint) toastOr(res.hint, 'info');
            } catch (e) { toastOr(String(e), 'error'); }
        }

        function renderKwargs(kwargs) {
            if (!body) return;
            if (!kwargs.length) {
                body.innerHTML = '<div class="feat-inspector-empty">No editable kwargs.</div>';
                return;
            }
            const groups = { Color: [], Geometry: [], Transform: [], Other: [] };
            for (const k of kwargs) {
                const g = k.group || 'Other';
                (groups[g] || groups.Other).push(k);
            }
            let html = '';
            for (const [name, rows] of Object.entries(groups)) {
                if (!rows.length) continue;
                html += `<div class="feat-inspector-group"><div class="feat-inspector-group-title">${escHtml(name)}</div>`;
                for (const k of rows) html += renderRow(k);
                html += '</div>';
            }
            body.innerHTML = html;
        }

        function renderRow(k) {
            if (k.type === 'numeric') {
                const step = (k.decimals > 0) ? (1 / Math.pow(10, k.decimals)) : 1;
                return `<div class="feat-inspector-row" data-kwarg="${escHtml(k.name)}">
                    <label>${escHtml(k.name)}</label>
                    <input type="range" min="${k.min}" max="${k.max}" step="${step}" value="${k.value}" data-kind="numeric" data-decimals="${k.decimals || 0}"/>
                    <span class="val">${escHtml(String(k.value))}</span>
                </div>`;
            }
            if (k.type === 'color') {
                return `<div class="feat-inspector-row" data-kwarg="${escHtml(k.name)}">
                    <label>${escHtml(k.name)}</label>
                    <input type="color" value="${escHtml(k.value)}" data-kind="color"/>
                    <span class="val">${escHtml(k.value)}</span>
                </div>`;
            }
            return `<div class="feat-inspector-row" data-kwarg="${escHtml(k.name)}">
                <label>${escHtml(k.name)}</label>
                <span class="val">${escHtml(String(k.value))}</span>
                <span class="lock"><i class="fas fa-lock"></i></span>
            </div>`;
        }

        body?.addEventListener('input', async (e) => {
            if (!currentObject) return;
            const row = e.target.closest('.feat-inspector-row');
            if (!row) return;
            const name = row.dataset.kwarg;
            const kind = e.target.dataset.kind;
            const val  = (kind === 'numeric')
                ? Number(parseFloat(e.target.value).toFixed(parseInt(e.target.dataset.decimals, 10) || 0))
                : e.target.value;
            const valEl = row.querySelector('.val');
            if (valEl) valEl.textContent = String(val);
        });
        body?.addEventListener('change', async (e) => {
            if (!currentObject) return;
            const row = e.target.closest('.feat-inspector-row');
            if (!row) return;
            const name = row.dataset.kwarg;
            const val  = e.target.value;
            if (!await waitApi()) return;
            let code = '';
            try {
                if (typeof getEditorValue === 'function') code = getEditorValue();
                else if (typeof editor !== 'undefined' && editor?.getValue) code = editor.getValue();
            } catch (e) {}
            try {
                const res = await window.pywebview.api.inspector_mutate(
                    currentObject.object_path, name, val, 2, code || null);
                if (res?.status !== 'ok') toastOr(res?.message || 'Mutation failed', 'error');
                else {
                    if (srcEl && res.source_excerpt) srcEl.textContent = res.source_excerpt;
                    // If working on scratch, push updated code back to editor
                    if (res.scratch && res.updated_code && typeof editor !== 'undefined' && editor?.setValue) {
                        const pos = editor.getPosition?.();
                        editor.setValue(res.updated_code);
                        if (pos) try { editor.setPosition(pos); } catch(_) {}
                    }
                }
            } catch (e) { toastOr(String(e), 'error'); }
        });

        window.openInspector = async (objectPath) => {
            panel.hidden = false;
            if (objectPath) await loadObject(objectPath);
        };
    })();


    // (F-01 Timeline removed by user request 2026-05-05.)
    // The Python backend (timeline.py) and ManimAPI methods
    // (timeline_parse, timeline_apply_edits) remain available for
    // future re-introduction.

    // (F-12 Render Farm IIFE removed by user request 2026-05-06.
    // The backend Python module render_farm.py and the ManimAPI methods
    // farm_start / farm_status / farm_cancel / farm_analyse remain on
    // disk for future re-introduction.)

})();
