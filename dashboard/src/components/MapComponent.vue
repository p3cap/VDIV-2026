<template>
  <div class="map-wrapper">
    <div class="map" ref="mapElement">
      <div v-for="(row, y) in map.grid" :key="y" class="row">
        <div v-for="(cell, x) in row" :key="x" class="cell" :class="cellClass(cell, x, y)" />
      </div>

      <div ref="roverVisual" class="rover-entity"></div>

      <svg
        class="path-overlay"
        :width="totalWidth"
        :height="totalHeight"
        :viewBox="`0 0 ${totalWidthPx} ${totalHeightPx}`"
      >
        <defs>
          <marker id="endX" markerWidth="5" markerHeight="5" refX="2.5" refY="2.5" orient="auto">
            <path
              d="M1,1 L4,4 M4,1 L1,4"
              stroke="#00ffcc"
              stroke-width="1"
              stroke-linecap="round"
              class="destination"
            />
          </marker>
        </defs>

        <polyline
          v-if="pathPoints.length >= 2"
          :points="svgPoints"
          fill="none"
          stroke="#00ffcc"
          stroke-width="3.2"
          stroke-linecap="round"
          stroke-linejoin="round"
          marker-end="url(#endX)"
          class="path-line"
        />
      </svg>
    </div>
  </div>
</template>
<script>
import { computed, ref, watch, onMounted } from 'vue'
import { animate } from 'animejs'
import marsMap from '@/data/marsMap.json'

export default {
  name: 'MapComponent',
  props: {
    roverPosition: { type: Object, default: () => ({ x: 0, y: 0 }) },
    pathPlan: { type: Array, default: () => [] },
  },

  setup(props) {
    const CELL_SIZE = 22
    const PADDING = 10
    const roverVisual = ref(null)

    // Referencia az aktuálisan futó animációnak, hogy megállíthassuk
    let activeAnimation = null

    // Koordináta -> Pixel konverzió (biztonsági mentéssel, ha a koordináta undefined)
    const getPixelPos = (coords) => {
      return {
        x: (coords?.x ?? 0) * CELL_SIZE + PADDING,
        y: (coords?.y ?? 0) * CELL_SIZE + PADDING,
      }
    }

    /**
     * Mozgatásért felelős függvény
     * @param {Object} newPos - Az új koordináták {x, y}
     * @param {Boolean} instant - Ha igaz, animáció nélkül ugrik a helyére
     */
    const moveRover = (newPos, instant = false) => {
      if (!roverVisual.value || !newPos) return

      const targetPixels = getPixelPos(newPos)

      // Ha már fut egy animáció, azt megállítjuk, hogy ne legyen rángatózás
      if (activeAnimation) activeAnimation.pause()

      activeAnimation = animate(roverVisual.value, {
        translateX: targetPixels.x,
        translateY: targetPixels.y,
        duration: instant ? 0 : 700,
        easing: 'easeInOutQuad',
      })
    }

    // Figyeljük a roverPosition prop-ot
    watch(
      () => props.roverPosition,
      (newVal, oldVal) => {
        if (!newVal) return

        // Csak akkor indítunk új animációt, ha tényleg változott a koordináta
        const hasChanged = !oldVal || newVal.x !== oldVal.x || newVal.y !== oldVal.y

        if (hasChanged) {
          moveRover(newVal)
        }
      },
      { deep: true },
    )

    // Amikor a komponens megjelenik (vagy a Map JSON betöltődik)
    onMounted(() => {
      if (props.roverPosition) {
        // Azonnali ugrás a kezdőpozícióra (0ms alatt), így nincs 0,0-ról indulás
        moveRover(props.roverPosition, true)
      }
    })

    // --- Számítások az SVG útvonalhoz és a rácshoz ---
    const currentPosition = computed(() => props.roverPosition)

    const plannedPath = computed(() => {
      const path = []
      let pos = { ...currentPosition.value }
      for (const step of props.pathPlan) {
        pos = { x: pos.x + step.x, y: pos.y + step.y }
        path.push({ ...pos })
      }
      return path
    })

    const pathPoints = computed(() => [currentPosition.value, ...plannedPath.value])

    const rowCount = computed(() => marsMap.grid.length)
    const colCount = computed(() => marsMap.grid[0]?.length ?? 0)

    const totalWidthPx = computed(() => colCount.value * CELL_SIZE + PADDING * 2)
    const totalHeightPx = computed(() => rowCount.value * CELL_SIZE + PADDING * 2)

    const svgPoints = computed(() => {
      return pathPoints.value
        .map((p) => {
          const cx = p.x * CELL_SIZE + CELL_SIZE / 2 + PADDING
          const cy = p.y * CELL_SIZE + CELL_SIZE / 2 + PADDING
          return `${cx},${cy}`
        })
        .join(' ')
    })

    function cellClass(cell, x, y) {
      switch (cell) {
        case '.':
          return 'ground'
        case '#':
          return 'rock'
        case 'B':
          return 'blue'
        case 'Y':
          return 'yellow'
        case 'G':
          return 'green'
        case 'S':
          return 'start'
        default:
          return 'unknown'
      }
    }

    return {
      map: marsMap,
      cellClass,
      pathPoints,
      svgPoints,
      totalWidth: computed(() => `${totalWidthPx.value}px`),
      totalHeight: computed(() => `${totalHeightPx.value}px`),
      totalWidthPx,
      totalHeightPx,
      roverVisual,
    }
  },
}
</script>

<style scoped>
.map-wrapper {
  position: relative;
  display: inline-block;
  padding: 20px;
  background: #1a1a1a;
  border-radius: 20px;
}

.map {
  padding: 10px;
  background: #3d2b1f;
  border-radius: 8px;
  position: relative;
  box-shadow:
    inset 0 0 20px rgba(0, 0, 0, 0.5),
    0 10px 30px rgba(0, 0, 0, 0.8);
  border: 4px solid #2a1d15;
  line-height: 0;
}

.row {
  display: flex;
}

.cell {
  width: 20px;
  height: 20px;
  margin: 1px;
  box-sizing: border-box;
  border-radius: 3px;
  transition: all 0.3s ease;
}

.ground {
  background-color: #bc6124;
  background-image: radial-gradient(#cc7539 10%, transparent 20%);
  background-size: 4px 4px;
}

.rock {
  background: #4a4a4a;
  box-shadow: inset -3px -3px 0px #2a2a2a;
  border-radius: 5px;
  position: relative;
}
.rock::after {
  content: '';
  position: absolute;
  top: 4px;
  left: 4px;
  width: 4px;
  height: 4px;
  background: #666;
  border-radius: 50%;
}

.blue {
  background: #4cc9f0;
  box-shadow:
    0 0 8px #4cc9f0,
    inset -3px -3px 0 white;
  border-radius: 5px;
  position: relative;
}
.blue::after {
  content: '';
  position: absolute;
  top: 4px;
  left: 4px;
  width: 4px;
  height: 4px;
  background: rgb(165, 165, 255);
  border-radius: 50%;
}

.yellow {
  background: #ffd700;
  box-shadow:
    0 0 10px #ffd700,
    inset -3px -3px 0 white;
  border-radius: 5px;
  position: relative;
}

.green {
  background: #2ecc71;
  box-shadow:
    0 0 8px #2ecc71,
    inset -3px -3px 0 white;
  border-radius: 5px;
  position: relative;
}

.start {
  background: #333;
  border: 2px dashed #00ffcc;
  display: flex;
  align-items: center;
  justify-content: center;
}

.rover-entity {
  top: 3px;
  left: 3px;
  position: absolute;
  width: 16px;
  height: 16px;
  background: #ffffff;
  border-radius: 4px;
  box-shadow:
    0 0 15px #fff,
    0 0 5px #e63946;
  z-index: 10;
  pointer-events: none;
  will-change: transform;
}

.rover-entity::after {
  content: '';
  position: absolute;
  width: 6px;
  height: 6px;
  background: #e63946;
  border-radius: 50%;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
}

.path-overlay {
  position: absolute;
  top: 0;
  left: 0;
  pointer-events: none;
  z-index: 5;
}

.path-line {
  filter: drop-shadow(0 0 3px #00ffcc);
  stroke-dasharray: 4;
  animation: dash 20s linear infinite;
}

@keyframes dash {
  to {
    stroke-dashoffset: -100;
  }
}

.destination {
  filter: drop-shadow(0 0 5px #00ffcc);
}
</style>
