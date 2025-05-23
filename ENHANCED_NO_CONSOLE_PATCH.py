# ENHANCED_NO_CONSOLE_PATCH.py
# This ensures all subprocess calls hide console windows
# IMPROVED: Added protection against recursive patching

import subprocess
import sys
import os
import ctypes

# Check if already patched to prevent recursion
if hasattr(subprocess, '_manimstudio_patched'):
    print("Subprocess already patched, skipping additional patching")
else:
    # Import unified process utilities if available
    try:
        from process_utils import run_hidden_process, popen_hidden_process
    except ImportError:
        # Will be defined below
        pass

    # Define the Windows constants here to guarantee they're available
    if sys.platform == "win32":
        # Define this constant if not available
        if not hasattr(subprocess, "CREATE_NO_WINDOW"):
            subprocess.CREATE_NO_WINDOW = 0x08000000
        
        # Other Windows constants
        CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW
        DETACHED_PROCESS = 0x00000008
        SW_HIDE = 0
        STARTF_USESHOWWINDOW = 0x00000001

    # Load Windows API functions for more aggressive console hiding
    if sys.platform == "win32":
        try:
            # Get kernel32 functions for additional window hiding
            try:
                kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
                user32 = ctypes.WinDLL('user32', use_last_error=True)
                
                # Windows API functions
                GetConsoleWindow = kernel32.GetConsoleWindow
                ShowWindow = user32.ShowWindow
                
                # Hide console immediately
                hwnd = GetConsoleWindow()
                if hwnd:
                    ShowWindow(hwnd, SW_HIDE)
            except Exception:
                pass
        except Exception:
            pass

    # Store original functions BEFORE defining any wrappers
    # to prevent recursive calls
    _original_run = subprocess.run
    _original_popen = subprocess.Popen
    _original_call = subprocess.call
    _original_check_output = subprocess.check_output
    _original_check_call = subprocess.check_call

    # Define the unified process utilities if they weren't imported
    if 'run_hidden_process' not in globals():
        def run_hidden_process(command, **kwargs):
            """Run a process with hidden console window"""
            startupinfo = None
            creationflags = 0
            
            if sys.platform == "win32":
                # Set up startupinfo to hide window
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = SW_HIDE
                
                # Set creation flags to hide console
                creationflags = CREATE_NO_WINDOW | DETACHED_PROCESS
                
                # Add to kwargs
                kwargs['startupinfo'] = startupinfo
                kwargs['creationflags'] = kwargs.get('creationflags', 0) | creationflags
                
                # Handle capture_output conflict
                if kwargs.get('capture_output') and ('stdout' in kwargs or 'stderr' in kwargs):
                    kwargs.pop('stdout', None)
                    kwargs.pop('stderr', None)
            
            # Run the process using original run - directly reference the saved original
            return _original_run(command, **kwargs)

        def popen_hidden_process(command, **kwargs):
            """Create a Popen object with hidden console window"""
            startupinfo = None
            creationflags = 0
            
            if sys.platform == "win32":
                # Set up startupinfo to hide window
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = SW_HIDE
                
                # Set creation flags to hide console
                creationflags = CREATE_NO_WINDOW | DETACHED_PROCESS
                
                # Add to kwargs
                kwargs['startupinfo'] = startupinfo
                kwargs['creationflags'] = kwargs.get('creationflags', 0) | creationflags
                
                # Handle stdout/stderr if not specified
                if 'stdout' not in kwargs:
                    kwargs['stdout'] = subprocess.PIPE
                if 'stderr' not in kwargs:
                    kwargs['stderr'] = subprocess.PIPE
            
            # Create the process using original Popen
            return _original_popen(command, **kwargs)

    # Helper functions for the other subprocess functions
    def _no_console_call(*args, **kwargs):
        """call wrapper with enhanced console hiding"""
        return run_hidden_process(*args, **kwargs).returncode

    def _no_console_check_output(*args, **kwargs):
        """check_output wrapper with enhanced console hiding"""
        kwargs['stdout'] = subprocess.PIPE
        kwargs['stderr'] = subprocess.DEVNULL
        result = run_hidden_process(*args, **kwargs)
        if result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode, args[0], result.stdout, result.stderr)
        return result.stdout

    def _no_console_check_call(*args, **kwargs):
        """check_call wrapper with enhanced console hiding"""
        result = run_hidden_process(*args, **kwargs)
        if result.returncode != 0:
            raise subprocess.CalledProcessError(result.returncode, args[0])
        return 0

    # Monkey patch ALL subprocess functions
    subprocess.run = run_hidden_process
    subprocess.Popen = popen_hidden_process
    subprocess.call = _no_console_call
    subprocess.check_output = _no_console_check_output
    subprocess.check_call = _no_console_check_call

    # Patch Python's system function too for good measure
    if hasattr(os, 'system'):
        _original_system = os.system
        
        def _no_console_system(command):
            """system wrapper that hides console"""
            return run_hidden_process(command, shell=True).returncode
        
        os.system = _no_console_system

    # Mark as patched to prevent recursive patching
    subprocess._manimstudio_patched = True
    subprocess._original_run = _original_run  # Store reference to original
    subprocess._original_popen = _original_popen  # Store reference to original

    print("Subprocess patching complete - all console windows will be hidden")

# Export the utility functions so they can be imported
__all__ = ['run_hidden_process', 'popen_hidden_process']
