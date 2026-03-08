import sys, subprocess, platform, webbrowser
from pathlib import Path
import questionary
import os
import signal
import shlex

root = Path(__file__).resolve().parent.parent
mars = root / "MarsRover"
dash = root / "dashboard"
osys = platform.system()

procs = []


def get_project_python():
    if osys == "Windows":
        py = mars / "venv" / "Scripts" / "python.exe"
    else:
        py = mars / "venv" / "bin" / "python"
    return py

def new_terminal(cmd, cwd):
    """Open command in a new terminal window and return Popen handle"""
    quoted_cwd = shlex.quote(str(cwd))
    if osys == "Windows":
        # start new cmd window and keep it open
        p = subprocess.Popen(f'start cmd /k "{cmd}"', cwd=cwd, shell=True)
    elif osys == "Darwin":
        # macOS Terminal
        osa_cmd = f'tell app "Terminal" to do script "cd {quoted_cwd}; {cmd}"'
        p = subprocess.Popen(["osascript", "-e", osa_cmd])
    else:
        # Linux: gnome-terminal
        p = subprocess.Popen(["gnome-terminal", "--", "bash", "-c", f"cd {quoted_cwd}; {cmd}; exec bash"])
    return p

project_python = get_project_python()
if not project_python.exists():
    print("Python virtualenv not found.")
    print("Run setup/setup_deps.py first, then start setup/run_dev.py again.")
    sys.exit(1)

python_cmd = shlex.quote(str(project_python))

# --- Choose mode ---
mode = questionary.select("Select mode:", choices=["test", "ai", "none"]).ask()
if mode == "test":
    procs.append(new_terminal(f"{python_cmd} main.py", mars))
elif mode == "ai":
    procs.append(new_terminal(f"{python_cmd} MachineLearning/live_rover_test.py", mars))

# --- Start Server ---
procs.append(new_terminal(f"{python_cmd} Server/Server.py", root))

# --- Dashboard ---
procs.append(new_terminal("npm run dev", dash))
webbrowser.open("http://localhost:5173/")

# --- Wait until user stops ---
print("\nPress ENTER to stop all processes...")
try:
    input()
finally:
    print("Stopping all terminals...")
    # Kill child processes
    for p in procs:
      if osys == "Windows":
          p.terminate()
      else:
          os.killpg(os.getpgid(p.pid), signal.SIGTERM) # TODO NOT TESTED

    print("All terminated.")
