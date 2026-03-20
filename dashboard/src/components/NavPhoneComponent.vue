<script setup>
import { ref } from 'vue'
import { RouterLink } from 'vue-router'
import { Settings, Earth, ChartNoAxesCombined, Rotate3d, House } from 'lucide-vue-next'
import SettingsComponent from '@/components/SettingsComponent.vue'

const settingsPopup = ref(null)

const menuItems = [
  { id: 'welcome',   to: '/',          icon: House               },
  { id: 'map',       to: '/map',       icon: Earth               },
  { id: 'map3d',     to: '/map3d',     icon: Rotate3d            },
  { id: 'dashboard', to: '/dashboard', icon: ChartNoAxesCombined },
]
</script>

<template>
  <nav class="mobile-nav">
    <RouterLink to="/" class="logo">
      <img src="@/assets/huh_logo.png" alt="logo" />
    </RouterLink>

    <ul>
      <li v-for="item in menuItems" :key="item.id" class="menu-item">
        <RouterLink :to="item.to" class="menu-link">
          <component :is="item.icon" size="28" />
        </RouterLink>
      </li>

      <li class="menu-item">
        <button class="menu-link" @click="settingsPopup.open()">
          <Settings />
        </button>
      </li>
    </ul>
  </nav>

  <SettingsComponent ref="settingsPopup" />
</template>

<style src="../styles/main.css"></style>