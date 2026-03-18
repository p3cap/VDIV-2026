// dictionary
import translationDictonary from './langDictionary.js'

function translateKey(translationKey) {
  const lang = "HU"
  const key = translationDictonary[translationKey]
  let translation = key ? key[lang] : translationKey

  return translation
}

export { translateKey }
