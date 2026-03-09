<script setup>
import { RouterView } from 'vue-router';
import NavComponent from './components/NavComponent.vue';
</script>

<template>
  <div class="view">
    <router-view />
  </div>
  <div class="nav">
    <NavComponent />
  </div>
</template>

<style>

body {
  margin: 0;
  font-family: system-ui, Arial, sans-serif;
  background: black;
  color: white;

}

</style>
