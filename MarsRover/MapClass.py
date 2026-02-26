import csv
from typing import Iterable, Optional
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

	def to_vector2(self, pos) -> Vector2:
		"""Normalize tuple/list positions to Vector2."""
		if isinstance(pos, Vector2):
			return pos
		if isinstance(pos, (tuple, list)) and len(pos) == 2:
			return Vector2(int(pos[0]), int(pos[1]))
		raise TypeError(f"Unsupported position type: {type(pos)}")

	def in_bounds(self, pos) -> bool:
		p = self.to_vector2(pos)
		return 0 <= p.x < self.width and 0 <= p.y < self.height

	def get_poses_of_tile(self, tile_name:str, limit:int=-1):
		found = []
		for y in range(self.height):
			for x in range(self.width):
				if self.map_data[y][x] == tile_name:
					found.append(Vector2(x,y))
					if limit > 0 and len(found) >= limit:
						return found[0] if limit == 1 else found
		return found

	def get_tile(self, position):
		p = self.to_vector2(position)
		return self.map_data[p.y][p.x]

	def set_tile(self, position, value:str):
		p = self.to_vector2(position)
		self.map_data[p.y][p.x] = value

	def is_walkable(self, pos) -> bool:
		p = self.to_vector2(pos)
		return self.get_tile(p) != self.barrier_marker

	def is_valid_pos(self, pos) -> bool:
		return self.in_bounds(pos) and self.is_walkable(pos)

	def find_tiles(self, tile_names, limit:int=-1):
		"""Find all coordinates for one marker or a set of markers."""
		markers = {tile_names} if isinstance(tile_names, str) else set(tile_names)
		found = []
		for y in range(self.height):
			for x in range(self.width):
				if self.map_data[y][x] in markers:
					found.append(Vector2(x, y))
					if limit > 0 and len(found) >= limit:
						return found[0] if limit == 1 else found
		return found

	def count_tiles(self, tile_name: str) -> int:
		return len(self.get_poses_of_tile(tile_name))

	def count_minerals(self, markers: Optional[Iterable[str]] = None) -> int:
		markers = list(markers) if markers is not None else self.mineral_markers
		return sum(self.count_tiles(marker) for marker in markers)

	def manhattan_distance(self, a, b) -> int:
		p1 = self.to_vector2(a)
		p2 = self.to_vector2(b)
		return abs(p1.x - p2.x) + abs(p1.y - p2.y)

	def nearest_tile(self, start, tile_name: str) -> Optional[Vector2]:
		origin = self.to_vector2(start)
		candidates = self.get_poses_of_tile(tile_name)
		if not candidates:
			return None
		return min(candidates, key=lambda p: self.manhattan_distance(origin, p))

	def nearest_mineral(self, start, markers: Optional[Iterable[str]] = None):
		"""Return (marker, position, distance) for the closest mineral."""
		origin = self.to_vector2(start)
		markers = list(markers) if markers is not None else self.mineral_markers
		best = None
		for marker in markers:
			pos = self.nearest_tile(origin, marker)
			if pos is None:
				continue
			dist = self.manhattan_distance(origin, pos)
			if best is None or dist < best[2]:
				best = (marker, pos, dist)
		return best
