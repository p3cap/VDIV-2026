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

<style>
body {
  margin: 0;
  font-family: system-ui, Arial, sans-serif;
  background: black;
  color: white;
}

/* Hide mobile nav on larger screens */
.mobile-navbar {
  display: none;
}

/* Hide desktop nav on small screens */
.desktop-navbar {
  display: block;
}

/* Media query for phones (max-width 768px) */
@media (max-width: 576px) {
  .mobile-navbar {
    display: block;
  }
  .desktop-navbar {
    display: none;
  }
}
</style>