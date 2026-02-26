import { useState } from 'react'
import { Select } from 'antd'
import { Globe } from 'lucide-react'
import { useTranslation } from 'react-i18next'

const LanguageSwitcher = () => {
  const { i18n } = useTranslation()
  const [currentLanguage, setCurrentLanguage] = useState(i18n.language)

  const handleLanguageChange = (value: string) => {
    i18n.changeLanguage(value)
    setCurrentLanguage(value)
    localStorage.setItem('language', value) // 保存到本地存储
  }

  const languageOptions = [
    {
      value: 'zh-CN',
      label: (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span>🇨🇳</span>
          <span>简体中文</span>
        </div>
      ),
    },
    {
      value: 'en-US',
      label: (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span>🇺🇸</span>
          <span>English</span>
        </div>
      ),
    },
  ]

  return (
    <Select
      value={currentLanguage}
      onChange={handleLanguageChange}
      options={languageOptions}
      style={{ width: 160 }}
      suffixIcon={<Globe size={14} />}
      size="large"
    />
  )
}

export default LanguageSwitcher
