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
.view {
  position: relative;
  width: 97vw;
  height: 100vh;
  float: right;
}
.nav {
  position: relative;
  top: 0;
  right: 0;
  width: 3vw;
  height: 100vh;
  background: #07080c;
}
</style>
