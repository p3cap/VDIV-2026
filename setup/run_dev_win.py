import sys, subprocess, platform, webbrowser
from pathlib import Path
import os

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


# --- Start Server ---
procs.append(new_terminal(f"{sys.executable} Server/Server.py", root))

# --- Dashboard ---
procs.append(new_terminal("npm run dev", dash))
webbrowser.open("http://localhost:5173/")


# --- Choose mode ---
mode = input("Select rover algorythm [test, ai, brain, none]")
if mode == "test":
    procs.append(new_terminal(f"{sys.executable} main.py", mars))
elif mode == "ai":
    procs.append(new_terminal(f"{sys.executable} MachineLearning/live_rover_test.py --debug-nn", mars))
elif mode == "brain":
    procs.append(new_terminal(f"{sys.executable} brain.py", mars))


# --- Wait until user stops ---
print("\nPress ENTER to stop all processes...")
try:
    input()
finally:
    print("Stopping all terminals...")
    # Kill child processes
    for p in procs:
        p.terminate()

    print("All terminated.")