# Mars Rover Documentation

## Concept
The Mars rover module is a small Python simulation package. It contains the rover logic, the map, the time/day-night simulation, and a world wrapper that can step the whole system and optionally send live data to the dashboard/server.

## Main Components

### class Rover
Main controllable rover object.

- constructor arguments:
 - `id`: rover name / id `[str]`
 - `sim`: active simulation object `[Simulation]`
 - `map_csv_path`: optional map path for the pathfinding backend `[str | None]`

- enum types:
 - `STATUS`: `MINE`, `IDLE`, `MOVE`, `DEAD`
  - Current rover state.
 - `GEARS`: `SLOW`, `NORMAL`, `FAST`
  - Movement speed presets.

- important variables:
 - `battery`: current battery charge `[float]`
 - `status`: current rover state `[STATUS]`
 - `pos`: current rover position `[Vector2]`
 - `start_pos`: starting position `[Vector2]`
 - `path`: planned movement steps `[Vector2 list]`
 - `gear`: current speed preset `[GEARS]`
 - `move_progress`: progress toward the next step `[float]`
 - `mine_process_hrs`: remaining mining time `[float]`
 - `storage`: collected minerals by marker `[dict[str, int]]`
 - `distance_travelled`: travelled distance in tiles `[int]`
 - `mined`: list of mined coordinates `[list]`

- functions:
 - `movement_cost(self, delta_hrs: float)`
  - Returns movement energy use for the given time window with the current gear.
 - `energy_consumed(self, delta_hrs: float)`
  - Returns energy use for the given time window based on the current rover state.
 - `energy_produced(self, delta_hrs: float)`
  - Returns battery charge produced during the given time window from daylight.
 - `path_find_to(self, goal: Vector2)`
  - Plans a path to the target position and switches the rover to move state.
 - `mine(self)`
  - Starts mining if the rover is standing on a mineral tile.
 - `mine_finished(self)`
  - Finalizes mining, stores the mineral, and clears the tile.
 - `update(self, delta_hrs: float)`
  - Updates movement, mining, battery, and rover state. This should be called continuously.
 - `get_live_data(self, delta_hrs: float)`
  - Returns the current live rover data in dashboard/server payload format.
 - `get_setup_data(self)`
  - Returns static setup data about the rover and simulation.

### class Map
Grid-based Mars map object.

- constructor arguments:
 - `map_data`: 2D map matrix `[list[list[str]]]`
 - `path_marker`: default walkable tile marker `[str]`
 - `barrier_marker`: blocked tile marker `[str]`
 - `rover_marker`: rover start marker `[str]`
 - `mineral_markers`: mineral tile markers `[list[str]]`

- important variables:
 - `map_data`: full tile matrix `[list[list[str]]]`
 - `width`: map width `[int]`
 - `height`: map height `[int]`
 - `path_marker`: walkable tile marker `[str]`
 - `barrier_marker`: blocked tile marker `[str]`
 - `rover_marker`: rover start marker `[str]`
 - `mineral_markers`: valid mineral markers `[list[str]]`
 - `marker_descriptions`: display labels for the markers `[dict[str, str]]`

- functions:
 - `get_poses_of_tiles(self, tile_names: list[str], limit: int = -1)`
  - Returns positions of the requested tile types.
 - `get_tile(self, position: Vector2)`
  - Returns the tile marker at the given position.
 - `set_tile(self, position: Vector2, value: str)`
  - Replaces the tile marker at the given position.
 - `is_valid_pos(self, pos: Vector2)`
  - Returns whether the position is inside the map and not blocked.

### class Simulation
Time and day-night cycle controller.

- constructor arguments:
 - `map_obj`: active map object `[Map]`
 - `run_hrs`: total runtime in hours `[float]`
 - `sim_time_multiplier`: stored simulation speed multiplier `[float]`
 - `day_hrs`: daylight length `[float]`
 - `night_hrs`: night length `[float]`

- important variables:
 - `map_obj`: active simulation map `[Map]`
 - `run_hrs`: total configured runtime `[float]`
 - `elapsed_hrs`: elapsed simulation time `[float]`
 - `day_hrs`: daylight length `[float]`
 - `night_hrs`: night length `[float]`
 - `is_day`: current day/night flag `[bool]`
 - `is_running`: tells whether the simulation is still active `[bool]`

- functions:
 - `update(self, delta_hrs: float)`
  - Advances the simulation clock and refreshes day/night state.
 - `get_daytime_in_interval(self, start_hrs: float, end_hrs: float)`
  - Returns how much daylight falls inside the given time window.

### class RoverSimulationWorld
High-level wrapper that creates and steps the whole rover world.

- constructor arguments:
 - `run_hrs`: total simulation runtime `[float]`
 - `delta_mode`: time stepping mode, for example fixed or real-time `[str]`
 - `set_delta_hrs`: fixed simulation step size in hours `[float]`
 - `tick_seconds`: optional real sleep time between steps `[float]`
 - `env_speed`: speed multiplier for real-time stepping `[float]`
 - `web_logger`: enable sending data to the server/dashboard `[bool]`
 - `base_url`: server base url `[str]`
 - `send_every`: send live data every N steps `[int]`
 - `map_csv_path`: optional custom map csv path `[str | None]`

- important variables:
 - `sim`: current simulation object `[Simulation]`
 - `rover`: current rover object `[Rover]`
 - `map_path`: resolved map file path `[Path]`
 - `map_template`: loaded base map matrix `[list[list[str]]]`
 - `last_send_ok`: result of the latest logging send attempt `[bool | None]`

- functions:
 - `reset(self)`
  - Recreates the map, simulation, and rover from the stored configuration.
 - `step(self, sleep: bool = False)`
  - Advances the world by one step and optionally sends live rover data.
 - `minerals(self)`
  - Returns all mineral positions currently on the map.
 - `close(self)`
  - Closes the logger connection if logging is enabled.
