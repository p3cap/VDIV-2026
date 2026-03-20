import csv
import json
from pathlib import Path

in_path = Path("..\map\mars_map_50x50.csv")
out_path = Path("..\src\data\marsMap.json")

def load_map(csv_path):
    grid = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            grid.append(row)

    return {
        "width": len(grid[0]),
        "height": len(grid),
        "grid": grid
    }

