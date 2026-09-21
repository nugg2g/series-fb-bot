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
    if len(sys.argv) > 1:
        from cli import main as cli_main
        cli_main()
    else:
        from app_gui import main as gui_main
        gui_main()
