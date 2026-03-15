<template>
    <div class="map-wrapper">
        <div ref="pixiContainer" class="pixi-container"></div>
    </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'
import * as PIXI from 'pixi.js'
import { Viewport } from 'pixi-viewport'
import { Assets } from 'pixi.js'
import surface from '@/assets/textures/redsand.png'
import stone from '@/assets/textures/stone.jpg'
import lapis from '@/assets/textures/lapis.webp'
import copper from '@/assets/textures/copper.webp'
import gold from '@/assets/textures/gold.jpeg'
import roverImg from '@/assets/rover.png'

let roverTexture = null
onMounted(async () => {
    roverTexture = await Assets.load(roverImg)
})

const props = defineProps({
    roverPosition: { type: Object, default: () => ({ x: 0, y: 0 }) },
    pathPlan: { type: Array, default: () => [] },
    mapMatrix: { type: Array, default: () => [] },
    mined: { type: Array, default: () => [] },
})

const pixiContainer = ref(null)
const initialized = ref(false)
const cellSize = ref(16)

let app = null
let viewport = null
let mapContainer = null
let rover = null
let pathGraphics = null
let textureMap = {}
let cellNodes = []
let grid = ref([])

const texturePaths = {
    '.': surface,
    '#': stone,
    B: lapis,
    Y: gold,
    G: copper,
    S: surface,
}

onMounted(async () => {
    if (!pixiContainer.value) return
    if (!props.mapMatrix?.length || !props.mapMatrix[0]?.length) return

    grid.value = props.mapMatrix.map((row) => [...row])

    const rows = grid.value.length
    const cols = grid.value[0].length

    app = new PIXI.Application()
    await app.init({
        backgroundColor: 0x0f1623,
        resizeTo: pixiContainer.value,
        antialias: true,
        resolution: window.devicePixelRatio || 1,
        autoDensity: true,
    })

    pixiContainer.value.appendChild(app.canvas)

    const worldW = cols * cellSize.value
    const worldH = rows * cellSize.value

    viewport = new Viewport({
        screenWidth: app.screen.width,
        screenHeight: app.screen.height,
        worldWidth: worldW,
        worldHeight: worldH,
        events: app.renderer.events,
    })

    viewport.drag().wheel().pinch().decelerate().clampZoom({ minScale: 0.2, maxScale: 8 })

    app.stage.addChild(viewport)
    mapContainer = new PIXI.Container()
    viewport.addChild(mapContainer)

    textureMap = await loadTextures()

    drawFullGrid()

    pathGraphics = new PIXI.Graphics()
    mapContainer.addChild(pathGraphics)

    rover = createRover()
    mapContainer.addChild(rover)

    updateRoverPosition(props.roverPosition, true)
    drawPath() // initial draw

    viewport.fit(true)
    viewport.moveCenter(worldW / 2, worldH / 2)

    initialized.value = true

    window.addEventListener('resize', onResize)
})

onUnmounted(() => {
    window.removeEventListener('resize', onResize)
    if (app) app.destroy(true, { children: true })
})

async function loadTextures() {
    const map = {}
    for (const [key, path] of Object.entries(texturePaths)) {
        try {
            map[key] = await Assets.load(path)
        } catch {
            map[key] = null
        }
    }
    return map
}

function drawFullGrid() {
    cellNodes = Array.from({ length: grid.value.length }, () =>
        Array(grid.value[0].length).fill(null),
    )

    for (let y = 0; y < grid.value.length; y++) {
        for (let x = 0; x < grid.value[y].length; x++) {
            const cell = createCell(grid.value[y][x], x, y)
            cellNodes[y][x] = cell
            mapContainer.addChild(cell)
        }
    }
}

function createCell(type, x, y) {
    const tex = textureMap[type]
    let cell

    if (tex) {
        cell = new PIXI.Sprite(tex)
        cell.width = cellSize.value
        cell.height = cellSize.value
    } else {
        cell = new PIXI.Graphics()
        cell.rect(0, 0, cellSize.value, cellSize.value).fill(getColor(type))
    }

    cell.position.set(x * cellSize.value, y * cellSize.value)
    cell.cellType = type
    return cell
}

function createRover() {
    const size = cellSize.value * 0.8
    const sprite = new PIXI.Sprite(roverTexture)
    sprite.width = size
    sprite.height = size
    sprite.anchor.set(0.5)
    return sprite
}

function updateRoverPosition(pos, instant = false) {
    if (!rover || (!pos?.x && pos?.x !== 0)) return

    const tx = pos.x * cellSize.value + cellSize.value / 2
    const ty = pos.y * cellSize.value + cellSize.value / 2

    if (instant) {
        rover.position.set(tx, ty)
        return
    }

    const sx = rover.x,
        sy = rover.y
    const start = performance.now()
    const dur = 380

    function anim(now) {
        const t = Math.min((now - start) / dur, 1)
        const ease = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2
        rover.x = sx + (tx - sx) * ease
        rover.y = sy + (ty - sy) * ease
        if (t < 1) requestAnimationFrame(anim)
    }
    requestAnimationFrame(anim)
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
                currentY * cellSize.value + cellSize.value / 2,
            )
            .lineTo(
                nextX * cellSize.value + cellSize.value / 2,
                nextY * cellSize.value + cellSize.value / 2,
            )
            .stroke({ width: 3, color: 0x00ffcc, alpha: 0.8, cap: 'round' })

        currentX = nextX
        currentY = nextY
    }
}

function onResize() {
    if (!app || !viewport) return
    const w = pixiContainer.value?.clientWidth ?? 800
    const h = pixiContainer.value?.clientHeight ?? 600
    app.renderer.resize(w, h)
    viewport.resize(w, h)
}

function getColor(type) {
    const c = { '.': 0xb5651d, '#': 0x555555, B: 0x40c4ff, Y: 0xffd54f, G: 0x66bb6a, S: 0x8d6e63 }
    return c[type] ?? 0x777777
}

// ��� Watches ������������������������������������������������

watch(
    () => props.roverPosition,
    (nv) => {
        if (initialized.value && nv) {
            updateRoverPosition(nv)
            drawPath()
        }
    },
    { deep: true },
)

watch(
    () => props.pathPlan,
    () => {
        if (initialized.value) {
            console.log('[PATH WATCH] pathPlan changed � redrawing')
            drawPath()
        }
    },
    { deep: true, immediate: true },
)

watch(
    () => props.mined,
    (mined) => {
        if (!initialized.value || !Array.isArray(mined)) return

        mined.forEach(({ x, y }) => {
            if (
                Number.isInteger(x) &&
                Number.isInteger(y) &&
                y >= 0 &&
                y < grid.value.length &&
                x >= 0 &&
                x < grid.value[y].length &&
                grid.value[y][x] !== '.' &&
                grid.value[y][x] !== '#'
            ) {
                grid.value[y][x] = '.'

                const old = cellNodes[y][x]
                if (old?.parent) {
                    const idx = mapContainer.children.indexOf(old)
                    mapContainer.removeChild(old)
                    old.destroy()
                    const neu = createCell('.', x, y)
                    mapContainer.addChildAt(neu, idx)
                    cellNodes[y][x] = neu
                }
            }
        })
    },
    { deep: true },
)
</script>

<style src="../styles/main.css"></style>
