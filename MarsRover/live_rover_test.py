import argparse
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import torch
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv

MARS_ROVER_ROOT = Path(__file__).resolve().parent
ML_ROOT = MARS_ROVER_ROOT / "MachineLearning"

if str(MARS_ROVER_ROOT) not in sys.path:
    sys.path.append(str(MARS_ROVER_ROOT))
if str(ML_ROOT) not in sys.path:
    sys.path.append(str(ML_ROOT))

from PPO_test import RoverSimpleEnv
from RoverLogger import RoverLogger


def ts_print(message: str):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


def parse_args():
    parser = argparse.ArgumentParser(description="Run trained PPO model as live rover logger.")
    parser.add_argument(
        "--model",
        type=str,
        default=str(ML_ROOT / "trained" / "rover_ppo_simple"),
        help="Model base path or explicit .zip/.pt path.",
    )
    parser.add_argument("--base-url", type=str, default="http://127.0.0.1:8000")
    parser.add_argument("--steps", type=int, default=0, help="0 means run until episode ends.")
    parser.add_argument("--delta-hrs", type=float, default=0.5)
    parser.add_argument("--tick-seconds", type=float, default=1.0)
    parser.add_argument("--send-every", type=int, default=1, help="Send live every N ticks.")
    parser.add_argument("--run-hrs", type=float, default=24.0)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument(
        "--device",
        type=str,
        default="auto",
        choices=["auto", "cpu", "cuda"],
        help="Torch device for loading .zip model.",
    )
    parser.add_argument(
        "--clear-screen",
        action="store_true",
        help="Clear terminal every frame.",
    )
    return parser.parse_args()


def resolve_model_path(model_arg: str) -> Path:
    model_path = Path(model_arg).expanduser()
    if not model_path.is_absolute():
        model_path = (MARS_ROVER_ROOT / model_path).resolve()

    if model_path.suffix in {".zip", ".pt"}:
        return model_path

    zip_path = model_path.with_suffix(".zip")
    if zip_path.exists() and zip_path.stat().st_size > 0:
        return zip_path

    pt_path = model_path.with_suffix(".pt")
    if pt_path.exists() and pt_path.stat().st_size > 0:
        return pt_path

    # Prefer explicit suffix if nothing usable exists yet.
    return zip_path


def load_trained_model(model_path: Path, run_hrs: float, delta_hrs: float, device: str):
    resolved_device = "cuda" if device == "auto" and torch.cuda.is_available() else ("cpu" if device == "auto" else device)

    if model_path.suffix == ".pt":
        ts_print(f"Loading .pt fallback checkpoint: {model_path}")
        vec_env = DummyVecEnv([lambda: RoverSimpleEnv(run_hrs=run_hrs, delta_hrs=delta_hrs, mineral_count=1)])
        model = PPO("MlpPolicy", vec_env, verbose=0, device=resolved_device)
        checkpoint = torch.load(model_path, map_location="cpu")
        model.policy.load_state_dict(checkpoint["policy_state_dict"])
        optimizer_state = checkpoint.get("optimizer_state_dict")
        if optimizer_state is not None:
            model.policy.optimizer.load_state_dict(optimizer_state)
        model.num_timesteps = int(checkpoint.get("num_timesteps", 0))
        return model

    ts_print(f"Loading PPO zip model: {model_path}")
    return PPO.load(str(model_path), device=resolved_device)


def main():
    args = parse_args()
    if args.seed is not None:
        random.seed(args.seed)
        np.random.seed(args.seed)
        torch.manual_seed(args.seed)

    model_path = resolve_model_path(args.model)
    if not model_path.exists() or model_path.stat().st_size <= 0:
        raise FileNotFoundError(f"Model not found or empty: {model_path}")

    model = load_trained_model(
        model_path=model_path,
        run_hrs=args.run_hrs,
        delta_hrs=args.delta_hrs,
        device=args.device,
    )

    env = RoverSimpleEnv(run_hrs=args.run_hrs, delta_hrs=args.delta_hrs, mineral_count=1)
    obs, _ = env.reset()
    logger = RoverLogger(args.base_url)

    setup_ok = logger.send_setup(env.rover.get_setup_data())
    ts_print(f"setup sent: {'ok' if setup_ok else 'failed'}")

    last_time = time.perf_counter()
    step = 0
    total_reward = 0.0

    try:
        while True:
            step += 1
            delta_real = time.perf_counter() - last_time
            last_time = time.perf_counter()

            action, _ = model.predict(obs, deterministic=True)
            obs, reward, terminated, truncated, _ = env.step(action)
            total_reward += float(reward)

            live_data = env.rover.get_live_data(args.delta_hrs)
            sent_ok = True
            if step % max(1, args.send_every) == 0:
                sent_ok = logger.send_live(live_data)

            if args.clear_screen:
                os.system("cls" if os.name == "nt" else "clear")

            pos = live_data.get("rover_position", {"x": "?", "y": "?"})
            ts_print(
                f"step={step} real_dt={delta_real:.3f}s pos=({pos.get('x')},{pos.get('y')}) "
                f"status={live_data.get('status')} battery={live_data.get('rover_battery', 0):.2f} "
                f"reward={reward:.3f} total_reward={total_reward:.3f} sent={'ok' if sent_ok else 'failed'}"
            )

            if terminated or truncated:
                ts_print("episode finished, stopping live model run.")
                break

            if args.steps > 0 and step >= args.steps:
                ts_print("reached requested step count, stopping live model run.")
                break

            if args.tick_seconds > 0:
                time.sleep(args.tick_seconds)
    finally:
        logger.close()
        env.close()
        ts_print("logger closed.")


if __name__ == "__main__":
    main()
