<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import {
  AmbientLight,
  BoxGeometry,
  Color,
  Group,
  Mesh,
  MeshStandardMaterial,
  PerspectiveCamera,
  PlaneGeometry,
  Scene,
  SphereGeometry,
  Vector2,
  Vector3,
  WebGLRenderer,
  DirectionalLight,
} from "three";

const props = defineProps({
  roverPosition: { type: Object, required: true },
  pathPlan: { type: Array, default: () => [] },
  mapMatrix: { type: Array, required: true },
});

const containerRef = ref(null);

const matrix = computed(() => (Array.isArray(props.mapMatrix) ? props.mapMatrix : []));
const rows = computed(() => matrix.value.length || 1);
const cols = computed(() => matrix.value[0]?.length || 1);

const cellSize = 1.4;

let scene = null;
let camera = null;
let renderer = null;
let frameId = 0;
let resizeObserver = null;

let groundMesh = null;
let groundGeometry = null;

let wallsGroup = null;
let pathGroup = null;
let roverMesh = null;

const scratch = {
  half: new Vector2(),
  out: new Vector3(),
};

function toWorld(cellX, cellY, y = 0) {
  scratch.half.set((cols.value * cellSize) / 2, (rows.value * cellSize) / 2);

  return scratch.out.set(
    cellX * cellSize - scratch.half.x + cellSize / 2,
    y,
    cellY * cellSize - scratch.half.y + cellSize / 2,
  );
}

function clearGroup(group) {
  if (!group) return;

  while (group.children.length > 0) {
    const child = group.children[group.children.length - 1];
    group.remove(child);

    if (child?.geometry) {
      child.geometry.dispose();
    }

    if (Array.isArray(child?.material)) {
      child.material.forEach((material) => material.dispose());
    } else if (child?.material) {
      child.material.dispose();
    }
  }
}

function buildStaticScene() {
  if (!scene) return;

  if (!groundGeometry) {
    groundGeometry = new PlaneGeometry(cols.value * cellSize, rows.value * cellSize);
    groundMesh = new Mesh(
      groundGeometry,
      new MeshStandardMaterial({ color: "#1b2636", roughness: 0.9, metalness: 0.05 }),
    );
    groundMesh.rotation.x = -Math.PI / 2;
    scene.add(groundMesh);
  } else {
    groundGeometry.dispose();
    groundGeometry = new PlaneGeometry(cols.value * cellSize, rows.value * cellSize);
    groundMesh.geometry = groundGeometry;
  }

  clearGroup(wallsGroup);

  for (let y = 0; y < matrix.value.length; y++) {
    for (let x = 0; x < matrix.value[y].length; x++) {
      const value = matrix.value[y][x];

      if (value === 1 || value === true || value === "1") {
        const mesh = new Mesh(
          new BoxGeometry(cellSize * 0.9, 1, cellSize * 0.9),
          new MeshStandardMaterial({ color: "#7a3e2b", roughness: 0.8, metalness: 0.1 }),
        );

        mesh.position.copy(toWorld(x, y, 0.5));
        wallsGroup.add(mesh);
      }
    }
  }
}

function updatePath() {
  clearGroup(pathGroup);

  for (const point of props.pathPlan || []) {
    if (typeof point?.x !== "number" || typeof point?.y !== "number") {
      continue;
    }

    const marker = new Mesh(
      new SphereGeometry(0.16, 12, 12),
      new MeshStandardMaterial({
        color: "#44d1ff",
        emissive: new Color("#44d1ff"),
        emissiveIntensity: 0.6,
      }),
    );

    marker.position.copy(toWorld(point.x, point.y, 0.2));
    pathGroup.add(marker);
  }
}

function updateRover() {
  if (!roverMesh) return;

  const x = props.roverPosition?.x ?? 0;
  const y = props.roverPosition?.y ?? 0;
  roverMesh.position.copy(toWorld(x, y, 0.45));
}

function resizeRenderer() {
  if (!containerRef.value || !camera || !renderer) return;

  const width = Math.max(containerRef.value.clientWidth, 1);
  const height = Math.max(containerRef.value.clientHeight, 1);

  renderer.setSize(width, height, false);
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
}

function renderLoop() {
  if (!renderer || !scene || !camera) return;

  renderer.render(scene, camera);
  frameId = requestAnimationFrame(renderLoop);
}

onMounted(() => {
  if (!containerRef.value) return;

  scene = new Scene();
  scene.background = new Color("#0d1117");

  camera = new PerspectiveCamera(48, 1, 0.1, 300);
  camera.position.set(0, 28, 22);
  camera.lookAt(0, 0, 0);

  renderer = new WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));

  containerRef.value.appendChild(renderer.domElement);

  scene.add(new AmbientLight("#ffffff", 0.75));

  const sun = new DirectionalLight("#ffffff", 1.35);
  sun.position.set(15, 25, 10);
  scene.add(sun);

  wallsGroup = new Group();
  pathGroup = new Group();
  scene.add(wallsGroup);
  scene.add(pathGroup);

  roverMesh = new Mesh(
    new BoxGeometry(cellSize * 0.65, 0.7, cellSize * 0.9),
    new MeshStandardMaterial({ color: "#d7dbde", roughness: 0.5, metalness: 0.25 }),
  );
  scene.add(roverMesh);

  buildStaticScene();
  updatePath();
  updateRover();
  resizeRenderer();
  renderLoop();

  resizeObserver = new ResizeObserver(() => resizeRenderer());
  resizeObserver.observe(containerRef.value);
});

watch(
  matrix,
  () => {
    buildStaticScene();
    updatePath();
    updateRover();
  },
  { deep: true },
);

watch([rows, cols], () => {
  buildStaticScene();
  updatePath();
  updateRover();
});

watch(
  () => props.pathPlan,
  () => {
    updatePath();
  },
  { deep: true },
);

watch(
  () => props.roverPosition,
  () => {
    updateRover();
  },
  { deep: true },
);

onBeforeUnmount(() => {
  if (frameId) {
    cancelAnimationFrame(frameId);
    frameId = 0;
  }

  if (resizeObserver && containerRef.value) {
    resizeObserver.unobserve(containerRef.value);
    resizeObserver.disconnect();
    resizeObserver = null;
  }

  clearGroup(wallsGroup);
  clearGroup(pathGroup);

  if (roverMesh) {
    roverMesh.geometry.dispose();
    roverMesh.material.dispose();
  }

  if (groundMesh) {
    groundMesh.material.dispose();
  }

  if (groundGeometry) {
    groundGeometry.dispose();
  }

  if (renderer) {
    renderer.dispose();
    renderer.forceContextLoss();

    if (renderer.domElement?.parentNode === containerRef.value) {
      containerRef.value.removeChild(renderer.domElement);
    }
  }

  scene = null;
  camera = null;
  renderer = null;
  groundMesh = null;
  groundGeometry = null;
  wallsGroup = null;
  pathGroup = null;
  roverMesh = null;
});
</script>

<template>
  <div ref="containerRef" class="wrap"></div>
</template>

<style scoped>
.wrap {
  width: 100vw;
  height: 100vh;
}
</style>
