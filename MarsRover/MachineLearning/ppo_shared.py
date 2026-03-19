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
# battery, gear, run_hrs_norm, time_left, tod, rx, ry, prev_mined x/y
OBS_STATIC_FIELDS = 9
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


def tile_step_distance(a: Vector2, b: Vector2) -> int:
    """Tile steps needed with 8-direction movement (Chebyshev distance)."""
    return max(abs(a.x - b.x), abs(a.y - b.y))


def estimate_return_home_hrs(current_pos: Vector2, start_pos: Vector2, gear: GEARS = GEARS.FAST) -> float:
    """Fast estimate of how long returning home would take from the current tile."""
    gear_value = float(gear.value if isinstance(gear, GEARS) else gear)
    return tile_step_distance(current_pos, start_pos) / max(1.0, gear_value)


def return_focus_window_hrs(current_pos: Vector2, start_pos: Vector2, min_window_hrs: float = 5.0) -> float:
    """The return-home phase starts in the last N hours, or earlier if home is farther away."""
    return max(float(min_window_hrs), estimate_return_home_hrs(current_pos, start_pos))

# Inputs
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
    run_hrs = max(1e-6, float(sim.run_hrs))
    obs[2] = min(1.0, run_hrs / 240.0)
    time_left = max(0.0, run_hrs - float(sim.elapsed_hrs))
    obs[3] = min(1.0, time_left / run_hrs)
    obs[4] = (sim.elapsed_hrs % cycle) / cycle if cycle else 0.0
    obs[5] = rover.pos.x * inv_w
    obs[6] = rover.pos.y * inv_h
    px = prev_mined.x if prev_mined is not None else 0
    py = prev_mined.y if prev_mined is not None else 0
    obs[7] = px * inv_w
    obs[8] = py * inv_h

    cache = mineral_cache or []
    max_d = float(world.map_width + world.map_height)
    for i, (pos, dist) in enumerate(cache[:mineral_count]):
        base = OBS_STATIC_FIELDS + i * PER_MINERAL_FIELDS
        if USE_MINERAL_DISTANCE:
            obs[base] = len(rover._plan_path(rover.pos, pos))
            obs[base + 1] = pos.x * inv_w
            obs[base + 2] = pos.y * inv_h
        else:
            obs[base] = pos.x * inv_w
            obs[base + 1] = pos.y * inv_h

    # .copy() prevents accidental mutation by callers
    return obs.copy()


def compute_reward(
    mined_now: int,
    dist_gain: float,
    battery_cost: float,
    minerals_left: int,
    is_dead: bool = False,
    is_mining: bool = False,
    no_move_streak: int = 0,
    mining_streak: int = 0,
    no_mine_streak: int = 0,
    penalty_base: float = 6.0,
    penalty_streak: float = 2.0,
    penalty_cap: float = 30.0,
    travel_since_last_mine: float = 0.0,
    return_focus_active: bool = False,
    home_dist_before: float | None = None,
    home_dist_after: float | None = None,
    time_left_hrs: float | None = None,
    return_window_hrs_value: float = 5.0,
    max_home_dist: float = 1.0,
) -> tuple[float, int, int, int]:
    """Shared reward shaping with streak bookkeeping.

    Goals:
    - Strongly reward mining, with a bonus for consecutive mining (streak)
      and extra value for collecting nearby ores in tight clusters.
    - Penalize idling (no move + no mine) heavily; do not punish active mining ticks.
    - Penalize long gaps without mining even if moving, to keep pressure on ore collection.
    - Switch into a sticky return-home mode near the end where only homeward
      progress matters.
    """
    if return_focus_active:
        before = float(home_dist_before or 0.0)
        after = float(home_dist_after if home_dist_after is not None else before)
        return_window_hrs_value = max(1e-6, float(return_window_hrs_value))
        time_left_hrs = max(0.0, float(time_left_hrs if time_left_hrs is not None else return_window_hrs_value))

        progress = before - after
        urgency = 1.0 + 3.0 * (1.0 - min(1.0, time_left_hrs / return_window_hrs_value))

        reward = 0.0
        reward += progress * 42.0 * urgency
        if progress < 0:
            reward += progress * 24.0 * urgency
        elif after > 0:
            reward -= 4.0 * urgency
        if before > 0 and after <= 0:
            reward += 120.0 * urgency
        if is_dead:
            reward -= 200.0
        return float(reward), 0, 0, 0

    reward = -0.1  # mild time pressure for faster mining

    # Mining reward with streak bonus
    if mined_now > 0:
        mining_streak += 1
        no_mine_streak = 0
        streak_bonus = min(30.0, 5.0 * mining_streak)
        local_bonus = max(0.0, 18.0 - 1.25 * max(0.0, travel_since_last_mine))
        reward += mined_now * (30.0 + streak_bonus + local_bonus)
    else:
        mining_streak = 0
        if not is_mining:
            no_mine_streak += 1
            reward -= min(14.0, 1.75 * no_mine_streak)

    # Travel should still happen, but shorter ore-to-ore routes are better.
    reward -= dist_gain * 0.3
    reward -= battery_cost * 0.05

    # Large idle penalty when neither moving nor mining
    if dist_gain <= 0 and mined_now <= 0 and not is_mining:
        no_move_streak += 1
        reward -= min(penalty_cap, penalty_base + penalty_streak * no_move_streak)
    else:
        no_move_streak = 0

    if is_dead:
        reward -= 150.0
    if minerals_left == 0:
        reward += 80.0

    return float(reward), no_move_streak, mining_streak, no_mine_streak
