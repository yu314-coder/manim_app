/**
 * Manim Studio - Flask API Adapter
 * This file provides a pywebview.api-compatible interface for Flask backend
 * It can be used alongside renderer_desktop.js by loading this before it
 */

// Create a mock pywebview object that uses Flask API endpoints
const pywebview = {
    api: {}
};

// Base API URL (change if Flask runs on different host/port)
const API_BASE_URL = window.location.origin;

// Helper function to make API calls to Flask backend
async function apiCall(endpoint, method = 'GET', data = null) {
    const options = {
        method: method,
        headers: {
            'Content-Type': 'application/json'
        }
    };

    if (data && method !== 'GET') {
        options.body = JSON.stringify(data);
    }

    try {
        const response = await fetch(`${API_BASE_URL}/api/${endpoint}`, options);
        const result = await response.json();
        return result;
    } catch (error) {
        console.error(`API call failed: ${endpoint}`, error);
        throw error;
    }
}

// Helper function for file uploads
async function apiUpload(endpoint, files) {
    const formData = new FormData();

    if (Array.isArray(files)) {
        files.forEach(file => formData.append('files', file));
    } else {
        formData.append('files', files);
    }

    try {
        const response = await fetch(`${API_BASE_URL}/api/${endpoint}`, {
            method: 'POST',
            body: formData
        });
        const result = await response.json();
        return result;
    } catch (error) {
        console.error(`Upload failed: ${endpoint}`, error);
        throw error;
    }
}

// ============================================================================
// API Methods - Match ManimAPI from app.py
// ============================================================================

pywebview.api.get_code = async function() {
    return await apiCall('get_code');
};

pywebview.api.set_code = async function(code) {
    return await apiCall('set_code', 'POST', { code });
};

pywebview.api.new_file = async function() {
    return await apiCall('new_file', 'POST');
};

pywebview.api.open_file_dialog = async function() {
    // Flask version uses HTML5 file picker instead of native dialog
    return new Promise((resolve) => {
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = '.py';
        input.onchange = async (e) => {
            const file = e.target.files[0];
            if (file) {
                const text = await file.text();
                resolve({
                    success: true,
                    file_path: file.name,
                    code: text
                });
            } else {
                resolve({ success: false });
            }
        };
        input.click();
    });
};

pywebview.api.save_file = async function(code, file_path = null) {
    return await apiCall('save_file', 'POST', { code, file_path });
};

pywebview.api.save_file_dialog = async function(code) {
    // Flask version uses HTML5 file download instead of native dialog
    const blob = new Blob([code], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'manim_scene.py';
    a.click();
    URL.revokeObjectURL(url);
    return { success: true, file_path: 'manim_scene.py' };
};

pywebview.api.autosave_code = async function(code) {
    return await apiCall('autosave_code', 'POST', { code });
};

pywebview.api.get_autosave_files = async function() {
    return await apiCall('get_autosave_files');
};

pywebview.api.load_autosave = async function(autosave_file) {
    return await apiCall('load_autosave', 'POST', { autosave_file });
};

pywebview.api.delete_autosave = async function(autosave_file) {
    return await apiCall('delete_autosave', 'POST', { autosave_file });
};

pywebview.api.check_code_errors = async function(code) {
    return await apiCall('check_code_errors', 'POST', { code });
};

pywebview.api.render_animation = async function(code, quality = '720p', fps = 30, gpu_accelerate = false, format = 'mp4', width = null, height = null) {
    return await apiCall('render_animation', 'POST', {
        code,
        quality,
        fps,
        gpu_accelerate,
        format,
        width,
        height
    });
};

pywebview.api.quick_preview = async function(code, quality = '480p', fps = 15, gpu_accelerate = false, format = 'mp4') {
    return await apiCall('quick_preview', 'POST', {
        code,
        quality,
        fps,
        gpu_accelerate,
        format
    });
};

pywebview.api.stop_render = async function() {
    return await apiCall('stop_render', 'POST');
};

pywebview.api.list_assets = async function() {
    return await apiCall('list_assets');
};

pywebview.api.add_assets = async function(file_paths) {
    // For Flask, we need to handle file uploads differently
    // This would be called from a file input element
    console.warn('add_assets: Use file input element with apiUpload helper');
    return { success: false, error: 'Use file input for uploads in Flask version' };
};

pywebview.api.delete_asset = async function(file_path) {
    return await apiCall('delete_asset', 'POST', { file_path });
};

pywebview.api.get_asset_as_data_url = async function(file_path) {
    return await apiCall('get_asset_as_data_url', 'POST', { file_path });
};

pywebview.api.get_video_files = async function() {
    return await apiCall('get_video_files');
};

pywebview.api.list_media_files = async function() {
    // Alias for get_video_files
    return await apiCall('get_video_files');
};

pywebview.api.execute_command = async function(command) {
    return await apiCall('execute_command', 'POST', { command });
};

pywebview.api.read_file_text = async function(file_path) {
    return await apiCall('read_file_text', 'POST', { file_path });
};

pywebview.api.get_system_info = async function() {
    return await apiCall('get_system_info');
};

pywebview.api.get_gpu_info = async function() {
    return await apiCall('get_gpu_info');
};

pywebview.api.get_performance_data = async function() {
    return await apiCall('get_performance_data');
};

pywebview.api.save_rendered_file = async function(source_path, suggested_name) {
    // Download file from server
    const link = document.createElement('a');
    link.href = `/api/download_file?path=${encodeURIComponent(source_path)}`;
    link.download = suggested_name;
    link.click();
    return { success: true };
};

pywebview.api.open_media_folder = async function() {
    console.log('open_media_folder: Not available in web version');
    return { success: false, error: 'Not available in web version' };
};

pywebview.api.play_media = async function(file_path) {
    // Open media in new tab
    window.open(`/media/${encodeURIComponent(file_path)}`, '_blank');
    return { success: true };
};

pywebview.api.get_terminal_output = async function() {
    // Terminal output is handled via SocketIO in Flask version
    return { output: '' };
};

// ============================================================================
// SocketIO Integration for Real-time Features
// ============================================================================

let socket = null;

function initializeSocketIO() {
    if (typeof io === 'undefined') {
        console.warn('Socket.IO not loaded, real-time features disabled');
        return;
    }

    socket = io(API_BASE_URL);

    socket.on('connect', function() {
        console.log('Connected to Flask server via SocketIO');
    });

    socket.on('disconnect', function() {
        console.log('Disconnected from Flask server');
    });

    socket.on('terminal_output', function(data) {
        // Handle terminal output - write to xterm
        if (window.term && data.output) {
            window.term.write(data.output);
        }
    });

    socket.on('terminal_started', function(data) {
        console.log('[Terminal] Terminal started:', data);
    });

    socket.on('terminal_error', function(data) {
        console.error('[Terminal] Error:', data.error);
        if (window.term) {
            window.term.write('\r\n\x1b[31m[ERROR] ' + data.error + '\x1b[0m\r\n');
        }
    });

    socket.on('render_output', function(data) {
        // Handle render output - write to terminal
        if (window.term && data.output) {
            window.term.write(data.output);
        }
    });

    socket.on('render_complete', function(data) {
        console.log('[Render] Complete:', data);
        if (window.term) {
            if (data.success) {
                window.term.write('\r\n\x1b[32m[RENDER] Complete! File: ' + data.filename + '\x1b[0m\r\n');
            } else {
                window.term.write('\r\n\x1b[31m[RENDER] Failed: ' + data.error + '\x1b[0m\r\n');
            }
        }
    });

    socket.on('preview_output', function(data) {
        // Handle preview output - write to terminal
        if (window.term && data.output) {
            window.term.write(data.output);
        }
    });

    socket.on('preview_complete', function(data) {
        console.log('[Preview] Complete:', data);
        if (window.term) {
            if (data.success) {
                window.term.write('\r\n\x1b[32m[PREVIEW] Complete! File: ' + data.filename + '\x1b[0m\r\n');

                // Auto-load preview in the preview panel
                if (data.file_path && typeof window.loadPreviewVideo === 'function') {
                    window.loadPreviewVideo(data.file_path);
                }
            } else {
                window.term.write('\r\n\x1b[31m[PREVIEW] Failed: ' + data.error + '\x1b[0m\r\n');
            }
        }
    });

    socket.on('connected', function(data) {
        console.log('[SocketIO] Server message:', data.data);
    });
}

// Terminal functions using SocketIO
pywebview.api.start_terminal = function() {
    if (socket) {
        socket.emit('start_terminal');
    }
};

pywebview.api.send_terminal_command = function(command) {
    if (socket) {
        socket.emit('terminal_input', { command });
    }
};

// Initialize SocketIO when page loads
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeSocketIO);
} else {
    initializeSocketIO();
}

// ============================================================================
// File Upload Helper for Assets
// ============================================================================

// Add event listener for asset file uploads
window.uploadAssets = async function(files) {
    if (!files || files.length === 0) {
        return { success: false, error: 'No files selected' };
    }

    return await apiUpload('add_assets', files);
};

console.log('Flask API adapter loaded - pywebview.api is now available');

// ============================================================================
// Trigger PyWebView Ready Event
// ============================================================================

// The renderer_desktop.js expects a 'pywebviewready' event
// We need to trigger it after the pywebview.api object is fully set up
function triggerPyWebViewReady() {
    console.log('[FLASK ADAPTER] Triggering pywebviewready event...');
    const event = new Event('pywebviewready');
    window.dispatchEvent(event);
    console.log('[FLASK ADAPTER] pywebviewready event dispatched');
}

// Trigger the event after a short delay to ensure everything is loaded
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        setTimeout(triggerPyWebViewReady, 100);
    });
} else {
    setTimeout(triggerPyWebViewReady, 100);
}
