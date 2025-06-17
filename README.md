Don't add any other .py you can only change the exsisting .py

## Logs
Runtime logs are stored in `~/.manim_studio/manim_studio.log`. Additional
diagnostic logs are created under `~/.manim_studio/logs/`.

## LaTeX Requirement
The application requires a working LaTeX installation. If no LaTeX executable
is detected, the program will warn you at start up. Install a distribution such
as **MiKTeX** or **TeX Live** and ensure `latex` (or `pdflatex`) is available in
your `PATH`.

## Windows Unicode Paths
The packaged version previously crashed when installed under a user directory
containing non‑ASCII characters. Virtual environments and Python paths are now
converted to ASCII‑safe locations automatically, but keeping the installation
under an ASCII path is still recommended.
