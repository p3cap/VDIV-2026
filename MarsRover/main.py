import argparse
import os
import random
import time
from datetime import datetime

from Global import MARS_ROVER_PATH
from MapClass import Map, matrix_from_csv
from RoverClass import GEARS, STATUS, Rover
from RoverLogger import RoverLogger
from Simulation import Simulation


def ts_print(message: str):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")


def pick_target(map_obj: Map, marker: str):
    poses = map_obj.get_poses_of_tiles([marker])
    if not poses:
        return None
    return random.choice(poses)


def parse_args():
    parser = argparse.ArgumentParser(description="Rover websocket test runner.")
    parser.add_argument("--base-url", type=str, default="http://127.0.0.1:8000")
    parser.add_argument("--steps", type=int, default=0, help="0 means run forever.")
    parser.add_argument("--delta-hrs", type=float, default=0.5)
    parser.add_argument("--tick-seconds", type=float, default=1.0)
    parser.add_argument("--send-every", type=int, default=1, help="Send live every N ticks.")
    parser.add_argument("--target-marker", type=str, default="B")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument(
        "--gear",
        type=str,
        choices=["slow", "normal", "fast"],
        default="slow",
    )
    parser.add_argument("--sim-multiplier", type=float, default=15000.0)
    parser.add_argument(
        "--http-only",
        action="store_true",
        help="Disable websocket and use HTTP fallback only.",
    )
    parser.add_argument(
        "--clear-screen",
        action="store_true",
        help="Clear terminal every frame.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    if args.seed is not None:
        random.seed(args.seed)

    map_obj = Map(
        map_data=matrix_from_csv(str(MARS_ROVER_PATH / "data" / "mars_map_50x50.csv"))
    )

    sim = Simulation(
        map_obj=map_obj,
        sim_time_multiplier=args.sim_multiplier,
        run_hrs=24.0,
        day_hrs=16.0,
        night_hrs=8.0,
    )

    rover = Rover(id="test_rover", sim=sim)
    logger = RoverLogger(args.base_url, use_websocket=not args.http_only)

    gear_map = {
        "slow": GEARS.SLOW,
        "normal": GEARS.NORMAL,
        "fast": GEARS.FAST,
    }
    rover.gear = gear_map[args.gear]

    setup_ok = logger.send_setup(rover.get_setup_data())
    ts_print(f"setup sent: {'ok' if setup_ok else 'failed'}")

    first_target = pick_target(map_obj, args.target_marker)
    if first_target is not None:
        rover.path_find_to(first_target)
    else:
        ts_print(f"no target marker found on map: {args.target_marker}")

    last_time = time.perf_counter()
    step = 0

    try:
        while True:
            step += 1
            delta_real = time.perf_counter() - last_time
            last_time = time.perf_counter()

            sim.update(args.delta_hrs)
            rover.update(args.delta_hrs)

            if rover.status == STATUS.IDLE:
                rover.mine()
                target = pick_target(map_obj, args.target_marker)
                if target is not None:
                    rover.path_find_to(target)

            live_data = rover.get_live_data(args.delta_hrs)
            sent_ok = True
            if step % max(1, args.send_every) == 0:
                sent_ok = logger.send_live(live_data)

            if args.clear_screen:
                os.system("cls" if os.name == "nt" else "clear")

            pos = live_data.get("rover_position", {"x": "?", "y": "?"})
            ts_print(
                f"step={step} real_dt={delta_real:.3f}s pos=({pos.get('x')},{pos.get('y')}) "
                f"status={live_data.get('status')} battery={live_data.get('rover_battery', 0):.2f} "
                f"sent={'ok' if sent_ok else 'failed'}"
            )

            if rover.status == STATUS.DEAD:
                ts_print("rover is dead, stopping test run.")
                break

            if args.steps > 0 and step >= args.steps:
                ts_print("reached requested step count, stopping test run.")
                break

            if args.tick_seconds > 0:
                time.sleep(args.tick_seconds)
    finally:
        logger.close()
        ts_print("logger closed.")


if __name__ == "__main__":
    main()
