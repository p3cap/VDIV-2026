class Vector2():
	def __init__(self, x:int, y:int):
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
		return f"({self.x},{self.y})"