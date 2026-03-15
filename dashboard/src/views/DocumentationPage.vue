<template>
  <div class="app-container">
    <nav class="navbar">
      <!-- Nyelv váltó -->
      <div class="lang-switcher">
        <button
          class="lang-btn"
          :class="{ active: currentLang === 'hu' }"
          @click="setLanguage('hu')"
          title="Magyar"
        >
          HU
        </button>
        <button
          class="lang-btn"
          :class="{ active: currentLang === 'en' }"
          @click="setLanguage('en')"
          title="English"
        >
          EN
        </button>
      </div>

      <!-- Navigációs ikonok -->
      <button
        v-for="(item, index) in navItems"
        :key="item.path"
        @click="loadMarkdown(item.path)"
        class="nav-button"
        :class="{ active: currentPath === item.path }"
        :title="formatName(item.name)"
      >
        <component :is="icons[index % icons.length]" class="nav-icon" />
      </button>
    </nav>

    <div class="markdown-body-wrapper">
      <div class="markdown-body" v-html="currentMarkdown"></div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { marked } from 'marked'
import { Info, BookOpen, Settings, Code, MonitorCloud } from 'lucide-vue-next'

// Állapot
const currentLang = ref('hu')           // alapértelmezett nyelv
const currentMarkdown = ref('')
const currentPath = ref('')

// Ikonok
const icons = [MonitorCloud, Info, BookOpen, Settings, Code]

// Segédfüggvény: tooltip formázás
const formatName = (raw) => {
  return raw
    .replace(/[-_]/g, ' ')
    .split(' ')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(' ')
}

// Globálisan importáljuk az összes md fájlt HU/EN mappákból
const allMdFiles = import.meta.glob('../doc/*/*.md', { as: 'raw' })

// Szűrt navItems a kiválasztott nyelv alapján
const navItems = computed(() => {
  return Object.keys(allMdFiles)
    .filter(path => path.includes(`/doc/${currentLang.value}/`))
    .map(path => {
      const name = path.split('/').pop().replace('.md', '')
      return { name, path }
    })
    .sort((a, b) => a.name.localeCompare(b.name))
})

// Markdown betöltése
async function loadMarkdown(path) {
  currentPath.value = path
  try {
    const content = await allMdFiles[path]()
    currentMarkdown.value = marked(content)
  } catch (err) {
    console.error('Failed to load markdown:', err)
    currentMarkdown.value = `
      <p style="color:#f87171;font-weight:bold;">
        Nem sikerült betölteni a tartalmat<br>
        <small>${err.message}</small>
      </p>
    `
  }
}

// Nyelv váltás
function setLanguage(lang) {
  if (lang === currentLang.value) return
  currentLang.value = lang
  currentPath.value = ''
  currentMarkdown.value = ''

  setTimeout(() => {
    if (navItems.value.length > 0) {
      loadMarkdown(navItems.value[0].path)
    } else {
      currentMarkdown.value = `
        <p style="color:#94a3b8;text-align:center;padding:4rem 1rem;">
          Nincs elérhető dokumentáció ezen a nyelven (${lang.toUpperCase()})
        </p>
      `
    }
  }, 50)
}

// Betöltéskor automatikusan az első fájl kiválasztása
onMounted(() => {
  if (navItems.value.length > 0) {
    loadMarkdown(navItems.value[0].path)
  }
})
</script>

<style scoped>
@import 'github-markdown-css';

.app-container {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  background: #0f0f17;
  color: #e2e8f0;
  width: calc(100vw - 68px);
  margin-left: 68px;
}

.navbar {
  height: 68px;
  position: fixed;
  left: 0;
  right: 0;
  top: 0;
  z-index: 0;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 1.1rem;
  padding: 0 1.5rem;
  overflow-x: auto;

}

.lang-switcher {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  margin-right: 1.2rem;
  background: rgba(30, 30, 50, 0.4);
  padding: 0.3rem;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.lang-btn {
  height: 36px;
  min-width: 44px;
  border-radius: 8px;
  border: none;
  background: transparent;
  color: #c7d2fe;
  font-weight: 600;
  font-size: 0.92rem;
  cursor: pointer;
  transition: all 0.2s ease;
}

.lang-btn:hover {
  background: rgba(120, 113, 166, 0.25);
}

.lang-btn.active {
  background: linear-gradient(135deg, #7c3aed, #a78bfa);
  color: white;
  box-shadow: 0 2px 10px rgba(124, 58, 237, 0.4);
}

.nav-button {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 44px;
  width: 44px;
  min-width: 44px;
  border-radius: 12px;
  background: rgba(100, 100, 140, 0.35);
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: #c7d2fe;
  cursor: pointer;
  transition: all 0.22s ease;
  flex-shrink: 0;
}

.nav-icon {
  width: 22px;
  height: 22px;
  opacity: 0.9;
  transition: all 0.22s ease;
}

.nav-button:hover,
.nav-button:focus {
  background: rgba(120, 113, 166, 0.35);
  transform: translateY(-1px) scale(1.05);
}

.nav-button:hover .nav-icon,
.nav-button:focus .nav-icon {
  opacity: 1;
  transform: scale(1.12);
}

.nav-button.active {
  background: linear-gradient(135deg, #7c3aed, #a78bfa);
  color: white;
  box-shadow: 0 4px 14px rgba(124, 58, 237, 0.35);
}

.nav-button.active .nav-icon {
  opacity: 1;
}

.markdown-body-wrapper {
  flex: 1;
  overflow-y: auto;
  padding: 90px 2.5rem 3rem;
}

.markdown-body {
  background: #111827;
  padding: 2.5rem;
  border-radius: 14px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.35);
  max-width: 920px;
  margin: 0 auto;
  color: #e5e7eb;
}

@media (max-width: 576px) {
  .app-container {
    width: 100vw;
    margin-left: 0;
  }
  .navbar {
    top: 68px;
    gap: 0;
    justify-content: space-between;
    backdrop-filter: blur(1.5px);
  }
  .markdown-body-wrapper {
    padding-top: 140px;
  }
}
</style>