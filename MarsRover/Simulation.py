from MapClass import Map
from Global import Vector2
from typing import Optional

MIN_RUN_HRS = 24.0

class Simulation:
	def __init__(self, map_obj:Map, run_hrs:float=24.0, sim_time_multiplier:float=1.0, day_hrs:float=16.0, night_hrs:float=8.0):
		self.map_obj = map_obj
		self.run_hrs = run_hrs if run_hrs >= MIN_RUN_HRS else MIN_RUN_HRS
		self.sim_time_multiplier = sim_time_multiplier
		self.day_hrs = day_hrs
		self.night_hrs = night_hrs
		self.is_running = True
		
		self.elapsed_hrs = 0.0
		self.is_day = True

# ---- ML helper ----

	def get_context(self) -> dict:
		"""Compact simulation snapshot for ML state builders."""
		return {
			"elapsed_hrs": float(self.elapsed_hrs),
			"run_hrs": float(self.run_hrs),
			"remaining_hrs": float(self.remaining_hrs()),
			"time_in_cycle": float(self.get_time_in_cycle()),
			"cycle_hrs": float(self.get_cycle_hrs()),
			"is_day": bool(self.is_day),
			"is_running": bool(self.is_running),
			"sim_time_multiplier": float(self.sim_time_multiplier),
			"day_hrs": float(self.day_hrs),
			"night_hrs": float(self.night_hrs),
		}

# --- update ----

	def update(self, delta_hrs:float):
		if not self.is_running: print("Simulation stopped"); return
		self.elapsed_hrs += delta_hrs
		
		self.is_day = self.is_day_at(self.elapsed_hrs)

		self.is_running = self.elapsed_hrs < self.run_hrs

# ----- functions -------

	def reset(self):
		self.elapsed_hrs = 0.0
		self.is_day = True
		self.is_running = True

	def get_cycle_hrs(self) -> float:
		return self.day_hrs + self.night_hrs

	def get_time_in_cycle(self, elapsed_hrs: Optional[float] = None) -> float:
		ref = self.elapsed_hrs if elapsed_hrs is None else elapsed_hrs
		return ref % self.get_cycle_hrs()

	def is_day_at(self, elapsed_hrs: Optional[float] = None) -> bool:
		return self.get_time_in_cycle(elapsed_hrs) < self.day_hrs

	def remaining_hrs(self) -> float:
		return max(0.0, self.run_hrs - self.elapsed_hrs)

	def get_daytime_in_interval(self, start_hrs: float, end_hrs: float) -> float:
		"""Calculate hours of daytime within [start_hrs, end_hrs) interval.
		
		Accounts for day/night cycle boundaries. Both inputs are absolute elapsed hours.
		Returns the total daytime hours within that interval.
		"""
		if start_hrs >= end_hrs:
			return 0.0

		cycle = self.day_hrs + self.night_hrs
		
		# Normalize to cycle phase
		start_phase = start_hrs % cycle
		end_phase = end_hrs % cycle
		
		# Case 1: interval does NOT wrap the cycle boundary
		if end_hrs - start_hrs < cycle and end_phase > start_phase:
			# simple case: no wrap
			daytime = max(0, min(end_phase, self.day_hrs) - min(start_phase, self.day_hrs))
		else:
			# Case 2: interval wraps cycle boundary OR spans >= 1 full cycle
			# Calculate daytime in partial first cycle
			first_part = max(0, self.day_hrs - min(start_phase, self.day_hrs))
			
			# Full cycles in between
			full_cycles = int((end_hrs - start_hrs - first_part) // cycle)
			full_cycle_daytime = full_cycles * self.day_hrs
			
			# Partial last cycle
			remaining = (end_hrs - start_hrs) - first_part - (full_cycles * cycle)
			last_part = min(remaining, self.day_hrs) if remaining > 0 else 0
			
			daytime = first_part + full_cycle_daytime + last_part
		
		return daytime

# ------- Print helper --------

	def __repr__(self):
		line = "=" * 50
		
		cycle = self.day_hrs + self.night_hrs
		time_in_cycle = self.elapsed_hrs % cycle
		
		remaining = max(0.0, self.run_hrs - self.elapsed_hrs)
		phase = "DAY" if self.is_day else "NIGHT"

		return (
			f"\n{line}\n"
			f"SIMULATION\n"
			f"{line}\n"
			f"Elapsed time     : {self.elapsed_hrs:.2f} hrs\n"
			f"Remaining time   : {remaining:.2f} hrs\n"
			f"Total run time   : {self.run_hrs:.2f} hrs\n"
			f"Cycle length     : {cycle:.2f} hrs\n"
			f"Time in cycle    : {time_in_cycle:.2f} hrs\n"
			f"Phase            : {phase}\n"
			f"Day length       : {self.day_hrs:.2f} hrs\n"
			f"Night length     : {self.night_hrs:.2f} hrs\n"
			f"{line}"
		)
