<template>
    <h1>Mars térkép haha</h1> 
    <MapComponent />
</template>

<script>
import MapComponent from '@/components/MapComponent.vue';

export default {
  name: "MapTestPage",
  components: { MapComponent },
};
</script>

<style scoped>
body {
    display: flex;
    justify-content: center;
    align-items: center;
    flex-direction: column;
    width: 100vw;
}

</style>
