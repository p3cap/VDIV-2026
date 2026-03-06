import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import torch
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv

MARS_ROVER_ROOT = Path(__file__).resolve().parent.parent
if str(MARS_ROVER_ROOT) not in sys.path:
  sys.path.append(str(MARS_ROVER_ROOT))

from PPO_test import RoverSimpleEnv
from RoverLogger import RoverLogger
from RoverClass import STATUS


def ts_print(message: str):
  print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


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

  return zip_path


def load_model(model_arg: str, device: str = "auto"):
  model_path = resolve_model_path(model_arg)
  resolved_device = "cuda" if device == "auto" and torch.cuda.is_available() else ("cpu" if device == "auto" else device)

  if not model_path.exists() or model_path.stat().st_size <= 0:
    raise FileNotFoundError(f"Model not found or empty: {model_path}")

  if model_path.suffix == ".pt":
    env = DummyVecEnv([lambda: RoverSimpleEnv(mineral_count=1)])
    model = PPO("MlpPolicy", env, verbose=0, device=resolved_device)
    checkpoint = torch.load(model_path, map_location="cpu")
    model.policy.load_state_dict(checkpoint["policy_state_dict"])
    optimizer_state = checkpoint.get("optimizer_state_dict")
    if optimizer_state is not None:
      model.policy.optimizer.load_state_dict(optimizer_state)
    model.num_timesteps = int(checkpoint.get("num_timesteps", 0))
    return model, str(model_path)

  return PPO.load(str(model_path), device=resolved_device), str(model_path)


def run_live_model(
  model_path: str,
  base_url: str,
  steps: int = 0,
  delta_hrs: float = 0.5,
  tick_seconds: float = 1.0,
  send_every: int = 1,
  clear_screen: bool = False,
  assist_stuck_steps: int = 8,
):
  model, resolved_model_path = load_model(model_path)
  env = RoverSimpleEnv(delta_hrs=delta_hrs, mineral_count=1)
  logger = RoverLogger(base_url)
  obs, _ = env.reset()

  setup_ok = logger.send_setup(env.rover.get_setup_data())
  logger.send_live(env.rover.get_live_data(delta_hrs))
  ts_print(f"loaded model: {resolved_model_path}")
  ts_print(f"setup sent: {'ok' if setup_ok else 'failed'}")

  step = 0
  total_reward = 0.0
  last_time = time.perf_counter()
  prev_pos = (env.rover.pos.x, env.rover.pos.y)
  prev_storage = sum(env.rover.storage.values())
  stuck_idle_steps = 0

  try:
    while True:
      step += 1
      delta_real = time.perf_counter() - last_time
      last_time = time.perf_counter()

      model_action, _ = model.predict(obs, deterministic=True)
      model_action = int(model_action)
      action = model_action
      override = ""

      if assist_stuck_steps > 0:
        tile = env.sim.map_obj.get_tile(env.rover.pos)
        if tile in env.sim.map_obj.mineral_markers and env.rover.status == STATUS.IDLE:
          action = 3 + env.mineral_count  # mine action
          override = "mine_here"
        elif stuck_idle_steps >= assist_stuck_steps and env.rover.status == STATUS.IDLE:
          action = 3  # go to nearest ranked mineral
          override = "unstick_goto"

      obs, reward, terminated, truncated, _ = env.step(action)
      total_reward += float(reward)

      cur_pos = (env.rover.pos.x, env.rover.pos.y)
      cur_storage = sum(env.rover.storage.values())
      if env.rover.status == STATUS.IDLE and cur_pos == prev_pos and cur_storage == prev_storage:
        stuck_idle_steps += 1
      else:
        stuck_idle_steps = 0
      prev_pos = cur_pos
      prev_storage = cur_storage

      live_data = env.rover.get_live_data(delta_hrs)
      sent_ok = True
      if step % max(1, send_every) == 0:
        sent_ok = logger.send_live(live_data)

      if clear_screen:
        os.system("cls" if os.name == "nt" else "clear")

      pos = live_data.get("rover_position", {"x": "?", "y": "?"})
      ts_print(
        f"step={step} real_dt={delta_real:.3f}s pos=({pos.get('x')},{pos.get('y')}) "
        f"status={live_data.get('status')} battery={live_data.get('rover_battery', 0):.2f} "
        f"reward={reward:.3f} total_reward={total_reward:.3f} action={action} model_action={model_action} "
        f"stuck_idle={stuck_idle_steps} override={override or '-'} sent={'ok' if sent_ok else 'failed'}"
      )

      if terminated or truncated:
        ts_print("episode finished, stopping run.")
        break

      if steps > 0 and step >= steps:
        ts_print("reached requested step count, stopping run.")
        break

      if tick_seconds > 0:
        time.sleep(tick_seconds)
  finally:
    logger.close()
    env.close()
    ts_print("logger closed.")


def main():
  parser = argparse.ArgumentParser(description="Run trained PPO rover model with server live logging.")
  parser.add_argument(
    "--model",
    type=str,
    default=str(MARS_ROVER_ROOT / "MachineLearning" / "trained" / "tes6"),
    help="Path to trained model base path, .zip, or .pt.",
  )
  parser.add_argument("--base-url", type=str, default="http://127.0.0.1:8000")
  parser.add_argument("--steps", type=int, default=0, help="0 means run until episode ends.")
  parser.add_argument("--delta-hrs", type=float, default=0.5)
  parser.add_argument("--tick-seconds", type=float, default=1.0)
  parser.add_argument("--send-every", type=int, default=1, help="Send live every N ticks.")
  parser.add_argument(
    "--assist-stuck-steps",
    type=int,
    default=8,
    help="If >0, force go-to-nearest after this many idle no-progress ticks.",
  )
  parser.add_argument("--clear-screen", action="store_true", help="Clear terminal every frame.")
  args = parser.parse_args()

  run_live_model(
    model_path=args.model,
    base_url=args.base_url,
    steps=args.steps,
    delta_hrs=args.delta_hrs,
    tick_seconds=args.tick_seconds,
    send_every=args.send_every,
    clear_screen=args.clear_screen,
    assist_stuck_steps=args.assist_stuck_steps,
  )


if __name__ == "__main__":
  main()
