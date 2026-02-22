<script>
import marsMap from "@/data/marsMap.json";

export default {
  name: "MapComponent",
  props: {
    roverPosition: {
      type: Object,
      required: false, // { x: number, y: number }
      default: null,
    },
  },
  setup(props) {
    function findStartPosition(grid) {
      for (let y = 0; y < grid.length; y += 1) {
        const x = grid[y].indexOf("S");
        if (x !== -1) {
          return { x, y };
        }
      }
      return { x: 0, y: 0 };
    }

    const startPosition = findStartPosition(marsMap.grid);

    function getRoverPosition() {
      return props.roverPosition ?? startPosition;
    }

    function cellClass(cell, x, y) {
      const roverPos = getRoverPosition();
      if (x === roverPos.x && y === roverPos.y) return "rover";

      switch (cell) {
        case ".": return "ground";
        case "#": return "rock";
        case "B": return "blue";
        case "Y": return "yellow";
        case "G": return "green";
        case "S": return "start";
        default: return "unknown";
      }
    }

    return { map: marsMap, cellClass };
  },
};
</script>
<template>
  <div class="map">
    <div v-for="(row, y) in map.grid" :key="y" class="row">
      <div
        v-for="(cell, x) in row"
        :key="x"
        class="cell"
        :class="cellClass(cell, x, y)"
      />
    </div>
  </div>
</template>

<style scoped>
.rover { background: black;}
.map {
    padding: 8px;
    background: brown;
    border-radius: 6px;
}

.row {
    display: flex;
}

.cell {
    width: 14px;
    height: 14px;
    box-sizing: border-box;
    border: 1px solid rgb(0, 0, 0, 0.2);
}


.ground {
    background: orange;
}

.rock {
    background: gray;
}

.blue {
    background: lightblue;
}

.yellow {
    background: gold; /* aranyosabb, mint a sima yellow, de még mindig jól látszik a fekete keret a cellák között*/
}

.green {
    background: green;
}

.start {
    background: white;
}

.unknown {
    background: magenta;
}
</style>
