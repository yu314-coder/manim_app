// NEW FEATURES: File Upload via PyWebView Dialog
console.log('[NEW_FEATURES] Loaded new_features.js - Version 2025-01-26-v10');

// ======================
// 1. FILE UPLOAD FUNCTIONALITY (Using PyWebView File Dialog)
// ======================
document.addEventListener('DOMContentLoaded', function() {
    const dropZone = document.getElementById('assetsDropZone');

    if (dropZone) {
        // Click drop zone to open file dialog
        dropZone.addEventListener('click', async () => {
            console.log('[UPLOAD] Drop zone clicked - opening file dialog...');
            await openFileDialogAndUpload();
        });

        // Disable drag-drop events (not supported in PyWebView browser mode)
        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.stopPropagation();
        });

        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            e.stopPropagation();
            console.log('[UPLOAD] Drop not supported - please click to upload');
            toast('Drag-drop not supported. Click to select files.', 'info');
        });
    }
});

async function openFileDialogAndUpload() {
    try {
        console.log('[UPLOAD] Checking PyWebView API...');
        if (typeof pywebview === 'undefined' || !pywebview.api) {
            console.error('[UPLOAD] PyWebView API not available');
            alert('PyWebView API not available. Please restart the app.');
            return;
        }

        console.log('[UPLOAD] Opening file dialog...');
        // Use PyWebView's file dialog API
        const result = await pywebview.api.select_files_to_upload();

        console.log('[UPLOAD] File dialog result:', result);

        if (result && result.status === 'success' && result.file_paths && result.file_paths.length > 0) {
            console.log('[UPLOAD] Selected files:', result.file_paths);
            await uploadFiles(result.file_paths);
        } else if (result && result.status === 'cancelled') {
            console.log('[UPLOAD] User cancelled file selection');
        } else {
            console.log('[UPLOAD] No files selected');
        }
    } catch (error) {
        console.error('[UPLOAD] Error opening file dialog:', error);
        alert(`Error: ${error.message}`);
    }
}

async function uploadFiles(filePaths) {
    try {
        console.log('[UPLOAD] Uploading', filePaths.length, 'files...');
        const result = await pywebview.api.add_assets(filePaths);

        console.log('[UPLOAD] Upload result:', result);

        if (result.status === 'success') {
            toast(`Added ${result.added} file(s) to assets`, 'success');
            if (typeof refreshAssets === 'function') {
                refreshAssets();
            }
        } else {
            toast(result.message || 'Failed to add files', 'error');
            if (result.errors && result.errors.length > 0) {
                console.error('[UPLOAD] Errors:', result.errors);
            }
        }
    } catch (error) {
        console.error('[UPLOAD] Error uploading files:', error);
        toast('Error uploading files', 'error');
    }
}

// ======================
// 2. DELETE ASSET FUNCTIONALITY
// ======================
function deleteAsset(filePath, fileName) {
    if (!confirm(`Delete "${fileName}"?`)) return;

    pywebview.api.delete_asset(filePath)
        .then(result => {
            if (result.status === 'success') {
                toast('File deleted', 'success');
                refreshAssets();
            } else {
                toast(result.message || 'Failed to delete', 'error');
            }
        })
        .catch(error => {
            console.error('Error deleting:', error);
            toast('Error deleting file', 'error');
        });
}

// ======================
// 3. SAVE DIALOG CODE REMOVED
// ======================
// Save dialog functionality has been completely removed
// Render now works exactly like Preview - no save dialogs

// ======================
// 4. WINDOWS EXPLORER DETAILS LIST VIEW FOR ASSETS
// ======================
function displayAssets(data) {
    const container = document.getElementById('simpleAssetsContainer');
    if (!container) {
        console.error('[ASSETS] simpleAssetsContainer not found');
        return;
    }

    // Clear container
    container.innerHTML = '';

    if (!data || !data.files || data.files.length === 0) {
        container.innerHTML = '<div style="text-align:center; padding:40px; color:var(--text-secondary);">No assets found. Upload some media files to get started.</div>';
        return;
    }

    // Create table with header (like Windows Explorer Details view)
    const table = document.createElement('div');
    table.style.cssText = 'width:100%; font-family:system-ui, -apple-system, sans-serif;';

    // Header row
    const header = document.createElement('div');
    header.style.cssText = 'display:flex; align-items:center; padding:8px 12px; background:var(--bg-secondary); border-bottom:2px solid var(--border-color); font-weight:600; font-size:13px; color:var(--text-secondary);';
    header.innerHTML = `
        <div style="width:40px; flex-shrink:0;"></div>
        <div style="flex:1; min-width:200px;">Name</div>
        <div style="width:120px; flex-shrink:0;">Size</div>
        <div style="width:150px; flex-shrink:0;">Type</div>
        <div style="width:80px; flex-shrink:0; text-align:center;">Actions</div>
    `;
    table.appendChild(header);

    // Data rows
    data.files.forEach(asset => {
        const row = document.createElement('div');
        row.style.cssText = 'display:flex; align-items:center; padding:8px 12px; border-bottom:1px solid var(--border-color); cursor:pointer; transition:background 0.15s;';

        row.onmouseover = () => {
            row.style.background = 'var(--bg-secondary)';
        };
        row.onmouseout = () => {
            row.style.background = 'transparent';
        };

        const ext = asset.name.split('.').pop().toLowerCase();
        const fileType = getFileType(ext);

        row.innerHTML = `
            <div style="width:40px; flex-shrink:0; font-size:20px; color:var(--text-secondary);">
                ${getAssetIcon(asset.name)}
            </div>
            <div style="flex:1; min-width:200px; font-size:14px; color:var(--text-primary); overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
                ${asset.name}
            </div>
            <div style="width:120px; flex-shrink:0; font-size:13px; color:var(--text-secondary);">
                ${formatBytes(asset.size)}
            </div>
            <div style="width:150px; flex-shrink:0; font-size:13px; color:var(--text-secondary);">
                ${fileType}
            </div>
            <div style="width:80px; flex-shrink:0; text-align:center;">
                <button class="delete-asset-btn" style="padding:6px 10px; background:var(--danger-color); color:white; border:none; border-radius:4px; cursor:pointer; font-size:12px;" title="Delete">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        `;

        // Click to preview (on the row, not the button)
        row.addEventListener('click', (e) => {
            if (e.target.closest('.delete-asset-btn')) return;
            showPreviewPyWebView(asset.path, asset.name);
            // Switch to workspace tab
            const workspaceTab = document.querySelector('.tab-pill[data-tab="workspace"]');
            if (workspaceTab) workspaceTab.click();
        });

        // Delete button
        const deleteBtn = row.querySelector('.delete-asset-btn');
        deleteBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            deleteAsset(asset.path, asset.name);
        });

        table.appendChild(row);
    });

    container.appendChild(table);
}

function getFileType(ext) {
    const types = {
        'mp4': 'MP4 Video',
        'mov': 'MOV Video',
        'avi': 'AVI Video',
        'webm': 'WebM Video',
        'gif': 'GIF Image',
        'png': 'PNG Image',
        'jpg': 'JPEG Image',
        'jpeg': 'JPEG Image',
        'mp3': 'MP3 Audio',
        'wav': 'WAV Audio'
    };
    return types[ext] || (ext.toUpperCase() + ' File');
}

// Show preview using PyWebView API to avoid file:// restrictions
function showPreviewPyWebView(filepath, filename) {
    console.log('[PREVIEW] Showing asset:', filename);

    const previewVideo = document.getElementById('previewVideo');
    const previewImage = document.getElementById('previewImage');
    const previewFilename = document.getElementById('previewFilename');
    const previewFilesize = document.getElementById('previewFilesize');

    if (!previewVideo || !previewImage) {
        console.error('[PREVIEW] Preview elements not found');
        return;
    }

    // Update filename display
    if (previewFilename) previewFilename.textContent = filename;
    if (previewFilesize) previewFilesize.textContent = '';

    const ext = filename.split('.').pop().toLowerCase();
    const videoExts = ['mp4', 'mov', 'avi', 'webm', 'gif'];
    const imageExts = ['png', 'jpg', 'jpeg'];

    if (videoExts.includes(ext)) {
        // Show video
        previewImage.style.display = 'none';
        previewVideo.style.display = 'block';
        // Use the video path directly - PyWebView allows this
        previewVideo.src = filepath;
        previewVideo.load();
    } else if (imageExts.includes(ext)) {
        // Show image
        previewVideo.style.display = 'none';
        previewImage.style.display = 'block';
        // For images, read as base64 via Python API
        if (window.pywebview) {
            window.pywebview.api.read_file_as_base64(filepath).then(function(base64Data) {
                previewImage.src = 'data:image/' + ext + ';base64,' + base64Data;
            }).catch(function(err) {
                console.error('[PREVIEW] Failed to load image:', err);
                alert('Failed to load image preview');
            });
        } else {
            // Fallback - just try direct path
            previewImage.src = filepath;
        }
    }
}

function getAssetIcon(filename) {
    const ext = filename.split('.').pop().toLowerCase();
    const icons = {
        'mp4': '<i class="fas fa-file-video"></i>',
        'mov': '<i class="fas fa-file-video"></i>',
        'avi': '<i class="fas fa-file-video"></i>',
        'webm': '<i class="fas fa-file-video"></i>',
        'gif': '<i class="fas fa-file-image"></i>',
        'png': '<i class="fas fa-file-image"></i>',
        'jpg': '<i class="fas fa-file-image"></i>',
        'jpeg': '<i class="fas fa-file-image"></i>',
        'mp3': '<i class="fas fa-file-audio"></i>',
        'wav': '<i class="fas fa-file-audio"></i>'
    };
    return icons[ext] || '<i class="fas fa-file"></i>';
}

function formatBytes(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

// ======================
// 5. RENDER BUTTON CODE REMOVED
// ======================
// Render button now uses the default handler from renderer_desktop.js
// NO save dialog - just renders and shows preview
