<script setup>
import { ref, watch, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import { Settings, Earth, ChartNoAxesCombined, House, Rotate3d } from 'lucide-vue-next'
import { animate, stagger } from 'animejs'
import { translateKey as t } from '@/data/translate.js'
import SettingsComponent from '@/components/SettingsComponent.vue'

const isExpanded = ref(false)
const sidebarRef = ref(null)
const labelRefs  = ref([])
const settingsPopup  = ref(null)

const menuItems = [
  { id: 'welcome',   to: '/',          icon: House,               label: 'nav_welcome'   },
  { id: 'map',       to: '/map',       icon: Earth,               label: 'nav_map'       },
  { id: 'map3d',     to: '/map3d',     icon: Rotate3d,            label: 'nav_map3d'     },
  { id: 'dashboard', to: '/dashboard', icon: ChartNoAxesCombined, label: 'nav_dashboard' },
]

watch(isExpanded, (expanded) => {
  if (!sidebarRef.value) return

  animate(sidebarRef.value, {
    width: expanded ? 240 : 68,
    easing: expanded ? 'easeOutExpo' : 'easeInOutQuint',
    duration: expanded ? 420 : 380,
    boxShadow: expanded ? '6px 0 20px rgba(0,0,0,0.16)' : '1px 0 8px rgba(0,0,0,0.08)',
  })

  if (labelRefs.value.length > 0) {
    animate(labelRefs.value, {
      translateX: expanded ? [-30, 0] : [0, -30],
      opacity:    expanded ? [0, 1]   : [1, 0],
      duration: 320,
      delay: stagger(30, { from: expanded ? 'first' : 'last', easing: 'easeOutQuad' }),
      easing: 'easeOutQuad',
    })
  }
})

onMounted(() => {
  const logoImg = document.querySelector('.logo img')
  if (!logoImg) return
  logoImg.addEventListener('mouseenter', () =>
    animate(logoImg, { scale: 1.12, rotate: '10deg', duration: 600, easing: 'easeOutBack' }))
  logoImg.addEventListener('mouseleave', () =>
    animate(logoImg, { scale: 1, rotate: '0deg', duration: 400, easing: 'easeInOutQuad' }))
})
</script>

<template>
  <nav
    ref="sidebarRef"
    class="sidebar"
    :class="{ expanded: isExpanded }"
    @mouseenter="isExpanded = true"
    @mouseleave="isExpanded = false"
  >
    <ul>
      <li class="logo">
        <img src="@/assets/huh_logo.png" alt="logo" />
      </li>

      <li v-for="(item, index) in menuItems" :key="item.id" :id="item.id" class="menu-item">
        <RouterLink :to="item.to">
          <component :is="item.icon" size="28" />
          <span
            v-if="isExpanded"
            class="menu-label"
            :ref="el => { if (el) labelRefs[index] = el }"
          >{{ t(item.label) }}</span>
        </RouterLink>
      </li>

      <li id="settings" class="menu-item">
        <button class="settings-btn" @click="settingsPopup.open()">
          <Settings size="28" />
          <span
            v-if="isExpanded"
            class="menu-label"
            :ref="el => { if (el) labelRefs[menuItems.length] = el }"
          >{{ t('nav_settings') }}</span>
        </button>
      </li>
    </ul>
  </nav>

  <SettingsComponent ref="settingsPopup" />
</template>

<style src="../styles/main.css"></style>

<style scoped>
.settings-btn {
  display: flex;
  align-items: center;
  gap: 14px;
  width: 100%;
  padding: 10px 18px;
  background: none;
  border: none;
  color: inherit;
  cursor: pointer;
  border-radius: 10px;
  transition: background 0.18s;
  font-family: inherit;
}
.settings-btn:hover {
  background: rgba(255, 255, 255, 0.07);
}
</style>