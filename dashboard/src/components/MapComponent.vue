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
import marsMap from '@/data/marsMap.json'
import testpng from '@/assets/textures/pttt_logo_mini.png'
/* PROPS */
const props = defineProps({
  roverPosition: { type: Object, default: () => ({ x: 0, y: 0 }) },
  pathPlan: { type: Array, default: () => [] },
})

/* =======================
   REFS / STATE
======================= */
const pixiContainer = ref(null)
const initialized = ref(false)
const cellSize = ref(28)

let app = null
let viewport = null
let mapContainer = null
let rover = null
let pathGraphics = null

/* =======================
   CONSTANTS
======================= */
const PADDING = 30

// ─── ITT KELL CSAK MÓDOSÍTANOD ────────────────────────────────
// Minden típus → textúra elérési útja (relatív a public mappához vagy src/assets-hez)
const texturePaths = {
  '.': testpng,          // vagy '@/assets/textures/dirt.png' – attól függ, mit használsz
  '#': '/textures/rock.png',
  'B': '/textures/blue-crystal.png',
  'Y': '/textures/yellow-gem.png',
  'G': '/textures/green-plant.png',
  'S': '/textures/sand.png',
  // ha új típus jön, csak ide írd be az utat
}

/* =======================
   MOUNT
======================= */
onMounted(async () => {
  if (!pixiContainer.value) return

  app = new PIXI.Application()

  await app.init({
    backgroundColor: 0x1e1e2e,
    resizeTo: pixiContainer.value,
    antialias: true,
    resolution: window.devicePixelRatio || 1,
    autoDensity: true,
  })

  pixiContainer.value.appendChild(app.canvas)

  const cols = marsMap.grid[0].length
  const rows = marsMap.grid.length
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

  // Textúrák betöltése + fallback logika
  const textureMap = await loadTexturesWithFallback()

  drawGrid(mapContainer, textureMap)

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

/* =======================
   TEXTÚRA BETÖLTÉS + FALLBACK
======================= */
async function loadTexturesWithFallback() {
  const textureMap = {}           // type → PIXI.Texture | null
  const loadPromises = []

  for (const [type, path] of Object.entries(texturePaths)) {
    if (!path) {
      textureMap[type] = null
      continue
    }

    const promise = Assets.load(path)
      .then(texture => {
        textureMap[type] = texture
        console.log(`Textúra betöltve: ${type} → ${path}`)
      })
      .catch(err => {
        console.warn(`Textúra betöltési hiba (${type}): ${path}`, err)
        textureMap[type] = null   // → fallback a drawGrid-ben
      })

    loadPromises.push(promise)
  }

  // Megvárjuk az összeset, de nem áll le, ha van hiba
  await Promise.allSettled(loadPromises)

  return textureMap
}

/* =======================
   GRID – textúra vagy fallback szín
======================= */
function drawGrid(container, textureMap) {
  const rows = marsMap.grid.length
  const cols = marsMap.grid[0].length

  for (let y = 0; y < rows; y++) {
    for (let x = 0; x < cols; x++) {
      const type = marsMap.grid[y][x]
      const texture = textureMap[type]   // lehet null

      let cell

      if (texture) {
        // Textúrás verzió
        cell = new PIXI.Sprite(texture)
        cell.width = cellSize.value - 2
        cell.height = cellSize.value - 2
        cell.position.set(
          x * cellSize.value + PADDING + 1,
          y * cellSize.value + PADDING + 1
        )

        // Opcionális: ha pixeles / blurry kell lenni
        // cell.texture.source.scaleMode = 'nearest'

      } else {
        // Fallback: régi színes Graphics
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

      // Kereshetővé tesszük később is
      cell.cellType = type
      cell.gridX = x
      cell.gridY = y

      container.addChild(cell)
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

/* =======================
   ROVER (változatlan)
======================= */
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

  const sx = rover.x, sy = rover.y
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

/* =======================
   PATH (változatlan)
======================= */
function drawPath() {
  if (!pathGraphics) return
  pathGraphics.clear()

  if (!props.pathPlan?.length) return

  let current = { ...props.roverPosition }

  for (const step of props.pathPlan) {
    if (!step || typeof step.x !== 'number' || typeof step.y !== 'number') continue

    const next = {
      x: current.x + step.x,
      y: current.y + step.y
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

/* =======================
   RESIZE (változatlan)
======================= */
function forceResize() {
  if (!app || !viewport || !pixiContainer.value) return
  const w = pixiContainer.value.clientWidth
  const h = pixiContainer.value.clientHeight
  if (w <= 0 || h <= 0) return

  app.renderer.resize(w, h)
  viewport.resize(w, h)
  viewport.fitWorld(true)
}

/* =======================
   WATCHERS (változatlan)
======================= */
watch(() => props.roverPosition, (newPos) => {
  if (initialized.value) {
    updateRoverPosition(newPos)
    drawPath()
  }
}, { deep: true })

watch(() => props.pathPlan, () => {
  if (initialized.value) drawPath()
}, { deep: true })
</script>

<style scoped>
.map-wrapper {
  display: flex;
  justify-content: center;
  align-items: center;
  width: 60vw;
  max-width: 1600px;
  height: 85vh;
  margin: 0 auto;
  background: #1a1a2e;
  border-radius: 20px;
  overflow: hidden;
  box-shadow: 0 8px 24px rgba(0,0,0,0.3);
  flex: none;
}

.pixi-container {
  width: 100% !important;
  height: 100% !important;
}
</style>