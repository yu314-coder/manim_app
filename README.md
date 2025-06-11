Don't add any other .py you can only change the exsisting .py

## Logs
Runtime logs are stored in `~/.manim_studio/manim_studio.log`. Additional
diagnostic logs are created under `~/.manim_studio/logs/`.

## LaTeX Requirement
The application requires a working LaTeX installation. If no LaTeX executable
is detected, the program will warn you at start up. Install a distribution such
as **MiKTeX** or **TeX Live** and ensure `latex` (or `pdflatex`) is available in
your `PATH`.

### Installing LaTeX

If you do not already have a LaTeX distribution installed, follow the
instructions below depending on your operating system:

- **Windows:** Download and install **MiKTeX** from [https://miktex.org](https://miktex.org). After installation open a new command prompt so the `latex` command is available.
- **macOS:** Install **MacTeX** from [https://www.tug.org/mactex/](https://www.tug.org/mactex/).
- **Linux:** Install **TeX Live** using your package manager, for example:
  `sudo apt install texlive-full` on Debian/Ubuntu.

After installation restart the application. The startup check will confirm that
`latex` or `pdflatex` can be executed.
The status bar in the application window will show "LaTeX: Installed" or
"LaTeX: Missing" depending on this check.
