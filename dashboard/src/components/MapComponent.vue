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
import testpng from '@/assets/textures/pttt_logo_mini.png'
import t, { getLanguage, setLanguage } from '@/data/translate'



const props = defineProps({
  roverPosition: { type: Object, default: () => ({ x: 0, y: 0 }) },
  pathPlan: { type: Array, default: () => [] },
  mapMatrix: { type: Array, default: () => [] },
})

const pixiContainer = ref(null)
const initialized = ref(false)
const cellSize = ref(28)

let app = null
let viewport = null
let mapContainer = null
let rover = null
let pathGraphics = null
let textureMap = {}
let cellNodes = []

const PADDING = 30

const texturePaths = {
  '.': testpng,
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
  const worldW = cols * cellSize.value + PADDING * 2
  const worldH = rows * cellSize.value + PADDING * 2

  viewport = new Viewport({
    screenWidth: app.screen.width,
    screenHeight: app.screen.height,
    worldWidth: worldW,
    worldHeight: worldH,
    events: app.renderer.events,
  })

  viewport
    .drag()
    .wheel()
    .pinch()
    .decelerate()
    .clamp({ direction: 'all' })
    .clampZoom({ minScale: 0.4, maxScale: 3.0 })

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

  viewport.moveCenter(worldW / 2, worldH / 2)
  viewport.fitWorld(true)
  viewport.scale.set(0.95)

  initialized.value = true

  await nextTick()
  forceResize()
  setTimeout(forceResize, 100)

  window.addEventListener('resize', forceResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', forceResize)
  if (app) app.destroy(true, { children: true })
})

async function loadTexturesWithFallback() {
  const map = {}
  const loadPromises = []

  for (const [type, path] of Object.entries(texturePaths)) {
    if (!path) {
      map[type] = null
      continue
    }

    const promise = Assets.load(path)
      .then(texture => {
        map[type] = texture
      })
      .catch(() => {
        map[type] = null
      })

    loadPromises.push(promise)
  }

  await Promise.allSettled(loadPromises)

  return map
}

function createCell(type, x, y) {
  const texture = textureMap[type]
  let cell

  if (texture) {
    cell = new PIXI.Sprite(texture)
    cell.width = cellSize.value - 2
    cell.height = cellSize.value - 2
    cell.position.set(
      x * cellSize.value + PADDING + 1,
      y * cellSize.value + PADDING + 1
    )
  } else {
    cell = new PIXI.Graphics()
    cell
      .roundRect(
        x * cellSize.value + PADDING,
        y * cellSize.value + PADDING,
        cellSize.value - 2,
        cellSize.value - 2,
        4
      )
      .fill(getCellColor(type))
  }

  cell.cellType = type
  cell.gridX = x
  cell.gridY = y
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

function syncGrid(grid) {
  if (!mapContainer || !grid.length || !grid[0]?.length) return

  const rows = grid.length
  const cols = grid[0].length

  if (cellNodes.length !== rows || (cellNodes[0] && cellNodes[0].length !== cols)) {
    for (const row of cellNodes) {
      for (const node of row) {
        if (node) mapContainer.removeChild(node)
      }
    }
    cellNodes = []
    drawGrid(grid)
    return
  }

  for (let y = 0; y < rows; y++) {
    for (let x = 0; x < cols; x++) {
      const nextType = grid[y][x]
      const currentNode = cellNodes[y][x]
      if (!currentNode) continue
      if (currentNode.cellType === nextType) continue

      const nextNode = createCell(nextType, x, y)
      const currentIndex = mapContainer.getChildIndex(currentNode)
      mapContainer.removeChild(currentNode)
      mapContainer.addChildAt(nextNode, currentIndex)
      cellNodes[y][x] = nextNode
    }
  }
}

function getCellColor(type) {
  const colors = {
    '.': 0xbc6124,
    '#': 0x4a4a4a,
    'B': 0x4cc9f0,
    'Y': 0xffd700,
    'G': 0x2ecc71,
    'S': 0x333333,
  }
  return colors[type] || 0x555555
}

function createRoverGraphics() {
  const cont = new PIXI.Container()
  const body = new PIXI.Graphics()
    .roundRect(0, 0, 18, 18, 4)
    .fill(0xffffff)

  const dot = new PIXI.Graphics()
    .circle(9, 9, 4)
    .fill(0xe63946)

  cont.addChild(body, dot)
  cont.pivot.set(9, 9)
  return cont
}

function updateRoverPosition(pos, instant = false) {
  if (!rover || !pos) return

  const tx = pos.x * cellSize.value + cellSize.value / 2 + PADDING
  const ty = pos.y * cellSize.value + cellSize.value / 2 + PADDING

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
    rover.x = sx + (tx - sx) * t
    rover.y = sy + (ty - sy) * t
    if (t < 1) requestAnimationFrame(animate)
  }

  requestAnimationFrame(animate)
}

function drawPath() {
  if (!pathGraphics) return
  pathGraphics.clear()

  if (!props.pathPlan?.length) return

  let current = { ...props.roverPosition }

  for (const step of props.pathPlan) {
    if (!step || typeof step.x !== 'number' || typeof step.y !== 'number') continue

    const next = {
      x: current.x + step.x,
      y: current.y + step.y,
    }

    if (Math.abs(step.x) <= 1 && Math.abs(step.y) <= 1 && (step.x !== 0 || step.y !== 0)) {
      pathGraphics
        .moveTo(
          current.x * cellSize.value + cellSize.value / 2 + PADDING,
          current.y * cellSize.value + cellSize.value / 2 + PADDING
        )
        .lineTo(
          next.x * cellSize.value + cellSize.value / 2 + PADDING,
          next.y * cellSize.value + cellSize.value / 2 + PADDING
        )
        .stroke({ width: 4, color: 0x00ffcc, alpha: 1, cap: 'round', join: 'round' })
    }

    current = next
  }
}

function forceResize() {
  if (!app || !viewport || !pixiContainer.value) return
  const w = pixiContainer.value.clientWidth
  const h = pixiContainer.value.clientHeight
  if (w <= 0 || h <= 0) return

  app.renderer.resize(w, h)
  viewport.resize(w, h)
  viewport.fitWorld(true)
}

watch(() => props.roverPosition, (newPos) => {
  if (initialized.value) {
    updateRoverPosition(newPos)
    drawPath()
  }
}, { deep: true })

watch(() => props.pathPlan, () => {
  if (initialized.value) drawPath()
}, { deep: true })

watch(() => props.mapMatrix, (newMatrix) => {
  if (!initialized.value) return
  if (!Array.isArray(newMatrix) || !newMatrix.length || !newMatrix[0]?.length) return
  syncGrid(newMatrix)
}, { deep: true })
</script>

<style scoped>
.map-wrapper {
  display: flex;
  justify-content: center;
  align-items: center;
  width: 60vw;
  height: 85vh;
  margin: 0 auto;
  background: #1a1a2e;
  border-radius: 16px;
  overflow: hidden;
  box-shadow: 0 8px 24px rgba(0,0,0,0.3);
  flex: none;
}

.pixi-container {
  width: 100% !important;
  height: 100% !important;
}
</style>
