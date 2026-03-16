"""Shared PPO observation/action wiring used by both training and live runs.

Keep all input/output layout, gear snapping, and reward shaping here so
changing the policy interface updates every consumer automatically.
"""
from __future__ import annotations

from typing import Sequence

import sys
from pathlib import Path

import numpy as np

ML_ROOT = Path(__file__).parent
MARS_ROVER_ROOT = ML_ROOT.parent
if str(MARS_ROVER_ROOT) not in sys.path:
    sys.path.append(str(MARS_ROVER_ROOT))

from Global import Vector2
from RoverClass import GEARS

# Observation layout constants
OBS_STATIC_FIELDS = 8  # battery, gear, run_hrs, tod, rx, ry, prev_mined x/y
DEFAULT_MINERAL_COUNT = 10
# Toggle inclusion of distance per mineral (Manhattan placeholder for A*)
USE_MINERAL_DISTANCE = True
PER_MINERAL_FIELDS = 3 if USE_MINERAL_DISTANCE else 2

# Shared gear mapping helpers
GEAR_TO_FLOAT = {GEARS.SLOW: 0.0, GEARS.NORMAL: 0.5, GEARS.FAST: 1.0}
FLOAT_TO_GEAR = {value: gear for gear, value in GEAR_TO_FLOAT.items()}


def obs_size(mineral_count: int = DEFAULT_MINERAL_COUNT) -> int:
    """Return flattened observation size for a given mineral count."""
    return OBS_STATIC_FIELDS + max(0, mineral_count) * PER_MINERAL_FIELDS


def snap_gear(value: float) -> GEARS:
    """Snap a continuous gear value to the nearest discrete gear."""
    snapped = min(FLOAT_TO_GEAR.keys(), key=lambda g: abs(g - float(value)))
    return FLOAT_TO_GEAR[snapped]


def rank_minerals(world, mineral_count: int) -> list[tuple[Vector2, float]]: # TODO revise for distance clearing
    """Return the nearest minerals; distance optional to avoid A* for now."""
    minerals = list(world.minerals())
    if not minerals:
        return []
    rover = world.rover
    rx, ry = rover.pos.x, rover.pos.y
    ranked = sorted(minerals, key=lambda m: abs(m.x - rx) + abs(m.y - ry))
    if USE_MINERAL_DISTANCE:
        return [(m, float(abs(m.x - rx) + abs(m.y - ry))) for m in ranked[:max(0, mineral_count)]]
    return [(m, 0.0) for m in ranked[:max(0, mineral_count)]]


def build_obs(
    world,
    mineral_count: int,
    prev_mined: Vector2 | None,
    mineral_cache: Sequence[tuple[Vector2, float]] | None,
    obs_buf: np.ndarray | None = None,
) -> np.ndarray:
    """Produce the policy observation vector using the shared layout."""
    size = obs_size(mineral_count)
    obs = obs_buf if obs_buf is not None and obs_buf.shape[0] == size else np.zeros(size, dtype=np.float32)
    obs.fill(0.0)

    rover = world.rover
    sim = world.sim
    cycle = sim.day_hrs + sim.night_hrs
    inv_w = world.inv_w
    inv_h = world.inv_h

    obs[0] = rover.battery / rover.MAX_BATTERY_CHARGE
    obs[1] = GEAR_TO_FLOAT[rover.gear]
    obs[2] = min(1.0, world.run_hrs / 240.0)
    obs[3] = (sim.elapsed_hrs % cycle) / cycle if cycle else 0.0
    obs[4] = rover.pos.x * inv_w
    obs[5] = rover.pos.y * inv_h
    px = prev_mined.x if prev_mined is not None else 0
    py = prev_mined.y if prev_mined is not None else 0
    obs[6] = px * inv_w
    obs[7] = py * inv_h

    cache = mineral_cache or []
    max_d = float(world.map_width + world.map_height)
    for i, (pos, dist) in enumerate(cache[:mineral_count]):
        base = OBS_STATIC_FIELDS + i * PER_MINERAL_FIELDS
        if USE_MINERAL_DISTANCE:
            obs[base] = min(1.0, dist / max_d) if max_d > 0 else 0.0
            obs[base + 1] = pos.x * inv_w
            obs[base + 2] = pos.y * inv_h
        else:
            obs[base] = pos.x * inv_w
            obs[base + 1] = pos.y * inv_h

    # copy() prevents accidental mutation by callers
    return obs.copy()


def compute_reward(
    mined_now: int,
    dist_gain: float,
    battery_cost: float,
    minerals_left: int,
    is_dead: bool,
    no_move_streak: int,
    mining_streak: int,
    penalty_base: float = 6.0,
    penalty_streak: float = 2.0,
    penalty_cap: float = 30.0,
) -> tuple[float, int, int]:
    """Shared reward shaping with streak bookkeeping.

    Goals:
    - Strongly reward mining, with a bonus for consecutive mining (streak).
    - Penalize idling (no move + no mine) heavily.
    - Small time penalty to push faster collection.
    """
    reward = -0.1  # time pressure for faster mining

    # Mining reward with streak bonus
    if mined_now > 0:
        mining_streak += 1
        streak_bonus = min(24.0, 4.0 * mining_streak)
        reward += mined_now * (22.0 + streak_bonus)
    else:
        mining_streak = 0
        reward -= 1.2  # no mining this step (keeps pressure to find minerals)

    # Movement/battery shaping (fast but not reckless)
    reward += dist_gain * 0.15
    reward -= battery_cost * 0.03

    # Large idle penalty when neither moving nor mining
    if dist_gain <= 0 and mined_now <= 0:
        no_move_streak += 1
        reward -= min(penalty_cap, penalty_base + penalty_streak * no_move_streak)
    else:
        no_move_streak = 0

    if is_dead:
        reward -= 150.0
    if minerals_left == 0:
        reward += 80.0

    return float(reward), no_move_streak, mining_streak
