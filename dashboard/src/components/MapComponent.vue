<template>
    <div class="map-wrapper">
        <div class="texture-switcher">
            <label for="texture-pack">Textures</label>
            <select id="texture-pack" v-model="activeTexturePack">
                <option v-for="pack in texturePacks" :key="pack" :value="pack">
                    {{ formatTexturePack(pack) }}
                </option>
            </select>
        </div>
        <div ref="pixiContainer" class="pixi-container"></div>
    </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'
import * as PIXI from 'pixi.js'
import { Viewport } from 'pixi-viewport'
import { Assets } from 'pixi.js'
import ground from '@/assets/default/redsand.png'
import barrier from '@/assets/default/stone.jpg'
import blue from '@/assets/default/lapis.webp'
import green from '@/assets/default/copper.webp'
import yellow from '@/assets/default/gold.jpeg'
import roverImg from '@/assets/rover.png'
import start from '@/assets/start.png'

const textureFiles = import.meta.glob('@/assets/**/*.png', { eager: true, as: 'url' })
const textureIndex = Object.entries(textureFiles).reduce((acc, [path, url]) => {
    const normalized = path.replaceAll('\\', '/')
    const match = normalized.match(/\/assets\/([^/]+)\/([^/]+\.png)$/)
    if (!match) return acc
    const [, pack, filename] = match
    acc[pack] = acc[pack] || {}
    acc[pack][filename] = url
    return acc
}, {})

const props = defineProps({
    roverPosition: { type: Object, default: () => ({ x: 0, y: 0 }) },
    pathPlan: { type: Array, default: () => [] },
    mapMatrix: { type: Array, default: () => [] },
    mined: { type: Array, default: () => [] },
})

const pixiContainer = ref(null)
const initialized = ref(false)
const cellSize = ref(16)
const activeTexturePack = ref('default')
const texturePacks = ['default', 'pixelart', 'minecraft']

let app = null
let viewport = null
let mapContainer = null
let rover = null
let pathGraphics = null
let textureMap = {}
let cellNodes = []
let grid = ref([])
let roverTexture = null
let textureLoadId = 0

const defaultTextureUrls = {
    ground: ground,
    barrier: barrier,
    blue: blue,
    yellow: yellow,
    green: green,
    rover: roverImg,
    start : start,
}

const textureKeysByCell = {
    '.': 'ground',
    S: 'start',
    '#': 'barrier',
    B: 'blue',
    Y: 'yellow',
    G: 'green',
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

    await applyTexturePack(activeTexturePack.value, { initial: true })

    viewport.fit(true)
    viewport.moveCenter(worldW / 2, worldH / 2)

    initialized.value = true

    window.addEventListener('resize', onResize)
})

onUnmounted(() => {
    window.removeEventListener('resize', onResize)
    if (app) app.destroy(true, { children: true })
})

function formatTexturePack(pack) {
    const labels = {
        default: 'Default (Colors)',
        pixelart: 'Pixel Art',
        minecraft: 'Minecraft',
    }
    return labels[pack] ?? pack
}

function resolveTextureUrl(pack, key) {
    const filename = `${key}.png`
    const packUrl = textureIndex[pack]?.[filename]
    if (packUrl) return packUrl
    const fallbackUrl = textureIndex.default?.[filename]
    if (fallbackUrl) return fallbackUrl
    return defaultTextureUrls[key] ?? null
}

async function loadTextures(pack) {
    const map = {}
    const useTextures = pack !== 'default'
    for (const [cellType, key] of Object.entries(textureKeysByCell)) {
        if (!useTextures) {
            map[cellType] = null
            continue
        }
        const url = resolveTextureUrl(pack, key)
        try {
            map[cellType] = url ? await Assets.load(url) : null
        } catch {
            map[cellType] = null
        }
    }
    const roverUrl = useTextures ? resolveTextureUrl(pack, 'rover') : defaultTextureUrls.rover
    let roverTex = null
    try {
        roverTex = roverUrl ? await Assets.load(roverUrl) : null
    } catch {
        roverTex = null
    }
    return { map, roverTex }
}

async function applyTexturePack(pack, { initial = false } = {}) {
    const currentLoadId = ++textureLoadId
    const { map, roverTex } = await loadTextures(pack)
    if (currentLoadId !== textureLoadId) return

    textureMap = map
    roverTexture = roverTex ?? roverTexture

    if (initial) {
        drawFullGrid()

        pathGraphics = new PIXI.Graphics()
        mapContainer.addChild(pathGraphics)

        rover = createRover()
        mapContainer.addChild(rover)

        updateRoverPosition(props.roverPosition, true)
        drawPath()
        return
    }

    refreshGridTextures()
    if (rover && roverTexture) rover.texture = roverTexture
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
    const sprite = new PIXI.Sprite(roverTexture ?? PIXI.Texture.WHITE)
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

    const isRelative = isRelativePath(props.pathPlan)
    const roverX = props.roverPosition.x
    const roverY = props.roverPosition.y

    if (isRelative) {
        let currentX = roverX
        let currentY = roverY
        for (const step of props.pathPlan) {
            const { x, y } = normalizeStep(step)
            const nextX = currentX + x
            const nextY = currentY + y

            if (nextX === currentX && nextY === currentY) {
                continue
            }

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
        return
    }

    const points = props.pathPlan.map(normalizeStep).filter(({ x, y }) => Number.isFinite(x) && Number.isFinite(y))
    if (points.length < 2) return

    // Ha az első pont a rover pozija, indulhatunk onnan; különben ne húzzunk vonalat rover->start között.
    let startIndex = 0
    let currentX = points[0].x
    let currentY = points[0].y
    if (currentX === roverX && currentY === roverY) {
        startIndex = 1
    }

    for (let i = startIndex; i < points.length; i++) {
        const nextX = points[i].x
        const nextY = points[i].y

        if (nextX === currentX && nextY === currentY) {
            continue
        }

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

function normalizeStep(step) {
    if (Array.isArray(step) && step.length >= 2) {
        return { x: Number(step[0]), y: Number(step[1]) }
    }
    return { x: Number(step?.x ?? 0), y: Number(step?.y ?? 0) }
}

function isRelativePath(pathPlan) {
    if (!Array.isArray(pathPlan) || pathPlan.length === 0) return true
    return pathPlan.every((step) => {
        const { x, y } = normalizeStep(step)
        return Number.isFinite(x) && Number.isFinite(y) && Math.abs(x) <= 1 && Math.abs(y) <= 1
    })
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

function refreshGridTextures() {
    if (!mapContainer || !cellNodes.length) return
    for (let y = 0; y < grid.value.length; y++) {
        for (let x = 0; x < grid.value[y].length; x++) {
            const type = grid.value[y][x]
            const old = cellNodes[y][x]
            if (!old) {
                const neu = createCell(type, x, y)
                cellNodes[y][x] = neu
                mapContainer.addChild(neu)
                continue
            }
            const idx = mapContainer.children.indexOf(old)
            if (idx === -1) continue
            mapContainer.removeChild(old)
            old.destroy()
            const neu = createCell(type, x, y)
            mapContainer.addChildAt(neu, idx)
            cellNodes[y][x] = neu
        }
    }
}

// ��� Watches ������������������������������������������������

watch(
    () => activeTexturePack.value,
    (pack) => {
        if (!initialized.value) return
        applyTexturePack(pack)
    },
)

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
