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




#teszteleshez, majd kesobb fastapi
def main():
    data = load_map(in_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print("Converted to JSON")

if __name__ == "__main__":
    main()
