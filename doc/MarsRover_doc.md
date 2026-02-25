# UNFINISHED
# Mars Rover Documentation

## Concept
Egy külön objectként működő python kód. Külsős rendszerbe beágyazható és egy adott IP-re logokat küld jelnlegi státuszáról.

## Components

class Rover:
- constructor arguments:
 - id: A rover neve/id-ja [str]
 - sim: Simulation object [Simulation]

- var types:
 - STATUS: MINE, IDLE, MOVE, DEAD
	- Automatikus kezelt, nem kell változtatni, a state mechine (rover státuszához kell)
 - GEARS: SLOW (2blocks/hrs), NORMAL (4blocks/hrs), FAST (6block/hrs)


- varibles:
 - battery: a rover töltöttsége [int]
 - status: a rover state machine status [rover.STATUS]
 - pos: x,y jelenelgi pozicioja [global.Vector2]
 - start_pos: pos, kezdeti másolata [global.Vector2]
 - path: a rover tervezett útvonala [global.Vector2 list]
 - gear: a rover sebesség típusa [rover.GEAR]
 - move_progress: a rover progressje a következő path célponthoz (inkozisztens update-hoz, 0.0->100.0) [float]
 - mine_process_hrs: bányászat progress (inkozisztens update-hoz, 0.0->100.0) [float]
 - storage: dict=> key: érc neve, value: mennyiség [dict{str:int}]
 - distance_travelled: [int]

- functions:
 - movement_cost(self, delta_hrs:float)
  - Adott eltel órák (delat_hrs) alatti MOZGÁS fogyasztás a jelenlegi állapot alapján
 - energy_consumed(self, delta_hrs:float)
  - Adott eltel órák (delat_hrs) alatti fogyasztás a jelenlegi állapot alapján
 - path_find_to(self, goal:global.Vector2)
  - menjen a goal-hoz a rover (automiatikusan megy ha status == STATUS.MOVE, A* pathfiding)
 - update(self, delta_hrs:float)
  - firssiti a rover állapotát (mindenét, meg kell hívni folyamatosan), delta_hrs-> eltelt idő a két update meghívás közt
 - mine()

