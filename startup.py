import os
import sys
import locale


def initialize_encoding():
    """Initialize proper encoding to prevent crashes"""
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    os.environ['PYTHONLEGACYWINDOWSFSENCODING'] = '0'
    try:
        locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
    except Exception:
        try:
            locale.setlocale(locale.LC_ALL, 'C.UTF-8')
        except Exception:
            pass

    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8', errors='ignore')
            sys.stderr.reconfigure(encoding='utf-8', errors='ignore')
        except Exception:
            pass

if __name__ == "__main__":
    initialize_encoding()
