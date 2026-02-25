<script setup>
import { RouterView } from 'vue-router';
import NavComponent from './components/NavComponent.vue';

</script>

<template>
  <router-view />
  <NavComponent />
</template>

<style>

body {
  margin: 0;
  font-family: system-ui, Arial, sans-serif;
  background: black;
  color: white;

}
</style>
