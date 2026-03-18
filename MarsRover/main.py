import argparse
import os
import random
from datetime import datetime

from MapClass import Map
from RoverClass import GEARS, STATUS, Rover
from Simulation_env import RoverSimulationWorld


def pick_target(map_obj: Map, marker: str):
    poses = map_obj.get_poses_of_tiles([marker])
    if not poses:
        return None
    return random.choice(poses)


def parse_args():
    parser = argparse.ArgumentParser(description="Rover simulation runner.")
    parser.add_argument("--steps", type=int, default=0, help="0 means run forever.")
    parser.add_argument(
        "--delta-mode",
        type=str,
        choices=["set_time", "real_time"],
        default="set_time",
    )
    parser.add_argument("--delta-hrs", type=float, default=0.5)
    parser.add_argument("--run-hrs", type=float, default=2400.0)
    parser.add_argument("--tick-seconds", type=float, default=1.0)
    parser.add_argument("--env-speed", type=float, default=1.0)
    parser.add_argument("--base-url", type=str, default="http://127.0.0.1:8000")
    parser.add_argument("--map-csv", type=str, default=None)
    parser.add_argument("--target-marker", type=str, default="B")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument(
        "--gear",
        type=str,
        choices=["slow", "normal", "fast"],
        default="slow",
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

    world = RoverSimulationWorld(
        run_hrs=args.run_hrs,
        delta_mode=args.delta_mode,
        set_delta_hrs=args.delta_hrs,
        tick_seconds=args.tick_seconds,
        env_speed=args.env_speed,
        web_logger=True,
        base_url=args.base_url,
        map_csv_path=args.map_csv,
    )

    rover: Rover = world.rover

    gear_map = {
        "slow": GEARS.SLOW,
        "normal": GEARS.NORMAL,
        "fast": GEARS.FAST,
    }
    rover.gear = gear_map[args.gear]

    first_target = pick_target(world.sim.map_obj, args.target_marker)
    if first_target is not None:
        rover.path_find_to(first_target)
    else:
        print(f"no target marker found on map: {args.target_marker}")

    step = 0

    try:
        while True:
            step += 1
            delta_hrs, delta_real = world.step(sleep=True)

            if rover.status == STATUS.IDLE:
                rover.mine()
                target = pick_target(world.sim.map_obj, args.target_marker)
                if target is not None:
                    rover.path_find_to(target)

            live_data = rover.get_live_data(delta_hrs)
            if args.clear_screen:
                os.system("cls" if os.name == "nt" else "clear")

            pos = live_data.get("rover_position", {"x": "?", "y": "?"})
            print(world.rover)

            if rover.status == STATUS.DEAD:
                print("rover is dead, stopping test run.")
                break

            if args.steps > 0 and step >= args.steps:
                print("reached requested step count, stopping test run.")
                break
    finally:
        world.close()
        print("simulation closed.")


if __name__ == "__main__":
    main()
