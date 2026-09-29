//
//  JSEngine.swift
//  ManimStudio
//
//  JavaScript for the terminal's `js` / `node` commands.
//
//  The shell (python-ios-lib's offlinai_shell) writes
//  $TMPDIR/latex_signals/js_eval_request.txt — JSON {"id", "src", "reset"} —
//  then polls up to 30 s for js_eval_resp_<id>.txt, JSON {"ok", "stdout",
//  "result", "error", "stack"}. CodeBench answers from its own JSEngine;
//  ManimStudio had nothing listening, so every `js` / `node` call sat out
//  the 30 s and failed. LaTeXEngine's signal watcher now hands the request
//  file here.
//
//  One JSContext lives across requests, so REPL globals persist the way
//  they do in Node's interactive mode; {"reset": true} starts a fresh one.
//  The context gets a small Node-flavoured environment — console, process,
//  require('fs' | 'path' | 'os' | 'util'), timers and a synchronous fetch —
//  enough for scripting, not a Node runtime.
//

import Foundation
import JavaScriptCore

nonisolated final class JSEngine: @unchecked Sendable {
    static let shared = JSEngine()

    /// Every JavaScriptCore call happens on this queue, never on the main
    /// thread the signal watcher ticks on. Serial, so requests run in order.
    private let queue = DispatchQueue(label: "euleryu.ManimStudio.JSEngine",
                                      qos: .userInitiated)

    // Touched only on `queue`.
    private var context: JSContext?
    private var output = ""
    private var outputTruncated = false
    private var pendingException: JSValue?

    /// Console text kept for one request.
    private static let outputLimit = 4 << 20
    /// How long pending timers may keep a request going. The shell stops
    /// waiting at 30 s, so the answer has to be written well before that.
    private static let timerBudget: TimeInterval = 20
    /// Largest response body one fetch() buffers.
    private static let fetchLimit = 32 << 20

    private init() {}

    /// Called on the main thread when js_eval_request.txt appears: takes
    /// the file (so the next watcher tick doesn't see it again) and answers
    /// from the engine queue.
    func takeRequest(in signalDir: String) {
        let path = signalDir + "js_eval_request.txt"
        guard let data = FileManager.default.contents(atPath: path) else { return }
        try? FileManager.default.removeItem(atPath: path)
        queue.async { self.handle(data, signalDir: signalDir) }
    }

    // MARK: - Requests

    private func handle(_ data: Data, signalDir: String) {
        guard let request = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
              let rawID = request["id"] as? String else { return }
        // The id becomes part of a file name.
        let id = String(rawID.filter { $0.isASCII && ($0.isLetter || $0.isNumber) }.prefix(64))
        guard !id.isEmpty else { return }

        let reply: [String: Any]
        if request["reset"] as? Bool == true {
            context = nil
            reply = ["ok": true, "stdout": "", "result": "", "error": "", "stack": ""]
        } else {
            reply = evaluate(request["src"] as? String ?? "")
        }
        removeStaleReplies(in: signalDir)
        // Atomic, so the shell never reads half a reply.
        let url = URL(fileURLWithPath: signalDir + "js_eval_resp_\(id).txt")
        if let json = try? JSONSerialization.data(withJSONObject: reply) {
            try? json.write(to: url, options: .atomic)
        }
    }

    /// Replies the shell gave up waiting for would otherwise pile up.
    private func removeStaleReplies(in signalDir: String) {
        let fm = FileManager.default
        guard let names = try? fm.contentsOfDirectory(atPath: signalDir) else { return }
        let cutoff = Date().addingTimeInterval(-120)
        for name in names where name.hasPrefix("js_eval_resp_") {
            let path = signalDir + name
            if let modified = (try? fm.attributesOfItem(atPath: path))?[.modificationDate] as? Date,
               modified < cutoff {
                try? fm.removeItem(atPath: path)
            }
        }
    }

    private func evaluate(_ source: String) -> [String: Any] {
        guard let ctx = context ?? makeContext() else {
            return ["ok": false, "stdout": "", "result": "",
                    "error": "JavaScriptCore context unavailable", "stack": ""]
        }
        context = ctx
        output = ""
        outputTruncated = false
        pendingException = nil

        let value = ctx.evaluateScript(source, withSourceURL: URL(string: "repl"))
        var failure = takeException()
        var result = ""
        if failure == nil, let value, !value.isUndefined {
            result = ctx.objectForKeyedSubscript("__ms_inspect")
                .call(withArguments: [value])?.toString() ?? ""
            failure = takeException()
        }
        if failure == nil {
            failure = drainTimers(ctx)
        } else {
            ctx.evaluateScript("__ms_timers.clear()")
        }
        if outputTruncated {
            output += "\n… output truncated at \(Self.outputLimit >> 20) MB\n"
        }

        guard let failure else {
            return ["ok": true, "stdout": output, "result": result, "error": "", "stack": ""]
        }
        let info = ctx.objectForKeyedSubscript("__ms_describe").call(withArguments: [failure])
        pendingException = nil
        if let code = info?.objectForKeyedSubscript("exit"), !code.isUndefined {
            // process.exit(): a normal way to stop, not an error.
            let status = code.toInt32()
            return ["ok": status == 0, "stdout": output, "result": "",
                    "error": status == 0 ? "" : "process.exit(\(status))", "stack": ""]
        }
        return ["ok": false, "stdout": output, "result": "",
                "error": info?.objectForKeyedSubscript("error")?.toString() ?? failure.toString() ?? "error",
                "stack": info?.objectForKeyedSubscript("stack")?.toString() ?? ""]
    }

    private func takeException() -> JSValue? {
        defer { pendingException = nil }
        return pendingException
    }

    /// Runs setTimeout / setInterval callbacks the script left behind, the
    /// way Node keeps a script alive until its timers are done. Each one is
    /// its own evaluateScript call, so promise callbacks settle in between.
    private func drainTimers(_ ctx: JSContext) -> JSValue? {
        let deadline = Date().addingTimeInterval(Self.timerBudget)
        while let next = ctx.evaluateScript("__ms_timers.next()"), next.isNumber {
            let wait = next.toDouble() / 1000   // seconds to the earliest timer; < 0 when none
            if wait < 0 { return nil }
            if Date().addingTimeInterval(wait) > deadline {
                let left = ctx.evaluateScript("__ms_timers.clear()")?.toInt32() ?? 0
                append("(stopped after \(Int(Self.timerBudget)) s — \(left) timer"
                       + (left == 1 ? "" : "s") + " still pending)\n")
                return nil
            }
            if wait > 0 { Thread.sleep(forTimeInterval: wait) }
            ctx.evaluateScript("__ms_timers.fire()")
            if let exception = takeException() {
                ctx.evaluateScript("__ms_timers.clear()")
                return exception
            }
        }
        return nil
    }

    private func append(_ text: String) {
        guard !outputTruncated else { return }
        if output.utf8.count + text.utf8.count > Self.outputLimit {
            outputTruncated = true
            return
        }
        output += text
    }

    // MARK: - Context

    private func makeContext() -> JSContext? {
        guard let ctx = JSContext() else { return nil }
        ctx.name = "ManimStudio terminal"
        ctx.exceptionHandler = { [weak self] _, exception in
            self?.pendingException = exception
        }

        let write: @convention(block) (String) -> Void = { [weak self] text in
            self?.append(text)
        }
        let cwd: @convention(block) () -> String = {
            FileManager.default.currentDirectoryPath
        }
        let fileCall: @convention(block) (String, String, JSValue) -> [String: Any] = { op, path, data in
            JSEngine.fileOp(op, path: JSEngine.resolve(path), data: data)
        }
        let fetchCall: @convention(block) (String, String, JSValue, JSValue) -> [String: Any] = {
            url, method, headers, body in
            JSEngine.fetch(url, method: method,
                           headers: headers.toDictionary() as? [String: Any] ?? [:],
                           body: body.isString ? body.toString() : nil)
        }
        ctx.setObject(write, forKeyedSubscript: "__ms_write" as NSString)
        ctx.setObject(cwd, forKeyedSubscript: "__ms_cwd" as NSString)
        ctx.setObject(fileCall, forKeyedSubscript: "__ms_fs" as NSString)
        ctx.setObject(fetchCall, forKeyedSubscript: "__ms_fetch" as NSString)
        ctx.setObject(ProcessInfo.processInfo.environment, forKeyedSubscript: "__ms_env" as NSString)
        let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first?.path ?? ""
        ctx.setObject(documents, forKeyedSubscript: "__documents__" as NSString)
        ctx.evaluateScript(Self.prelude, withSourceURL: URL(string: "ms-prelude"))
        if let exception = takeException() {
            NSLog("%@", "[js] prelude failed: \(exception)")
        }
        return ctx
    }

    // MARK: - fs

    /// `~` is $HOME (the shell points it at Documents); relative paths
    /// resolve against the shell's working directory, which is this
    /// process's, since the shell runs in-process.
    private static func resolve(_ path: String) -> String {
        var p = path
        if p == "~" || p.hasPrefix("~/") {
            let home = getenv("HOME").map { String(cString: $0) } ?? NSHomeDirectory()
            p = home + p.dropFirst()
        }
        if !p.hasPrefix("/") {
            p = FileManager.default.currentDirectoryPath + "/" + p
        }
        return (p as NSString).standardizingPath
    }

    private static func fileOp(_ op: String, path: String, data: JSValue) -> [String: Any] {
        let fm = FileManager.default
        var isDir: ObjCBool = false
        let exists = fm.fileExists(atPath: path, isDirectory: &isDir)
        func failure(_ code: String, _ message: String) -> [String: Any] {
            ["error": true, "code": code, "message": message]
        }
        let missing = failure("ENOENT", "no such file or directory")
        do {
            switch op {
            case "exists":
                return ["value": exists]
            case "read":
                guard exists else { return missing }
                if isDir.boolValue { return failure("EISDIR", "illegal operation on a directory") }
                let bytes = try Data(contentsOf: URL(fileURLWithPath: path))
                // Text only; bytes that aren't UTF-8 come through as Latin-1.
                let text = String(data: bytes, encoding: .utf8)
                    ?? String(data: bytes, encoding: .isoLatin1) ?? ""
                return ["value": text]
            case "write", "append":
                if isDir.boolValue { return failure("EISDIR", "illegal operation on a directory") }
                let bytes = Data((data.toString() ?? "").utf8)
                if op == "append", exists {
                    let handle = try FileHandle(forWritingTo: URL(fileURLWithPath: path))
                    defer { try? handle.close() }
                    try handle.seekToEnd()
                    try handle.write(contentsOf: bytes)
                } else {
                    try bytes.write(to: URL(fileURLWithPath: path))
                }
                return ["value": true]
            case "readdir":
                guard exists else { return missing }
                guard isDir.boolValue else { return failure("ENOTDIR", "not a directory") }
                return ["value": try fm.contentsOfDirectory(atPath: path).sorted()]
            case "unlink":
                guard exists else { return missing }
                if isDir.boolValue { return failure("EISDIR", "illegal operation on a directory") }
                try fm.removeItem(atPath: path)
                return ["value": true]
            case "mkdir":
                if exists, !data.toBool() { return failure("EEXIST", "file already exists") }
                try fm.createDirectory(atPath: path, withIntermediateDirectories: data.toBool())
                return ["value": true]
            case "stat":
                guard exists else { return missing }
                let attrs = try fm.attributesOfItem(atPath: path)
                let modified = (attrs[.modificationDate] as? Date)?.timeIntervalSince1970 ?? 0
                return ["value": ["size": (attrs[.size] as? NSNumber)?.int64Value ?? 0,
                                  "mtimeMs": modified * 1000,
                                  "dir": isDir.boolValue]]
            default:
                return failure("ENOSYS", "unsupported operation \(op)")
            }
        } catch {
            return failure("EIO", error.localizedDescription)
        }
    }

    // MARK: - fetch

    /// Blocking HTTP for the fetch() shim; runs on the engine queue, and
    /// URLSession calls the delegate on its own queue, so waiting is safe.
    private static func fetch(_ urlString: String, method: String,
                              headers: [String: Any], body: String?) -> [String: Any] {
        guard let url = URL(string: urlString), let scheme = url.scheme?.lowercased(),
              scheme == "http" || scheme == "https" else {
            return ["error": "unsupported URL \(urlString)"]
        }
        var request = URLRequest(url: url, timeoutInterval: 20)
        request.httpMethod = method
        for (name, value) in headers { request.setValue("\(value)", forHTTPHeaderField: name) }
        if let body { request.httpBody = Data(body.utf8) }

        let delegate = FetchDelegate(limit: fetchLimit)
        let session = URLSession(configuration: .ephemeral, delegate: delegate, delegateQueue: nil)
        session.dataTask(with: request).resume()
        let finished = delegate.done.wait(timeout: .now() + 25) == .success
        session.invalidateAndCancel()

        if delegate.tooLarge {
            return ["error": "response is larger than \(fetchLimit >> 20) MB — use `curl -o FILE` to download it"]
        }
        guard finished else { return ["error": "timed out"] }
        if let error = delegate.error { return ["error": error.localizedDescription] }
        guard let response = delegate.response else { return ["error": "no response"] }
        var headerMap: [String: String] = [:]
        for (name, value) in response.allHeaderFields {
            headerMap["\(name)"] = "\(value)"
        }
        let text = String(data: delegate.data, encoding: .utf8)
            ?? String(data: delegate.data, encoding: .isoLatin1) ?? ""
        return ["status": response.statusCode,
                "statusText": HTTPURLResponse.localizedString(forStatusCode: response.statusCode),
                "url": response.url?.absoluteString ?? urlString,
                "redirected": response.url != nil && response.url != url,
                "headers": headerMap,
                "body": text]
    }

    /// Collects one response, cancelling once it passes `limit` bytes so a
    /// large download can't take the app's memory with it.
    private nonisolated final class FetchDelegate: NSObject, URLSessionDataDelegate, @unchecked Sendable {
        let limit: Int
        let done = DispatchSemaphore(value: 0)
        var data = Data()
        var response: HTTPURLResponse?
        var error: Error?
        var tooLarge = false

        init(limit: Int) { self.limit = limit }

        func urlSession(_ session: URLSession, dataTask: URLSessionDataTask,
                        didReceive response: URLResponse,
                        completionHandler: @escaping (URLSession.ResponseDisposition) -> Void) {
            self.response = response as? HTTPURLResponse
            if response.expectedContentLength > Int64(limit) {
                tooLarge = true
                completionHandler(.cancel)
            } else {
                completionHandler(.allow)
            }
        }

        func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive chunk: Data) {
            if data.count + chunk.count > limit {
                tooLarge = true
                dataTask.cancel()
            } else {
                data.append(chunk)
            }
        }

        func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
            self.error = error
            done.signal()
        }
    }

    // MARK: - Prelude

    /// The Node-flavoured environment. Native hooks (__ms_write, __ms_fs,
    /// __ms_fetch, __ms_cwd, __ms_env) are captured and removed from the
    /// global object; the three the engine calls back into stay, hidden
    /// from enumeration.
    private static let prelude = #"""
    (function (g) {
      'use strict';
      const write = g.__ms_write, fsCall = g.__ms_fs, fetchCall = g.__ms_fetch,
            cwd = g.__ms_cwd, env = g.__ms_env || {};
      for (const k of ['__ms_write', '__ms_fs', '__ms_fetch', '__ms_cwd', '__ms_env']) delete g[k];
      const started = Date.now();

      // ── inspect / format (roughly util.inspect and util.format) ──
      const quote = s => "'" + s.replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/\n/g, '\\n') + "'";
      function inspect(v, depth, seen) {
        switch (typeof v) {
          case 'string': return depth > 0 ? quote(v) : v;
          case 'number': return Object.is(v, -0) ? '-0' : String(v);
          case 'bigint': return v + 'n';
          case 'function': return v.name ? '[Function: ' + v.name + ']' : '[Function (anonymous)]';
          case 'object': break;
          default: return String(v);
        }
        if (v === null) return 'null';
        seen = seen || [];
        if (seen.indexOf(v) >= 0) return '[Circular]';
        if (v instanceof Error) return v.name + ': ' + v.message;
        if (v instanceof Date) return isNaN(v) ? 'Invalid Date' : v.toISOString();
        if (v instanceof RegExp) return String(v);
        if (v instanceof Promise) return 'Promise {}';
        if (depth > 3) return Array.isArray(v) ? '[Array]' : '[Object]';
        const next = seen.concat([v]);
        const item = x => inspect(x, depth + 1, next);
        const list = (n, at) => {
          const out = [];
          for (let i = 0; i < Math.min(n, 100); i++) out.push(at(i));
          if (n > 100) out.push('… ' + (n - 100) + ' more');
          return out;
        };
        if (Array.isArray(v) || ArrayBuffer.isView(v)) {
          const parts = list(v.length, i => item(v[i]));
          const head = Array.isArray(v) ? '' : v.constructor.name + '(' + v.length + ') ';
          return head + (parts.length ? '[ ' + parts.join(', ') + ' ]' : '[]');
        }
        if (v instanceof Map || v instanceof Set) {
          const entries = Array.from(v);
          const parts = list(entries.length, i => v instanceof Map
            ? item(entries[i][0]) + ' => ' + item(entries[i][1]) : item(entries[i]));
          return v.constructor.name + '(' + v.size + ') {' + (parts.length ? ' ' + parts.join(', ') + ' ' : '') + '}';
        }
        const keys = Object.keys(v);
        const parts = list(keys.length, i =>
          (/^[A-Za-z_$][\w$]*$/.test(keys[i]) ? keys[i] : quote(keys[i])) + ': ' + item(v[keys[i]]));
        const proto = Object.getPrototypeOf(v);
        const name = proto === null ? '[Object: null prototype] '
          : (v.constructor && v.constructor !== Object && v.constructor.name ? v.constructor.name + ' ' : '');
        return name + (parts.length ? '{ ' + parts.join(', ') + ' }' : '{}');
      }
      function format(args) {
        const out = [];
        let i = 0;
        if (typeof args[0] === 'string' && args.length > 1 && args[0].indexOf('%') >= 0) {
          i = 1;
          out.push(args[0].replace(/%[sdifjoOc%]/g, m => {
            if (m === '%%') return '%';
            if (i >= args.length) return m;
            const a = args[i++];
            switch (m) {
              case '%s': return typeof a === 'string' ? a : inspect(a, 1);
              case '%d': return String(Number(a));
              case '%i': return String(parseInt(a, 10));
              case '%f': return String(parseFloat(a));
              case '%j': try { return JSON.stringify(a); } catch (e) { return '[Circular]'; }
              case '%c': return '';
              default: return inspect(a, 1);
            }
          }));
        }
        for (; i < args.length; i++) out.push(inspect(args[i], 0));
        return out.join(' ');
      }

      // ── console ──
      const counts = {}, times = {};
      const line = (...a) => write(format(a) + '\n');
      g.console = {
        log: line, info: line, debug: line, warn: line, error: line, trace: line, table: line,
        group: line, groupCollapsed: line, groupEnd: () => {},
        dir: v => write(inspect(v, 1) + '\n'),
        assert: (ok, ...a) => { if (!ok) write('Assertion failed' + (a.length ? ': ' + format(a) : '') + '\n'); },
        count: (l = 'default') => { counts[l] = (counts[l] || 0) + 1; write(l + ': ' + counts[l] + '\n'); },
        countReset: (l = 'default') => { delete counts[l]; },
        time: (l = 'default') => { times[l] = Date.now(); },
        timeLog: (l = 'default', ...a) => { if (l in times) write(l + ': ' + (Date.now() - times[l]) + 'ms' + (a.length ? ' ' + format(a) : '') + '\n'); },
        timeEnd: (l = 'default') => { if (l in times) { write(l + ': ' + (Date.now() - times[l]) + 'ms\n'); delete times[l]; } },
      };
      if (typeof g.performance === 'undefined') g.performance = { now: () => Date.now() - started };

      // ── timers: queued here, run by JSEngine.drainTimers after the script ──
      let timerList = [], timerSeq = 0;
      const earliest = () => {
        let best = -1;
        for (let k = 0; k < timerList.length; k++) {
          const t = timerList[k], b = timerList[best];
          if (best < 0 || t.due < b.due || (t.due === b.due && t.id < b.id)) best = k;
        }
        return best;
      };
      const addTimer = (fn, ms, args, every) => {
        if (typeof fn !== 'function') throw new TypeError('The "callback" argument must be of type function');
        ms = Math.max(every ? 1 : 0, Number(ms) || 0);
        const id = ++timerSeq;
        timerList.push({ id, fn, args, due: Date.now() + ms, every: every ? ms : null });
        return id;
      };
      const clearTimer = id => { timerList = timerList.filter(t => t.id !== id); };
      g.setTimeout = (fn, ms, ...a) => addTimer(fn, ms, a, false);
      g.setInterval = (fn, ms, ...a) => addTimer(fn, ms, a, true);
      g.setImmediate = (fn, ...a) => addTimer(fn, 0, a, false);
      g.clearTimeout = g.clearInterval = g.clearImmediate = clearTimer;
      if (typeof g.queueMicrotask !== 'function') g.queueMicrotask = fn => { Promise.resolve().then(fn); };
      const timers = {
        next() { const k = earliest(); return k < 0 ? -1 : Math.max(0, timerList[k].due - Date.now()); },
        fire() {
          const k = earliest();
          if (k < 0) return;
          const t = timerList[k];
          if (t.every !== null) t.due = Date.now() + t.every; else timerList.splice(k, 1);
          t.fn.apply(undefined, t.args);
        },
        clear() { const n = timerList.length; timerList = []; return n; },
      };

      // ── process ──
      g.process = {
        platform: 'ios', arch: 'arm64', version: 'jsc', versions: {}, argv: ['js'], env,
        cwd: () => cwd(),
        exit: code => { throw { __ms_exit: code === undefined ? 0 : (code | 0) }; },
        stdout: { write: s => { write(String(s)); return true; }, isTTY: false },
        stderr: { write: s => { write(String(s)); return true; }, isTTY: false },
        nextTick: (fn, ...a) => { Promise.resolve().then(() => fn(...a)); },
        uptime: () => (Date.now() - started) / 1000,
        hrtime: prev => {
          const ms = Date.now() - started, s = Math.floor(ms / 1000), ns = (ms % 1000) * 1e6;
          return prev ? [s - prev[0] - (ns < prev[1] ? 1 : 0), (ns - prev[1] + 1e9) % 1e9] : [s, ns];
        },
        on: () => g.process,
      };

      // ── fs (sync, text only) ──
      const fsError = (r, op, p) => {
        const e = new Error(r.code + ': ' + r.message + ', ' + op + " '" + p + "'");
        e.code = r.code; e.syscall = op; e.path = p;
        return e;
      };
      const fsDo = (op, p, data) => {
        const r = fsCall(op, String(p), data === undefined ? null : data);
        if (r.error) throw fsError(r, op, p);
        return r.value;
      };
      const fs = {
        readFileSync: p => fsDo('read', p),
        writeFileSync: (p, d) => { fsDo('write', p, String(d)); },
        appendFileSync: (p, d) => { fsDo('append', p, String(d)); },
        existsSync: p => fsCall('exists', String(p), null).value === true,
        readdirSync: p => fsDo('readdir', p),
        unlinkSync: p => { fsDo('unlink', p); },
        mkdirSync: (p, o) => { fsDo('mkdir', p, !!(o && o.recursive)); },
        statSync: p => {
          const s = fsDo('stat', p);
          return { size: s.size, mtimeMs: s.mtimeMs, mtime: new Date(s.mtimeMs),
                   isFile: () => !s.dir, isDirectory: () => s.dir };
        },
      };
      const later = f => (...a) => new Promise(resolve => resolve(f(...a)));
      fs.promises = { readFile: later(fs.readFileSync), writeFile: later(fs.writeFileSync),
                      appendFile: later(fs.appendFileSync), readdir: later(fs.readdirSync),
                      unlink: later(fs.unlinkSync), mkdir: later(fs.mkdirSync), stat: later(fs.statSync) };

      // ── path ──
      const path = {
        sep: '/', delimiter: ':',
        isAbsolute: p => String(p).startsWith('/'),
        normalize(p) {
          p = String(p);
          const abs = p.startsWith('/'), out = [];
          for (const seg of p.split('/')) {
            if (!seg || seg === '.') continue;
            if (seg === '..') { if (out.length && out[out.length - 1] !== '..') out.pop(); else if (!abs) out.push('..'); }
            else out.push(seg);
          }
          return ((abs ? '/' : '') + out.join('/')) || (abs ? '/' : '.');
        },
        join: (...parts) => path.normalize(parts.filter(x => x !== '').join('/') || '.'),
        resolve(...parts) {
          let r = '';
          for (let i = parts.length - 1; i >= 0 && !r.startsWith('/'); i--) if (parts[i]) r = parts[i] + (r ? '/' + r : '');
          return path.normalize(r.startsWith('/') ? r : cwd() + (r ? '/' + r : ''));
        },
        basename(p, ext) {
          let b = String(p).replace(/\/+$/, '');
          b = b.slice(b.lastIndexOf('/') + 1);
          return ext && b.endsWith(ext) && b !== ext ? b.slice(0, -ext.length) : b;
        },
        dirname(p) {
          p = String(p).replace(/\/+$/, '');
          const i = p.lastIndexOf('/');
          return i < 0 ? '.' : i === 0 ? '/' : p.slice(0, i);
        },
        extname(p) { const b = path.basename(p), i = b.lastIndexOf('.'); return i <= 0 ? '' : b.slice(i); },
      };

      const os = { EOL: '\n', platform: () => 'ios', arch: () => 'arm64', type: () => 'Darwin',
                   homedir: () => env.HOME || '', tmpdir: () => env.TMPDIR || '' };
      const util = { inspect: v => inspect(v, 1), format: (...a) => format(a) };

      // ── require: the shims above, plus CommonJS files by relative path ──
      const modules = { fs, path, os, util, process: g.process };
      const loaded = {};
      const requireFrom = base => function require(name) {
        name = String(name);
        const bare = name.replace(/^node:/, '');
        if (Object.prototype.hasOwnProperty.call(modules, bare)) return modules[bare];
        if (!/^(\.{1,2}\/|\/)/.test(name))
          throw new Error("Cannot find module '" + name + "' — the terminal's js is JavaScriptCore, " +
                          'not Node; it provides fs, path, os, util and process');
        let file = path.resolve(base, name);
        if (!fs.existsSync(file) || fs.statSync(file).isDirectory())
          for (const ext of ['.js', '.json', '/index.js']) if (fs.existsSync(file + ext)) { file += ext; break; }
        if (loaded[file]) return loaded[file].exports;
        const src = fs.readFileSync(file);
        if (file.endsWith('.json')) return (loaded[file] = { exports: JSON.parse(src) }).exports;
        const module = loaded[file] = { exports: {}, id: file, filename: file };
        const dir = path.dirname(file);
        new Function('exports', 'require', 'module', '__filename', '__dirname', src)(
          module.exports, requireFrom(dir), module, file, dir);
        return module.exports;
      };
      g.module = { exports: {} };
      g.exports = g.module.exports;
      g.require = name => requireFrom(cwd())(name);
      g.require.main = g.module;

      // ── fetch (resolves synchronously; the native side blocks) ──
      const headersOf = h => {
        const map = {};
        for (const k in h) map[k.toLowerCase()] = h[k];
        const entries = () => Object.keys(map).map(k => [k, map[k]]);
        return { get: k => { k = String(k).toLowerCase(); return k in map ? map[k] : null; },
                 has: k => String(k).toLowerCase() in map,
                 forEach: fn => { for (const k in map) fn(map[k], k); },
                 entries: () => entries()[Symbol.iterator](),
                 [Symbol.iterator]: () => entries()[Symbol.iterator]() };
      };
      g.fetch = (input, init) => new Promise((resolve, reject) => {
        init = init || {};
        const r = fetchCall(String(input && input.url || input), String(init.method || 'GET').toUpperCase(),
                            init.headers || {}, init.body == null ? null : String(init.body));
        if (r.error) { reject(new TypeError('fetch failed: ' + r.error)); return; }
        const body = r.body;
        resolve({ ok: r.status >= 200 && r.status < 300, status: r.status, statusText: r.statusText,
                  url: r.url, redirected: r.redirected, headers: headersOf(r.headers),
                  text: () => Promise.resolve(body),
                  json: () => new Promise(res => res(JSON.parse(body))) });
      });

      // ── hooks the engine calls ──
      const describe = e => {
        if (e && typeof e === 'object' && '__ms_exit' in e) return { exit: e.__ms_exit };
        if (e instanceof Error || (e && typeof e === 'object' && typeof e.message === 'string' && typeof e.name === 'string')) {
          const frames = String(e.stack || '').split('\n')
            .filter(f => f && f.indexOf('[native code]') < 0 && f.indexOf('ms-prelude') < 0);
          let error = (e.name || 'Error') + ': ' + e.message;
          if (frames.length <= 1 && typeof e.line === 'number') error += ' (line ' + e.line + ')';
          const stack = frames.length > 1 ? frames.map(f => {
            const at = f.lastIndexOf('@');
            return '    at ' + (at > 0 ? f.slice(0, at) + ' (' + f.slice(at + 1) + ')' : f.replace(/^@/, ''));
          }).join('\n') : '';
          return { error, stack };
        }
        return { error: 'Uncaught ' + inspect(e, 1), stack: '' };
      };
      Object.defineProperty(g, '__ms_inspect', { value: v => inspect(v, 1) });
      Object.defineProperty(g, '__ms_describe', { value: describe });
      Object.defineProperty(g, '__ms_timers', { value: timers });
    })(globalThis);
    """#
}
