import csv
from Global import Vector2

def matrix_from_csv(csv_path:str):
	with open(csv_path, newline="", encoding="utf-8") as f:
		return [row for row in csv.reader(f)]

class Map:
	def __init__(self, map_data:list[list[str]], path_marker:str=".", barrier_marker:str="#", rover_marker:str="S", mineral_markers:list[str]=["B","Y","G"]):
		self.map_data = map_data
		self.path_marker = path_marker
		self.barrier_marker = barrier_marker
		self.rover_marker = rover_marker
		self.mineral_markers = mineral_markers
		self.width = len(map_data[0])
		self.height = len(map_data)
		self.marker_descriptions = {
				"S": "Rover Start",
				".": "Field",
				"#": "Barrier",
				"Y": "Gold",
				"B": "Ice",
				"G": "Green"
		}

	def get_poses_of_tile(self, tile_name:str, limit:int=-1):
		found = []
		for y in range(self.height):
			for x in range(self.width):
				if self.map_data[y][x] == tile_name:
					found.append(Vector2(x,y))
					if limit > 0 and len(found) >= limit:
						return found[0] if limit == 1 else found
		return found

	def get_tile(self, position:Vector2):
		return self.map_data[position.y][position.x]

	def set_tile(self, position:Vector2, value:str):
		self.map_data[position.y][position.x] = value

	def is_valid_pos(self, pos:Vector2):
		if pos.x < 0 or pos.y < 0:
			return False
		if pos.x >= self.width or pos.y >= self.height:
			return False
		if self.get_tile(pos) == self.barrier_marker:
			return False
		return True