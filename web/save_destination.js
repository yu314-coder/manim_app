/**
 * Modern Save Destination UI
 * Simplified local-only flow
 */

// Track the current file being saved
const saveDestinationState = {
    currentFilePath: null,
    currentFileName: null
};

// Show save destination modal (local-only)
function showSaveDestinationModal(filePath) {
    console.log('[SAVE] showSaveDestinationModal called with:', filePath);

    saveDestinationState.currentFilePath = filePath || null;
    saveDestinationState.currentFileName = filePath ? filePath.split(/[\\/]/).pop() : 'animation.mp4';

    console.log('[SAVE] Current file path:', saveDestinationState.currentFilePath);
    console.log('[SAVE] Current file name:', saveDestinationState.currentFileName);

    const modal = document.getElementById('saveDestinationModal');
    if (modal) {
        modal.style.display = 'flex';
    } else {
        console.error('[SAVE] Modal not found! ID: saveDestinationModal');
    }
}

// Close destination choice modal
function closeSaveDestinationModal() {
    const modal = document.getElementById('saveDestinationModal');
    if (modal) modal.style.display = 'none';
}

// Save to the local computer
async function showComputerSave() {
    console.log('[SAVE] User chose This Computer');
    console.log('[SAVE] File path:', saveDestinationState.currentFilePath);
    console.log('[SAVE] File name:', saveDestinationState.currentFileName);

    closeSaveDestinationModal();

    if (!saveDestinationState.currentFilePath) {
        toast('No rendered file available to save yet', 'warning');
        return;
    }

    try {
        // Use PyWebView file dialog
        console.log('[SAVE] Opening file dialog...');
        const result = await pywebview.api.save_rendered_file_dialog(
            saveDestinationState.currentFileName
        );

        console.log('[SAVE] Dialog result:', result);

        if (result && result.status === 'success' && result.path) {
            console.log('[SAVE] User selected path:', result.path);

            // Copy file to selected location
            toast('📋 Copying file...', 'info');
            const copyResult = await pywebview.api.copy_file(
                saveDestinationState.currentFilePath,
                result.path
            );

            console.log('[SAVE] Copy result:', copyResult);

            if (copyResult && copyResult.status === 'success') {
                toast('✓ File saved successfully!', 'success');
            } else {
                toast('✗ Failed to save file: ' + (copyResult?.message || 'Unknown error'), 'error');
            }
        } else if (result && result.status === 'canceled') {
            console.log('[SAVE] User canceled save dialog');
        } else {
            toast('✗ Failed to open save dialog', 'error');
        }
    } catch (error) {
        console.error('[SAVE] Computer save error:', error);
        toast('✗ Error saving file: ' + error.message, 'error');
    }
}

// Export for use in other scripts
window.showSaveDestinationModal = showSaveDestinationModal;
window.showComputerSave = showComputerSave;

console.log('[SAVE] Local save destination module loaded');
