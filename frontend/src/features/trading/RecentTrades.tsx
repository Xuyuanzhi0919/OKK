import { useEffect, useState } from 'react'
import { Spin } from 'antd'
import { TrendingUp, TrendingDown } from 'lucide-react'
import { wsService, TradesData } from '@/services/websocket'
import { formatPrice, formatQuantityDisplay } from '@/utils/format'

interface RecentTradesProps {
  symbol: string
  maxTrades?: number
}

export default function RecentTrades({ symbol, maxTrades = 50 }: RecentTradesProps) {
  const [trades, setTrades] = useState<TradesData['trades']>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // 订阅WebSocket数据
    wsService.subscribe(symbol)

    // 监听trades数据
    const unsubscribe = wsService.onTrades(symbol, (data) => {
      setTrades((prevTrades) => {
        // 合并新数据并保持最新的maxTrades条
        const newTrades = [...data.trades, ...prevTrades].slice(0, maxTrades)
        return newTrades
      })
      setLoading(false)
    })

    // 清理函数
    return () => {
      unsubscribe()
      wsService.unsubscribe(symbol)
    }
  }, [symbol, maxTrades])

  if (loading && trades.length === 0) {
    return (
      <div style={{ padding: '40px 0', textAlign: 'center' }}>
        <Spin tip="Loading..." />
      </div>
    )
  }

  if (trades.length === 0) {
    return (
      <div style={{ padding: '40px 0', textAlign: 'center', color: '#737373' }}>
        No recent trades
      </div>
    )
  }

  return (
    <div style={{ fontSize: 12 }}>
      {/* 表头 */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '100px 1fr 1fr 60px',
          padding: '8px 12px',
          borderBottom: '1px solid #2a2a2a',
          fontSize: 10,
          fontWeight: 600,
          color: '#737373',
          textTransform: 'uppercase',
          position: 'sticky',
          top: 0,
          background: '#1a1a1a',
          zIndex: 1,
        }}
      >
        <div style={{ textAlign: 'left' }}>Time</div>
        <div style={{ textAlign: 'right' }}>Price (USDT)</div>
        <div style={{ textAlign: 'right' }}>Amount</div>
        <div style={{ textAlign: 'center' }}>Side</div>
      </div>

      {/* 成交记录列表 */}
      <div>
        {trades.map((trade) => {
          const isBuy = trade.side === 'buy'
          const tradeTime = new Date(trade.ts).toLocaleTimeString('en-US', {
            hour12: false,
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
          })

          return (
            <div
              key={`${trade.tradeId}-${trade.ts}`}
              style={{
                display: 'grid',
                gridTemplateColumns: '100px 1fr 1fr 60px',
                padding: '4px 12px',
                fontFamily: 'monospace',
                fontSize: 11,
                transition: 'background 0.15s',
                animation: 'fadeIn 0.3s ease-in',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = isBuy
                  ? 'rgba(34, 197, 94, 0.05)'
                  : 'rgba(239, 68, 68, 0.05)'
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = 'transparent'
              }}
            >
              <div style={{ color: '#737373' }}>{tradeTime}</div>
              <div
                style={{
                  textAlign: 'right',
                  color: isBuy ? '#22c55e' : '#ef4444',
                  fontWeight: 600,
                }}
              >
                {formatPrice(trade.price)}
              </div>
              <div style={{ textAlign: 'right', color: '#e5e5e5' }}>
                {formatQuantityDisplay(trade.size)}
              </div>
              <div style={{ textAlign: 'center' }}>
                {isBuy ? (
                  <TrendingUp size={10} style={{ color: '#22c55e' }} />
                ) : (
                  <TrendingDown size={10} style={{ color: '#ef4444' }} />
                )}
              </div>
            </div>
          )
        })}
      </div>

      <style>{`
        @keyframes fadeIn {
          from {
            opacity: 0;
            background: ${trades[0]?.side === 'buy' ? 'rgba(34, 197, 94, 0.2)' : 'rgba(239, 68, 68, 0.2)'};
          }
          to {
            opacity: 1;
            background: transparent;
          }
        }
      `}</style>
    </div>
  )
}
