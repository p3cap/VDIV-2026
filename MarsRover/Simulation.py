import math

from MapClass import Map
from Global import Vector2

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
		self.is_day = True # TODO make func for calculating elapsed times daynight cycle

	def update(self, delta_hrs:float):
		if not self.is_running: print("Simulation stopped"); return
		self.elapsed_hrs += delta_hrs
		
		cycle = self.day_hrs + self.night_hrs
		time_in_cycle = self.elapsed_hrs % cycle
		
		self.is_day = time_in_cycle < self.day_hrs

		self.is_running = self.elapsed_hrs < self.run_hrs

	def get_daytime_in_interval(self, start_hrs: float, end_hrs: float) -> float:
		"""Calculate hours of daytime within [start_hrs, end_hrs) interval.
		
		Accounts for day/night cycle boundaries. Both inputs are absolute elapsed hours.
		Returns the total daytime hours within that interval.
		"""
		if start_hrs >= end_hrs:
			return 0.0

		cycle = self.day_hrs + self.night_hrs
		daytime = 0.0
		current = start_hrs

		while current < end_hrs:
			cycle_index = math.floor(current / cycle)
			cycle_start = cycle_index * cycle
			cycle_end = cycle_start + cycle
			window_end = min(end_hrs, cycle_end)

			day_start = cycle_start
			day_end = cycle_start + self.day_hrs

			overlap_start = max(current, day_start)
			overlap_end = min(window_end, day_end)
			if overlap_end > overlap_start:
				daytime += overlap_end - overlap_start

			current = window_end

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
