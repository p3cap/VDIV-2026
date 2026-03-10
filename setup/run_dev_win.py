import sys, subprocess, platform, webbrowser
from pathlib import Path
import questionary
import os
import signal
import time

root = Path(__file__).resolve().parent.parent
mars = root / "MarsRover"
dash = root / "dashboard"
osys = platform.system()

procs = []

def new_terminal(cmd, cwd):
    """Open command in a new terminal window and return Popen handle"""
    if osys == "Windows":
        # start new cmd window and keep it open
        p = subprocess.Popen(f'start cmd /k "{cmd}"', cwd=cwd, shell=True)
    elif osys == "Darwin":
        # macOS Terminal
        osa_cmd = f'tell app "Terminal" to do script "cd {cwd}; {cmd}"'
        p = subprocess.Popen(["osascript", "-e", osa_cmd])
    else:
        # Linux: gnome-terminal
        p = subprocess.Popen(["gnome-terminal", "--", "bash", "-c", f"cd {cwd}; {cmd}; exec bash"])
    return p


# --- Choose mode ---
mode = questionary.select("Select mode:", choices=["test", "ai", "none"]).ask()
if mode == "test":
    procs.append(new_terminal(f"{sys.executable} main.py", mars))
elif mode == "ai":
    procs.append(new_terminal(f"{sys.executable} MachineLearning/live_rover_test.py", mars))

# --- Start Server ---
procs.append(new_terminal(f"{sys.executable} Server/Server.py", root))

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

<<<<<<< HEAD:setup/run_dev.py


    print("All terminated.")

    print("All terminated.")


=======
    print("All terminated.")
>>>>>>> origin/main:setup/run_dev_win.py
