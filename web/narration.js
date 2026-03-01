// narration.js — Auto-narration on render/preview (Kokoro TTS)
// When code contains narrate("...") calls, TTS is generated and merged
// automatically after render/preview completes.  No panel needed.
// Dependencies: editor, pywebview, toast(), appendConsole()
(function initAutoNarration() {
    'use strict';

    const NARRATE_RE = /@?narrate\(\s*["'](.+?)["']\s*\)/g;

    /** Check if current editor code has narrate() calls. */
    function codeHasNarrate() {
        if (typeof editor === 'undefined' || !editor) return false;
        const code = editor.getModel().getValue();
        NARRATE_RE.lastIndex = 0;
        return NARRATE_RE.test(code);
    }

    /** Attach WebVTT subtitles to a <video> element. */
    async function attachSubtitles(videoEl) {
        try {
            if (!pywebview?.api?.get_narration_subtitles) return;
            const res = await pywebview.api.get_narration_subtitles();
            if (res.status !== 'success' || !res.vtt) return;

            // Remove existing narration tracks
            videoEl.querySelectorAll('track[data-narration]').forEach(t => t.remove());

            const blob = new Blob([res.vtt], { type: 'text/vtt' });
            const track = document.createElement('track');
            track.kind = 'subtitles';
            track.label = 'Narration';
            track.srclang = 'en';
            track.src = URL.createObjectURL(blob);
            track.default = true;
            track.setAttribute('data-narration', '1');
            videoEl.appendChild(track);

            setTimeout(() => {
                for (const t of videoEl.textTracks) {
                    if (t.label === 'Narration') { t.mode = 'showing'; break; }
                }
            }, 100);
        } catch (e) {
            console.log('[NARRATION] Subtitle error:', e);
        }
    }

    /**
     * Auto-narrate: called by renderCompleted / previewCompleted.
     * 1. Check if code has narrate() calls
     * 2. Generate TTS audio (poll until done)
     * 3. Merge audio with the rendered video
     * 4. Reload preview with narrated video + subtitles
     */
    window._autoNarrate = async function (videoPath) {
        if (!codeHasNarrate()) return;
        if (!pywebview?.api?.generate_narration) return;

        const code = editor.getModel().getValue();
        const voice = (() => { try { return localStorage.getItem('narration_voice') || 'af_heart'; } catch(e) { return 'af_heart'; } })();
        const speed = 1.0;

        console.log('[NARRATION] Auto-narrate starting...');
        if (typeof appendConsole === 'function') appendConsole('Generating narration...', 'info');
        if (typeof toast === 'function') toast('Generating narration...', 'info');

        // 1. Start generation
        try {
            const res = await pywebview.api.generate_narration(code, voice, speed);
            if (res.status === 'error') {
                console.warn('[NARRATION]', res.message);
                if (typeof toast === 'function') toast('Narration: ' + res.message, 'warning');
                return;
            }
        } catch (e) {
            console.error('[NARRATION] generate error:', e);
            return;
        }

        // 2. Poll until done
        const poll = () => new Promise((resolve) => {
            const timer = setInterval(async () => {
                try {
                    const p = await pywebview.api.narration_poll();
                    if (p.message && typeof appendConsole === 'function') {
                        appendConsole('Narration: ' + p.message, 'info');
                    }
                    if (p.done) {
                        clearInterval(timer);
                        resolve(p);
                    }
                } catch (e) {
                    clearInterval(timer);
                    resolve({ status: 'error', message: String(e) });
                }
            }, 800);
        });

        const result = await poll();
        if (result.status !== 'success') {
            const msg = result.message || 'TTS generation failed';
            console.warn('[NARRATION]', msg);
            if (typeof toast === 'function') toast('Narration: ' + msg, 'error');
            return;
        }

        if (typeof appendConsole === 'function')
            appendConsole(`Narration: ${result.segments.length} segments, ${result.total_duration}s — merging with video...`, 'info');

        // 3. Merge audio with video
        try {
            const merge = await pywebview.api.merge_narration_video(videoPath);
            if (merge.status === 'success') {
                if (typeof toast === 'function') toast('Narration merged!', 'success');
                if (typeof appendConsole === 'function') appendConsole('Narration merged with video', 'success');

                // 4. Reload preview with narrated video + subtitles
                const vid = document.getElementById('previewVideo');
                if (vid && merge.output_path) {
                    if (typeof showPreview === 'function') {
                        showPreview(merge.output_path, true);
                    } else {
                        vid.src = merge.output_path + '?t=' + Date.now();
                    }
                    window._lastRenderedVideo = merge.output_path;
                    attachSubtitles(vid);
                }
            } else {
                if (typeof toast === 'function') toast('Merge: ' + (merge.message || 'failed'), 'error');
            }
        } catch (e) {
            console.error('[NARRATION] merge error:', e);
            if (typeof toast === 'function') toast('Narration merge error', 'error');
        }
    };

    console.log('[NARRATION] Auto-narration loaded');
})();
