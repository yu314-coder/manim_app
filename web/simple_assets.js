// SIMPLE ASSETS - WINDOWS EXPLORER DETAILS LIST VIEW WITH AUTO-LOAD
// Version: 2025-01-26-AUTO-LOAD-FIX

console.log('[SIMPLE ASSETS] Loaded - Details List View with Auto-Load');

// Upload function
window.uploadAssets = async function() {
    console.log('[SIMPLE] Upload clicked');
    try {
        const result = await pywebview.api.select_files_to_upload();
        if (result && result.status === 'success' && result.file_paths) {
            const addResult = await pywebview.api.add_assets(result.file_paths);
            if (addResult.status === 'success') {
                showCustomAlert(`Successfully added ${addResult.added} file${addResult.added !== 1 ? 's' : ''}!`, 'success');
                window.loadAssets();
            }
        }
    } catch (error) {
        console.error('[SIMPLE] Upload error:', error);
        showCustomAlert('Error: ' + error.message, 'error');
    }
};

// Load and display assets in Modern Card Grid view
window.loadAssets = async function() {
    console.log('[SIMPLE] Loading assets...');
    const container = document.getElementById('simpleAssetsContainer');

    if (!container) {
        console.error('[SIMPLE] Container not found!');
        return;
    }

    try {
        const result = await pywebview.api.list_media_files();
        console.log('[SIMPLE] Got files:', result);

        if (!result.files || result.files.length === 0) {
            container.innerHTML = `
                <div class="assets-empty">
                    <i class="fas fa-folder-open"></i>
                    <p>No assets found. Drag & drop files to get started.</p>
                </div>
            `;
            return;
        }

        // Clear container
        container.innerHTML = '';

        // Create rows for each file
        result.files.forEach(function(file, index) {
            const ext = file.name.split('.').pop().toLowerCase();
            const fileType = getFileType(ext);
            const rowType = getCardType(ext);

            const row = document.createElement('div');
            row.className = `asset-row ${rowType}`;
            row.dataset.filepath = file.path;
            row.dataset.filename = file.name;
            row.dataset.index = index;

            // Check if it's an image to show thumbnail
            const imageExts = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg'];
            const isImage = imageExts.includes(ext);

            row.innerHTML = `
                <div class="asset-col-preview">
                    ${isImage ?
                        `<img class="asset-thumbnail" src="#" data-filepath="${escapeHtml(file.path)}" alt="${escapeHtml(file.name)}">` :
                        `<div class="asset-preview">${getAssetIcon(file.name)}</div>`
                    }
                </div>
                <div class="asset-col-name">
                    <div class="asset-name" title="${escapeHtml(file.name)}">${escapeHtml(file.name)}</div>
                </div>
                <div class="asset-col-type">
                    <div class="asset-type">${fileType}</div>
                </div>
                <div class="asset-col-size">
                    <div class="asset-size">${formatBytes(file.size)}</div>
                </div>
                <div class="asset-col-actions">
                    <div class="asset-actions">
                        <button class="asset-action-btn" onclick="event.stopPropagation(); showPreviewInAssetsTab('${escapeForJs(file.path)}', '${escapeForJs(file.name)}');">
                            <i class="fas fa-eye"></i> View
                        </button>
                        <button class="asset-action-btn delete" onclick="event.stopPropagation(); window.deleteAssetById('${escapeForJs(file.path)}', '${escapeForJs(file.name)}');">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                </div>
            `;

            // Click row to preview
            row.addEventListener('click', function() {
                showPreviewInAssetsTab(file.path, file.name);
            });

            // Load thumbnail for images
            if (isImage) {
                const img = row.querySelector('.asset-thumbnail');
                if (img && window.pywebview && window.pywebview.api) {
                    window.pywebview.api.read_file_as_base64(file.path)
                        .then(function(base64Data) {
                            img.src = `data:image/${ext};base64,${base64Data}`;
                        })
                        .catch(function(err) {
                            console.error('[THUMBNAIL] Failed to load:', err);
                            // Fallback to icon
                            img.outerHTML = `<div class="asset-preview">${getAssetIcon(file.name)}</div>`;
                        });
                }
            }

            container.appendChild(row);
        });

        console.log('[SIMPLE] [OK] Displayed', result.files.length, 'assets in Column Table view');

    } catch (error) {
        console.error('[SIMPLE] Load error:', error);
        container.innerHTML = '<div class="assets-empty"><i class="fas fa-exclamation-triangle"></i><p style="color: #ef4444;">Error loading assets</p></div>';
        showCustomAlert('Error loading assets: ' + error.message, 'error');
    }
};

// Get card type for styling
function getCardType(ext) {
    const videoExts = ['mp4', 'mov', 'avi', 'webm', 'mkv', 'flv', 'm4v'];
    const imageExts = ['png', 'jpg', 'jpeg', 'gif', 'svg', 'bmp', 'webp', 'ico'];
    const audioExts = ['mp3', 'wav', 'ogg', 'm4a', 'aac', 'flac', 'wma'];
    const fontExts = ['ttf', 'otf', 'woff', 'woff2', 'ttc', 'eot'];

    if (videoExts.includes(ext)) return 'video';
    if (imageExts.includes(ext)) return 'image';
    if (audioExts.includes(ext)) return 'audio';
    if (fontExts.includes(ext)) return 'font';
    return 'other';
}

// Delete asset
function deleteAsset(filePath, fileName) {
    console.log('[DELETE] Deleting:', fileName);

    showCustomConfirm(
        `Are you sure you want to delete "${fileName}"?`,
        () => {
            // User confirmed - proceed with deletion
            pywebview.api.delete_asset(filePath)
                .then(result => {
                    console.log('[DELETE] Result:', result);
                    if (result.status === 'success') {
                        showCustomAlert('File deleted successfully', 'success');
                        window.loadAssets();
                    } else {
                        showCustomAlert(result.message || 'Failed to delete', 'error');
                    }
                })
                .catch(error => {
                    console.error('[DELETE] Error:', error);
                    showCustomAlert('Error deleting file: ' + error.message, 'error');
                });
        }
    );
}

// Show preview in the assets tab preview panel (not workspace)
function showPreviewInAssetsTab(filepath, filename) {
    console.log('[PREVIEW] Showing asset in Assets tab:', filename);

    const previewContainer = document.getElementById('assetsPreviewContainer');
    const previewInfo = document.getElementById('assetsPreviewInfo');

    if (!previewContainer) {
        console.error('[PREVIEW] Preview container not found');
        return;
    }

    // Update info with styled filename
    if (previewInfo) {
        const ext = filename.split('.').pop().toLowerCase();
        const fileType = getFileType(ext);
        previewInfo.innerHTML = `<strong>${escapeHtml(filename)}</strong><br><span style="opacity: 0.7;">${fileType}</span>`;
    }

    const ext = filename.split('.').pop().toLowerCase();
    const videoExts = ['mp4', 'mov', 'avi', 'webm', 'gif', 'mkv', 'flv', 'm4v'];
    const imageExts = ['png', 'jpg', 'jpeg', 'svg', 'bmp', 'webp', 'ico'];
    const fontExts = ['ttf', 'otf', 'woff', 'woff2', 'ttc', 'eot'];
    const audioExts = ['mp3', 'wav', 'ogg', 'm4a', 'aac', 'flac', 'wma'];
    const subtitleExts = ['srt', 'vtt', 'ass', 'ssa', 'sub'];
    const textExts = ['txt', 'md', 'json', 'xml', 'csv'];

    if (videoExts.includes(ext)) {
        // Show video - use get_asset_as_data_url to get HTTP URL
        if (window.pywebview && window.pywebview.api) {
            previewContainer.innerHTML = '<div style="color:#aaa; text-align:center; padding: 30px;">Loading video...</div>';

            window.pywebview.api.get_asset_as_data_url(filepath)
                .then(function(result) {
                    if (result.status === 'success') {
                        previewContainer.innerHTML = `
                            <video controls autoplay loop style="max-width:100%; max-height:100%; object-fit:contain;">
                                <source src="${result.dataUrl}" type="video/${ext}">
                                Your browser does not support the video tag.
                            </video>
                        `;
                    } else {
                        previewContainer.innerHTML = '<div style="color:red; text-align:center;">Failed to load video</div>';
                    }
                })
                .catch(function(err) {
                    console.error('[VIDEO PREVIEW] Failed:', err);
                    previewContainer.innerHTML = '<div style="color:red; text-align:center;">Failed to load video</div>';
                });
        }
    } else if (imageExts.includes(ext)) {
        // Show image using base64
        if (window.pywebview && window.pywebview.api) {
            previewContainer.innerHTML = '<div style="color:#aaa;">Loading image...</div>';
            window.pywebview.api.read_file_as_base64(filepath)
                .then(function(base64Data) {
                    previewContainer.innerHTML = `
                        <img src="data:image/${ext};base64,${base64Data}"
                             style="max-width:100%; max-height:100%; object-fit:contain;"
                             alt="${filename}">
                    `;
                })
                .catch(function(err) {
                    console.error('[PREVIEW] Failed to load image:', err);
                    previewContainer.innerHTML = '<div style="color:red; text-align:center;">Failed to load image</div>';
                });
        }
    } else if (fontExts.includes(ext)) {
        // Show font preview
        showFontPreview(filepath, filename, ext, previewContainer);
    } else if (audioExts.includes(ext)) {
        // Show audio player
        showAudioPreview(filepath, filename, ext, previewContainer);
    } else if (subtitleExts.includes(ext)) {
        // Show subtitle content
        showSubtitlePreview(filepath, filename, previewContainer);
    } else if (textExts.includes(ext)) {
        // Show text file content
        showTextPreview(filepath, filename, previewContainer);
    } else {
        previewContainer.innerHTML = `
            <div style="text-align:center; color:#aaa;">
                <i class="fas fa-file" style="font-size:64px; margin-bottom:12px; opacity:0.3;"></i>
                <p>Preview not available for this file type</p>
            </div>
        `;
    }
}

// Show font preview
function showFontPreview(filepath, filename, ext, container) {
    console.log('[FONT PREVIEW] Loading font:', filename);

    if (window.pywebview && window.pywebview.api) {
        container.innerHTML = '<div style="color:#aaa; padding: 30px; text-align: center;">Loading font...</div>';

        window.pywebview.api.get_asset_as_data_url(filepath)
            .then(function(result) {
                if (result.status === 'success') {
                    // Generate unique font family name
                    const fontFamily = 'PreviewFont_' + Date.now();

                    // Determine font format for @font-face
                    const formatMap = {
                        'ttf': 'truetype',
                        'otf': 'opentype',
                        'woff': 'woff',
                        'woff2': 'woff2',
                        'ttc': 'truetype'
                    };
                    const format = formatMap[ext] || 'truetype';

                    // Create style element with @font-face using HTTP URL
                    const styleId = 'font-preview-style';
                    let styleEl = document.getElementById(styleId);
                    if (styleEl) {
                        styleEl.remove();
                    }
                    styleEl = document.createElement('style');
                    styleEl.id = styleId;
                    styleEl.textContent = `
                        @font-face {
                            font-family: '${fontFamily}';
                            src: url('${result.dataUrl}') format('${format}');
                        }
                    `;
                    document.head.appendChild(styleEl);

                    // Create preview HTML
                    container.innerHTML = `
                        <div style="
                            padding: 20px;
                            overflow-y: auto;
                            max-height: 100%;
                            font-family: '${fontFamily}', sans-serif;
                        ">
                            <!-- Font name header -->
                            <div style="
                                margin-bottom: 20px;
                                padding-bottom: 15px;
                                border-bottom: 2px solid #444;
                            ">
                                <div style="font-size: 18px; color: #3b82f6; font-weight: 600; margin-bottom: 4px;">
                                    <i class="fas fa-font"></i> ${escapeHtml(filename)}
                                </div>
                                <div style="font-size: 12px; color: #888;">
                                    Font Preview
                                </div>
                            </div>

                            <!-- Large sample -->
                            <div style="
                                font-size: 48px;
                                color: #fff;
                                margin-bottom: 24px;
                                line-height: 1.3;
                            ">
                                The quick brown fox jumps over the lazy dog
                            </div>

                            <!-- Medium sample -->
                            <div style="
                                font-size: 32px;
                                color: #ddd;
                                margin-bottom: 24px;
                                line-height: 1.3;
                            ">
                                ABCDEFGHIJKLMNOPQRSTUVWXYZ
                            </div>

                            <div style="
                                font-size: 32px;
                                color: #ddd;
                                margin-bottom: 24px;
                                line-height: 1.3;
                            ">
                                abcdefghijklmnopqrstuvwxyz
                            </div>

                            <div style="
                                font-size: 32px;
                                color: #ddd;
                                margin-bottom: 24px;
                                line-height: 1.3;
                            ">
                                0123456789 !@#$%^&*()
                            </div>

                            <!-- Size samples -->
                            <div style="margin-top: 32px;">
                                <div style="font-size: 12px; color: #888; margin-bottom: 8px;">Different Sizes:</div>

                                <div style="font-size: 14px; color: #ccc; margin-bottom: 8px;">
                                    14px: The quick brown fox jumps over the lazy dog
                                </div>

                                <div style="font-size: 18px; color: #ccc; margin-bottom: 8px;">
                                    18px: The quick brown fox jumps over the lazy dog
                                </div>

                                <div style="font-size: 24px; color: #ccc; margin-bottom: 8px;">
                                    24px: The quick brown fox jumps over the lazy dog
                                </div>

                                <div style="font-size: 36px; color: #ccc; margin-bottom: 8px;">
                                    36px: Typography Sample
                                </div>
                            </div>

                            <!-- Usage tip -->
                            <div style="
                                margin-top: 32px;
                                padding: 16px;
                                background: rgba(59, 130, 246, 0.1);
                                border-left: 3px solid #3b82f6;
                                border-radius: 4px;
                            ">
                                <div style="font-family: system-ui; font-size: 12px; color: #3b82f6; font-weight: 600; margin-bottom: 8px;">
                                    <i class="fas fa-code"></i> Usage in Manim:
                                </div>
                                <pre style="
                                    font-family: 'Courier New', monospace;
                                    font-size: 11px;
                                    color: #ddd;
                                    background: rgba(0,0,0,0.3);
                                    padding: 12px;
                                    border-radius: 4px;
                                    margin: 0;
                                    overflow-x: auto;
                                ">class MyScene(Scene):
    def construct(self):
        # Files in assets folder are found automatically
        register_font("${escapeHtml(filename)}")

        # Use the font in text
        text = Text("Hello World", font="${escapeHtml(filename.split('.')[0])}")
        self.play(Write(text))</pre>
                            </div>
                        </div>
                    `;

                    console.log('[FONT PREVIEW] Font preview loaded successfully');
                } else {
                    container.innerHTML = '<div style="color:red; text-align:center; padding: 30px;">Failed to load font file</div>';
                }
            })
            .catch(function(err) {
                console.error('[FONT PREVIEW] Failed:', err);
                container.innerHTML = '<div style="color:red; text-align:center; padding: 30px;">Failed to load font file</div>';
            });
    }
}

// Show audio preview
function showAudioPreview(filepath, filename, ext, container) {
    console.log('[AUDIO PREVIEW] Loading audio:', filename);

    const audioTypeMap = {
        'mp3': 'audio/mpeg',
        'wav': 'audio/wav',
        'ogg': 'audio/ogg',
        'm4a': 'audio/mp4',
        'aac': 'audio/aac',
        'flac': 'audio/flac',
        'wma': 'audio/x-ms-wma'
    };
    const audioType = audioTypeMap[ext] || 'audio/mpeg';

    if (window.pywebview && window.pywebview.api) {
        container.innerHTML = '<div style="color:#aaa; padding: 30px; text-align: center;">Loading audio...</div>';

        window.pywebview.api.get_asset_as_data_url(filepath)
            .then(function(result) {
                if (result.status === 'success') {
                    container.innerHTML = `
                        <div style="padding: 30px; text-align: center;">
                            <!-- Header -->
                            <div style="margin-bottom: 30px;">
                                <div style="font-size: 64px; color: #10b981; margin-bottom: 16px;">
                                    <i class="fas fa-music"></i>
                                </div>
                                <div style="font-size: 18px; color: #fff; font-weight: 600; margin-bottom: 4px;">
                                    ${escapeHtml(filename)}
                                </div>
                                <div style="font-size: 12px; color: #888;">
                                    ${getFileType(ext)}
                                </div>
                            </div>

                            <!-- Audio Player -->
                            <div style="max-width: 500px; margin: 0 auto 30px;">
                                <audio controls autoplay style="width: 100%; outline: none;">
                                    <source src="${result.dataUrl}" type="${audioType}">
                                    Your browser does not support the audio element.
                                </audio>
                            </div>

                            <!-- Usage tip -->
                            <div style="
                                max-width: 600px;
                                margin: 0 auto;
                                padding: 16px;
                                background: rgba(16, 185, 129, 0.1);
                                border-left: 3px solid #10b981;
                                border-radius: 4px;
                                text-align: left;
                            ">
                                <div style="font-size: 12px; color: #10b981; font-weight: 600; margin-bottom: 8px;">
                                    <i class="fas fa-code"></i> Usage in Manim:
                                </div>
                                <pre style="
                                    font-family: 'Courier New', monospace;
                                    font-size: 11px;
                                    color: #ddd;
                                    background: rgba(0,0,0,0.3);
                                    padding: 12px;
                                    border-radius: 4px;
                                    margin: 0;
                                    overflow-x: auto;
                                ">class MyScene(Scene):
    def construct(self):
        # Files in assets folder are found automatically
        self.add_sound("${escapeHtml(filename)}")

        # Your animation code here
        circle = Circle()
        self.play(Create(circle))
        self.wait()</pre>
                            </div>
                        </div>
                    `;
                } else {
                    container.innerHTML = '<div style="color:red; text-align:center; padding: 30px;">Failed to load audio file</div>';
                }
            })
            .catch(function(err) {
                console.error('[AUDIO PREVIEW] Failed:', err);
                container.innerHTML = '<div style="color:red; text-align:center; padding: 30px;">Failed to load audio file</div>';
            });
    }
}

// Show subtitle preview
function showSubtitlePreview(filepath, filename, container) {
    console.log('[SUBTITLE PREVIEW] Loading subtitle:', filename);

    if (window.pywebview && window.pywebview.api) {
        container.innerHTML = '<div style="color:#aaa; padding: 30px; text-align: center;">Loading subtitle file...</div>';

        window.pywebview.api.read_file_text(filepath)
            .then(function(content) {
                container.innerHTML = `
                    <div style="padding: 20px; overflow-y: auto; max-height: 100%;">
                        <!-- Header -->
                        <div style="margin-bottom: 20px; padding-bottom: 15px; border-bottom: 2px solid #444;">
                            <div style="font-size: 18px; color: #f59e0b; font-weight: 600; margin-bottom: 4px;">
                                <i class="fas fa-closed-captioning"></i> ${escapeHtml(filename)}
                            </div>
                            <div style="font-size: 12px; color: #888;">
                                Subtitle File Preview
                            </div>
                        </div>

                        <!-- Content -->
                        <pre style="
                            font-family: 'Courier New', monospace;
                            font-size: 13px;
                            color: #ddd;
                            background: rgba(0,0,0,0.3);
                            padding: 16px;
                            border-radius: 4px;
                            white-space: pre-wrap;
                            word-wrap: break-word;
                            line-height: 1.5;
                            max-height: 400px;
                            overflow-y: auto;
                        ">${escapeHtml(content)}</pre>

                        <!-- Usage tip -->
                        <div style="
                            margin-top: 24px;
                            padding: 16px;
                            background: rgba(245, 158, 11, 0.1);
                            border-left: 3px solid #f59e0b;
                            border-radius: 4px;
                        ">
                            <div style="font-size: 12px; color: #f59e0b; font-weight: 600; margin-bottom: 8px;">
                                <i class="fas fa-info-circle"></i> Using Subtitles in Manim:
                            </div>
                            <div style="font-size: 11px; color: #ccc; line-height: 1.6; margin-bottom: 8px;">
                                ${filename.endsWith('.srt') ? 'SRT format with timecodes and text' :
                                  filename.endsWith('.vtt') ? 'WebVTT format for web video' :
                                  'Subtitle file for video synchronization'}
                            </div>
                            <div style="font-size: 11px; color: #aaa; line-height: 1.6; margin-top: 8px;">
                                <strong>Note:</strong> Manim doesn't natively support SRT/VTT files. You can:
                                <ul style="margin: 8px 0 0 20px; padding: 0;">
                                    <li>Parse subtitle files and create Text objects with timing</li>
                                    <li>Use external tools like <code style="background: rgba(0,0,0,0.3); padding: 2px 4px; border-radius: 2px;">manim-subtitler</code></li>
                                    <li>Add subtitles in post-production with video editing software</li>
                                </ul>
                            </div>
                        </div>
                    </div>
                `;
            })
            .catch(function(err) {
                console.error('[SUBTITLE PREVIEW] Failed to load:', err);
                container.innerHTML = '<div style="color:red; text-align:center; padding: 30px;">Failed to load subtitle file</div>';
            });
    }
}

// Show text file preview
function showTextPreview(filepath, filename, container) {
    console.log('[TEXT PREVIEW] Loading text file:', filename);

    if (window.pywebview && window.pywebview.api) {
        container.innerHTML = '<div style="color:#aaa; padding: 30px; text-align: center;">Loading text file...</div>';

        window.pywebview.api.read_file_text(filepath)
            .then(function(content) {
                const ext = filename.split('.').pop().toLowerCase();
                const isCode = ['json', 'xml', 'csv'].includes(ext);

                container.innerHTML = `
                    <div style="padding: 20px; overflow-y: auto; max-height: 100%;">
                        <!-- Header -->
                        <div style="margin-bottom: 20px; padding-bottom: 15px; border-bottom: 2px solid #444;">
                            <div style="font-size: 18px; color: #3b82f6; font-weight: 600; margin-bottom: 4px;">
                                <i class="fas ${isCode ? 'fa-file-code' : 'fa-file-alt'}"></i> ${escapeHtml(filename)}
                            </div>
                            <div style="font-size: 12px; color: #888;">
                                ${getFileType(ext)}
                            </div>
                        </div>

                        <!-- Content -->
                        <pre style="
                            font-family: 'Courier New', monospace;
                            font-size: 13px;
                            color: #ddd;
                            background: rgba(0,0,0,0.3);
                            padding: 16px;
                            border-radius: 4px;
                            white-space: pre-wrap;
                            word-wrap: break-word;
                            line-height: 1.6;
                            max-height: 500px;
                            overflow-y: auto;
                        ">${escapeHtml(content)}</pre>
                    </div>
                `;
            })
            .catch(function(err) {
                console.error('[TEXT PREVIEW] Failed to load:', err);
                container.innerHTML = '<div style="color:red; text-align:center; padding: 30px;">Failed to load text file</div>';
            });
    }
}

// Get file type description
function getFileType(ext) {
    const types = {
        // Videos
        'mp4': 'MP4 Video',
        'mov': 'MOV Video',
        'avi': 'AVI Video',
        'webm': 'WebM Video',
        'mkv': 'MKV Video',
        'flv': 'FLV Video',
        'm4v': 'M4V Video',
        // Images
        'gif': 'GIF Image',
        'png': 'PNG Image',
        'jpg': 'JPEG Image',
        'jpeg': 'JPEG Image',
        'svg': 'SVG Image',
        'bmp': 'BMP Image',
        'webp': 'WebP Image',
        'ico': 'Icon File',
        // Audio
        'mp3': 'MP3 Audio',
        'wav': 'WAV Audio',
        'ogg': 'OGG Audio',
        'm4a': 'M4A Audio',
        'aac': 'AAC Audio',
        'flac': 'FLAC Audio',
        'wma': 'WMA Audio',
        // Fonts
        'ttf': 'TrueType Font',
        'otf': 'OpenType Font',
        'woff': 'WOFF Font',
        'woff2': 'WOFF2 Font',
        'ttc': 'TrueType Collection',
        'eot': 'EOT Font',
        // Subtitles
        'srt': 'SRT Subtitle',
        'vtt': 'WebVTT Subtitle',
        'ass': 'ASS Subtitle',
        'ssa': 'SSA Subtitle',
        'sub': 'SUB Subtitle',
        // Text
        'txt': 'Text File',
        'md': 'Markdown File',
        'json': 'JSON File',
        'xml': 'XML File',
        'csv': 'CSV File'
    };
    return types[ext] || (ext.toUpperCase() + ' File');
}

// Get icon for file type
function getAssetIcon(filename) {
    const ext = filename.split('.').pop().toLowerCase();
    const icons = {
        // Videos
        'mp4': '<i class="fas fa-file-video"></i>',
        'mov': '<i class="fas fa-file-video"></i>',
        'avi': '<i class="fas fa-file-video"></i>',
        'webm': '<i class="fas fa-file-video"></i>',
        'mkv': '<i class="fas fa-file-video"></i>',
        'flv': '<i class="fas fa-file-video"></i>',
        'm4v': '<i class="fas fa-file-video"></i>',
        // Images
        'gif': '<i class="fas fa-file-image"></i>',
        'png': '<i class="fas fa-file-image"></i>',
        'jpg': '<i class="fas fa-file-image"></i>',
        'jpeg': '<i class="fas fa-file-image"></i>',
        'svg': '<i class="fas fa-file-image"></i>',
        'bmp': '<i class="fas fa-file-image"></i>',
        'webp': '<i class="fas fa-file-image"></i>',
        'ico': '<i class="fas fa-file-image"></i>',
        // Audio
        'mp3': '<i class="fas fa-file-audio"></i>',
        'wav': '<i class="fas fa-file-audio"></i>',
        'ogg': '<i class="fas fa-file-audio"></i>',
        'm4a': '<i class="fas fa-file-audio"></i>',
        'aac': '<i class="fas fa-file-audio"></i>',
        'flac': '<i class="fas fa-file-audio"></i>',
        'wma': '<i class="fas fa-file-audio"></i>',
        // Fonts
        'ttf': '<i class="fas fa-font"></i>',
        'otf': '<i class="fas fa-font"></i>',
        'woff': '<i class="fas fa-font"></i>',
        'woff2': '<i class="fas fa-font"></i>',
        'ttc': '<i class="fas fa-font"></i>',
        'eot': '<i class="fas fa-font"></i>',
        // Subtitles
        'srt': '<i class="fas fa-closed-captioning"></i>',
        'vtt': '<i class="fas fa-closed-captioning"></i>',
        'ass': '<i class="fas fa-closed-captioning"></i>',
        'ssa': '<i class="fas fa-closed-captioning"></i>',
        'sub': '<i class="fas fa-closed-captioning"></i>',
        // Text
        'txt': '<i class="fas fa-file-alt"></i>',
        'md': '<i class="fas fa-file-alt"></i>',
        'json': '<i class="fas fa-file-code"></i>',
        'xml': '<i class="fas fa-file-code"></i>',
        'csv': '<i class="fas fa-file-csv"></i>'
    };
    return icons[ext] || '<i class="fas fa-file"></i>';
}

// Format bytes to human readable
function formatBytes(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

// Escape HTML to prevent XSS in data attributes
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Escape for JavaScript strings
function escapeForJs(text) {
    return text.replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/"/g, '\\"').replace(/\n/g, '\\n');
}

// Global delete function that can be called from onclick
window.deleteAssetById = function(filepath, filename) {
    console.log('[DELETE] Delete button clicked for:', filename);
    deleteAsset(filepath, filename);
};

// Auto-load on pywebview ready
window.addEventListener('pywebviewready', () => {
    console.log('[SIMPLE] PyWebView ready - loading assets');
    setTimeout(() => window.loadAssets(), 500);

    // Initialize drag and drop
    initDragAndDrop();
});

// Initialize Drag and Drop functionality
function initDragAndDrop() {
    const dropzone = document.getElementById('assetsDropzone');

    if (!dropzone) {
        console.warn('[DRAG&DROP] Dropzone not found');
        return;
    }

    // Drag and drop is now handled in renderer_desktop.js
    // Commented out old implementation to prevent conflicts
    console.log('[DRAG&DROP] Drag and drop handled by renderer_desktop.js');

    // // Prevent default drag behaviors on the entire document
    // ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
    //     document.body.addEventListener(eventName, preventDefaults, false);
    // });

    // function preventDefaults(e) {
    //     e.preventDefault();
    //     e.stopPropagation();
    // }

    // // Highlight drop zone when item is dragged over it
    // ['dragenter', 'dragover'].forEach(eventName => {
    //     dropzone.addEventListener(eventName, highlight, false);
    // });

    // ['dragleave', 'drop'].forEach(eventName => {
    //     dropzone.addEventListener(eventName, unhighlight, false);
    // });

    // function highlight(e) {
    //     dropzone.classList.add('dragover');
    // }

    // function unhighlight(e) {
    //     dropzone.classList.remove('dragover');
    // }

    // // Handle dropped files
    // dropzone.addEventListener('drop', handleDrop, false);

    // async function handleDrop(e) {
    //     const dt = e.dataTransfer;
    //     const files = dt.files;

    //     console.log('[DRAG&DROP] Files dropped:', files.length);

    //     if (files.length === 0) {
    //         console.log('[DRAG&DROP] No files in drop');
    //         return;
    //     }

    //     // Convert FileList to array
    //     const fileArray = Array.from(files);

    //     // Show loading state
    //     dropzone.innerHTML = `
    //         <div class="dropzone-icon">
    //             <i class="fas fa-spinner fa-spin"></i>
    //         </div>
    //         <div class="dropzone-content">
    //             <div class="dropzone-text">Uploading ${fileArray.length} file${fileArray.length > 1 ? 's' : ''}...</div>
    //             <div class="dropzone-hint">Please wait</div>
    //         </div>
    //     `;

    //     try {
    //         // Get file paths from the dropped files
    //         // Note: In a desktop app with PyWebView, we need to handle this differently
    //         // The files from drag-drop are File objects, we need to save them temporarily

    //         // For now, show a message that drag-drop from desktop needs special handling
    //         console.warn('[DRAG&DROP] Desktop file drag-drop requires special handling in PyWebView');

    //         // Restore dropzone UI
    //         restoreDropzoneUI();

    //         showCustomAlert('Please use the upload button to add files', 'info');

    //     } catch (error) {
    //         console.error('[DRAG&DROP] Error handling dropped files:', error);
    //         restoreDropzoneUI();
    //         showCustomAlert('Error uploading files: ' + error.message, 'error');
    //     }
    // }

    function restoreDropzoneUI() {
        dropzone.innerHTML = `
            <div class="dropzone-icon">
                <i class="fas fa-cloud-upload-alt"></i>
            </div>
            <div class="dropzone-content">
                <div class="dropzone-text">Drag & Drop Files Here</div>
                <div class="dropzone-hint">or click to browse • Images, Videos, Audio, Fonts & More</div>
            </div>
        `;
    }

    console.log('[DRAG&DROP] Drag and drop initialized');
}

// Auto-load when Assets tab is clicked
document.addEventListener('DOMContentLoaded', function() {
    console.log('[SIMPLE] Setting up tab change listener');

    const assetTabBtn = document.querySelector('.tab-pill[data-tab="assets"]');
    if (assetTabBtn) {
        assetTabBtn.addEventListener('click', function() {
            console.log('[SIMPLE] Assets tab clicked - auto-loading files');
            setTimeout(() => {
                if (window.pywebview && window.pywebview.api) {
                    window.loadAssets();
                }
            }, 100);
        });
        console.log('[SIMPLE] Tab listener attached');
    } else {
        console.warn('[SIMPLE] Assets tab button not found');
    }

    // Initialize drag and drop if pywebview is already ready
    if (window.pywebview && window.pywebview.api) {
        setTimeout(() => initDragAndDrop(), 100);
    }
});

// Custom confirmation dialog
function showCustomConfirm(message, onConfirm) {
    // Remove any existing modal
    const existingModal = document.getElementById('customConfirmModal');
    if (existingModal) existingModal.remove();

    // Create modal overlay
    const modal = document.createElement('div');
    modal.id = 'customConfirmModal';
    modal.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.7);
        backdrop-filter: blur(4px);
        display: flex;
        justify-content: center;
        align-items: center;
        z-index: 10000;
        animation: fadeIn 0.2s ease;
    `;

    // Create dialog box
    const dialog = document.createElement('div');
    dialog.style.cssText = `
        background: linear-gradient(135deg, #2a2a2a 0%, #1e1e1e 100%);
        border: 1px solid #444;
        border-radius: 12px;
        padding: 30px;
        max-width: 450px;
        width: 90%;
        box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
        animation: slideIn 0.3s ease;
    `;

    dialog.innerHTML = `
        <div style="margin-bottom: 24px;">
            <div style="font-size: 48px; text-align: center; margin-bottom: 16px; color: #f59e0b;">⚠️</div>
            <div style="color: #fff; font-size: 16px; line-height: 1.6; text-align: center; font-weight: 500;">
                ${escapeHtml(message)}
            </div>
        </div>
        <div style="display: flex; gap: 12px; justify-content: center;">
            <button id="confirmYes" style="
                padding: 10px 24px;
                background: #dc3545;
                color: #fff;
                border: none;
                border-radius: 6px;
                cursor: pointer;
                font-size: 14px;
                font-weight: 600;
                transition: all 0.2s;
                box-shadow: 0 2px 8px rgba(220, 53, 69, 0.3);
            ">Delete</button>
            <button id="confirmNo" style="
                padding: 10px 24px;
                background: #444;
                color: #fff;
                border: none;
                border-radius: 6px;
                cursor: pointer;
                font-size: 14px;
                font-weight: 600;
                transition: all 0.2s;
            ">Cancel</button>
        </div>
    `;

    modal.appendChild(dialog);
    document.body.appendChild(modal);

    // Add CSS animations
    const style = document.createElement('style');
    style.textContent = `
        @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
        }
        @keyframes slideIn {
            from { transform: scale(0.9) translateY(-20px); opacity: 0; }
            to { transform: scale(1) translateY(0); opacity: 1; }
        }
        #confirmYes:hover {
            background: #c82333 !important;
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(220, 53, 69, 0.4) !important;
        }
        #confirmNo:hover {
            background: #555 !important;
            transform: translateY(-2px);
        }
    `;
    document.head.appendChild(style);

    // Event handlers
    document.getElementById('confirmYes').addEventListener('click', () => {
        modal.remove();
        if (onConfirm) onConfirm();
    });

    document.getElementById('confirmNo').addEventListener('click', () => {
        modal.remove();
    });

    // Close on overlay click
    modal.addEventListener('click', (e) => {
        if (e.target === modal) modal.remove();
    });

    // ESC key to close
    const escHandler = (e) => {
        if (e.key === 'Escape') {
            modal.remove();
            document.removeEventListener('keydown', escHandler);
        }
    };
    document.addEventListener('keydown', escHandler);
}

// Custom alert dialog
function showCustomAlert(message, type = 'info') {
    // Remove any existing alert
    const existingAlert = document.getElementById('customAlertModal');
    if (existingAlert) existingAlert.remove();

    const colors = {
        success: { bg: '#10b981', icon: '✓', shadow: 'rgba(16, 185, 129, 0.3)' },
        error: { bg: '#dc3545', icon: '✕', shadow: 'rgba(220, 53, 69, 0.3)' },
        info: { bg: '#3b82f6', icon: 'ℹ', shadow: 'rgba(59, 130, 246, 0.3)' }
    };

    const color = colors[type] || colors.info;

    const modal = document.createElement('div');
    modal.id = 'customAlertModal';
    modal.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.7);
        backdrop-filter: blur(4px);
        display: flex;
        justify-content: center;
        align-items: center;
        z-index: 10000;
        animation: fadeIn 0.2s ease;
    `;

    const dialog = document.createElement('div');
    dialog.style.cssText = `
        background: linear-gradient(135deg, #2a2a2a 0%, #1e1e1e 100%);
        border: 1px solid #444;
        border-radius: 12px;
        padding: 30px;
        max-width: 400px;
        width: 90%;
        box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
        animation: slideIn 0.3s ease;
    `;

    dialog.innerHTML = `
        <div style="margin-bottom: 24px;">
            <div style="
                width: 60px;
                height: 60px;
                border-radius: 50%;
                background: ${color.bg};
                color: #fff;
                font-size: 32px;
                font-weight: bold;
                display: flex;
                align-items: center;
                justify-content: center;
                margin: 0 auto 16px;
                box-shadow: 0 4px 16px ${color.shadow};
            ">${color.icon}</div>
            <div style="color: #fff; font-size: 15px; line-height: 1.6; text-align: center;">
                ${escapeHtml(message)}
            </div>
        </div>
        <div style="text-align: center;">
            <button id="alertOk" style="
                padding: 10px 32px;
                background: ${color.bg};
                color: #fff;
                border: none;
                border-radius: 6px;
                cursor: pointer;
                font-size: 14px;
                font-weight: 600;
                transition: all 0.2s;
                box-shadow: 0 2px 8px ${color.shadow};
            ">OK</button>
        </div>
    `;

    modal.appendChild(dialog);
    document.body.appendChild(modal);

    // Event handlers
    const closeAlert = () => modal.remove();
    document.getElementById('alertOk').addEventListener('click', closeAlert);
    modal.addEventListener('click', (e) => {
        if (e.target === modal) closeAlert();
    });

    const escHandler = (e) => {
        if (e.key === 'Escape') {
            closeAlert();
            document.removeEventListener('keydown', escHandler);
        }
    };
    document.addEventListener('keydown', escHandler);

    // Auto-close success messages after 2 seconds
    if (type === 'success') {
        setTimeout(closeAlert, 2000);
    }
}

console.log('[SIMPLE] Simple assets script ready - Details List View with Auto-Load');
