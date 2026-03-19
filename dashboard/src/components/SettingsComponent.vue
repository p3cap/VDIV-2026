<script setup>
import { setLanguage, currentLang } from '@/data/translate.js'
</script>

<template>
  <button class="gombocska"
    @click="setLanguage('HU')" 
    :class="{ active: currentLang.value === 'HU' }"
  >
    HU
  </button>

  <button 
    @click="setLanguage('EN')" 
    :class="{ active: currentLang.value === 'EN' }"
  >
    EN
  </button>
</template>
<style src="../styles/main.css">
</style>
