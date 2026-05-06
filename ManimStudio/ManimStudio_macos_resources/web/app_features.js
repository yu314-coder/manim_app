/**
 * Manim Studio - Additional Features
 * Help Modal, Theme Toggle, Settings Dialog
 * Version: 2025-01-26-v1
 */

console.log('[APP_FEATURES] Loading app_features.js...');

// ============================================================================
// TOAST NOTIFICATION (Fallback if not defined)
// ============================================================================

if (typeof toast === 'undefined') {
    window.toast = function(message, type) {
        console.log(`[TOAST ${type}] ${message}`);
        // Simple alert as fallback
        if (type === 'error') {
            alert(`Error: ${message}`);
        }
    };
}

// ============================================================================
// THEME TOGGLE (Moon Button)
// ============================================================================

let currentTheme = localStorage.getItem('manim-theme') || 'dark';

function initializeTheme() {
    // Apply saved theme
    document.body.setAttribute('data-theme', currentTheme);
    updateThemeIcon();
    console.log('[THEME] Initialized theme:', currentTheme);
}

function toggleTheme() {
    currentTheme = currentTheme === 'dark' ? 'light' : 'dark';
    document.body.setAttribute('data-theme', currentTheme);
    localStorage.setItem('manim-theme', currentTheme);
    updateThemeIcon();
    console.log('[THEME] Switched to:', currentTheme);
    toast(`Switched to ${currentTheme} mode`, 'success');
}

function updateThemeIcon() {
    const themeBtn = document.getElementById('themeBtn');
    if (themeBtn) {
        const icon = themeBtn.querySelector('i');
        if (currentTheme === 'dark') {
            icon.className = 'fas fa-moon';
            themeBtn.title = 'Switch to Light Mode';
        } else {
            icon.className = 'fas fa-sun';
            themeBtn.title = 'Switch to Dark Mode';
        }
    }
}

// ============================================================================
// GPU ACCELERATION TOGGLE
// ============================================================================

let gpuAccelerationEnabled = localStorage.getItem('manim-gpu-acceleration') === 'true' || false;

function initializeGPUToggle() {
    // Apply saved GPU setting
    updateGPUToggleUI();
    console.log('[GPU] Initialized GPU acceleration:', gpuAccelerationEnabled);
}

function toggleGPUAcceleration() {
    gpuAccelerationEnabled = !gpuAccelerationEnabled;
    localStorage.setItem('manim-gpu-acceleration', gpuAccelerationEnabled.toString());
    updateGPUToggleUI();

    const mode = gpuAccelerationEnabled ? 'OpenGL (GPU)' : 'Cairo (CPU)';
    console.log('[GPU] Switched to:', mode);
    toast(`Renderer: ${mode}`, 'success');
}

function updateGPUToggleUI() {
    const gpuToggleBtn = document.getElementById('gpuToggleBtn');
    const gpuToggleText = document.getElementById('gpuToggleText');

    if (gpuToggleBtn && gpuToggleText) {
        if (gpuAccelerationEnabled) {
            gpuToggleBtn.classList.add('gpu-active');
            gpuToggleText.textContent = 'GPU: ON';
            gpuToggleBtn.title = 'GPU Acceleration Enabled (OpenGL Renderer) - Click to disable';
        } else {
            gpuToggleBtn.classList.remove('gpu-active');
            gpuToggleText.textContent = 'GPU: OFF';
            gpuToggleBtn.title = 'GPU Acceleration Disabled (Cairo Renderer) - Click to enable';
        }
    }
}

function getGPUAccelerationSetting() {
    return gpuAccelerationEnabled;
}

// ============================================================================
// HELP MODAL (? Button)
// ============================================================================

function showHelpModal() {
    console.log('[HELP] showHelpModal() called');
    const modal = document.getElementById('helpModal');
    console.log('[HELP] Modal element:', modal);
    if (modal) {
        modal.classList.add('active');
        console.log('[HELP] Added active class to modal');
        console.log('[HELP] Modal classes:', modal.className);
    } else {
        console.error('[HELP] Help modal not found in DOM!');
    }
}

function closeHelpModal() {
    const modal = document.getElementById('helpModal');
    if (modal) {
        modal.classList.remove('active');
    }
}

// ============================================================================
// SETTINGS MODAL (Gear Button)
// ============================================================================

// Settings state
let appSettings = {
    defaultSaveLocation: '',
    renderQuality: '1080p',
    fps: 60,
    autoSave: true,
    autoOpenOutput: false,
    theme: 'dark',
    disableCache: false  // Default: cache enabled
};

async function loadAppSettings() {
    console.log('[SETTINGS] Loading settings from backend...');
    try {
        // Check if pywebview API is available
        if (typeof pywebview === 'undefined' || !pywebview.api) {
            console.warn('[SETTINGS] PyWebView API not available, using defaults');
            return;
        }

        const result = await pywebview.api.load_app_settings();
        console.log('[SETTINGS] Load result:', result);

        if (result && result.status === 'success' && result.settings) {
            appSettings = { ...appSettings, ...result.settings };
            console.log('[SETTINGS] Loaded from .manim_studio/settings.json:', appSettings);

            // Apply loaded settings to render and preview dropdowns
            applySettingsToUI();
        }
    } catch (error) {
        console.error('[SETTINGS] Error loading:', error);
    }
}

function applySettingsToUI() {
    console.log('[SETTINGS] Applying settings to UI dropdowns...');

    // Update render control dropdowns
    const renderQualityDropdown = document.getElementById('qualitySelect');
    const renderFpsDropdown = document.getElementById('fpsSelect');

    if (renderQualityDropdown && appSettings.renderQuality) {
        renderQualityDropdown.value = appSettings.renderQuality;
        console.log('[SETTINGS] Set render quality dropdown to:', appSettings.renderQuality);
    }

    if (renderFpsDropdown && appSettings.fps) {
        renderFpsDropdown.value = appSettings.fps.toString();
        console.log('[SETTINGS] Set render FPS dropdown to:', appSettings.fps);
    }

    // Preview dropdowns should stay at hardcoded defaults (480p, 15fps)
    // Don't apply settings to preview - it should always default to fast preview
    const previewQualityDropdown = document.getElementById('previewQualitySelect');
    const previewFpsDropdown = document.getElementById('previewFpsSelect');

    if (previewQualityDropdown) {
        previewQualityDropdown.value = '480p';
        console.log('[SETTINGS] Preview quality hardcoded to: 480p');
    }

    if (previewFpsDropdown) {
        previewFpsDropdown.value = '15';
        console.log('[SETTINGS] Preview FPS hardcoded to: 15');
    }
}

async function saveAppSettings() {
    console.log('[SETTINGS] Saving settings to backend...');
    try {
        // Check if pywebview API is available
        if (typeof pywebview === 'undefined' || !pywebview.api) {
            console.error('[SETTINGS] PyWebView API not available');
            alert('Cannot save settings: PyWebView API not available');
            return;
        }

        const result = await pywebview.api.save_app_settings(appSettings);
        console.log('[SETTINGS] Save result:', result);

        if (result && result.status === 'success') {
            console.log('[SETTINGS] Saved to .manim_studio/settings.json:', appSettings);
            toast('Settings saved successfully!', 'success');
        } else {
            toast('Failed to save settings', 'error');
        }
    } catch (error) {
        console.error('[SETTINGS] Error saving:', error);
        alert(`Failed to save settings: ${error.message}`);
    }
}

function showSettingsModal() {
    console.log('[SETTINGS] showSettingsModal() called');
    const modal = document.getElementById('settingsModal');
    console.log('[SETTINGS] Modal element:', modal);

    if (modal) {
        // Populate current settings
        console.log('[SETTINGS] Populating form with current settings:', appSettings);
        document.getElementById('settingDefaultSaveLocation').value = appSettings.defaultSaveLocation || '';
        document.getElementById('settingRenderQuality').value = appSettings.renderQuality || '1080p';
        document.getElementById('settingFPS').value = appSettings.fps || 60;
        document.getElementById('settingAutoSave').checked = appSettings.autoSave !== false;
        document.getElementById('settingAutoOpenOutput').checked = appSettings.autoOpenOutput === true;
        document.getElementById('settingDisableCache').checked = appSettings.disableCache !== false;

        modal.classList.add('active');
        console.log('[SETTINGS] Added active class to modal');
        console.log('[SETTINGS] Modal classes:', modal.className);

        // Load autosave backups when settings modal opens
        console.log('[SETTINGS] Loading autosave backups...');
        loadAutosaveBackups();

        // Log all buttons in the modal
        const buttons = modal.querySelectorAll('button');
        console.log('[SETTINGS] Found buttons in modal:', buttons.length);
        buttons.forEach((btn, index) => {
            console.log(`[SETTINGS] Button ${index}: id="${btn.id}", text="${btn.textContent.trim()}"`);
        });
    } else {
        console.error('[SETTINGS] Settings modal not found in DOM!');
    }
}

function closeSettingsModal() {
    console.log('[SETTINGS] closeSettingsModal() called');
    const modal = document.getElementById('settingsModal');
    if (modal) {
        console.log('[SETTINGS] Removing active class from modal');
        modal.classList.remove('active');
    } else {
        console.error('[SETTINGS] Settings modal not found!');
    }
}

async function browseSaveLocation() {
    console.log('[SETTINGS] Browse button clicked - opening folder dialog');
    try {
        // Check if pywebview API is available
        if (typeof pywebview === 'undefined' || !pywebview.api) {
            console.error('[SETTINGS] PyWebView API not available');
            alert('PyWebView API not available. Please ensure the app is running correctly.');
            return;
        }

        // Use PyWebView API to show folder dialog
        console.log('[SETTINGS] Calling pywebview.api.select_folder()...');
        const result = await pywebview.api.select_folder();
        console.log('[SETTINGS] Folder dialog result:', result);

        if (result && result.status === 'success' && result.path) {
            const input = document.getElementById('settingDefaultSaveLocation');
            if (input) {
                input.value = result.path;
                appSettings.defaultSaveLocation = result.path;
                console.log('[SETTINGS] Default save location set to:', result.path);
                toast('Save location updated', 'success');
            }
        } else if (result && result.status === 'cancelled') {
            console.log('[SETTINGS] Folder selection cancelled');
        }
    } catch (error) {
        console.error('[SETTINGS] Error browsing folder:', error);
        alert(`Failed to open folder dialog: ${error.message}`);
    }
}

async function applySettings() {
    console.log('[SETTINGS] Applying settings...');
    try {
        // Get values from form
        const saveLocationInput = document.getElementById('settingDefaultSaveLocation');
        const qualitySelect = document.getElementById('settingRenderQuality');
        const fpsSelect = document.getElementById('settingFPS');
        const autoSaveCheck = document.getElementById('settingAutoSave');
        const autoOpenCheck = document.getElementById('settingAutoOpenOutput');
        const disableCacheCheck = document.getElementById('settingDisableCache');

        if (saveLocationInput) appSettings.defaultSaveLocation = saveLocationInput.value;
        if (qualitySelect) appSettings.renderQuality = qualitySelect.value;
        if (fpsSelect) appSettings.fps = parseInt(fpsSelect.value) || 60;
        if (autoSaveCheck) appSettings.autoSave = autoSaveCheck.checked;
        if (autoOpenCheck) appSettings.autoOpenOutput = autoOpenCheck.checked;
        if (disableCacheCheck) appSettings.disableCache = disableCacheCheck.checked;

        console.log('[SETTINGS] Settings updated:', appSettings);

        // Apply settings to UI dropdowns
        applySettingsToUI();

        // Save to .manim_studio/settings.json
        await saveAppSettings();

        // Close modal
        closeSettingsModal();

        console.log('[SETTINGS] Settings applied successfully');
    } catch (error) {
        console.error('[SETTINGS] Error applying settings:', error);
        alert(`Error applying settings: ${error.message}`);
    }
}

// ============================================================================
// SELECT FOLDER API (Backend)
// ============================================================================

// Add select_folder method to backend API (in app.py)
// This will be called from browseSaveLocation()

// ============================================================================
// AUTOSAVE BACKUP MANAGEMENT
// ============================================================================

async function loadAutosaveBackups() {
    console.log('[BACKUPS] Loading autosave backups...');
    const container = document.getElementById('autosaveBackupsList');
    if (!container) return;

    container.innerHTML = `
        <div style="text-align: center; color: var(--text-secondary); padding: 20px;">
            <i class="fas fa-spinner fa-spin"></i> Loading backups...
        </div>
    `;

    try {
        const result = await window.pywebview.api.get_autosave_files();
        console.log('[BACKUPS] Result:', result);

        if (result.status === 'success' && result.files && result.files.length > 0) {
            container.innerHTML = result.files.map((file, index) => {
                const timestamp = file.timestamp || 'Unknown';
                const date = new Date(timestamp.replace(/_/g, (m, i) => i < 10 ? '-' : (i === 13 || i === 16 ? ':' : m)));
                const dateStr = isNaN(date.getTime()) ? timestamp : date.toLocaleString();

                return `
                    <div class="backup-item" style="display: flex; align-items: center; justify-content: space-between; padding: 10px 12px; background: var(--bg-secondary); border-radius: 6px; margin-bottom: 6px; border: 1px solid var(--border-color);">
                        <div style="flex: 1;">
                            <div style="font-size: 13px; color: var(--text-primary); font-weight: 500;">
                                <i class="fas fa-file-code" style="color: #3b82f6; margin-right: 6px;"></i>
                                Backup ${index + 1}
                            </div>
                            <div style="font-size: 11px; color: var(--text-secondary); margin-top: 2px;">
                                ${dateStr}
                            </div>
                        </div>
                        <div style="display: flex; gap: 6px;">
                            <button onclick="restoreBackup('${file.autosave_file.replace(/\\/g, '\\\\')}')"
                                    style="background: rgba(16, 185, 129, 0.15); border: 1px solid rgba(16, 185, 129, 0.3); color: #10b981; padding: 5px 10px; border-radius: 4px; cursor: pointer; font-size: 11px; font-weight: 600;">
                                <i class="fas fa-undo"></i> Restore
                            </button>
                            <button onclick="deleteBackup('${file.autosave_file.replace(/\\/g, '\\\\')}')"
                                    style="background: rgba(239, 68, 68, 0.15); border: 1px solid rgba(239, 68, 68, 0.3); color: #ef4444; padding: 5px 10px; border-radius: 4px; cursor: pointer; font-size: 11px; font-weight: 600;">
                                <i class="fas fa-trash"></i>
                            </button>
                        </div>
                    </div>
                `;
            }).join('');
        } else {
            container.innerHTML = `
                <div style="text-align: center; color: var(--text-secondary); padding: 30px;">
                    <i class="fas fa-inbox" style="font-size: 32px; margin-bottom: 10px; opacity: 0.3;"></i>
                    <p>No backups available</p>
                </div>
            `;
        }
    } catch (error) {
        console.error('[BACKUPS] Error loading backups:', error);
        container.innerHTML = `
            <div style="text-align: center; color: #ef4444; padding: 20px;">
                <i class="fas fa-exclamation-circle"></i> Error loading backups
            </div>
        `;
    }
}

async function restoreBackup(filepath) {
    if (!confirm('This will replace your current code with the backup. Continue?')) {
        return;
    }

    try {
        const result = await window.pywebview.api.load_autosave(filepath);
        if (result.status === 'success' && result.code) {
            // Set editor content
            if (window.monacoEditor) {
                window.monacoEditor.setValue(result.code);
            }
            closeSettingsModal();
            if (window.showToast) {
                window.showToast('Backup restored successfully!', 'success');
            }
        } else {
            alert('Failed to restore backup: ' + (result.message || 'Unknown error'));
        }
    } catch (error) {
        console.error('[BACKUPS] Error restoring backup:', error);
        alert('Error restoring backup: ' + error.message);
    }
}

async function deleteBackup(filepath) {
    if (!confirm('Delete this backup?')) {
        return;
    }

    try {
        const result = await window.pywebview.api.delete_autosave(filepath);
        if (result.status === 'success') {
            loadAutosaveBackups(); // Refresh the list
            if (window.showToast) {
                window.showToast('Backup deleted', 'info');
            }
        } else {
            alert('Failed to delete backup: ' + (result.message || 'Unknown error'));
        }
    } catch (error) {
        console.error('[BACKUPS] Error deleting backup:', error);
        alert('Error deleting backup: ' + error.message);
    }
}

async function deleteAllBackups() {
    if (!confirm('Delete ALL autosave backups? This cannot be undone.')) {
        return;
    }

    try {
        const result = await window.pywebview.api.delete_all_autosaves();
        if (result.status === 'success') {
            loadAutosaveBackups(); // Refresh the list
            if (window.showToast) {
                window.showToast(`Deleted ${result.deleted_count} backup(s)`, 'success');
            }
        } else {
            alert('Failed to delete backups: ' + (result.message || 'Unknown error'));
        }
    } catch (error) {
        console.error('[BACKUPS] Error deleting all backups:', error);
        alert('Error deleting backups: ' + error.message);
    }
}

async function openBackupsFolder() {
    try {
        const result = await window.pywebview.api.open_autosave_folder();
        if (result.status !== 'success') {
            alert('Failed to open folder: ' + (result.message || 'Unknown error'));
        }
    } catch (error) {
        console.error('[BACKUPS] Error opening folder:', error);
        alert('Error opening folder: ' + error.message);
    }
}

// ============================================================================
// CACHE MANAGEMENT
// ============================================================================

async function clearManimCache() {
    if (!confirm('Clear all Manim cache files? This includes partial movie files and Tex cache. You may need to re-render animations.')) {
        return;
    }

    try {
        const btn = document.getElementById('clearCacheBtn');
        if (btn) {
            btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Clearing...';
            btn.disabled = true;
        }

        const result = await window.pywebview.api.clear_manim_cache();

        if (btn) {
            btn.innerHTML = '<i class="fas fa-trash"></i> Clear Manim Cache';
            btn.disabled = false;
        }

        if (result.status === 'success') {
            if (window.showToast) {
                window.showToast(`Cache cleared: ${result.deleted_count} files (${result.deleted_size_mb} MB)`, 'success');
            } else {
                alert(`Cache cleared: ${result.deleted_count} files (${result.deleted_size_mb} MB)`);
            }
        } else {
            alert('Failed to clear cache: ' + (result.message || 'Unknown error'));
        }
    } catch (error) {
        console.error('[CACHE] Error clearing cache:', error);
        alert('Error clearing cache: ' + error.message);
    }
}

// ============================================================================
// EVENT LISTENERS SETUP
// ============================================================================

function setupModalEventListeners() {
    console.log('[APP_FEATURES] ============================================');
    console.log('[APP_FEATURES] Setting up modal event listeners...');
    console.log('[APP_FEATURES] ============================================');

    // Help Modal Buttons
    const helpModalClose = document.getElementById('helpModalClose');
    const helpModalOk = document.getElementById('helpModalOk');

    console.log('[APP_FEATURES] Help modal close button:', helpModalClose);
    console.log('[APP_FEATURES] Help modal OK button:', helpModalOk);

    if (helpModalClose) {
        helpModalClose.addEventListener('click', (e) => {
            console.log('[APP_FEATURES] ✓✓✓ HELP CLOSE CLICKED ✓✓✓');
            e.preventDefault();
            e.stopPropagation();
            closeHelpModal();
        });
        console.log('[APP_FEATURES] ✓ Help close button listener added');
    } else {
        console.error('[APP_FEATURES] ✗ Help close button NOT FOUND');
    }

    if (helpModalOk) {
        helpModalOk.addEventListener('click', (e) => {
            console.log('[APP_FEATURES] ✓✓✓ HELP OK CLICKED ✓✓✓');
            e.preventDefault();
            e.stopPropagation();
            closeHelpModal();
        });
        console.log('[APP_FEATURES] ✓ Help OK button listener added');
    } else {
        console.error('[APP_FEATURES] ✗ Help OK button NOT FOUND');
    }

    // Settings Modal Buttons
    const settingsModalClose = document.getElementById('settingsModalClose');
    const cancelSettingsBtn = document.getElementById('cancelSettingsBtn');
    const applySettingsBtn = document.getElementById('applySettingsBtn');
    const browseBtn = document.getElementById('browseDefaultSaveLocation');

    console.log('[APP_FEATURES] Settings close button:', settingsModalClose);
    console.log('[APP_FEATURES] Cancel button:', cancelSettingsBtn);
    console.log('[APP_FEATURES] Apply button:', applySettingsBtn);
    console.log('[APP_FEATURES] Browse button:', browseBtn);

    if (settingsModalClose) {
        settingsModalClose.addEventListener('click', (e) => {
            console.log('[APP_FEATURES] ✓✓✓ SETTINGS CLOSE X CLICKED ✓✓✓');
            e.preventDefault();
            e.stopPropagation();
            closeSettingsModal();
        });
        console.log('[APP_FEATURES] ✓ Settings close button listener added');
    } else {
        console.error('[APP_FEATURES] ✗ Settings close button NOT FOUND');
    }

    if (cancelSettingsBtn) {
        cancelSettingsBtn.addEventListener('click', (e) => {
            console.log('[APP_FEATURES] ✓✓✓ CANCEL BUTTON CLICKED ✓✓✓');
            e.preventDefault();
            e.stopPropagation();
            closeSettingsModal();
        });
        console.log('[APP_FEATURES] ✓ Cancel button listener added');
    } else {
        console.error('[APP_FEATURES] ✗ Cancel button NOT FOUND');
    }

    if (applySettingsBtn) {
        applySettingsBtn.addEventListener('click', (e) => {
            console.log('[APP_FEATURES] ✓✓✓ APPLY SETTINGS CLICKED ✓✓✓');
            e.preventDefault();
            e.stopPropagation();
            applySettings();
        });
        console.log('[APP_FEATURES] ✓ Apply button listener added');
    } else {
        console.error('[APP_FEATURES] ✗ Apply button NOT FOUND');
    }

    if (browseBtn) {
        browseBtn.addEventListener('click', (e) => {
            console.log('[APP_FEATURES] ✓✓✓ BROWSE BUTTON CLICKED ✓✓✓');
            e.preventDefault();
            e.stopPropagation();
            browseSaveLocation();
        });
        console.log('[APP_FEATURES] ✓ Browse button listener added');
    } else {
        console.error('[APP_FEATURES] ✗ Browse button NOT FOUND');
    }

    // Autosave Backup Buttons
    const refreshBackupsBtn = document.getElementById('refreshBackupsBtn');
    const deleteAllBackupsBtn = document.getElementById('deleteAllBackupsBtn');
    const openBackupsFolderBtn = document.getElementById('openBackupsFolderBtn');

    console.log('[APP_FEATURES] Refresh backups button:', refreshBackupsBtn);
    console.log('[APP_FEATURES] Delete all backups button:', deleteAllBackupsBtn);
    console.log('[APP_FEATURES] Open backups folder button:', openBackupsFolderBtn);

    if (refreshBackupsBtn) {
        refreshBackupsBtn.addEventListener('click', (e) => {
            console.log('[APP_FEATURES] ✓✓✓ REFRESH BACKUPS CLICKED ✓✓✓');
            e.preventDefault();
            e.stopPropagation();
            loadAutosaveBackups();
        });
        console.log('[APP_FEATURES] ✓ Refresh backups button listener added');
    } else {
        console.error('[APP_FEATURES] ✗ Refresh backups button NOT FOUND');
    }

    if (deleteAllBackupsBtn) {
        deleteAllBackupsBtn.addEventListener('click', (e) => {
            console.log('[APP_FEATURES] ✓✓✓ DELETE ALL BACKUPS CLICKED ✓✓✓');
            e.preventDefault();
            e.stopPropagation();
            deleteAllBackups();
        });
        console.log('[APP_FEATURES] ✓ Delete all backups button listener added');
    } else {
        console.error('[APP_FEATURES] ✗ Delete all backups button NOT FOUND');
    }

    if (openBackupsFolderBtn) {
        openBackupsFolderBtn.addEventListener('click', async (e) => {
            console.log('[APP_FEATURES] ✓✓✓ OPEN BACKUPS FOLDER CLICKED ✓✓✓');
            e.preventDefault();
            e.stopPropagation();
            try {
                const result = await pywebview.api.open_autosave_folder();
                console.log('[APP_FEATURES] Open folder result:', result);
                if (result.status !== 'success') {
                    alert('Error opening folder: ' + (result.message || 'Unknown error'));
                }
            } catch (error) {
                console.error('[APP_FEATURES] Error opening folder:', error);
                alert('Error opening autosave folder: ' + error.message);
            }
        });
        console.log('[APP_FEATURES] ✓ Open backups folder button listener added');
    } else {
        console.error('[APP_FEATURES] ✗ Open backups folder button NOT FOUND');
    }

    // Intercept native fullscreen button to open in separate window
    setTimeout(() => {
        const previewVideo = document.getElementById('previewVideo');

        if (previewVideo) {
            console.log('[APP_FEATURES] Setting up fullscreen interception...');

            let handlerActive = true;

            // Handler that executes only ONCE then disables itself temporarily
            const handleFullscreen = (e) => {
                // ONLY act when ENTERING fullscreen (not exiting)
                const isEnteringFullscreen = document.fullscreenElement === previewVideo ||
                    document.webkitFullscreenElement === previewVideo ||
                    document.mozFullScreenElement === previewVideo ||
                    document.msFullscreenElement === previewVideo;

                if (isEnteringFullscreen && handlerActive) {
                    // Disable handler IMMEDIATELY
                    handlerActive = false;

                    console.log('[APP_FEATURES] ========================================');
                    console.log('[APP_FEATURES] FULLSCREEN ENTERED - Opening separate window');
                    console.log('[APP_FEATURES] Handler disabled');
                    console.log('[APP_FEATURES] ========================================');

                    // Exit fullscreen immediately
                    if (document.exitFullscreen) {
                        document.exitFullscreen();
                    } else if (document.webkitExitFullscreen) {
                        document.webkitExitFullscreen();
                    } else if (document.mozCancelFullScreen) {
                        document.mozCancelFullScreen();
                    } else if (document.msExitFullscreen) {
                        document.msExitFullscreen();
                    }

                    // Open in new window
                    const videoSrc = previewVideo.src;
                    console.log('[APP_FEATURES] Video source:', videoSrc);

                    if (videoSrc && videoSrc !== '') {
                        pywebview.api.open_video_fullscreen(videoSrc)
                            .then(result => {
                                console.log('[APP_FEATURES] API response:', result);
                                if (result.status === 'success') {
                                    console.log('[APP_FEATURES] ✅ Video window opened');
                                }
                            })
                            .catch(error => {
                                console.error('[APP_FEATURES] ❌ Exception:', error);
                            })
                            .finally(() => {
                                // Re-enable handler after 3 seconds
                                setTimeout(() => {
                                    handlerActive = true;
                                    console.log('[APP_FEATURES] Handler re-enabled');
                                }, 3000);
                            });
                    } else {
                        // No video, re-enable handler after delay
                        setTimeout(() => {
                            handlerActive = true;
                        }, 3000);
                    }

                    console.log('[APP_FEATURES] ========================================');
                } else if (!handlerActive) {
                    console.log('[APP_FEATURES] Handler disabled, ignoring fullscreen event');
                }
            };

            // Use only ONE event listener
            document.addEventListener('fullscreenchange', handleFullscreen);

            console.log('[APP_FEATURES] ✓ Fullscreen interception enabled');
        }
    }, 500);

    // Close modals when clicking outside (on overlay)
    const helpModal = document.getElementById('helpModal');
    const settingsModal = document.getElementById('settingsModal');

    console.log('[APP_FEATURES] Help modal element:', helpModal);
    console.log('[APP_FEATURES] Settings modal element:', settingsModal);

    if (helpModal) {
        helpModal.addEventListener('click', (e) => {
            console.log('[APP_FEATURES] Click on help modal overlay, target:', e.target.id);
            if (e.target.id === 'helpModal') {
                console.log('[APP_FEATURES] Clicked outside help modal, closing');
                closeHelpModal();
            }
        });
    }

    if (settingsModal) {
        settingsModal.addEventListener('click', (e) => {
            console.log('[APP_FEATURES] Click on settings modal overlay, target:', e.target.id);
            if (e.target.id === 'settingsModal') {
                console.log('[APP_FEATURES] Clicked outside settings modal, closing');
                closeSettingsModal();
            }
        });
    }

    console.log('[APP_FEATURES] ============================================');
    console.log('[APP_FEATURES] Modal event listeners setup complete');
    console.log('[APP_FEATURES] ============================================');
}

// ============================================================================
// EVENT LISTENERS
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    console.log('[APP_FEATURES] ============================================');
    console.log('[APP_FEATURES] DOMContentLoaded fired');
    console.log('[APP_FEATURES] ============================================');

    // Initialize theme (doesn't need API)
    initializeTheme();

    // Initialize GPU toggle (doesn't need API)
    initializeGPUToggle();

    // DON'T load settings here - wait for pywebviewready
    // loadAppSettings() will be called when pywebviewready fires

    // Theme button
    const themeBtn = document.getElementById('themeBtn');
    console.log('[APP_FEATURES] Theme button:', themeBtn);
    if (themeBtn) {
        themeBtn.addEventListener('click', () => {
            console.log('[APP_FEATURES] Theme button clicked!');
            toggleTheme();
        });
        console.log('[APP_FEATURES] ✓ Theme button listener added');
    } else {
        console.error('[APP_FEATURES] ✗ Theme button NOT FOUND');
    }

    // GPU toggle button
    const gpuToggleBtn = document.getElementById('gpuToggleBtn');
    console.log('[APP_FEATURES] GPU toggle button:', gpuToggleBtn);
    if (gpuToggleBtn) {
        gpuToggleBtn.addEventListener('click', () => {
            console.log('[APP_FEATURES] GPU toggle button clicked!');
            toggleGPUAcceleration();
        });
        console.log('[APP_FEATURES] ✓ GPU toggle button listener added');
    } else {
        console.error('[APP_FEATURES] ✗ GPU toggle button NOT FOUND');
    }

    // Help button
    const helpBtn = document.getElementById('helpBtn');
    console.log('[APP_FEATURES] Help button:', helpBtn);
    if (helpBtn) {
        helpBtn.addEventListener('click', () => {
            console.log('[APP_FEATURES] Help button clicked!');
            showHelpModal();
        });
        console.log('[APP_FEATURES] ✓ Help button listener added');
    } else {
        console.error('[APP_FEATURES] ✗ Help button NOT FOUND');
    }

    // Settings button
    const settingsBtn = document.getElementById('settingsBtn');
    console.log('[APP_FEATURES] Settings button:', settingsBtn);
    if (settingsBtn) {
        settingsBtn.addEventListener('click', () => {
            console.log('[APP_FEATURES] ✓✓✓ SETTINGS BUTTON CLICKED ✓✓✓');
            showSettingsModal();
        });
        console.log('[APP_FEATURES] ✓ Settings button listener added');
    } else {
        console.error('[APP_FEATURES] ✗ Settings button NOT FOUND');
    }

    // Autosave backup buttons - these are in the modal, so attach after modals are loaded
    // Will be attached in the modalsReady event listener below

    // ============================================================================
    // KEYBOARD SHORTCUTS
    // ============================================================================

    console.log('[APP_FEATURES] Setting up keyboard shortcuts...');

    document.addEventListener('keydown', (e) => {
        // Don't trigger shortcuts if user is typing in an input or textarea
        const activeElement = document.activeElement;
        const isTyping = activeElement && (
            activeElement.tagName === 'INPUT' ||
            activeElement.tagName === 'TEXTAREA' ||
            activeElement.isContentEditable
        );

        // F5 - Render Animation
        if (e.key === 'F5') {
            e.preventDefault();
            const renderBtn = document.getElementById('renderBtn');
            if (renderBtn && renderBtn.style.display !== 'none') {
                console.log('[APP_FEATURES] F5 pressed - triggering render');
                renderBtn.click();
            }
            return;
        }

        // F6 - Quick Preview
        if (e.key === 'F6') {
            e.preventDefault();
            const previewBtn = document.getElementById('previewBtn');
            if (previewBtn) {
                console.log('[APP_FEATURES] F6 pressed - triggering preview');
                previewBtn.click();
            }
            return;
        }

        // Skip other shortcuts if typing
        if (isTyping) return;

        // Ctrl+S - Save File
        if ((e.ctrlKey || e.metaKey) && e.key === 's') {
            e.preventDefault();
            const saveBtn = document.getElementById('saveFileBtn');
            if (saveBtn) {
                console.log('[APP_FEATURES] Ctrl+S pressed - triggering save');
                saveBtn.click();
            }
            return;
        }

        // Ctrl+N - New File
        if ((e.ctrlKey || e.metaKey) && e.key === 'n') {
            e.preventDefault();
            const newBtn = document.getElementById('newFileBtn');
            if (newBtn) {
                console.log('[APP_FEATURES] Ctrl+N pressed - triggering new file');
                newBtn.click();
            }
            return;
        }

        // Ctrl+O - Open File
        if ((e.ctrlKey || e.metaKey) && e.key === 'o') {
            e.preventDefault();
            const openBtn = document.getElementById('openFileBtn');
            if (openBtn) {
                console.log('[APP_FEATURES] Ctrl+O pressed - triggering open file');
                openBtn.click();
            }
            return;
        }
    });

    console.log('[APP_FEATURES] ✓ Keyboard shortcuts registered');
    console.log('[APP_FEATURES] - F5: Render Animation');
    console.log('[APP_FEATURES] - F6: Quick Preview');
    console.log('[APP_FEATURES] - Ctrl+S: Save File');
    console.log('[APP_FEATURES] - Ctrl+N: New File');
    console.log('[APP_FEATURES] - Ctrl+O: Open File');

    // Wait for modals to load before setting up their event listeners
    window.addEventListener('modalsReady', () => {
        console.log('[APP_FEATURES] ============================================');
        console.log('[APP_FEATURES] MODALS READY EVENT RECEIVED');
        console.log('[APP_FEATURES] ============================================');
        setupModalEventListeners();
    });

    // Fallback: Try after a delay if modalsReady doesn't fire
    setTimeout(() => {
        const helpModal = document.getElementById('helpModal');
        const settingsModal = document.getElementById('settingsModal');
        console.log('[APP_FEATURES] Timeout check - Help modal:', helpModal);
        console.log('[APP_FEATURES] Timeout check - Settings modal:', settingsModal);

        if (helpModal && settingsModal) {
            console.log('[APP_FEATURES] ============================================');
            console.log('[APP_FEATURES] MODALS FOUND VIA TIMEOUT');
            console.log('[APP_FEATURES] ============================================');
            setupModalEventListeners();
        } else {
            console.error('[APP_FEATURES] MODALS STILL NOT FOUND AFTER TIMEOUT!');
        }
    }, 500);

    console.log('[APP_FEATURES] Main event listeners set up successfully');
});

// Wait for PyWebView ready to load settings
window.addEventListener('pywebviewready', () => {
    console.log('[APP_FEATURES] ============================================');
    console.log('[APP_FEATURES] PyWebView ready - loading settings...');
    console.log('[APP_FEATURES] ============================================');
    loadAppSettings();
});

// Export settings for use in other modules
window.getAppSettings = () => appSettings;

// ============================================================================
// MANIM COLOR PICKER
// ============================================================================

/** Complete Manim color palette grouped by hue family. */
const MANIM_COLORS = {
    'Blue': [
        ['BLUE_A','#C7E9F1'],['BLUE_B','#9CDCEB'],['BLUE_C','#58C4DD'],['BLUE_D','#29ABCA'],['BLUE_E','#236B8E'],['BLUE','#58C4DD'],['DARK_BLUE','#236B8E'],['PURE_BLUE','#0000FF'],
    ],
    'Teal / Green': [
        ['TEAL_A','#ACEAD7'],['TEAL_B','#76DDC0'],['TEAL_C','#5CD0B3'],['TEAL_D','#55C1A7'],['TEAL_E','#49A88F'],['TEAL','#5CD0B3'],
        ['GREEN_A','#C9E2AE'],['GREEN_B','#A6CF8C'],['GREEN_C','#83C167'],['GREEN_D','#77B05D'],['GREEN_E','#699C52'],['GREEN','#83C167'],['PURE_GREEN','#00FF00'],
    ],
    'Yellow / Gold': [
        ['YELLOW_A','#FFF1B6'],['YELLOW_B','#FFEA94'],['YELLOW_C','#FFFF00'],['YELLOW_D','#F4D345'],['YELLOW_E','#E8C11C'],['YELLOW','#FFFF00'],
        ['GOLD_A','#F7C797'],['GOLD_B','#F9B775'],['GOLD_C','#F0AC5F'],['GOLD_D','#E1A158'],['GOLD_E','#C78D46'],['GOLD','#F0AC5F'],
    ],
    'Red / Pink': [
        ['RED_A','#F7A1A3'],['RED_B','#FF8080'],['RED_C','#FC6255'],['RED_D','#E65A4C'],['RED_E','#CF5044'],['RED','#FC6255'],['PURE_RED','#FF0000'],
        ['MAROON_A','#ECABC1'],['MAROON_B','#EC92AB'],['MAROON_C','#C55F73'],['MAROON_D','#A24D61'],['MAROON_E','#94424F'],['MAROON','#C55F73'],
        ['PINK','#D147BD'],['LIGHT_PINK','#DC75CD'],
    ],
    'Purple': [
        ['PURPLE_A','#CAA3E8'],['PURPLE_B','#B189C6'],['PURPLE_C','#9A72AC'],['PURPLE_D','#715582'],['PURPLE_E','#644172'],['PURPLE','#9A72AC'],
    ],
    'Orange': [
        ['ORANGE','#FF862F'],['LIGHT_BROWN','#CD853F'],
    ],
    'Grayscale': [
        ['WHITE','#FFFFFF'],['GRAY_A','#DDDDDD'],['GRAY_B','#BBBBBB'],['GRAY_C','#888888'],['GRAY_D','#444444'],['GRAY_E','#222222'],
        ['GREY_A','#DDDDDD'],['GREY_B','#BBBBBB'],['GREY_C','#888888'],['GREY_D','#444444'],['GREY_E','#222222'],
        ['LIGHTER_GRAY','#DDDDDD'],['LIGHT_GRAY','#BBBBBB'],['LIGHT_GREY','#BBBBBB'],['GRAY','#888888'],['GREY','#888888'],['DARK_GRAY','#444444'],['DARK_GREY','#444444'],['DARKER_GREY','#222222'],
        ['BLACK','#000000'],
    ],
};

let _colorPickerOpen = false;

function toggleColorPicker() {
    const panel = document.getElementById('colorPickerPanel');
    if (!panel) return;
    _colorPickerOpen = !_colorPickerOpen;
    panel.style.display = _colorPickerOpen ? 'flex' : 'none';
    if (_colorPickerOpen) {
        _renderColorGrid();
        document.getElementById('colorSearchInput')?.focus();
    }
}

function _renderColorGrid(filter) {
    const body = document.getElementById('colorPickerBody');
    if (!body) return;
    body.innerHTML = '';
    const lc = (filter || '').toLowerCase();
    let anyMatch = false;

    for (const [group, colors] of Object.entries(MANIM_COLORS)) {
        const matches = colors.filter(([name]) => !lc || name.toLowerCase().includes(lc));
        if (matches.length === 0) continue;
        anyMatch = true;

        const label = document.createElement('div');
        label.className = 'color-group-label';
        label.textContent = group;
        body.appendChild(label);

        const grid = document.createElement('div');
        grid.className = 'color-grid';
        for (const [name, hex] of matches) {
            const sw = document.createElement('div');
            sw.className = 'color-swatch';
            sw.style.background = hex;
            // add a subtle inner border for very light/dark colors
            if (hex === '#FFFFFF' || hex === '#FFFF00' || hex.startsWith('#FFF')) {
                sw.style.borderColor = 'rgba(0,0,0,0.15)';
            } else if (hex === '#000000') {
                sw.style.borderColor = 'rgba(255,255,255,0.15)';
            }
            sw.innerHTML = '<span class="tooltip">' + name + '  ' + hex + '</span>';
            sw.title = name;
            sw.addEventListener('click', () => _insertColorAtCursor(name));
            grid.appendChild(sw);
        }
        body.appendChild(grid);
    }

    if (!anyMatch) {
        body.innerHTML = '<div style="text-align:center;padding:20px;color:var(--text-secondary);">No matching colors</div>';
    }
}

function filterManimColors(query) { _renderColorGrid(query); }

function _insertColorAtCursor(colorName) {
    // Insert the Manim color constant at the current cursor position in the editor
    if (typeof editor !== 'undefined' && editor) {
        const selection = editor.getSelection();
        const range = new monaco.Range(
            selection.startLineNumber, selection.startColumn,
            selection.endLineNumber, selection.endColumn
        );
        editor.executeEdits('color-picker', [{ range, text: colorName }]);
        editor.focus();
        if (typeof toast === 'function') toast('Inserted ' + colorName, 'success', 1500);
    }
}

// Wire up button
document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('colorPickerBtn')?.addEventListener('click', toggleColorPicker);
});

// Close on Escape
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && _colorPickerOpen) toggleColorPicker();
});

// Close when clicking outside
document.addEventListener('mousedown', (e) => {
    if (_colorPickerOpen) {
        const panel = document.getElementById('colorPickerPanel');
        const btn = document.getElementById('colorPickerBtn');
        if (panel && !panel.contains(e.target) && btn && !btn.contains(e.target)) {
            toggleColorPicker();
        }
    }
});

console.log('[APP_FEATURES] Loaded app_features.js successfully');
