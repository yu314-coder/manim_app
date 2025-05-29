import os
import shlex
import subprocess
from process_utils import popen_original

class Terminals:
    """Lightweight helper for launching subprocesses in a consistent way."""

    @staticmethod
    def popen(command, cwd=None, env=None):
        """Return a Popen object for the given command."""
        if isinstance(command, str):
            args = shlex.split(command, posix=(os.name != 'nt'))
        else:
            args = list(command)
        return popen_original(
            args,
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=cwd,
            env=env,
            universal_newlines=True
        )

__all__ = ["Terminals"]
