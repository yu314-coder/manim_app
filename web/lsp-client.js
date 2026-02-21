/**
 * Manim Studio — LSP Client
 *
 * Connects Monaco Editor to basedpyright-langserver (or pyright-langserver)
 * running as a subprocess in the Python host via the PyWebView API bridge.
 *
 * Transport:  JS → pywebview.api.lsp_send(jsonString)  → Python stdin → LSP server
 *             LSP server stdout → Python thread → window.lspReceive(jsonString) → JS
 *
 * The editor is immediately usable.  LSP starts 2 s after the editor mounts,
 * completely in the background — zero perceived startup lag.
 *
 * If basedpyright is not installed the client silently stays inactive and the
 * static completions from python-completions.js continue to work.
 */

(function () {
    'use strict';

    // ── workspace URIs (set to real paths by setup_lsp_workspace before init) ──
    // Fallback virtual paths used only if the backend call fails.
    let LSP_WORKSPACE_URI = 'file:///lsp-workspace';
    let LSP_FILE_URI      = 'file:///lsp-workspace/scene.py';

    // ── severity maps ─────────────────────────────────────────────────────────
    // LSP → Monaco marker severity
    const LSP_SEV = { 1: 8 /*Error*/, 2: 4 /*Warning*/, 3: 2 /*Info*/, 4: 1 /*Hint*/ };

    // LSP CompletionItemKind → Monaco CompletionItemKind (by numeric value)
    // Monaco: Text=18 Method=0 Function=1 Constructor=2 Field=3 Variable=4
    //         Class=5 Interface=7 Module=8 Property=9 Keyword=17 Snippet=22
    //         Color=19 File=20 Enum=15 EnumMember=16 Constant=14 Struct=6 TypeParameter=24
    const LSP_KIND_MAP = {
        1:18, 2:0, 3:1, 4:2, 5:3, 6:4, 7:5, 8:7, 9:8, 10:9,
        11:12, 12:13, 13:15, 14:17, 15:22, 16:19, 17:20, 18:21,
        19:23, 20:16, 21:14, 22:6, 23:10, 24:11, 25:24,
    };

    // ── LspClient class ───────────────────────────────────────────────────────
    class LspClient {
        constructor() {
            this._nextId     = 1;
            this._pending    = new Map();   // id → { resolve, reject, timer }
            this._handlers   = new Map();   // method → fn(params)
            this._initialized = false;
            this._docVersion  = 1;
        }

        // ── incoming message from Python ──────────────────────────────────────
        receive(jsonString) {
            let msg;
            try { msg = JSON.parse(jsonString); }
            catch (e) { console.warn('[LSP] Bad JSON:', e); return; }

            if (msg.id !== undefined && this._pending.has(msg.id)) {
                const { resolve, reject, timer } = this._pending.get(msg.id);
                this._pending.delete(msg.id);
                clearTimeout(timer);
                if (msg.error) reject(new Error(msg.error.message || JSON.stringify(msg.error)));
                else           resolve(msg.result);

            } else if (msg.method) {
                const h = this._handlers.get(msg.method);
                if (h) { try { h(msg.params); } catch (e) { console.warn('[LSP] Handler error:', e); } }
            }
        }

        // ── outgoing request (returns a Promise) ──────────────────────────────
        request(method, params, timeoutMs = 6000) {
            const id  = this._nextId++;
            const msg = JSON.stringify({ jsonrpc: '2.0', id, method, params });
            return new Promise((resolve, reject) => {
                const timer = setTimeout(() => {
                    this._pending.delete(id);
                    reject(new Error(`LSP timeout: ${method}`));
                }, timeoutMs);
                this._pending.set(id, { resolve, reject, timer });
                pywebview.api.lsp_send(msg).catch(reject);
            });
        }

        // ── outgoing notification (fire-and-forget) ───────────────────────────
        notify(method, params) {
            const msg = JSON.stringify({ jsonrpc: '2.0', method, params });
            pywebview.api.lsp_send(msg).catch(e => console.warn('[LSP] notify error:', e));
        }

        // ── register notification handler ─────────────────────────────────────
        on(method, handler) { this._handlers.set(method, handler); }
    }

    // ── global instance ───────────────────────────────────────────────────────
    const client = new LspClient();

    // Python calls this via evaluate_js("window.lspReceive(...)")
    window.lspReceive = (jsonString) => client.receive(jsonString);

    // ── Monaco provider helpers ───────────────────────────────────────────────
    function lspRangeToMonaco(r) {
        return {
            startLineNumber: r.start.line + 1,
            startColumn:     r.start.character + 1,
            endLineNumber:   r.end.line + 1,
            endColumn:       r.end.character + 1,
        };
    }

    function lspMarkdownToString(content) {
        if (!content) return '';
        if (typeof content === 'string') return content;
        if (Array.isArray(content)) return content.map(lspMarkdownToString).join('\n\n');
        return content.value || content.language
            ? (content.language ? '```' + content.language + '\n' + content.value + '\n```' : content.value || '')
            : '';
    }

    // ── register Monaco providers ─────────────────────────────────────────────
    function registerProviders(monaco, editor) {

        // ─ completions ────────────────────────────────────────────────────────
        monaco.languages.registerCompletionItemProvider('python', {
            triggerCharacters: ['.', '(', ',', ' ', 'import', 'from'],

            async provideCompletionItems(model, position) {
                if (!client._initialized) return null;

                let result;
                try {
                    result = await client.request('textDocument/completion', {
                        textDocument: { uri: LSP_FILE_URI },
                        position: { line: position.lineNumber - 1, character: position.column - 1 },
                        context:  { triggerKind: 1 },
                    }, 5000);
                } catch (e) {
                    return null;   // timeout or error — static completions still show
                }

                if (!result) return null;
                const items = Array.isArray(result) ? result : (result.items || []);

                return {
                    suggestions: items.map(item => {
                        const edit = item.textEdit;
                        const snippet = item.insertTextFormat === 2;
                        return {
                            label:            item.label,
                            kind:             LSP_KIND_MAP[item.kind] ?? 18,
                            detail:           item.detail || '',
                            documentation:    { value: lspMarkdownToString(item.documentation) },
                            insertText:       edit ? edit.newText : (item.insertText || item.label),
                            insertTextRules:  snippet ? 4 : 0,
                            range:            edit?.range ? lspRangeToMonaco(edit.range) : undefined,
                            sortText:         item.sortText || item.label,
                            filterText:       item.filterText || item.label,
                        };
                    }),
                    incomplete: result.isIncomplete || false,
                };
            },
        });

        // ─ hover ─────────────────────────────────────────────────────────────
        monaco.languages.registerHoverProvider('python', {
            async provideHover(model, position) {
                if (!client._initialized) return null;

                let result;
                try {
                    result = await client.request('textDocument/hover', {
                        textDocument: { uri: LSP_FILE_URI },
                        position: { line: position.lineNumber - 1, character: position.column - 1 },
                    }, 4000);
                } catch (e) { return null; }

                if (!result || !result.contents) return null;

                const value = lspMarkdownToString(result.contents);
                if (!value) return null;
                return {
                    contents: [{ value }],
                    range: result.range ? lspRangeToMonaco(result.range) : undefined,
                };
            },
        });

        // ─ signature help ─────────────────────────────────────────────────────
        monaco.languages.registerSignatureHelpProvider('python', {
            signatureHelpTriggerCharacters:   ['(', ','],
            signatureHelpRetriggerCharacters: [','],

            async provideSignatureHelp(model, position) {
                if (!client._initialized) return null;

                let result;
                try {
                    result = await client.request('textDocument/signatureHelp', {
                        textDocument: { uri: LSP_FILE_URI },
                        position: { line: position.lineNumber - 1, character: position.column - 1 },
                    }, 4000);
                } catch (e) { return null; }

                if (!result || !result.signatures?.length) return null;

                return {
                    value: {
                        activeSignature: result.activeSignature || 0,
                        activeParameter: result.activeParameter || 0,
                        signatures: result.signatures.map(sig => ({
                            label:         sig.label,
                            documentation: { value: lspMarkdownToString(sig.documentation) },
                            parameters: (sig.parameters || []).map(p => ({
                                label:         p.label,
                                documentation: { value: lspMarkdownToString(p.documentation) },
                            })),
                        })),
                    },
                    dispose() {},
                };
            },
        });

        // ─ diagnostics (errors / warnings) ───────────────────────────────────
        client.on('textDocument/publishDiagnostics', (params) => {
            if (params.uri !== LSP_FILE_URI) return;
            const model = editor.getModel();
            if (!model) return;

            const markers = (params.diagnostics || []).map(d => ({
                severity:        LSP_SEV[d.severity] ?? 4,
                startLineNumber: d.range.start.line + 1,
                startColumn:     d.range.start.character + 1,
                endLineNumber:   d.range.end.line + 1,
                endColumn:       d.range.end.character + 1,
                message:         d.message,
                source:          d.source || 'basedpyright',
                code:            d.code ? String(d.code) : undefined,
            }));

            monaco.editor.setModelMarkers(model, 'lsp', markers);
        });

        console.log('[LSP] Monaco providers registered');
    }

    // ── document sync helpers ─────────────────────────────────────────────────
    let _syncTimer = null;

    function syncDocument(editor) {
        clearTimeout(_syncTimer);
        _syncTimer = setTimeout(() => {
            if (!client._initialized) return;
            client.notify('textDocument/didChange', {
                textDocument: { uri: LSP_FILE_URI, version: client._docVersion++ },
                contentChanges: [{ text: editor.getValue() }],
            });
        }, 300);
    }

    // ── initialisation sequence ───────────────────────────────────────────────
    async function _doInit(monaco, editor) {
        // 1. Tell Python to start basedpyright
        let startResult;
        try {
            startResult = await pywebview.api.start_lsp();
        } catch (e) {
            console.warn('[LSP] start_lsp() failed:', e);
            return;
        }

        if (!startResult || startResult.status === 'error') {
            console.warn('[LSP] Server not available:', startResult?.message);
            // Static completions from python-completions.js continue to work.
            return;
        }

        console.log('[LSP] Server started:', startResult.exe || 'ok');

        // 2. Set up a real workspace directory with pyrightconfig.json so
        //    basedpyright can find the Manim venv and resolve imports correctly.
        try {
            const wsInfo = await pywebview.api.setup_lsp_workspace();
            if (wsInfo?.status === 'success') {
                LSP_WORKSPACE_URI = wsInfo.workspace_uri;
                LSP_FILE_URI      = wsInfo.file_uri;
                console.log('[LSP] Using real workspace:', LSP_WORKSPACE_URI);
            }
        } catch (e) {
            console.warn('[LSP] setup_lsp_workspace failed, using virtual path:', e);
        }

        // 3. Get venv Python path for initializationOptions
        const venvPython = await pywebview.api.get_python_path?.()
            .catch(() => null);

        // 4. LSP initialize handshake
        let initResult;
        try {
            initResult = await client.request('initialize', {
                processId:    null,
                rootUri:      LSP_WORKSPACE_URI,
                capabilities: {
                    textDocument: {
                        synchronization: {
                            didSave: false,
                            dynamicRegistration: false,
                        },
                        completion: {
                            completionItem: {
                                snippetSupport:          true,
                                documentationFormat:     ['markdown', 'plaintext'],
                                deprecatedSupport:       true,
                                preselectSupport:        true,
                                labelDetailsSupport:     true,
                                insertReplaceSupport:    true,
                                resolveSupport:          { properties: ['documentation', 'detail'] },
                            },
                            contextSupport: true,
                        },
                        hover: {
                            contentFormat: ['markdown', 'plaintext'],
                            dynamicRegistration: false,
                        },
                        signatureHelp: {
                            signatureInformation: {
                                documentationFormat: ['markdown', 'plaintext'],
                                parameterInformation: { labelOffsetSupport: true },
                            },
                            contextSupport: true,
                        },
                        publishDiagnostics: {
                            relatedInformation: true,
                            tagSupport: { valueSet: [1, 2] },
                        },
                    },
                    workspace: {
                        configuration:       false,
                        didChangeConfiguration: { dynamicRegistration: false },
                    },
                },
                initializationOptions: {
                    pythonPath: venvPython || undefined,
                },
            }, 20000 /* generous timeout for first init */);
        } catch (e) {
            console.warn('[LSP] initialize timed out or failed:', e);
            return;
        }

        // 5. Send initialized notification (required by LSP spec)
        client.notify('initialized', {});

        // 6. Reinforce Python path via workspace/didChangeConfiguration so
        //    basedpyright picks it up even if pyrightconfig.json wasn't read yet.
        if (venvPython) {
            client.notify('workspace/didChangeConfiguration', {
                settings: {
                    python:        { pythonPath: venvPython },
                    basedpyright:  { pythonPath: venvPython },
                    pyright:       { pythonPath: venvPython },
                },
            });
        }

        // 7. Open the document with current editor content
        client.notify('textDocument/didOpen', {
            textDocument: {
                uri:        LSP_FILE_URI,
                languageId: 'python',
                version:    client._docVersion++,
                text:       editor.getValue(),
            },
        });

        // 8. Mark client as ready — providers will now make real LSP calls
        client._initialized = true;
        console.log('[LSP] Ready. Server capabilities:', Object.keys(initResult?.capabilities || {}));

        // 9. Keep document in sync as the user types
        editor.onDidChangeModelContent(() => syncDocument(editor));

        // 10. Show status to user
        if (window.showToast) {
            showToast('IntelliSense ready (basedpyright)', 'success', 2500);
        }
    }

    // ── public entry point ────────────────────────────────────────────────────
    /**
     * Call this once, after the Monaco editor is created.
     * Waits 2 seconds so the editor is fully interactive first.
     */
    window.initializeLsp = function (monaco, editor) {
        registerProviders(monaco, editor);

        // Defer actual LSP startup — editor is already usable right now
        setTimeout(() => {
            // Make sure PyWebView API is ready before we call it
            if (typeof pywebview !== 'undefined' && pywebview.api) {
                _doInit(monaco, editor).catch(e => console.warn('[LSP] Init error:', e));
            } else {
                // Wait for pywebviewready event (shouldn't happen in normal flow)
                window.addEventListener('pywebviewready', () => {
                    _doInit(monaco, editor).catch(e => console.warn('[LSP] Init error:', e));
                }, { once: true });
            }
        }, 2000);
    };

    // ── expose helpers for debugging ──────────────────────────────────────────
    window._lspClient = client;

})();
