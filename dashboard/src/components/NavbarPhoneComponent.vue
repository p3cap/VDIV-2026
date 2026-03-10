<script setup>
import { RouterLink } from 'vue-router'
import { Settings, Earth, ChartNoAxesCombined, Rotate3d } from 'lucide-vue-next'

const menuItems = [
  { id: 'map',       to: '/',           icon: Earth },
  { id: 'dashboard', to: '/dashboard',  icon: ChartNoAxesCombined },
  { id: 'map3d',     to: '/map3d',      icon: Rotate3d },
  { id: 'settings',  to: '/settings',   icon: Settings }
]
</script>

<template>
  <nav class="mobile-nav">
    <RouterLink to="/" class="logo">
      <img src="@/assets/textures/pttt_logo_mini.png" alt="logo" />
    </RouterLink>

    <ul>
      <li v-for="item in menuItems" :key="item.id" class="menu-item">
        <RouterLink :to="item.to" class="menu-link">
          <component :is="item.icon" size="28" />
        </RouterLink>
      </li>
    </ul>
  </nav>
</template>

<style scoped>
.mobile-nav {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 70px;
  background: linear-gradient(280deg, #0099ff 0%, #62bbff 100%);
  display: flex;
  align-items: center;
  justify-content: space-around;
  padding: 0 0.5rem;
  z-index: 1000;
  box-shadow: 0 -2px 10px rgba(0,0,0,0.15);
  border-bottom-left-radius: 16px;
  border-bottom-right-radius: 16px;
}

.logo img {
  height: 48px;
  display: block;
}

ul {
  display: flex;
  gap: 1.5rem;
  padding: 0;
  margin: 0;
  list-style: none;
}

.menu-item {
  display: flex;
  align-items: center;
}

.menu-link {
  color: #1e40af;
  text-decoration: none;
  display: flex;
  align-items: center;
}

.menu-link:hover {
  color: #1e3a8a;
}
</style>