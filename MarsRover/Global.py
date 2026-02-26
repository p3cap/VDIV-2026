from pathlib import Path

MARS_ROVER_PATH = Path(__file__).parent

class Vector2():
	def __init__(self, x:int=0, y:int=0):
		self.x = x
		self.y = y

	def _dict(self): # convert to dict
		return {"x":self.x,"y":self.y}

	def __eq__(self, other):
		return self.x == other.x and self.y == other.y

	def __lt__(self, other):
		return (self.x, self.y) < (other.x, other.y)

	def __hash__(self):
		return hash((self.x,self.y))

	def __repr__(self): # for print
		return f"Vector2({self.x},{self.y})"
	
	def to_vector2(self, pos) -> Vector2: # convert list/dict/tuple to vector2
		if isinstance(pos, Vector2):
			return pos
		if isinstance(pos, (tuple, list)) and len(pos) == 2:
			return Vector2(int(pos[0]), int(pos[1]))
		if isinstance(pos, dict) and pos.get("x") and pos.get("y"):
			return Vector2(int(pos["x"]), int(pos["y"]))
		raise TypeError(f"Unsupported type: {type(pos)}")

	def distance_to(self, pos: Vector2):
		return abs(self.x - pos.x) + abs(self.y - pos.y)