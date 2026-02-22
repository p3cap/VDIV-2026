<template>
  <div :style="{ width: width, height: height }" ref="chartRef"></div>
</template>

<script setup>
import * as echarts from 'echarts';
import { onMounted, watch, ref, defineProps, onBeforeUnmount } from 'vue';

const props = defineProps({
  options: { type: Object, required: true },  // ECharts option objektum
  width: { type: String, default: '100%' },
  height: { type: String, default: '300px' }
});

const chartRef = ref(null);
let chartInstance = null;

onMounted(() => {
  chartInstance = echarts.init(chartRef.value);
  chartInstance.setOption(props.options);
});

watch(() => props.options, (newOptions) => {
  if (chartInstance) {
    chartInstance.setOption(newOptions, true);
  }
}, { deep: true });

onBeforeUnmount(() => {
  if (chartInstance) {
    chartInstance.dispose();
  }
});
</script>