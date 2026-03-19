// reactive for language change
import { ref } from 'vue'
import translationDictonary from './langDictionary.js'

const currentLang = ref('HU')

function translateKey(key, params = {}) {
  const entry = translationDictonary[key]
  let text = entry ? entry[currentLang.value] : key

  // paraméter behelyettesítés
  Object.keys(params).forEach(param => {
    text = text.replace(`{${param}}`, params[param])
  })

  return text
}

function setLanguage(lang) {
  currentLang.value = lang
}

export { translateKey, currentLang, setLanguage }