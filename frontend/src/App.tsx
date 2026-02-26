import { useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { ConfigProvider, theme, App as AntApp } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import enUS from 'antd/locale/en_US'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import MainLayout from './components/Layout/MainLayout'
import Dashboard from './features/dashboard/Dashboard'
import StrategyList from './features/strategy/StrategyList'
import StrategyCreatePage from './features/strategy/StrategyCreatePage'
import TradingView from './features/trading/TradingView'
import TradingManagement from './features/trading/TradingManagement'
import Settings from './features/settings/Settings'
import APIConfigManagement from './features/settings/APIConfigManagement'
import BacktestList from './features/backtest/BacktestList'
import BacktestDetail from './features/backtest/BacktestDetail'
import KlineManager from './features/backtest/KlineManager'
import AlertHistory from './features/alerts/AlertHistory'
import RiskControlPage from './features/risk-control/RiskControlPage'
import MarketAnalysisPage from './features/ai/MarketAnalysisPage'
import AIConfigManagement from './features/settings/AIConfigManagement'
import { wsService, NotificationData } from './services/websocket'
import { useWebSocketStore } from './stores/useWebSocketStore'

// 创建React Query客户端
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
})

// 内部组件，用于访问 App context
function AppContent() {
  const { message } = AntApp.useApp()
  const setConnected = useWebSocketStore((state) => state.setConnected)

  useEffect(() => {
    // 初始化WebSocket连接
    wsService.connect()

    // 监听连接事件
    const unsubscribeConnect = wsService.onConnect(() => {
      setConnected(true)
      // 显示连接成功通知
      message.success('WebSocket实时推送服务已连接')
    })

    const unsubscribeDisconnect = wsService.onDisconnect(() => {
      setConnected(false)
      // 显示断开连接通知
      message.warning('WebSocket连接已断开，正在尝试重新连接...')
    })

    // 监听系统通知
    const unsubscribeNotification = wsService.onNotification((data: NotificationData) => {
      // 根据通知类型显示不同样式的通知
      const messageContent = data.title ? `${data.title}: ${data.message}` : data.message
      message[data.type]({
        content: messageContent,
        duration: data.type === 'error' ? 8 : 5,
      })
    })

    // 清理函数
    return () => {
      unsubscribeConnect()
      unsubscribeDisconnect()
      unsubscribeNotification()
      wsService.disconnect()
    }
  }, [setConnected, message])

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<MainLayout />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="strategies" element={<StrategyList />} />
          <Route path="strategies/create/:type" element={<StrategyCreatePage />} />
          <Route path="trading" element={<TradingView />} />
          <Route path="trading-management" element={<TradingManagement />} />
          <Route path="backtest" element={<BacktestList />} />
          <Route path="backtest/:id" element={<BacktestDetail />} />
          <Route path="kline-manager" element={<KlineManager />} />
          <Route path="alerts" element={<AlertHistory />} />
          <Route path="risk-control" element={<RiskControlPage />} />
          <Route path="ai-analysis" element={<MarketAnalysisPage />} />
          <Route path="ai-config" element={<AIConfigManagement />} />
          <Route path="api-config" element={<APIConfigManagement />} />
          <Route path="settings" element={<Settings />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

function App() {
  const { i18n } = useTranslation()

  // 根据当前语言选择Ant Design locale
  const antdLocale = i18n.language === 'en-US' ? enUS : zhCN

  return (
    <QueryClientProvider client={queryClient}>
      <ConfigProvider
        locale={antdLocale}
        theme={{
          algorithm: theme.darkAlgorithm,
          token: {
            colorPrimary: '#1890ff',
            colorBgBase: '#0d0d0d',
            colorBgContainer: '#1a1a1a',
            colorBgElevated: '#222222',
            colorBorder: '#2a2a2a',
            colorText: '#e5e5e5',
            colorTextSecondary: '#a3a3a3',
            colorTextTertiary: '#737373',
            borderRadius: 4,
            fontSize: 14,
            fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
          },
          components: {
            Card: {
              colorBgContainer: '#1a1a1a',
              colorBorderSecondary: '#2a2a2a',
            },
            Table: {
              colorBgContainer: 'transparent',
              colorBorderSecondary: '#2a2a2a',
            },
          },
        }}
      >
        <AntApp>
          <AppContent />
        </AntApp>
      </ConfigProvider>
    </QueryClientProvider>
  )
}

export default App
