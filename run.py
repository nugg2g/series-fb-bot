import os
import sys

# Ensure working directory is always the script directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

if __name__ == "__main__":
    cli_flags = ["--cli", "--login", "--check"]
    if any(arg in sys.argv for arg in cli_flags):
        from cli import main as cli_main
        cli_main()
    else:
        from app_gui import main as gui_main
        gui_main()
