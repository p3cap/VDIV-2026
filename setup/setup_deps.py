import sys
import subprocess
from pathlib import Path
import platform

GREEN = "\033[92m"
RED = "\033[91m"
CYAN = "\033[96m"
RESET = "\033[0m"

def run(cmd, cwd=None):
    try:
        subprocess.check_call(cmd, shell=True, cwd=cwd)
    except subprocess.CalledProcessError:
        print(f"{RED}Failed: {cmd}{RESET}")
        sys.exit(1)

root = Path(__file__).parent.parent
marsrover = root / "MarsRover"
dashboard = root / "dashboard"
venv = marsrover / "venv"

print(f"{CYAN}Setting up the Mars Rover...{RESET}\n")

if not venv.exists():
    print(f"{CYAN}Creating venv...{RESET}")
    run(f"{sys.executable} -m venv venv", cwd=marsrover)

pip_path = venv / ("Scripts/pip" if platform.system() == "Windows" else "bin/pip")

print(f"{CYAN}Installing Python dependencies...{RESET}")
run(f'"{pip_path}" install -r requirements.txt', cwd=marsrover)
print(f"{GREEN}Rover dependencies installed!{RESET}\n")

# --- Dashboard ---
print(f"{CYAN}Setting up the Dashboard...{RESET}")
run("npm install", cwd=dashboard)
print(f"{GREEN}Dashboard dependencies installed!{RESET}\n")

print(f"{GREEN}Dependency installation succesful!{RESET}")