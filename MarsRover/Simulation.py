# coord type enum
class Vector2():
	def __init__(self, x:int, y:int):
		self.x = x
		self.y = y
	
	def _dict(self):
		return {"x":self.x,"y":self.y}

	def __repr__(self):
		return f"({self.x},{self.y})"

	def __eq__(self, other):
		return self.x == other.x and self.y == other.y

	def __hash__(self):
		return hash((self.x,self.y))


min_run_hrs = 24.0

class Simulation:
	def __init__(self, run_hrs:float=24.0, day_hrs:float=16.0, night_hrs:float=8.0):
		self.run_hrs = run_hrs if run_hrs >= min_run_hrs else min_run_hrs
		self.day_hrs = day_hrs
		self.night_hrs = night_hrs
		
		self.elapsed_hrs = 0.0
		self.is_day = True

	def next_frame(self, delta_hrs):
		self.elapsed_hrs += delta_hrs
		
		cycle = self.day_hrs + self.night_hrs
		time_in_cycle = self.elapsed_hrs % cycle
		
		self.is_day = time_in_cycle < self.day_hrs
