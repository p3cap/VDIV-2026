import sys
import subprocess
import webbrowser
from pathlib import Path
from urllib.parse import urlparse
import shutil
import math
from typing import Optional

try:
    import questionary
    from questionary import Choice
except:
    print("INSTALL REQUIRED DEPENDEINCIES OR RUN SETUP_DEPS.PY!")
    exit()

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

procs = []

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

def _ask_float(label: str, default: float, min_value: float = 0.0) -> float:
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

def _list_maps():
    if not MAPS_DIR.exists():
        return []
    return sorted(MAPS_DIR.glob("*.csv"))

def _default_map(maps):
    for p in maps:
        if p.name == DEFAULT_MAP_NAME:
            return p
    return maps[0] if maps else None

def _select_map(maps):
    if not maps:
        print("No maps found in Data/CSV_maps. Using default map name.")
        return None

    choices = []
    for p in maps:
        title = p.name
        if p.name == DEFAULT_MAP_NAME:
            title = f"{p.name} (default)"
        choices.append(Choice(title=title, value=p))

    return _require_answer(
        questionary.select("Select map (Data/CSV_maps):", choices=choices).ask(),
        "map",
    )

def _list_models():
    if not TRAINED_DIR.exists():
        return []
    return sorted(TRAINED_DIR.glob("*.zip"))

def _default_model_name(models):
    latest_hint = TRAINED_DIR / "latest_ppo_model.txt"
    if latest_hint.exists():
        try:
            name = latest_hint.read_text(encoding="utf-8").strip()
        except Exception:
            name = ""
        if name.endswith(".zip"):
            name = name[:-4]
        if name:
            return name
    if models:
        return models[-1].stem
    return "rover_ppo_simple"

def _select_model(auto_setup: bool) -> str:
    models = _list_models()
    default_name = _default_model_name(models)
    model_names = [m.stem for m in models]

    if auto_setup:
        return default_name

    choices = []
    if default_name and default_name not in model_names:
        choices.append(Choice(f"{default_name} (default)", default_name))
    for name in model_names:
        title = name
        if name == default_name:
            title = f"{name} (default)"
        choices.append(Choice(title, name))
    choices.append(Choice("Custom...", "__custom__"))

    selected = _require_answer(
        questionary.select("Select AI model:", choices=choices).ask(),
        "model",
    )
    if selected == "__custom__":
        custom = questionary.text("Model name or path:", default=default_name).ask()
        return _require_answer(custom, "model")
    return selected

def _copy_map_to_mars(map_path: Optional[Path]):
    if map_path is None:
        return
    MARS_DATA.mkdir(parents=True, exist_ok=True)
    target = MARS_DATA / DEFAULT_MAP_NAME
    shutil.copy2(map_path, target)

def _open_terminal(command: str, cwd: Path, env: Optional[dict] = None):
    p = subprocess.Popen(
        ["cmd.exe", "/k", command],
        cwd=str(cwd),
        env=env,
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )
    return p

def _cleanup():
    print("\nStopping all terminals...")
    for p in procs:
        try:
            subprocess.run(
                ["taskkill", "/PID", str(p.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        except Exception:
            try:
                p.terminate()
            except Exception:
                pass
    print("All terminated.")

def _build_cmd(args: list[str]) -> str:
    return subprocess.list2cmdline(args)

def _compute_steps(run_hrs: float, delta_mode: str, delta_hrs: float, env_speed: float, tick_seconds: float) -> int:
    if run_hrs <= 0:
        return 0
    if delta_mode == "set_time":
        step_hrs = max(1e-6, float(delta_hrs))
    else:
        step_hrs = max(1e-6, (tick_seconds / 3600.0) * max(1e-6, env_speed))
    return max(1, int(math.ceil(run_hrs / step_hrs)))

def main():
    try:
        setup_mode = _require_answer(
            questionary.select(
                "Setup mode:",
                choices=[
                    Choice("Auto (defaults, skip questions)", "auto"),
                    Choice("Custom (ask everything)", "custom"),
                ],
            ).ask(),
            "setup mode",
        )
        auto_setup = setup_mode == "auto"

        rover_mode = _require_answer(
            questionary.select(
                "Select rover type:",
                choices=[
                    Choice("ai - PPO policy (MachineLearning/live_rover_test.py)", "ai"),
                    Choice("brain - heuristic script (brain.py)", "brain"),
                    Choice("test - simple sim loop (main.py)", "test"),
                    Choice("none - no rover process", "none"),
                ],
            ).ask(),
            "rover type",
        )

        maps = _list_maps()
        map_path = _default_map(maps)

        run_hrs = DEFAULTS["run_hrs"]
        delta_mode = DEFAULTS["delta_mode"]
        delta_hrs = DEFAULTS["delta_hrs"]
        env_speed = DEFAULTS["env_speed"]
        base_url = DEFAULTS["base_url"]
        model_name = None

        if not auto_setup:
            map_path = _select_map(maps)
            run_hrs = _ask_float("Run hours (min 24):", DEFAULTS["run_hrs"], min_value=24.0)
            delta_mode = _require_answer(
                questionary.select(
                    "Simulation type:",
                    choices=[
                        Choice("realtime (delta follows wall clock)", "real_time"),
                        Choice("delta (fixed step size)", "set_time"),
                    ],
                ).ask(),
                "simulation type",
            )
            if delta_mode == "set_time":
                delta_hrs = _ask_float("Fixed delta hours:", DEFAULTS["delta_hrs"], min_value=0.0001)
            env_speed = _ask_float("Simulation speed (env speed multiplier):", DEFAULTS["env_speed"], min_value=0.01)
            raw_url = _require_answer(
                questionary.text("Websocket/server URL:", default=DEFAULTS["base_url"]).ask(),
                "websocket url",
            )
            base_url = _normalize_base_url(raw_url, DEFAULTS["base_url"])

        if rover_mode == "ai":
            model_name = _select_model(auto_setup)

        _copy_map_to_mars(map_path)

        py_cmd = str(sys.executable)
        tick_seconds = 1.0

        # --- Start Server ---
        procs.append(_open_terminal(_build_cmd([py_cmd, "Server/Server.py"]), ROOT))

        # --- Dashboard ---
        procs.append(_open_terminal("npm run dev", DASH))
        webbrowser.open("http://localhost:5173/")

        # --- Rover ---
        map_arg = ["--map-csv", str(map_path)] if map_path is not None else []

        if rover_mode == "test":
            steps = _compute_steps(run_hrs, delta_mode, delta_hrs, env_speed, tick_seconds)
            args = [
                py_cmd,
                "MarsRover/main.py",
                "--delta-mode", delta_mode,
                "--env-speed", str(env_speed),
                "--run-hrs", str(run_hrs),
                "--base-url", base_url,
            ]
            if delta_mode == "set_time":
                args += ["--delta-hrs", str(delta_hrs)]
            args += map_arg
            if steps > 0:
                args += ["--steps", str(steps)]
            procs.append(_open_terminal(_build_cmd(args), ROOT))
        elif rover_mode == "ai":
            args = [
                py_cmd,
                "MarsRover/MachineLearning/live_rover_test.py",
                "--delta-mode", delta_mode,
                "--delta-hrs", str(delta_hrs),
                "--env-speed", str(env_speed),
                "--run-hrs", str(run_hrs),
                "--base-url", base_url,
                "--debug",
            ]
            if model_name:
                args += ["--model", model_name]
            args += map_arg
            procs.append(_open_terminal(_build_cmd(args), ROOT))
        elif rover_mode == "brain":
            args = [
                py_cmd,
                "MarsRover/brain.py",
                "--delta-mode", delta_mode,
                "--delta-hrs", str(delta_hrs),
                "--env-speed", str(env_speed),
                "--run-hrs", str(run_hrs),
                "--base-url", base_url,
            ]
            args += map_arg
            procs.append(_open_terminal(_build_cmd(args), ROOT))

        # --- Wait until user stops ---
        input("\nPress ENTER to stop all processes...")

    finally:
        _cleanup()

if __name__ == "__main__":
    main()