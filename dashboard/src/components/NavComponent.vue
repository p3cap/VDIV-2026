<script setup>
import { ref, onMounted, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { Settings, Earth, ChartNoAxesCombined, Info, Rotate3d } from 'lucide-vue-next'
import { animate, stagger } from 'animejs'

const isExpanded = ref(false)

const menuItems = [
  { id: 'map',        to: '/',                  icon: Earth,               label: 'Map'       },
  { id: 'dashboard',  to: '/dashboard',         icon: ChartNoAxesCombined, label: 'Dashboard'    },
  { id: 'map3d',   to: '/map3d',             icon: Rotate3d,                label: '3d Map'   },
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

<style scoped>
.sidebar {
  position: fixed;
  left: 0;
  top: 0;
  height: 100vh;
  width: 68px;           
  background: linear-gradient(280deg, #0099ff 0%, #62bbff 100%);
  overflow: hidden;
  z-index: 900;
  border-radius: 0 16px 16px 0;
}

ul {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 0;
  margin: 0;
  list-style: none;
}

.logo {
  padding: 1.4rem 0;
  text-align: center;
}

.logo img {
  width: 48px;
  display: block;
  margin: 0 auto;
}

.menu-item a {
  display: flex;
  align-items: center;
  gap: 1.2rem;
  padding: 0.9rem 1.2rem;
  color: #1e40af;
  text-decoration: none;
  white-space: nowrap;
  transition: background 0.25s, color 0.25s;
}

.menu-item a:hover {
  background: rgba(255,255,255,0.45);
  color: #1e3a8a;
}

.menu-item svg {
  min-width: 28px;
  flex-shrink: 0;
}

.menu-label {
  font-weight: 500;
  font-size: 1.05rem;
}

#settings {
  margin-top: auto;
  padding-bottom: 2.2rem;
}
</style>