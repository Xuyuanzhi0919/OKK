import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import zhCN from './locales/zh-CN.json'
import enUS from './locales/en-US.json'

// 从localStorage获取保存的语言设置,默认中文
const savedLanguage = localStorage.getItem('language') || 'zh-CN'

i18n
  .use(initReactI18next) // 绑定react-i18next
  .init({
    resources: {
      'zh-CN': {
        translation: zhCN,
      },
      'en-US': {
        translation: enUS,
      },
    },
    lng: savedLanguage, // 默认语言
    fallbackLng: 'zh-CN', // 回退语言
    interpolation: {
      escapeValue: false, // React已经处理了XSS
    },
  })

export default i18n
