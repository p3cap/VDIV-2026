import sys
import time
from pathlib import Path

MARS_ROVER_ROOT = Path(__file__).resolve().parent
if str(MARS_ROVER_ROOT) not in sys.path:
    sys.path.append(str(MARS_ROVER_ROOT))

from MapClass import Map, matrix_from_csv
from RoverClass import Rover
from Simulation import Simulation
from RoverLogger import RoverLogger


class RoverSimulationWorld:
    """Creates, resets, and steps the rover simulation world."""

    def __init__(
        self,
        run_hrs: float = 24.0,
        delta_mode: str = "set_time",
        set_delta_hrs: float = 0.5,
        tick_seconds: float = 0.0,
        env_speed: float = 1.0,
        web_logger: bool = False,
        base_url: str = "http://127.0.0.1:8000",
        send_every: int = 1,
    ):
        self.run_hrs = run_hrs
        self.delta_mode = delta_mode
        self.set_delta_hrs = max(0.0, float(set_delta_hrs))
        self.tick_seconds = max(0.0, float(tick_seconds))
        self.env_speed = max(0.0, float(env_speed))
        self.web_logger = bool(web_logger)
        self.send_every = max(1, int(send_every))
        self.websocket_logger = RoverLogger(base_url) if self.web_logger else None
        self._step_count = 0
        self.last_send_ok = None
        self.map_path = MARS_ROVER_ROOT / "data" / "mars_map_50x50.csv"
        self.map_template = matrix_from_csv(str(self.map_path))
        self.map_width = len(self.map_template[0])
        self.map_height = len(self.map_template)
        self.inv_w = 1.0 / max(1, self.map_width - 1)
        self.inv_h = 1.0 / max(1, self.map_height - 1)
        self.max_dist = max(1.0, float(self.map_width * self.map_height))
        self.sim = None
        self.rover = None
        self._last_step_wall = 0.0
        self.reset()

    def reset(self):
        map_obj = Map([row[:] for row in self.map_template])
        self.sim = Simulation(
            map_obj=map_obj,
            run_hrs=self.run_hrs,
            day_hrs=16.0,
            night_hrs=8.0,
            sim_time_multiplier=1.0,
        )
        self.rover = Rover(id="ppo_rover", sim=self.sim)
        self._step_count = 0
        self.last_send_ok = None
        if self.websocket_logger is not None:
            self.last_send_ok = self.websocket_logger.send_setup(self.rover.get_setup_data())
        self._last_step_wall = time.perf_counter()

    def _compute_delta_hrs(self, real_dt_seconds: float) -> float:
        if self.delta_mode == "real_time":
            return max(0.0, (real_dt_seconds / 3600.0) * self.env_speed)
        return self.set_delta_hrs

    def step(self, sleep: bool = False) -> tuple[float, float]:
        if sleep and self.tick_seconds > 0.0:
            time.sleep(self.tick_seconds)

        now = time.perf_counter()
        real_dt_seconds = max(0.0, now - self._last_step_wall)
        self._last_step_wall = now

        delta_hrs = self._compute_delta_hrs(real_dt_seconds)
        self.sim.update(delta_hrs)
        self.rover.update(delta_hrs)
        self._step_count += 1

        if self.websocket_logger is not None and (self._step_count % self.send_every == 0):
            self.last_send_ok = self.websocket_logger.send_live(self.rover.get_live_data(delta_hrs))

        return delta_hrs, real_dt_seconds

    def minerals(self):
        return self.sim.map_obj.get_poses_of_tiles(self.sim.map_obj.mineral_markers)

    def close(self):
        if self.websocket_logger is not None:
            self.websocket_logger.close()
