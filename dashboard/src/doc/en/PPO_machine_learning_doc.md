# Machine Learning Inputs, outputs

## concept:
Custom PPO-based ([Proximal Policy Optimization](https://spinningup.openai.com/en/latest/algorithms/ppo.html)) rover environment 
built on top of the normal Mars rover simulation with the usage of stable_baselines3 library.

The ML side has 3 main parts:
- `ppo_shared.py`
 - Shared input/output layout, gear conversion, mineral ranking, and reward shaping.
- `PPO_model_trainer.py`
 - PPO training environment and model training entry point.
- `live_rover_test.py`
 - Loads a trained PPO model and runs it live with the real rover simulation + dashboard/server logging.

The policy does not directly move the rover tile-by-tile.
It receives a normalized observation vector, then it chooses:
- the rover gear
- a target x coordinate
- a target y coordinate

The rover environment then translates that output into normal rover actions such as `path_find_to()` or `mine()`.

## Inputs:
All observation values are normalized to the `0.0 - 1.0` range.

- rovers battery
- rovers gear
- simultion run_hrs
- simulations time_left
- simultion time of day
- rover x pos
- rover y pos
- previously mined x pos
- previously mined y pos

- n amounts of closest minerals distance, and position
	- closest mineral n - distance [excludable, pruposing the ai leanrs its astar pathfinding]
	- closest mineral n - x
	- closest mineral n - y

Important shared functions:
- `obs_size(mineral_count)`
 - Returns the flattened input vector size.
- `build_obs(world, mineral_count, prev_mined, mineral_cache, obs_buf=None)`
 - Builds the model input vector from the current rover world state.
- `rank_minerals(world, mineral_count)`
 - Returns the nearest minerals for the observation vector.

## Ouputs
The PPO action space is a continuous `Box` with 3 values.

- set gear
- path find to pos x
- path find to pos y

(mining is autamically handled when rover steps on a mineral)

Important shared functions:
- `snap_gear(value)`
 - Converts the raw policy output to the nearest valid rover gear.

## Training side

### class RoverEnv
Main Gymnasium environment used during PPO training.

- constructor arguments:
 - `run_hrs`: simulation runtime `[float]`
 - `delta_hrs`: fixed simulation step size `[float]`
 - `run_hrs_options`: optional runtime choices per episode `[Sequence[float] | None]`
 - `delta_mode`: simulation stepping mode `[str]`
 - `tick_seconds`: optional wall-time sleep per step `[float]`
 - `env_speed`: real-time speed multiplier `[float]`
 - `map_csv_path`: optional custom map path `[str | None]`

- important variables:
 - `world`: wrapped rover simulation world `[RoverSimulationWorld]`
 - `observation_space`: PPO input space `[spaces.Box]`
 - `action_space`: PPO output space `[spaces.Box]`
 - `OBS_SIZE`: flattened observation size `[int]`
 - `MINERAL_COUNT`: number of mineral slots used by the model `[int]`

- functions:
 - `reset(self, *, seed=None, options=None)`
  - Resets the whole rover world and returns the first observation.
 - `step(self, action)`
  - Applies the PPO action, advances the world by one step, calculates reward, and returns the Gym step tuple.

### class MinuteProgressCallback
Training callback that prints simple progress info while PPO is learning.

### main training functions

- `build_vec_env(...)`
 - Builds one or more training environments for PPO.
- `train_model(...)`
 - Creates or resumes a PPO model, trains it, saves it, and writes the run settings file.
- `main()`
 - Small console entry point for manual training.

## Shared reward / distance logic

- `tile_step_distance(a, b)`
 - Returns tile distance with 8-direction movement.
- `estimate_return_home_hrs(current_pos, start_pos, gear=GEARS.FAST)`
 - Estimates how long it would take to go back to the start.
- `return_focus_window_hrs(current_pos, start_pos, min_window_hrs=5.0)`
 - Returns the time window when the policy should switch into return-home mode.
- `compute_reward(...)`
 - Shared reward shaping used by both training and live inference.

Reward ideas currently included:
- reward for mining
- streak bonus for repeated mining
- penalty for no movement
- penalty for long time without mining
- battery usage penalty
- return-home mode near the end of the episode

## Live inference side

### class LivePolicyEnv
Thin wrapper used when running a trained PPO model live.

- constructor arguments:
 - `run_hrs`: simulation runtime `[float]`
 - `mineral_count`: expected model mineral slot count `[int]`
 - `delta_mode`: simulation stepping mode `[str]`
 - `set_delta_hrs`: fixed simulation step size `[float]`
 - `tick_seconds`: real sleep between steps `[float]`
 - `env_speed`: real-time speed multiplier `[float]`
 - `base_url`: backend base url `[str]`
 - `send_every`: websocket send frequency `[int]`
 - `map_csv_path`: optional custom map path `[str | None]`

- important variables:
 - `world`: wrapped rover simulation world `[RoverSimulationWorld]`
 - `obs_size`: expected input vector size `[int]`
 - `mineral_count`: number of mineral slots used by the loaded model `[int]`

- functions:
 - `obs(self)`
  - Builds the current model input vector.
 - `step(self, action)`
  - Applies one PPO action and advances the live rover world.
 - `reward(self, mined_now, dist_gain, battery_cost, minerals_left, is_dead)`
  - Rebuilds the shared reward value for debug/analysis output.

### live run functions

- `choose_model_base(requested)`
 - Chooses the trained model file to load.
- `infer_mineral_count(model)`
 - Reads the model observation size and infers how many mineral slots it expects.
- `main()`
 - Console entry point for loading a trained PPO model and running it live.
