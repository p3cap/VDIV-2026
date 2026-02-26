// full ai, majd atnezem


import langDictionary from './langDictionary.js'

const STORAGE_KEY = 'dashboard_language'
const DEFAULT_LANGUAGE = 'HU'
const FALLBACK_LANGUAGE = 'EN'
const SUPPORTED_LANGUAGES = ['HU', 'EN']

function normalizeLanguage(language) {
  if (!language || typeof language !== 'string') return DEFAULT_LANGUAGE
  const normalized = language.toUpperCase().trim()
  return SUPPORTED_LANGUAGES.includes(normalized) ? normalized : DEFAULT_LANGUAGE
}

function getNestedValue(obj, path) {
  if (!path || typeof path !== 'string') return undefined
  return path.split('.').reduce((current, key) => {
    if (!current || typeof current !== 'object') return undefined
    return current[key]
  }, obj)
}

function applyParams(text, params = {}) {
  if (typeof text !== 'string') return text
  return text.replace(/\{(\w+)\}/g, (_, token) => {
    const value = params[token]
    return value === undefined || value === null ? `{${token}}` : String(value)
  })
}

export function getLanguage() {
  if (typeof window === 'undefined') return DEFAULT_LANGUAGE
  const saved = window.localStorage.getItem(STORAGE_KEY)
  return normalizeLanguage(saved)
}

export function setLanguage(language) {
  const normalized = normalizeLanguage(language)
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(STORAGE_KEY, normalized)
  }
  return normalized
}

export function t(key, language = getLanguage(), params = {}) {
  const entry = getNestedValue(langDictionary, key)
  if (!entry) return key

  if (typeof entry === 'string') {
    return applyParams(entry, params)
  }

  const normalizedLanguage = normalizeLanguage(language)
  const text =
    entry[normalizedLanguage] ??
    entry[DEFAULT_LANGUAGE] ??
    entry[FALLBACK_LANGUAGE] ??
    Object.values(entry)[0]

  if (typeof text !== 'string') return key
  return applyParams(text, params)
}

export default t





`igy hasznlajatok 
    import t, { setLanguage } from '@/data/translate'

    <h1>{{ t('test', lang) }}</h1>
    <button @click="switchLanguage">
      Switch language ({{ lang }})
    </button>

    const lang = ref(getLanguage())

    function switchLanguage() {
      const next = lang.value === 'HU' ? 'EN' : 'HU'
      lang.value = setLanguage(next)
}
`