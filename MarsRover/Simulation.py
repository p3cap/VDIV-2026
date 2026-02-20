# coord type enum
class Vector2():
	def __init__(self, x: int, y: int):
		self.x = x
		self.y = y
	
	def _dict(self): 
		return {"x":self.x,"y":self.y}

	def __repr__(self):
		return (self.x,self.y)

min_run_hrs = 24.0

class Simulation:
	def __init__(self, run_hrs:float=24.0, day_hrs:float=16.0, night_hrs:float=8.0, time_multiplier:float=120):
		# the time the simulation will be running for
		self.run_hrs = run_hrs if run_hrs < min_run_hrs else min_run_hrs; print(f"Simulation time was set too low! Resetting to minimum simulation time ({min_run_hrs}).")
		self.day_hrs = day_hrs # hours how long day time lasts
		self.night_hrs = night_hrs # hours how long night time lasts
	
	def next_frame():
		pass

# Gives an undersatnding how to evaluate the map, with a few helper functuins
class Map:
	def __init__(self, map_data:list[list[str]], path_marker:str=".", barrier_marker:str="#", rover_marker:str="S", mineral_markers:list[str]=["B","Y","G"]):
		self.map_data = map_data
		self.path_marker = path_marker
		self.barrier_marker = barrier_marker
		self.rover_marker = rover_marker
		self.minerals = mineral_markers
	
	# returns a list of the tiles vector2 coord (if limit = 1, it returns it as a single object)
	def get_poses_of_tile(self, tile_name:str, limit:int=-1):
		found_tile_poses = []
		for row in self.map_data:
			for col in row:
				if col == tile_name:
					found_tile_poses.append(Vector2(col,row))
					if len(found_tile_poses) >= limit and limit >= 0:
						return found_tile_poses if limit > 1 else Vector2(col,row)

		return found_tile_poses

	def get_tile(self, position:Vector2):
		return self.map_data[position.x, position.y]
