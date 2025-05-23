# process_utils.py - Unified helper for subprocess handling with NO CONSOLE
import subprocess
import sys
import os

# Store original references to subprocess functions before they get patched
# This ensures we always have direct access to the original functions
if not hasattr(subprocess, '_original_stored'):
    subprocess._original_run = subprocess.run
    subprocess._original_popen = subprocess.Popen
    subprocess._original_call = subprocess.call
    subprocess._original_check_output = subprocess.check_output
    subprocess._original_check_call = subprocess.check_call
    subprocess._original_stored = True

def run_hidden_process(command, **kwargs):
    """Run a process with hidden console window
    
    This is a unified helper function that properly handles console hiding
    across different platforms. Use this instead of direct subprocess calls.
    """
    # Always use the original functions to prevent recursion
    original_run = subprocess._original_run
    
    # Configure for Windows console hiding
    startupinfo = None
    creationflags = 0
    
    if sys.platform == "win32":
        # For Windows, use both methods for maximum compatibility
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        
        # Add the CREATE_NO_WINDOW flag
        if not hasattr(subprocess, "CREATE_NO_WINDOW"):
            subprocess.CREATE_NO_WINDOW = 0x08000000
        creationflags = subprocess.CREATE_NO_WINDOW
        
        # Add startupinfo and creationflags to kwargs
        kwargs['startupinfo'] = startupinfo
        
        # Merge with existing creationflags if any
        if 'creationflags' in kwargs:
            kwargs['creationflags'] |= creationflags
        else:
            kwargs['creationflags'] = creationflags
    
    # Handle capture_output conflict with stdout/stderr
    if kwargs.get('capture_output') and ('stdout' in kwargs or 'stderr' in kwargs):
        kwargs.pop('stdout', None)
        kwargs.pop('stderr', None)
    
    # Run the process using original run to avoid recursion
    return original_run(command, **kwargs)

def popen_hidden_process(command, **kwargs):
    """Get a Popen object with hidden console window
    
    For longer-running processes when you need to interact with stdout/stderr
    during execution.
    """
    # Always use the original functions to prevent recursion
    original_popen = subprocess._original_popen
    
    # Configure for Windows console hiding
    startupinfo = None
    creationflags = 0
    
    if sys.platform == "win32":
        # For Windows, use both methods for maximum compatibility
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        
        # Add the CREATE_NO_WINDOW flag
        if not hasattr(subprocess, "CREATE_NO_WINDOW"):
            subprocess.CREATE_NO_WINDOW = 0x08000000
        creationflags = subprocess.CREATE_NO_WINDOW
        
        # Add startupinfo and creationflags to kwargs
        kwargs['startupinfo'] = startupinfo
        
        # Merge with existing creationflags if any
        if 'creationflags' in kwargs:
            kwargs['creationflags'] |= creationflags
        else:
            kwargs['creationflags'] = creationflags
    
    # Handle stdout/stderr if not specified
    if kwargs.get('stdout') is None:
        kwargs['stdout'] = subprocess.PIPE
    if kwargs.get('stderr') is None:
        kwargs['stderr'] = subprocess.PIPE
    
    # Create the process using original Popen to avoid recursion
    return original_popen(command, **kwargs)

def call_hidden_process(*args, **kwargs):
    """subprocess.call() with hidden console window"""
    return run_hidden_process(*args, **kwargs).returncode

def check_output_hidden_process(*args, **kwargs):
    """subprocess.check_output() with hidden console window"""
    if 'stdout' not in kwargs:
        kwargs['stdout'] = subprocess.PIPE
    if 'stderr' not in kwargs:
        kwargs['stderr'] = subprocess.DEVNULL
    
    result = run_hidden_process(*args, **kwargs)
    
    if result.returncode != 0:
        cmd = args[0] if args else kwargs.get('args')
        raise subprocess.CalledProcessError(
            result.returncode, cmd, result.stdout, result.stderr)
    
    return result.stdout

def check_call_hidden_process(*args, **kwargs):
    """subprocess.check_call() with hidden console window"""
    result = run_hidden_process(*args, **kwargs)
    
    if result.returncode != 0:
        cmd = args[0] if args else kwargs.get('args')
        raise subprocess.CalledProcessError(result.returncode, cmd)
    
    return 0

# Safe system replacement
def system_hidden_process(command):
    """os.system() replacement with hidden console window"""
    return run_hidden_process(command, shell=True).returncode

# Add direct access to original functions
run_original = subprocess._original_run
popen_original = subprocess._original_popen
call_original = subprocess._original_call
check_output_original = subprocess._original_check_output
check_call_original = subprocess._original_check_call

# Export all functions
__all__ = [
    'run_hidden_process', 
    'popen_hidden_process',
    'call_hidden_process',
    'check_output_hidden_process',
    'check_call_hidden_process',
    'system_hidden_process',
    'run_original',
    'popen_original',
    'call_original',
    'check_output_original',
    'check_call_original'
]
