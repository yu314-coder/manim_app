Don't add any other .py you can only change the exsisting .py

## Logs
Runtime logs are stored in `~/.manim_studio/manim_studio.log`. Additional
diagnostic logs are created under `~/.manim_studio/logs/`.

## LaTeX Requirement
The application requires a working LaTeX installation. If no LaTeX executable
is detected, the program will warn you at start up. Install a distribution such
as **MiKTeX** or **TeX Live** and ensure `latex` (or `pdflatex`) is available in
your `PATH`.

When starting the program it will try to locate `latex` automatically. The
detected path is printed to the console if found. Otherwise a warning dialog is
shown with installation instructions.

### Install LaTeX
1. **MiKTeX** – <https://miktex.org/download>
2. **TeX Live** – <https://www.tug.org/texlive/>

After installation verify that running `latex --version` in a terminal works
before launching the application.
