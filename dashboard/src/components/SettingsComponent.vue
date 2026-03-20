<script setup>
import { ref, nextTick } from 'vue'
import { X, Globe } from 'lucide-vue-next'
import { animate, stagger, createTimeline } from 'animejs'
import { setLanguage, currentLang } from '@/data/translate.js'

const overlayRef = ref(null)
const popupRef   = ref(null)
const itemRefs   = ref([])
const isOpen     = ref(false)

const languages = [
  { code: 'HU', label: 'Magyar', flag: 'HU' },
  { code: 'EN', label: 'English', flag: 'EN'  },
]

async function open() {
  isOpen.value = true
  await nextTick()

  animate(overlayRef.value, {
    opacity: [0, 1], duration: 260, easing: 'easeOutQuad',
  })

  createTimeline({ easing: 'easeOutExpo' })
    .add(popupRef.value, {
      opacity: [0, 1], translateY: [32, 0], scale: [0.93, 1], duration: 400,
    })
    .add(itemRefs.value, {
      opacity: [0, 1], translateX: [-16, 0], duration: 240,
      delay: stagger(60, { easing: 'easeOutQuad' }),
    }, '-=200')
}

async function close() {
  createTimeline({ easing: 'easeInQuart' })
    .add(popupRef.value, {
      opacity: [1, 0], translateY: [0, 20], scale: [1, 0.95], duration: 240,
    })
    .add(overlayRef.value, {
      opacity: [1, 0], duration: 180,
    }, '-=140')

  await new Promise(r => setTimeout(r, 250))
  isOpen.value = false
}

function select(code) {
  setLanguage(code)
  close()
}

defineExpose({ open })
</script>

<template>
  <Teleport to="body">
    <div v-if="isOpen" ref="overlayRef" class="overlay" @click.self="close">
      <div ref="popupRef" class="popup">

        <header class="popup-header">
          <span class="popup-title">
            <Globe :size="14" />
            Language
          </span>
          <button class="btn-close" @click="close" aria-label="Close">
            <X :size="15" />
          </button>
        </header>

        <div class="divider" />

        <ul class="lang-list" role="listbox">
          <li
            v-for="(lang, i) in languages"
            :key="lang.code"
            :ref="el => { if (el) itemRefs[i] = el }"
            role="option"
            :aria-selected="currentLang.value === lang.code"
            class="lang-item"
            :class="{ active: currentLang.value === lang.code }"
            @click="select(lang.code)"
          >
            <span class="lang-flag">{{ lang.flag }}</span>
            <span class="lang-label">{{ lang.label }}</span>
          </li>
        </ul>

      </div>
    </div>
  </Teleport>
</template>

<style src="../styles/main.css">

</style>