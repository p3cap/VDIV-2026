<script setup>
import { ref, onMounted, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { Settings, Earth, ChartNoAxesCombined, House, Rotate3d } from 'lucide-vue-next'
import { animate, stagger } from 'animejs'

const isExpanded = ref(false)

const menuItems = [
  { id: 'welcome',      to: '/welcome',             icon: House,                label: 'Welcome'      },
  { id: 'map',        to: '/',                  icon: Earth,               label: 'Map'       },
  { id: 'dashboard',  to: '/dashboard',         icon: ChartNoAxesCombined, label: 'Dashboard'    },
  { id: 'map3d',      to: '/map3d',                icon: Rotate3d,                label: '3d Map'   },
  { id: 'settings',   to: '/settings',          icon: Settings,            label: 'Settings'   }
  
]

const sidebarRef = ref(null)
const labelRefs = ref([])   

function toggleExpand() {
  isExpanded.value = !isExpanded.value
}

watch(isExpanded, (expanded) => {
  if (!sidebarRef.value) return


  animate(sidebarRef.value, {
    width: expanded ? 240 : 68,
    easing: expanded ? 'easeOutExpo' : 'easeInOutQuint',
    duration: expanded ? 420 : 380,
    boxShadow: expanded 
      ? '6px 0 20px rgba(0,0,0,0.16)' 
      : '1px 0 8px rgba(0,0,0,0.08)',
  })

  if (labelRefs.value.length > 0) {
    animate(labelRefs.value, {
      translateX: expanded ? [ -30, 0 ] : [0, -30],
      opacity: expanded ? [0, 1] : [1, 0],
      duration: 320,
      delay: stagger(30, { 
        from: expanded ? 'first' : 'last',
        easing: 'easeOutQuad'
      }),
      easing: 'easeOutQuad',
    })
  }
})


// ez ilyen opcionalis logo hover

onMounted(() => {
  const logoImg = document.querySelector('.logo img, .menu-item')
  if (!logoImg) return

  logoImg.addEventListener('mouseenter', () => {
    animate(logoImg, {
      scale: 1.12,
      rotate: '10deg',
      duration: 600,
      easing: 'easeOutBack'
    })
  })

  logoImg.addEventListener('mouseleave', () => {
    animate(logoImg, {
      scale: 1,
      rotate: '0deg',
      duration: 400,
      easing: 'easeInOutQuad'
    })
  })
})
</script>

<template>
  <nav
    ref="sidebarRef"
    class="sidebar"
    :class="{ 'expanded': isExpanded }"
    @mouseenter="isExpanded = true"
    @mouseleave="isExpanded = false"
  >
    <ul>
      <li class="logo">
        <img src="@/assets/textures/pttt_logo_mini.png" alt="logo" />
      </li>

      <li 
        v-for="(item, index) in menuItems" 
        :key="item.id" 
        :id="item.id" 
        class="menu-item"
      >
        <RouterLink :to="item.to">
          <component :is="item.icon" size="28" />
          <span 
            v-if="isExpanded" 
            class="menu-label"
            ref="el => { if (el) labelRefs[index] = el }"
          >
            {{ item.label }}
          </span>
        </RouterLink>
      </li>
    </ul>
  </nav>
</template>

<style src="../main.css"></style>
