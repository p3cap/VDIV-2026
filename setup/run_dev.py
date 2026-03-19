import sys
import subprocess
import platform
import webbrowser
from pathlib import Path
from urllib.parse import urlparse
import shutil
import math
import shlex
import signal
import os
from typing import Optional

try:
    import questionary
    from questionary import Choice
except:
    print("INSTALL REQUIRED DEPENDENCIES OR RUN SETUP_DEPS.PY!")
    sys.exit(1)


# -------------------------------------------------
# Paths
# -------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
MARS = ROOT / "MarsRover"
DASH = ROOT / "dashboard"
MAPS_DIR = ROOT / "Data" / "CSV_maps"
MARS_DATA = MARS / "data"
TRAINED_DIR = MARS / "MachineLearning" / "trained"

DEFAULT_MAP_NAME = "mars_map_50x50.csv"

DEFAULTS = {
    "run_hrs": 240.0,
    "delta_mode": "set_time",
    "delta_hrs": 0.5,
    "env_speed": 1000.0,
    "base_url": "http://127.0.0.1:8000",
}

OS_NAME = platform.system()
PYTHON = sys.executable

procs = []


# -------------------------------------------------
# Helpers
# -------------------------------------------------
def _require_answer(value, label):
    if value is None:
        raise SystemExit(f"Aborted: {label}")
    return value


def _float_validator(min_value: float):
    def _validate(text: str):
        try:
            value = float(text)
        except ValueError:
            return "Enter a number."
        if value < min_value:
            return f"Must be >= {min_value}."
        return True
    return _validate


def _ask_float(label, default, min_value=0.0):
    answer = questionary.text(
        label,
        default=str(default),
        validate=_float_validator(min_value),
    ).ask()
    return float(_require_answer(answer, label))


def _normalize_base_url(raw: str, fallback: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return fallback

    parsed = urlparse(raw)
    if not parsed.scheme:
        raw = f"http://{raw}"
        parsed = urlparse(raw)

    scheme = parsed.scheme.lower()
    if scheme in {"ws", "wss"}:
        scheme = "https" if scheme == "wss" else "http"

    host = parsed.netloc or parsed.path
    if not host:
        return fallback

    return f"{scheme}://{host}"


# -------------------------------------------------
# Maps
# -------------------------------------------------
def _list_maps():
    return sorted(MAPS_DIR.glob("*.csv")) if MAPS_DIR.exists() else []


def _default_map(maps):
    for p in maps:
        if p.name == DEFAULT_MAP_NAME:
            return p
    return maps[0] if maps else None


def _select_map(maps):
    if not maps:
        print("No maps found.")
        return None

    choices = []
    for p in maps:
        title = p.name
        if p.name == DEFAULT_MAP_NAME:
            title += " (default)"
        choices.append(Choice(title, p))

    return _require_answer(
        questionary.select("Select map:", choices=choices).ask(),
        "map",
    )


def _copy_map(map_path: Optional[Path]):
    if map_path is None:
        return
    MARS_DATA.mkdir(parents=True, exist_ok=True)
    shutil.copy2(map_path, MARS_DATA / DEFAULT_MAP_NAME)


# -------------------------------------------------
# Models
# -------------------------------------------------
def _list_models():
    return sorted(TRAINED_DIR.glob("*.zip")) if TRAINED_DIR.exists() else []


def _default_model_name(models):
    hint = TRAINED_DIR / "latest_ppo_model.txt"
    if hint.exists():
        try:
            name = hint.read_text().strip()
            return name.replace(".zip", "")
        except:
            pass
    return models[-1].stem if models else "rover_ppo_simple"


def _select_model(auto):
    models = _list_models()
    default = _default_model_name(models)

    if auto:
        return default

    names = [m.stem for m in models]
    choices = [Choice(f"{n}{' (default)' if n==default else ''}", n) for n in names]
    choices.append(Choice("Custom...", "__custom__"))

    selected = questionary.select("Select model:", choices=choices).ask()
    selected = _require_answer(selected, "model")

    if selected == "__custom__":
        return _require_answer(
            questionary.text("Enter model:", default=default).ask(),
            "model",
        )

    return selected


# -------------------------------------------------
# Terminal launcher (CROSS PLATFORM)
# -------------------------------------------------
def _open_terminal(command: str, cwd: Path):
    cwd = str(cwd)
    cwd_q = shlex.quote(cwd)
    cmd_q = command.replace('"', '\\"')

    if OS_NAME == "Windows":
        return subprocess.Popen(
            ["cmd.exe", "/k", command],
            cwd=cwd,
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )

    elif OS_NAME == "Darwin":
        osa = f'''
        tell application "Terminal"
            do script "cd {cwd_q}; {cmd_q}"
            activate
        end tell
        '''
        return subprocess.Popen(["osascript", "-e", osa], preexec_fn=os.setsid)

    else:
        return subprocess.Popen(
            ["gnome-terminal", "--", "bash", "-lc", f"cd {cwd_q}; {command}"],
            preexec_fn=os.setsid,
        )


# -------------------------------------------------
# Cleanup
# -------------------------------------------------
def _cleanup():
    print("\nStopping processes...")
    for p in procs:
        try:
            if OS_NAME == "Windows":
                subprocess.run(
                    ["taskkill", "/PID", str(p.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                os.killpg(os.getpgid(p.pid), signal.SIGTERM)
        except:
            pass
    print("Done.")


# -------------------------------------------------
# Steps
# -------------------------------------------------
def _compute_steps(run_hrs, delta_mode, delta_hrs, env_speed, tick=1.0):
    if run_hrs <= 0:
        return 0
    if delta_mode == "set_time":
        step = max(1e-6, delta_hrs)
    else:
        step = (tick / 3600.0) * max(1e-6, env_speed)
    return max(1, int(math.ceil(run_hrs / step)))


# -------------------------------------------------
# Main
# -------------------------------------------------
def main():
    try:
        mode = questionary.select(
            "Setup mode:",
            choices=["auto", "custom"]
        ).ask()
        auto = mode == "auto"

        rover = questionary.select(
            "Rover type:",
            choices=["ai", "brain", "test", "none"]
        ).ask()

        maps = _list_maps()
        map_path = _default_map(maps)

        run_hrs = DEFAULTS["run_hrs"]
        delta_mode = DEFAULTS["delta_mode"]
        delta_hrs = DEFAULTS["delta_hrs"]
        env_speed = DEFAULTS["env_speed"]
        base_url = DEFAULTS["base_url"]

        if not auto:
            map_path = _select_map(maps)
            run_hrs = _ask_float("Run hours:", run_hrs, 24)
            delta_mode = questionary.select(
                "Simulation type:",
                choices=["real_time", "set_time"]
            ).ask()
            if delta_mode == "set_time":
                delta_hrs = _ask_float("Delta hours:", delta_hrs, 0.0001)
            env_speed = _ask_float("Env speed:", env_speed, 0.01)
            base_url = _normalize_base_url(
                questionary.text("Server URL:", default=base_url).ask(),
                base_url
            )

        model = _select_model(auto) if rover == "ai" else None

        _copy_map(map_path)

        # --- Server
        procs.append(_open_terminal(f"{PYTHON} Server/Server.py", ROOT))

        # --- Dashboard
        procs.append(_open_terminal("npm run dev", DASH))
        webbrowser.open("http://localhost:5173/")

        # --- Rover
        map_arg = f' --map-csv "{map_path}"' if map_path else ""

        if rover == "test":
            steps = _compute_steps(run_hrs, delta_mode, delta_hrs, env_speed)
            cmd = (
                f'{PYTHON} MarsRover/main.py '
                f'--delta-mode {delta_mode} '
                f'--env-speed {env_speed} '
                f'--run-hrs {run_hrs} '
                f'--base-url {base_url} '
                f'--steps {steps}'
                f'{map_arg}'
            )
            procs.append(_open_terminal(cmd, ROOT))

        elif rover == "ai":
            cmd = (
                f'{PYTHON} MarsRover/MachineLearning/live_rover_test.py '
                f'--delta-mode {delta_mode} '
                f'--delta-hrs {delta_hrs} '
                f'--env-speed {env_speed} '
                f'--run-hrs {run_hrs} '
                f'--base-url {base_url} '
                f'--debug '
                f'--model {model}'
                f'{map_arg}'
            )
            procs.append(_open_terminal(cmd, ROOT))

        elif rover == "brain":
            cmd = (
                f'{PYTHON} MarsRover/brain.py '
                f'--delta-mode {delta_mode} '
                f'--delta-hrs {delta_hrs} '
                f'--env-speed {env_speed} '
                f'--run-hrs {run_hrs} '
                f'--base-url {base_url}'
                f'{map_arg}'
            )
            procs.append(_open_terminal(cmd, ROOT))

        input("\nPress ENTER to stop...")

    finally:
        _cleanup()


if __name__ == "__main__":
    main()