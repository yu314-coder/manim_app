Don't add any other .py you can only change the exsisting .py

## Logs
Runtime logs are stored in `~/.manim_studio/manim_studio.log`. Additional
diagnostic logs are created under `~/.manim_studio/logs/`.

## LaTeX Requirement
The application requires a working LaTeX installation. If no LaTeX executable
is detected, the program will warn you at start up. Install a distribution such
as **MiKTeX** or **TeX Live** and ensure `latex` (or `pdflatex`) is available in
your `PATH`.

## Setup
To run the application locally:
1. Create and activate a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements-build.txt
   ```
2. Ensure a working LaTeX installation is available in your `PATH`.
3. Start the app with:
   ```bash
   python app.py
   ```
