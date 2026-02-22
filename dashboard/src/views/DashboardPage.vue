<script setup>
import { reactive } from 'vue'
import ChartComponent from '@/components/ChartComponent.vue'

const lineChartOptions = reactive({
  title: { text: 'Fitymahegedu' },
  tooltip: { trigger: 'axis' },
  xAxis: {
    type: 'category',
    data: ['Jan', 'Feb', 'Mar', 'Apr', 'May'],
  },
  yAxis: { type: 'value' },
  series: [
    {
      name: 'Users',
      type: 'line',
      smooth: true,
      data: [120, 200, 150, 80, 70],
    },
  ],
})

function addRandomGradually() {
  let count = 0

  const interval = setInterval(() => {
    const value = Math.floor(Math.random() * 301)

    lineChartOptions.series[0].data.push(value)
    lineChartOptions.xAxis.data.push(
      `Extra ${lineChartOptions.xAxis.data.length}`
    )
    count++

    if (count >= 220) {
      clearInterval(interval)
    }
  }, 500)
}
</script>

<template>
  <div>
    <button @click="addRandomGradually">
      Random adatok hozzáadása
    </button>

    <ChartComponent
      :options="lineChartOptions"
      height="400px"
      width="600px"
    />
  </div>
</template>