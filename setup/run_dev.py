import sys
import subprocess
import platform
import webbrowser
from pathlib import Path
import questionary
import shlex
import signal
import os

# --- Paths ---
ROOT = Path(__file__).resolve().parent.parent
MARS = ROOT / "MarsRover"
DASH = ROOT / "dashboard"

OS_NAME = platform.system()
PYTHON = shlex.quote(sys.executable)

procs = []


# -------------------------------------------------
# Terminal Launcher (macOS / Linux)
# -------------------------------------------------
def open_terminal(command: str, cwd: Path):
    cwd = str(cwd)
    cwd_q = shlex.quote(cwd)
    cmd_q = command.replace('"', '\\"')

    if OS_NAME == "Darwin":
        # macOS Terminal using login shell (loads env, npm, python paths)
        osa_script = f'''
        tell application "Terminal"
            do script "cd {cwd_q}; {cmd_q}"
            activate
        end tell
        '''
        return subprocess.Popen(
            ["osascript", "-e", osa_script],
            preexec_fn=os.setsid
        )

    else:
        # Linux (gnome-terminal)
        return subprocess.Popen(
            ["gnome-terminal", "--", "bash", "-lc", f"cd {cwd_q}; {command}"],
            preexec_fn=os.setsid
        )


# -------------------------------------------------
# Graceful Cleanup
# -------------------------------------------------
def cleanup():
    print("\nStopping all processes...")

    for p in procs:
        try:
            os.killpg(os.getpgid(p.pid), signal.SIGTERM)
        except Exception:
            pass

    print("All terminated.")


# -------------------------------------------------
# Main
# -------------------------------------------------
def main():
    try:
        # --- Choose Mode ---
        mode = questionary.select(
            "Select mode:",
            choices=["test", "ai", "none"]
        ).ask()

        # --- Rover ---
        if mode == "test":
            procs.append(
                open_terminal(f"{PYTHON} main.py", MARS)
            )
        elif mode == "ai":
            procs.append(
                open_terminal(f"{PYTHON} MachineLearning/live_rover_test.py", MARS)
            )

        # --- Server ---
        procs.append(
            open_terminal(f"{PYTHON} Server/Server.py", ROOT)
        )

        # --- Dashboard ---
        procs.append(
            open_terminal("npm run dev", DASH)
        )

        # --- Open Browser ---
        webbrowser.open("http://localhost:5173/")

        # --- Wait ---
        input("\nPress ENTER to stop all processes...")

    finally:
        cleanup()


if __name__ == "__main__":
    main()