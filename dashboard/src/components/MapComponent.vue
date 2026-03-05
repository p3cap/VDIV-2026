<template>
  <div class="map-wrapper">
    <div ref="pixiContainer" class="pixi-container"></div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'
import * as PIXI from 'pixi.js'
import { Viewport } from 'pixi-viewport'
import { Assets } from 'pixi.js'
import surface from '@/assets/textures/tile_1.png'


const props = defineProps({
  roverPosition: { type: Object, default: () => ({ x: 0, y: 0 }) },
  pathPlan: { type: Array, default: () => [] },
  mapMatrix: { type: Array, default: () => [] },
})

const pixiContainer = ref(null)
const initialized = ref(false)
const cellSize = ref(15) // Increased slightly for better visibility


let app = null
let viewport = null
let mapContainer = null
let rover = null
let pathGraphics = null
let textureMap = {}
let cellNodes = []

const texturePaths = {
  '.': surface,
  '#': '/textures/rock.png',
  'B': '/textures/blue-crystal.png',
  'Y': '/textures/yellow-gem.png',
  'G': '/textures/green-plant.png',
  'S': '/textures/sand.png',
}

function getGrid() {
  return Array.isArray(props.mapMatrix) ? props.mapMatrix : []
}

onMounted(async () => {
  if (!pixiContainer.value) return

  const grid = getGrid()
  if (!grid.length || !grid[0]?.length) return

  app = new PIXI.Application()

  await app.init({
    backgroundColor: 0x1e1e2e,
    resizeTo: pixiContainer.value,
    antialias: true,
    resolution: window.devicePixelRatio || 1,
    autoDensity: true,
  })

  pixiContainer.value.appendChild(app.canvas)

  const cols = grid[0].length
  const rows = grid.length
  const worldW = cols * cellSize.value
  const worldH = rows * cellSize.value

  viewport = new Viewport({
    screenWidth: app.screen.width,
    screenHeight: app.screen.height,
    worldWidth: worldW,
    worldHeight: worldH,
    events: app.renderer.events,
  })

  // Better zoom/drag behavior to fill viewport
  viewport
    .drag()
    .wheel()
    .pinch()
    .decelerate()
    .clampZoom({ 
      minScale: 0.2, // Allow zooming out further
      maxScale: 5.0 
    })

  app.stage.addChild(viewport)

  mapContainer = new PIXI.Container()
  viewport.addChild(mapContainer)

  textureMap = await loadTexturesWithFallback()
  drawGrid(grid)

  pathGraphics = new PIXI.Graphics()
  mapContainer.addChild(pathGraphics)

  rover = createRoverGraphics()
  mapContainer.addChild(rover)

  updateRoverPosition(props.roverPosition, true)
  drawPath()

  // Initial Framing
  viewport.fit(true) 
  viewport.moveCenter(worldW / 2, worldH / 2)

  initialized.value = true

  window.addEventListener('resize', forceResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', forceResize)
  if (app) app.destroy(true, { children: true })
})

async function loadTexturesWithFallback() {
  const map = {}
  const loadPromises = Object.entries(texturePaths).map(async ([type, path]) => {
    if (!path) {
      map[type] = null
      return
    }
    try {
      map[type] = await Assets.load(path)
    } catch {
      map[type] = null
    }
  })
  await Promise.allSettled(loadPromises)
  return map
}

// REMOVED GAPS: No more -2 width or +1 offsets
function createCell(type, x, y) {
  const texture = textureMap[type]
  let cell

  if (texture) {
    cell = new PIXI.Sprite(texture)
    cell.width = cellSize.value
    cell.height = cellSize.value
    cell.position.set(x * cellSize.value, y * cellSize.value)
  } else {
    cell = new PIXI.Graphics()
    cell
      .rect(x * cellSize.value, y * cellSize.value, cellSize.value, cellSize.value)
      .fill(getCellColor(type))
  }

  cell.cellType = type
  return cell
}

function drawGrid(grid) {
  const rows = grid.length
  const cols = grid[0].length
  cellNodes = Array.from({ length: rows }, () => Array(cols).fill(null))

  for (let y = 0; y < rows; y++) {
    for (let x = 0; x < cols; x++) {
      const cell = createCell(grid[y][x], x, y)
      cellNodes[y][x] = cell
      mapContainer.addChild(cell)
    }
  }
}

function createRoverGraphics() {
  const cont = new PIXI.Container()
  
  // Rover body: slightly smaller than cell size to look good
  const size = cellSize.value * 0.7
  const body = new PIXI.Graphics()
    .roundRect(0, 0, size, size, 4)
    .fill(0xffffff)
    .stroke({ width: 2, color: 0x000000 })

  const dot = new PIXI.Graphics()
    .circle(size/2, size/2, size/4)
    .fill(0xe63946)

  cont.addChild(body, dot)
  cont.pivot.set(size / 2, size / 2) // Center the pivot
  return cont
}

function updateRoverPosition(pos, instant = false) {
  if (!rover || !pos) return

  // CALCULATE CENTER: (Index * Size) + Half Size
  const tx = pos.x * cellSize.value + cellSize.value / 2
  const ty = pos.y * cellSize.value + cellSize.value / 2

  if (instant) {
    rover.position.set(tx, ty)
    return
  }

  const sx = rover.x
  const sy = rover.y
  const start = performance.now()
  const duration = 300

  function animate(now) {
    const t = Math.min((now - start) / duration, 1)
    const ease = t * (2 - t) // Simple ease-out
    rover.x = sx + (tx - sx) * ease
    rover.y = sy + (ty - sy) * ease
    if (t < 1) requestAnimationFrame(animate)
  }

  requestAnimationFrame(animate)
}

function drawPath() {
  if (!pathGraphics) return
  pathGraphics.clear()
  if (!props.pathPlan?.length) return

  let currentX = props.roverPosition.x
  let currentY = props.roverPosition.y

  for (const step of props.pathPlan) {
    const nextX = currentX + step.x
    const nextY = currentY + step.y

    pathGraphics
      .moveTo(
        currentX * cellSize.value + cellSize.value / 2,
        currentY * cellSize.value + cellSize.value / 2
      )
      .lineTo(
        nextX * cellSize.value + cellSize.value / 2,
        nextY * cellSize.value + cellSize.value / 2
      )
      .stroke({ width: 3, color: 0x00ffcc, alpha: 0.8, cap: 'round' })

    currentX = nextX
    currentY = nextY
  }
}

function forceResize() {
  if (!app || !viewport || !pixiContainer.value) return
  const w = pixiContainer.value.clientWidth
  const h = pixiContainer.value.clientHeight
  app.renderer.resize(w, h)
  viewport.resize(w, h)
}

function getCellColor(type) {
  const colors = { '.': 0xbc6124, '#': 0x4a4a4a, 'B': 0x4cc9f0, 'Y': 0xffd700, 'G': 0x2ecc71, 'S': 0x333333 }
  return colors[type] || 0x555555
}

watch(() => props.roverPosition, (newPos) => {
  if (initialized.value) {
    updateRoverPosition(newPos)
    drawPath()
  }
}, { deep: true })

watch(() => props.mapMatrix, (newMatrix) => {
  if (initialized.value) {
    // For simplicity, redraw the whole grid if matrix changes
    mapContainer.removeChildren()
    drawGrid(newMatrix)
    mapContainer.addChild(pathGraphics)
    mapContainer.addChild(rover)
  }
}, { deep: true })
</script>

<style scoped>
.map-wrapper {
  width: 100%;
  height: 100%;
  min-height: 400px;
  background: #1a1a2e;
  border-radius: 12px;
  overflow: hidden;
}

.pixi-container {
  width: 100%;
  height: 100%;
  display: block;
}
</style>