<script setup>
import { RouterView } from 'vue-router';
import NavComponent from './components/NavComponent.vue';
import NavbarPhoneComponent from './components/NavbarPhoneComponent.vue';
</script>

<template>
  <router-view :key="$route.fullPath" />

  <!-- Desktop Navbar -->
  <div class="desktop-navbar">
    <NavComponent />
  </div>

  <!-- Mobile Navbar -->
  <div class="mobile-navbar">
    <NavbarPhoneComponent />
  </div>
</template>

<style src="./main.css"></style>
