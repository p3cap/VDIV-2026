<script setup>
import { RouterLink } from 'vue-router'
import { Settings, Earth, ChartNoAxesCombined, Rotate3d, House } from 'lucide-vue-next'

const menuItems = [
    { id: 'welcome', to: '/', icon: House },
    { id: 'map', to: '/map', icon: Earth },
    { id: 'map3d', to: '/map3d', icon: Rotate3d },
    { id: 'dashboard', to: '/dashboard', icon: ChartNoAxesCombined },
    { id: 'settings', to: '/settings', icon: Settings },
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

<style src="../styles/main.css"></style>
