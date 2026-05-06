/**
 * Responsive Scaling & DPI Detection
 * Automatically adjusts UI scale based on screen resolution and DPI
 */

(function() {
    'use strict';

    console.log('[RESPONSIVE] Initializing responsive scaling system...');

    /**
     * Detect screen properties (force fresh values, no caching)
     */
    function detectScreenProperties() {
        // Force read from live DOM values (no caching)
        const props = {
            width: window.screen.width,
            height: window.screen.height,
            availWidth: window.screen.availWidth,
            availHeight: window.screen.availHeight,
            devicePixelRatio: window.devicePixelRatio || 1,
            innerWidth: window.innerWidth,
            innerHeight: window.innerHeight,
            outerWidth: window.outerWidth,
            outerHeight: window.outerHeight,
            isFullscreen: !!(document.fullscreenElement || document.webkitFullscreenElement ||
                           document.mozFullScreenElement || document.msFullscreenElement)
        };

        console.log('[RESPONSIVE] Screen properties:', props);
        return props;
    }

    /**
     * Calculate optimal scale factor based on actual content area (minus sidebar)
     */
    function calculateScaleFactor(screenProps) {
        // Use actual window dimensions (innerWidth/innerHeight), not screen dimensions
        let { innerWidth, innerHeight, devicePixelRatio, isFullscreen } = screenProps;

        // Account for sidebar width if it's visible
        const sidebar = document.getElementById('controlsSidebar');
        let sidebarWidth = 0;

        if (sidebar && !sidebar.classList.contains('collapsed')) {
            // Check if sidebar is actually visible (not in overlay mode)
            const sidebarStyles = window.getComputedStyle(sidebar);
            const isOverlay = sidebarStyles.position === 'absolute';

            if (!isOverlay) {
                // Sidebar takes up space, subtract it from available width
                sidebarWidth = sidebar.offsetWidth || 240;
                innerWidth = innerWidth - sidebarWidth;
                console.log(`[RESPONSIVE] Sidebar visible (${sidebarWidth}px), adjusting content width to ${innerWidth}px`);
            } else {
                console.log(`[RESPONSIVE] Sidebar is overlay, not adjusting width`);
            }
        }

        console.log(`[RESPONSIVE] Calculating scale for: ${innerWidth}x${innerHeight} (Fullscreen: ${isFullscreen})`);

        // Base calculations on actual content area size
        const isHighDPI = devicePixelRatio >= 2;
        const isUltraHighDPI = devicePixelRatio >= 3;

        let scaleFactor = 1;
        let baseFontSize = 14;

        // Calculate scale based on actual content area width
        // Breakpoints adjusted for content area (after sidebar is subtracted)
        if (innerWidth >= 2320) {
            // Very large content area (2560px window - 240px sidebar)
            scaleFactor = 1.3;
            baseFontSize = 17;
            console.log('[RESPONSIVE] Large content area (≥2320px)');
        } else if (innerWidth >= 1680) {
            // Large content area (1920px window - 240px sidebar)
            scaleFactor = 1.1;
            baseFontSize = 15;
            console.log('[RESPONSIVE] Standard large content area (≥1680px)');
        } else if (innerWidth >= 1360) {
            // Default design size (1600px window - 240px sidebar)
            scaleFactor = 1.0;
            baseFontSize = 14;
            console.log('[RESPONSIVE] Default content area (≥1360px)');
        } else if (innerWidth >= 1040) {
            // Medium content area (1280px window - 240px sidebar)
            scaleFactor = 0.9;
            baseFontSize = 13;
            console.log('[RESPONSIVE] Medium content area (≥1040px)');
        } else {
            // Small content area
            scaleFactor = 0.85;
            baseFontSize = 12;
            console.log('[RESPONSIVE] Small content area (<1040px)');
        }

        // CRITICAL: Calculate height-based scaling properly
        // Formula: scale = available_height / required_height
        // Required heights at 100% scale:
        const headerHeight = 60;      // Header bar
        const statusBarHeight = 30;   // Status bar at bottom
        const editorMinHeight = 350;  // Minimum editor space
        const terminalHeight = 300;   // Terminal default height
        const dividerHeight = 2;      // Horizontal divider

        const totalRequiredHeight = headerHeight + editorMinHeight + terminalHeight + dividerHeight + statusBarHeight;
        const availableHeight = innerHeight;

        // Calculate height scale factor
        let heightScale = availableHeight / totalRequiredHeight;

        // Don't scale UP beyond 1.0 (only scale down if needed)
        if (heightScale > 1.0) {
            heightScale = 1.0;
        }

        // Don't scale down below 0.65 (minimum usable)
        if (heightScale < 0.65) {
            heightScale = 0.65;
        }

        // Apply height scaling
        if (heightScale < 1.0) {
            scaleFactor *= heightScale;
            baseFontSize = Math.round(baseFontSize * heightScale);
            console.log(`[RESPONSIVE] Height scaling applied: ${heightScale.toFixed(3)} (${availableHeight}px available / ${totalRequiredHeight}px required)`);
        } else {
            console.log(`[RESPONSIVE] No height scaling needed (${availableHeight}px >= ${totalRequiredHeight}px required)`);
        }

        // Adjust for high DPI (but less aggressive in windowed mode)
        if (isUltraHighDPI) {
            scaleFactor *= 1.15;
            baseFontSize *= 1.1;
            console.log('[RESPONSIVE] Applying Ultra High DPI scaling (3x)');
        } else if (isHighDPI) {
            scaleFactor *= 1.08;
            baseFontSize *= 1.05;
            console.log('[RESPONSIVE] Applying High DPI scaling (2x)');
        }

        // Also consider height for very narrow or very wide windows
        const aspectRatio = innerWidth / innerHeight;
        if (aspectRatio < 1.2) {
            // Very tall/narrow window
            scaleFactor *= 0.95;
            console.log('[RESPONSIVE] Adjusting for narrow window');
        } else if (aspectRatio > 2.5) {
            // Very wide window
            scaleFactor *= 0.95;
            console.log('[RESPONSIVE] Adjusting for ultra-wide window');
        }

        // Ensure reasonable bounds
        scaleFactor = Math.max(0.7, Math.min(1.5, scaleFactor));
        baseFontSize = Math.max(11, Math.min(20, baseFontSize));

        return { scaleFactor, baseFontSize };
    }

    /**
     * Apply scaling to the document
     */
    function applyScaling(scaleFactor, baseFontSize) {
        const root = document.documentElement;

        // Remove old values first to force recalculation
        root.style.removeProperty('--scale-factor');
        root.style.removeProperty('--base-font-size');

        // Force reflow before setting new values
        document.body.offsetHeight;

        // Set CSS variables with new values
        root.style.setProperty('--scale-factor', scaleFactor.toString());
        root.style.setProperty('--base-font-size', `${baseFontSize}px`);

        console.log(`[RESPONSIVE] ✓ Applied scaling - Factor: ${scaleFactor}, Base Font: ${baseFontSize}px`);

        // Update zoom level display in status bar
        updateZoomDisplay(scaleFactor);

        // Store in session for debugging
        if (window.sessionStorage) {
            sessionStorage.setItem('ui-scale-factor', scaleFactor);
            sessionStorage.setItem('ui-base-font-size', baseFontSize);
        }

        // Force CSS to re-evaluate (important for media queries)
        forceStyleRecalculation();
    }

    /**
     * Force CSS style recalculation (helps with media query updates)
     */
    function forceStyleRecalculation() {
        const root = document.documentElement;
        const currentDisplay = root.style.display;

        // Temporarily change display to force recalc
        root.style.display = 'none';
        root.offsetHeight; // Force reflow
        root.style.display = currentDisplay || '';

        console.log('[RESPONSIVE] Forced style recalculation');
    }

    /**
     * Update zoom level display in status bar
     */
    function updateZoomDisplay(scaleFactor) {
        const zoomLevelElement = document.getElementById('zoomLevel');
        if (zoomLevelElement) {
            const percentage = Math.round(scaleFactor * 100);
            zoomLevelElement.textContent = `${percentage}%`;

            // Color code based on zoom level
            const zoomControl = document.getElementById('zoomControl');
            if (zoomControl) {
                if (percentage < 90) {
                    zoomControl.style.color = '#f59e0b'; // Orange for zoomed out
                } else if (percentage > 110) {
                    zoomControl.style.color = '#3b82f6'; // Blue for zoomed in
                } else {
                    zoomControl.style.color = ''; // Default color
                }
            }
        }
    }

    /**
     * Setup zoom control interactions
     */
    function setupZoomControl() {
        const zoomControl = document.getElementById('zoomControl');
        if (zoomControl) {
            // Click to reset zoom to 100%
            zoomControl.addEventListener('click', () => {
                console.log('[RESPONSIVE] Resetting zoom to auto-detect');
                initializeResponsiveScaling();
            });

            // Right-click to show zoom options
            zoomControl.addEventListener('contextmenu', (e) => {
                e.preventDefault();
                showZoomMenu(e.clientX, e.clientY);
            });
        }

        // Keyboard shortcuts for zoom (Ctrl/Cmd + Plus/Minus/0)
        document.addEventListener('keydown', (e) => {
            const isMac = navigator.platform.toUpperCase().indexOf('MAC') >= 0;
            const modifier = isMac ? e.metaKey : e.ctrlKey;

            if (modifier) {
                const currentScale = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--scale-factor')) || 1;
                const currentFontSize = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--base-font-size')) || 14;

                if (e.key === '+' || e.key === '=') {
                    // Zoom in
                    e.preventDefault();
                    const newScale = Math.min(1.5, currentScale + 0.1);
                    const newFontSize = Math.min(20, currentFontSize + 1);
                    applyScaling(newScale, newFontSize);
                    console.log('[RESPONSIVE] Zoomed in via keyboard');
                } else if (e.key === '-' || e.key === '_') {
                    // Zoom out
                    e.preventDefault();
                    const newScale = Math.max(0.7, currentScale - 0.1);
                    const newFontSize = Math.max(11, currentFontSize - 1);
                    applyScaling(newScale, newFontSize);
                    console.log('[RESPONSIVE] Zoomed out via keyboard');
                } else if (e.key === '0') {
                    // Reset zoom
                    e.preventDefault();
                    initializeResponsiveScaling();
                    console.log('[RESPONSIVE] Reset zoom via keyboard');
                } else if (e.key === 'r' || e.key === 'R') {
                    // Ctrl+R: Force recalculation (useful after fullscreen issues)
                    e.preventDefault();
                    console.log('[RESPONSIVE] ⚡ FORCE RECALCULATION via Ctrl+R');
                    forceCompleteLayoutRecalc();
                    forceStyleRecalculation();
                    initializeResponsiveScaling();
                    forceTerminalResize();
                    setTimeout(() => {
                        forceCompleteLayoutRecalc();
                        initializeResponsiveScaling();
                        forceTerminalResize();
                    }, 200);
                    setTimeout(() => {
                        forceCompleteLayoutRecalc();
                        initializeResponsiveScaling();
                        forceTerminalResize();
                    }, 500);
                }
            }
        });
    }

    /**
     * Show zoom adjustment menu
     */
    function showZoomMenu(x, y) {
        // Remove existing menu if any
        const existingMenu = document.getElementById('zoomContextMenu');
        if (existingMenu) {
            existingMenu.remove();
        }

        // Create menu
        const menu = document.createElement('div');
        menu.id = 'zoomContextMenu';
        menu.style.cssText = `
            position: fixed;
            left: ${x}px;
            top: ${y}px;
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 8px;
            box-shadow: var(--shadow-lg);
            z-index: 10000;
            min-width: 150px;
        `;

        const zoomLevels = [
            { label: '50%', value: 0.5 },
            { label: '75%', value: 0.75 },
            { label: '90%', value: 0.9 },
            { label: '100% (Auto)', value: null },
            { label: '110%', value: 1.1 },
            { label: '125%', value: 1.25 },
            { label: '150%', value: 1.5 },
        ];

        zoomLevels.forEach(({ label, value }) => {
            const item = document.createElement('div');
            item.textContent = label;
            item.style.cssText = `
                padding: 8px 12px;
                cursor: pointer;
                border-radius: 4px;
                color: var(--text-primary);
                font-size: 13px;
                transition: background 0.2s;
            `;
            item.addEventListener('mouseenter', () => {
                item.style.background = 'var(--bg-hover)';
            });
            item.addEventListener('mouseleave', () => {
                item.style.background = '';
            });
            item.addEventListener('click', () => {
                if (value === null) {
                    initializeResponsiveScaling();
                } else {
                    const baseFontSize = 14 * value;
                    applyScaling(value, baseFontSize);
                }
                menu.remove();
            });
            menu.appendChild(item);
        });

        document.body.appendChild(menu);

        // Close menu when clicking elsewhere
        setTimeout(() => {
            document.addEventListener('click', function closeMenu() {
                menu.remove();
                document.removeEventListener('click', closeMenu);
            });
        }, 100);
    }

    /**
     * Initialize responsive scaling
     */
    function initializeResponsiveScaling() {
        try {
            // Detect screen properties
            const screenProps = detectScreenProperties();

            // Calculate optimal scale
            const { scaleFactor, baseFontSize } = calculateScaleFactor(screenProps);

            // Apply scaling
            applyScaling(scaleFactor, baseFontSize);

            // Add scaling info to UI (optional debug info)
            addScalingDebugInfo(screenProps, scaleFactor, baseFontSize);

            console.log('[RESPONSIVE] Responsive scaling initialized successfully');
            return true;
        } catch (error) {
            console.error('[RESPONSIVE] Error initializing responsive scaling:', error);
            return false;
        }
    }

    /**
     * Add debug info to the page (for development/testing)
     */
    function addScalingDebugInfo(screenProps, scaleFactor, baseFontSize) {
        // Calculate content area (accounting for sidebar)
        const sidebar = document.getElementById('controlsSidebar');
        let contentWidth = screenProps.innerWidth;
        let sidebarWidth = 0;

        if (sidebar && !sidebar.classList.contains('collapsed')) {
            const sidebarStyles = window.getComputedStyle(sidebar);
            const isOverlay = sidebarStyles.position === 'absolute';
            if (!isOverlay) {
                sidebarWidth = sidebar.offsetWidth || 240;
                contentWidth = contentWidth - sidebarWidth;
            }
        }

        // Always add debug info (useful for troubleshooting)
        const debugInfo = {
            windowSize: `${screenProps.innerWidth}×${screenProps.innerHeight}`,
            contentArea: `${contentWidth}×${screenProps.innerHeight}`,
            sidebarWidth: `${sidebarWidth}px`,
            screenSize: `${screenProps.width}×${screenProps.height}`,
            dpi: screenProps.devicePixelRatio,
            scale: scaleFactor.toFixed(2),
            fontSize: `${baseFontSize}px`,
            aspectRatio: (contentWidth / screenProps.innerHeight).toFixed(2)
        };

        console.log('[RESPONSIVE] Debug Info:', debugInfo);

        // Store for access from DevTools
        window.__responsiveScaling = debugInfo;
    }

    /**
     * Handle window resize events
     */
    function handleResize() {
        // Debounce resize events (reduced to 100ms for faster response)
        clearTimeout(window.__resizeTimeout);
        window.__resizeTimeout = setTimeout(() => {
            console.log(`[RESPONSIVE] Window resized to: ${window.innerWidth}x${window.innerHeight}`);
            console.log('[RESPONSIVE] Recalculating scaling...');

            // Force fresh recalculation
            initializeResponsiveScaling();

            // Additional recalc after short delay (ensures CSS media queries update)
            setTimeout(() => {
                console.log('[RESPONSIVE] Secondary resize recalculation...');
                initializeResponsiveScaling();
            }, 50);
        }, 100);
    }

    /**
     * Detect zoom level changes (browser zoom)
     */
    function detectZoomChanges() {
        let lastDevicePixelRatio = window.devicePixelRatio;

        setInterval(() => {
            if (window.devicePixelRatio !== lastDevicePixelRatio) {
                console.log('[RESPONSIVE] Zoom level changed, recalculating...');
                lastDevicePixelRatio = window.devicePixelRatio;
                initializeResponsiveScaling();
            }
        }, 500);
    }

    /**
     * Force complete layout recalculation (sidebar + all containers)
     */
    function forceCompleteLayoutRecalc() {
        console.log('[RESPONSIVE] Forcing complete layout recalculation...');

        // Get all key layout elements
        const workspaceContainer = document.querySelector('.workspace-container');
        const workspaceMain = document.querySelector('.workspace-main-content');
        const workspaceTop = document.getElementById('workspaceTop');
        const workspaceBottom = document.getElementById('workspaceBottom');
        const sidebar = document.getElementById('controlsSidebar');
        const terminalContainer = document.getElementById('terminalContainer');

        // Force reflow by toggling display on workspace container
        if (workspaceContainer) {
            const originalDisplay = workspaceContainer.style.display;
            workspaceContainer.style.display = 'none';
            document.body.offsetHeight; // Force reflow
            workspaceContainer.style.display = originalDisplay || '';
            console.log('[RESPONSIVE] Workspace container reflowed');
        }

        // Ensure sidebar is visible on large windows
        if (sidebar && window.innerWidth > 1440) {
            if (sidebar.classList.contains('collapsed')) {
                sidebar.classList.remove('collapsed');
                console.log('[RESPONSIVE] Removed collapsed class from sidebar');
            }
        }

        // Log dimensions for debugging
        setTimeout(() => {
            if (terminalContainer) {
                const rect = terminalContainer.getBoundingClientRect();
                console.log('[RESPONSIVE] Terminal container size:', {
                    width: rect.width,
                    height: rect.height
                });
            }
            if (sidebar) {
                const rect = sidebar.getBoundingClientRect();
                const computed = window.getComputedStyle(sidebar);
                console.log('[RESPONSIVE] Sidebar size:', {
                    width: rect.width,
                    visible: rect.width > 0,
                    position: computed.position
                });
            }
        }, 50);
    }

    /**
     * Force terminal to resize (fixes PTY staying at fullscreen size)
     * Uses multiple resize event dispatches to ensure the ResizeObserver picks up the change
     */
    function forceTerminalResize() {
        console.log('[RESPONSIVE] Triggering terminal resize events...');

        // Don't manually calculate - let the ResizeObserver handle it
        // Just trigger resize events at multiple intervals to ensure it catches the new size

        // Immediate trigger
        window.dispatchEvent(new Event('resize'));

        // Additional triggers at intervals (container needs time to resize)
        setTimeout(() => {
            console.log('[RESPONSIVE] Terminal resize trigger #1');
            window.dispatchEvent(new Event('resize'));
        }, 100);

        setTimeout(() => {
            console.log('[RESPONSIVE] Terminal resize trigger #2');
            window.dispatchEvent(new Event('resize'));
        }, 300);

        setTimeout(() => {
            console.log('[RESPONSIVE] Terminal resize trigger #3 (final)');
            window.dispatchEvent(new Event('resize'));
        }, 600);
    }

    /**
     * Handle fullscreen changes (fix for layout breaking bug)
     * This fixes the issue where UI gets cut off after exiting fullscreen
     * Source: https://developer.mozilla.org/en-US/docs/Web/API/Document/fullscreenchange_event
     */
    function handleFullscreenChange() {
        const isFullscreen = !!(document.fullscreenElement ||
                               document.webkitFullscreenElement ||
                               document.mozFullScreenElement ||
                               document.msFullscreenElement);

        console.log(`[RESPONSIVE] Fullscreen ${isFullscreen ? 'entered' : 'exited'}`);
        console.log(`[RESPONSIVE] Current window size: ${window.innerWidth}x${window.innerHeight}`);

        // Clear any pending resize timeouts to avoid conflicts
        clearTimeout(window.__resizeTimeout);
        clearTimeout(window.__fullscreenRecalcTimeout1);
        clearTimeout(window.__fullscreenRecalcTimeout2);
        clearTimeout(window.__fullscreenRecalcTimeout3);
        clearTimeout(window.__fullscreenRecalcTimeout4);

        // CRITICAL: Multiple recalculations at different intervals
        // Browsers update window dimensions at different times after fullscreen change

        // Immediate recalculation (may have stale dimensions)
        requestAnimationFrame(() => {
            console.log('[RESPONSIVE] Immediate recalculation...');
            window.dispatchEvent(new Event('resize'));
            forceTerminalResize();
        });

        // First delay - 50ms (catch early dimension updates)
        window.__fullscreenRecalcTimeout1 = setTimeout(() => {
            console.log(`[RESPONSIVE] Recalc #1: Window size: ${window.innerWidth}x${window.innerHeight}`);
            forceCompleteLayoutRecalc();
            initializeResponsiveScaling();
            document.body.offsetHeight; // Trigger reflow
        }, 50);

        // Second delay - 200ms (layout should be updating)
        window.__fullscreenRecalcTimeout2 = setTimeout(() => {
            console.log(`[RESPONSIVE] Recalc #2: Window size: ${window.innerWidth}x${window.innerHeight}`);
            forceCompleteLayoutRecalc();
            initializeResponsiveScaling();
            forceTerminalResize(); // First terminal resize attempt
            document.body.offsetHeight; // Trigger reflow
        }, 200);

        // Third delay - 400ms (ensure all browsers have updated)
        window.__fullscreenRecalcTimeout3 = setTimeout(() => {
            console.log(`[RESPONSIVE] Recalc #3: Window size: ${window.innerWidth}x${window.innerHeight}`);
            forceCompleteLayoutRecalc();
            initializeResponsiveScaling();
            forceTerminalResize(); // Second terminal resize attempt

            // Force CSS media queries to re-evaluate
            document.documentElement.style.display = 'none';
            document.documentElement.offsetHeight; // Trigger reflow
            document.documentElement.style.display = '';
        }, 400);

        // Fourth delay - 800ms (final resize to be absolutely sure)
        window.__fullscreenRecalcTimeout4 = setTimeout(() => {
            console.log(`[RESPONSIVE] Recalc #4 (Final): Window size: ${window.innerWidth}x${window.innerHeight}`);
            forceCompleteLayoutRecalc();
            forceTerminalResize(); // Final terminal resize
            console.log('[RESPONSIVE] Layout fully recalculated after fullscreen change');
        }, 800);
    }

    /**
     * Setup fullscreen change listeners
     */
    function setupFullscreenListeners() {
        // Listen to all fullscreen change events (cross-browser)
        // Source: https://developer.mozilla.org/en-US/docs/Web/API/Document/fullscreenchange_event
        document.addEventListener('fullscreenchange', handleFullscreenChange);
        document.addEventListener('webkitfullscreenchange', handleFullscreenChange);
        document.addEventListener('mozfullscreenchange', handleFullscreenChange);
        document.addEventListener('MSFullscreenChange', handleFullscreenChange);

        console.log('[RESPONSIVE] Fullscreen change listeners registered');
    }

    /**
     * Public API for manual adjustments
     */
    window.ResponsiveScaling = {
        reinitialize: initializeResponsiveScaling,
        getScaleFactor: () => parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--scale-factor')),
        setScaleFactor: (factor) => {
            document.documentElement.style.setProperty('--scale-factor', factor);
            console.log(`[RESPONSIVE] Manual scale factor set to: ${factor}`);
        },
        getBaseFontSize: () => getComputedStyle(document.documentElement).getPropertyValue('--base-font-size'),
        setBaseFontSize: (size) => {
            document.documentElement.style.setProperty('--base-font-size', `${size}px`);
            console.log(`[RESPONSIVE] Manual base font size set to: ${size}px`);
        }
    };

    /**
     * Setup sidebar toggle functionality
     */
    function setupSidebarToggle() {
        const sidebar = document.getElementById('controlsSidebar');
        const openBtn = document.getElementById('sidebarOpenBtn');
        const closeBtn = document.getElementById('sidebarCloseBtn');

        if (!sidebar) return;

        // Check if window is small and auto-collapse sidebar
        function checkSidebarVisibility() {
            const shouldCollapse = window.innerWidth <= 1440;

            if (shouldCollapse) {
                sidebar.classList.add('collapsed');
                console.log(`[SIDEBAR] Collapsed (window width: ${window.innerWidth}px <= 1440px)`);
            } else {
                sidebar.classList.remove('collapsed');
                console.log(`[SIDEBAR] Visible (window width: ${window.innerWidth}px > 1440px)`);
            }

            // Debug: Check actual sidebar position and visibility
            const rect = sidebar.getBoundingClientRect();
            const computed = window.getComputedStyle(sidebar);
            console.log(`[SIDEBAR] Position:`, {
                left: rect.left,
                right: rect.right,
                width: rect.width,
                display: computed.display,
                visibility: computed.visibility,
                opacity: computed.opacity,
                transform: computed.transform,
                position: computed.position
            });
        }

        // Initial check
        checkSidebarVisibility();

        // Open sidebar
        if (openBtn) {
            openBtn.addEventListener('click', () => {
                sidebar.classList.remove('collapsed');
                console.log('[RESPONSIVE] Sidebar opened');
            });
        }

        // Close sidebar
        if (closeBtn) {
            closeBtn.addEventListener('click', () => {
                sidebar.classList.add('collapsed');
                console.log('[RESPONSIVE] Sidebar closed');
            });
        }

        // Check on resize
        window.addEventListener('resize', () => {
            clearTimeout(window.__sidebarResizeTimeout);
            window.__sidebarResizeTimeout = setTimeout(checkSidebarVisibility, 150);
        });

        // Close sidebar when clicking outside on small screens
        document.addEventListener('click', (e) => {
            if (window.innerWidth <= 1440 &&
                !sidebar.contains(e.target) &&
                !openBtn.contains(e.target) &&
                !sidebar.classList.contains('collapsed')) {
                sidebar.classList.add('collapsed');
            }
        });
    }

    // Initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            initializeResponsiveScaling();
            setupZoomControl();
            setupSidebarToggle();
            setupFullscreenListeners(); // Fix for fullscreen transition bug
            window.addEventListener('resize', handleResize);
            detectZoomChanges();
        });
    } else {
        // DOM already loaded
        initializeResponsiveScaling();
        setupZoomControl();
        setupSidebarToggle();
        setupFullscreenListeners(); // Fix for fullscreen transition bug
        window.addEventListener('resize', handleResize);
        detectZoomChanges();
    }

})();
