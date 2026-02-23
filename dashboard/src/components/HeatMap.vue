<template>
  <div ref="chartRef" class="heatmap"></div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from "vue"
import * as echarts from "echarts"
import marsMap from '@/data/marsMap.json'

const chartRef = ref(null)
let chartInstance = null

// Symbol → numeric value mapping
const valueMap = {
  ".": 0,
  "#": 1,
  "B": 2,
  "Y": 3,
  "G": 4,
  "S": 5
}

// Convert grid to ECharts heatmap format
function buildHeatmapData(grid) {
  const data = []
  const height = grid.length

  for (let y = 0; y < height; y++) {
    for (let x = 0; x < grid[y].length; x++) {
      data.push([x, height - 1 - y, valueMap[grid[y][x]]])
    }
  }
  return data
}

onMounted(() => {
  chartInstance = echarts.init(chartRef.value)

  chartInstance.setOption({
    tooltip: {
      formatter: ({ value }) =>
        `x: ${value[0]}<br/>y: ${value[1]}<br/>value: ${value[2]}`
    },
    grid: {
      top: 20,
      right: 20,
      bottom: 50,
      left: 50
    },
    xAxis: {
      type: "category",
      data: Array.from({ length: marsMap.width }, (_, i) => i),
      axisLabel: { show: false },
      axisTick: { show: false },
      splitLine: { show: false }
    },
    yAxis: {
      type: "category",
      data: Array.from({ length: marsMap.height }, (_, i) => i),
      axisLabel: { show: false },
      axisTick: { show: false },
      splitLine: { show: false }
    },
    visualMap: {
      min: 0,
      max: 5,
      orient: "horizontal",
      left: "center",
      bottom: 0,
      calculable: true,
      inRange: {
        color: [
          "#1e1e1e", // .
          "#616161", // #
          "#1976d2", // B
          "#fbc02d", // Y
          "#388e3c", // G
          "#d32f2f"  // S
        ]
      }
    },
    series: [
      {
        type: "heatmap",
        data: buildHeatmapData(marsMap.grid),
        emphasis: {
          itemStyle: {
            borderColor: "#fff",
            borderWidth: 1
          }
        }
      }
    ]
  })

  window.addEventListener("resize", resize)
})

function resize() {
  chartInstance?.resize()
}

onBeforeUnmount(() => {
  window.removeEventListener("resize", resize)
  chartInstance?.dispose()
})
</script>

<style scoped>
.heatmap {
  width: 100%;
  height: 600px;
}
</style>
