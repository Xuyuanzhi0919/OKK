import { useEffect, useState } from 'react'
import { Row, Col, Card, Table, Spin, message, Button, Statistic, Progress, Tag } from 'antd'
import {
  TrendingUp,
  TrendingDown,
  RefreshCw,
  DollarSign,
  Wifi,
  Clock,
} from 'lucide-react'
import type { ColumnsType } from 'antd/es/table'
import { accountApi, marketApi, strategyApi, orderApi } from '@/services/api'
import { wsService, StrategyUpdateData, StrategyStatsData, OrderUpdateData, BalanceUpdateData, PositionsUpdateData } from '@/services/websocket'
import { useTranslation } from 'react-i18next'
import { formatPrice, formatQuantityDisplay, formatAmount, formatPercent } from '@/utils/format'

const Dashboard = () => {
  const { t } = useTranslation()
  const [loading, setLoading] = useState(true)
  const [balance, setBalance] = useState<any>(null)
  const [positions, setPositions] = useState<any[]>([])
  const [positionsWithPrice, setPositionsWithPrice] = useState<any[]>([])
  const [strategies, setStrategies] = useState<any[]>([])
  const [runningStrategies, setRunningStrategies] = useState<any[]>([])
  const [wsConnected, setWsConnected] = useState(false)
  const [lastUpdateTime, setLastUpdateTime] = useState<Date>(new Date())
  const [currentTime, setCurrentTime] = useState<Date>(new Date())
  const [recentOrders, setRecentOrders] = useState<any[]>([])

  // 格式化相对时间
  const getRelativeTime = (date: Date): string => {
    const seconds = Math.floor((currentTime.getTime() - date.getTime()) / 1000)
    if (seconds < 5) return '刚刚'
    if (seconds < 60) return `${seconds}秒前`
    const minutes = Math.floor(seconds / 60)
    if (minutes < 60) return `${minutes}分钟前`
    const hours = Math.floor(minutes / 60)
    if (hours < 24) return `${hours}小时前`
    return `${Math.floor(hours / 24)}天前`
  }

  // 获取账户数据
  const fetchDashboardData = async () => {
    try {
      setLoading(true)

      // 并行获取余额、持仓、策略和最近订单
      const [balanceData, positionsData, strategiesData, ordersData] = await Promise.all([
        accountApi.getBalance().catch((err) => {
          return null
        }),
        accountApi.getPositions().catch((err) => {
          return []
        }),
        strategyApi.getList().catch((err) => {
          return { items: [] }
        }),
        orderApi.getList({ status: 'filled', limit: 10 }).catch((err) => {
          return []
        }),
      ])

      setBalance(balanceData)

      // 从余额数据中提取现货余额显示为"持仓"
      const spotBalances: any[] = []
      if (balanceData && balanceData.details) {
        for (const detail of balanceData.details) {
          const eq = parseFloat(detail.eq || '0') // 总持仓数量（包含可用+锁定）
          const eqUsd = parseFloat(detail.eqUsd || '0')
          const accAvgPx = parseFloat(detail.accAvgPx || '0') // OKX提供的累计成本均价

          // 只显示价值大于0.5 USDT的币种，排除USDT
          if (eqUsd > 0.5 && detail.ccy !== 'USDT') {
            spotBalances.push({
              ccy: detail.ccy,
              eq, // 使用总持仓而不是可用余额
              eqUsd,
              accAvgPx, // 保存OKX的成本均价
              spotUpl: parseFloat(detail.spotUpl || '0'),
            })
          }
        }
      }

      // 获取每个现货币种的当前价格
      const spotPositions: any[] = []
      if (spotBalances.length > 0) {
        const balancesWithPrices = await Promise.all(
          spotBalances.map(async (bal: any) => {
            try {
              const symbol = `${bal.ccy}-USDT`
              const ticker = await marketApi.getTicker(symbol)
              const currentPrice = parseFloat((ticker as any)?.last || '0')

              // 使用OKX提供的成本均价，如果没有则使用当前价格作为参考
              const avgPrice = bal.accAvgPx > 0 ? bal.accAvgPx : currentPrice

              return {
                key: `spot-${bal.ccy}`,
                type: 'SPOT',
                symbol: symbol,
                amount: bal.eq, // 使用总持仓数量
                avgPrice: avgPrice, // 使用OKX的成本均价
                currentPrice: currentPrice,
                profit: bal.spotUpl,
                profitPercent: bal.eqUsd > 0 ? (bal.spotUpl / bal.eqUsd) * 100 : 0,
                value: bal.eqUsd,
              }
            } catch (error) {
              return {
                key: `spot-${bal.ccy}`,
                type: 'SPOT',
                symbol: `${bal.ccy}-USDT`,
                amount: bal.eq, // 使用总持仓数量
                avgPrice: bal.accAvgPx || 0, // 使用OKX的成本均价
                currentPrice: 0,
                profit: bal.spotUpl,
                profitPercent: 0,
                value: bal.eqUsd,
              }
            }
          })
        )
        spotPositions.push(...balancesWithPrices)
      }

      // 处理合约持仓数据
      const positions = Array.isArray(positionsData) ? positionsData : []
      const contractPositions: any[] = []

      if (positions.length > 0) {
        for (const pos of positions) {
          try {
            const posData = pos as any
            // 后端返回的格式: symbol, avg_price, size, current_price, unrealized_pnl等
            const symbol = posData.symbol || posData.instId
            const ticker = await marketApi.getTicker(symbol)
            const currentPrice = posData.current_price || parseFloat((ticker as any)?.last || '0')
            const avgPx = posData.avg_price || parseFloat(posData.avgPx || '0')
            const posSize = posData.size || parseFloat(posData.pos || '0')
            const upl = posData.unrealized_pnl || parseFloat(posData.upl || '0')
            const uplRatio = posData.unrealized_pnl_pct || parseFloat(posData.uplRatio || '0') * 100

            // 计算持仓价值 (如果后端没返回)
            const value = posSize * currentPrice

            contractPositions.push({
              key: `contract-${symbol}`,
              type: 'SWAP', // 永续合约
              symbol: symbol,
              amount: posSize,
              avgPrice: avgPx,
              currentPrice: currentPrice,
              profit: upl,
              profitPercent: uplRatio,
              value: value,
            })
          } catch (error) {
            const posData = pos as any
            // 处理错误,跳过该持仓
          }
        }
      }

      // 合并现货和合约持仓
      const allPositions = [...spotPositions, ...contractPositions]
      setPositionsWithPrice(allPositions)
      setPositions(positions)

      // 处理策略数据
      const allStrategies = (strategiesData as any)?.items || []
      setStrategies(allStrategies)

      // 筛选出运行中的策略
      const running = allStrategies.filter((s: any) => s.status === 'running')
      setRunningStrategies(running)

      // 处理订单数据 (只显示最近10条已成交订单)
      const orders = Array.isArray(ordersData) ? ordersData : []
      setRecentOrders(orders.slice(0, 10))
    } catch (error) {
      message.error((error as Error).message || t('dashboard.fetchDataFailed'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchDashboardData()
    const timer = setInterval(fetchDashboardData, 30000)

    // 每秒更新当前时间（用于相对时间显示）
    const timeUpdateTimer = setInterval(() => {
      setCurrentTime(new Date())
    }, 1000)

    // 订阅所有策略的实时更新
    wsService.subscribeAllStrategies()

    // 立即检查当前WebSocket连接状态
    setWsConnected(wsService.isConnected())

    // 监听WebSocket连接状态
    const unsubscribeConnect = wsService.onConnect(() => {
      setWsConnected(true)
      setLastUpdateTime(new Date()) // 连接成功时更新时间
    })

    const unsubscribeDisconnect = wsService.onDisconnect(() => {
      setWsConnected(false)
    })

    // 监听策略状态更新（每50秒数据库持久化时）
    const unsubscribeUpdate = wsService.onStrategyUpdate((data: StrategyUpdateData) => {
      setLastUpdateTime(new Date()) // 更新时间戳
      // 更新运行中策略列表中的对应策略
      setRunningStrategies((prev) =>
        prev.map((s) =>
          s.id === data.strategy_id
            ? {
                ...s,
                total_profit: data.total_profit,
                total_trades: data.total_trades,
                win_rate: data.win_rate,
              }
            : s
        )
      )
    })

    // 监听策略实时统计（每5秒一次）
    const unsubscribeStats = wsService.onStrategyStats((data: StrategyStatsData) => {
      setLastUpdateTime(new Date()) // 更新时间戳
      // 可以选择在这里更新更详细的统计信息
      setRunningStrategies((prev) =>
        prev.map((s) =>
          s.id === data.strategy_id
            ? {
                ...s,
                // 更新实时统计数据
                _realtime_stats: data,
              }
            : s
        )
      )
    })

    // 监听全局订单更新
    const unsubscribeOrder = wsService.onOrderUpdate((orderData: OrderUpdateData) => {
      setLastUpdateTime(new Date()) // 更新时间戳

      // 根据订单事件显示通知
      const sideText = orderData.side === 'buy' ? '买入' : '卖出'
      const strategyName = runningStrategies.find(s => s.id === orderData.strategy_id)?.name || `策略${orderData.strategy_id}`

      if (orderData.event === 'filled') {
        message.success({
          content: `[${strategyName}] ${sideText}订单已成交: ${orderData.symbol} @ ${formatPrice(orderData.price)}`,
          duration: 3,
        })
      } else if (orderData.event === 'partially_filled') {
        message.info({
          content: `[${strategyName}] ${sideText}订单部分成交: ${orderData.symbol} (${orderData.filled}/${orderData.amount})`,
          duration: 3,
        })
      }
    })

    // 监听余额更新(WebSocket推送)
    const unsubscribeBalance = wsService.onBalanceUpdate((data: BalanceUpdateData) => {
      setLastUpdateTime(new Date())
      // 更新余额数据
      setBalance({
        totalEq: data.total_equity.toString(),
        availBal: data.available_balance.toString(),
        total_upl: data.unrealized_pnl.toString(),
        details: data.details,
      })
    })

    // 监听持仓更新(WebSocket推送)
    const unsubscribePositions = wsService.onPositionsUpdate(async (data: PositionsUpdateData) => {
      setLastUpdateTime(new Date())

      // 转换持仓数据为前端格式
      const contractPositions = await Promise.all(
        data.positions.map(async (pos) => {
          try {
            // 获取当前价格(如果WebSocket没提供或需要更新)
            const ticker = await marketApi.getTicker(pos.symbol)
            const currentPrice = pos.current_price || parseFloat((ticker as any)?.last || '0')

            return {
              key: `contract-${pos.symbol}`,
              type: pos.inst_type || 'SWAP',
              symbol: pos.symbol,
              amount: pos.size,
              avgPrice: pos.avg_price,
              currentPrice: currentPrice,
              profit: pos.unrealized_pnl,
              profitPercent: pos.unrealized_pnl_pct,
              value: pos.size * currentPrice,
            }
          } catch (error) {
            console.error(`获取价格失败 ${pos.symbol}:`, error)
            return {
              key: `contract-${pos.symbol}`,
              type: pos.inst_type || 'SWAP',
              symbol: pos.symbol,
              amount: pos.size,
              avgPrice: pos.avg_price,
              currentPrice: pos.current_price,
              profit: pos.unrealized_pnl,
              profitPercent: pos.unrealized_pnl_pct,
              value: pos.size * pos.current_price,
            }
          }
        })
      )

      // 更新持仓列表(这里只更新合约持仓,现货持仓保持原有逻辑)
      setPositionsWithPrice((prev) => {
        const spotPositions = prev.filter((p) => p.type === 'SPOT')
        return [...spotPositions, ...contractPositions]
      })
    })

    return () => {
      clearInterval(timer)
      clearInterval(timeUpdateTimer)
      unsubscribeConnect()
      unsubscribeDisconnect()
      unsubscribeUpdate()
      unsubscribeStats()
      unsubscribeOrder()
      unsubscribeBalance()
      unsubscribePositions()
      wsService.unsubscribeAllStrategies()
    }
  }, [])

  // 计算统计数据
  const totalAssets = balance ? parseFloat(balance.totalEq || '0') : 0
  const totalUpl = positionsWithPrice.reduce((sum, pos) => sum + (pos.profit || 0), 0)
  const uplPercent = totalAssets > 0 ? (totalUpl / totalAssets) * 100 : 0
  const totalPositionValue = positionsWithPrice.reduce(
    (sum, pos) => sum + (pos.value || 0),
    0
  )

  // 计算所有策略的总盈亏
  const totalStrategyProfit = runningStrategies.reduce((sum, s) => {
    return sum + (s.total_profit || 0)
  }, 0)

  if (loading && !balance) {
    return (
      <div style={{ textAlign: 'center', padding: '100px 0' }}>
        <Spin size="large" tip={t('common.loading')}>
          <div style={{ minHeight: 100 }} />
        </Spin>
      </div>
    )
  }

  const positionColumns: ColumnsType<any> = [
    {
      title: t('dashboard.type').toUpperCase(),
      dataIndex: 'type',
      key: 'type',
      width: 70,
      render: (text) => (
        <Tag
          style={{
            margin: 0,
            fontSize: 10,
            padding: '1px 6px',
            fontWeight: 600,
            border: 'none',
            background: text === 'SPOT' ? 'rgba(24, 144, 255, 0.15)' : 'rgba(245, 158, 11, 0.15)',
            color: text === 'SPOT' ? '#1890ff' : '#f59e0b',
          }}
        >
          {text}
        </Tag>
      ),
    },
    {
      title: t('dashboard.symbol').toUpperCase(),
      dataIndex: 'symbol',
      key: 'symbol',
      width: 140,
      render: (text) => <span style={{ fontWeight: 600 }}>{text}</span>,
    },
    {
      title: t('dashboard.amount').toUpperCase(),
      dataIndex: 'amount',
      key: 'amount',
      width: 120,
      align: 'right',
      render: (value) => (
        <span className="font-mono" style={{ fontSize: 13 }}>
          {formatQuantityDisplay(value)}
        </span>
      ),
    },
    {
      title: t('dashboard.avgPrice').toUpperCase(),
      dataIndex: 'avgPrice',
      key: 'avgPrice',
      width: 130,
      align: 'right',
      render: (value) => (
        <span className="font-mono" style={{ fontSize: 13, color: '#a3a3a3' }}>
          ${formatPrice(value)}
        </span>
      ),
    },
    {
      title: t('dashboard.currentPrice').toUpperCase(),
      dataIndex: 'currentPrice',
      key: 'currentPrice',
      width: 130,
      align: 'right',
      render: (value) => (
        <span className="font-mono" style={{ fontSize: 13, fontWeight: 600 }}>
          ${formatPrice(value)}
        </span>
      ),
    },
    {
      title: t('dashboard.value').toUpperCase(),
      dataIndex: 'value',
      key: 'value',
      width: 110,
      align: 'right',
      render: (value) => (
        <span className="font-mono" style={{ fontSize: 13 }}>
          ${formatAmount(value)}
        </span>
      ),
    },
    {
      title: t('dashboard.pnl').toUpperCase(),
      key: 'profit',
      width: 150,
      align: 'right',
      render: (_, record) => {
        const isProfit = record.profit >= 0
        return (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 4 }}>
            {isProfit ? (
              <TrendingUp size={12} style={{ color: '#22c55e' }} />
            ) : (
              <TrendingDown size={12} style={{ color: '#ef4444' }} />
            )}
            <span className={`font-mono ${isProfit ? 'text-up' : 'text-down'}`} style={{ fontSize: 13 }}>
              {isProfit ? '+' : ''}
              {formatAmount(record.profit)}
            </span>
            <span className={`font-mono ${isProfit ? 'text-up' : 'text-down'}`} style={{ fontSize: 12 }}>
              ({record.profitPercent >= 0 ? '+' : ''}
              {formatPercent(record.profitPercent)}%)
            </span>
          </div>
        )
      },
    },
  ]

  return (
    <div>
      {/* 顶部统计卡片 */}
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={6} xl={4} xxl={4}>
          <Card variant="borderless" size="small" style={{ height: '100%' }}>
            <div style={{ marginBottom: 8 }}>
              <div className="pro-card-header">{t('dashboard.totalEquity').toUpperCase()}</div>
            </div>
            <Statistic
              value={totalAssets}
              precision={2}
              prefix="$"
              valueStyle={{ fontSize: 28, fontWeight: 700, fontFamily: 'monospace' }}
            />
            <div style={{ marginTop: 8, fontSize: 11, color: '#737373' }}>
              <DollarSign size={11} style={{ marginRight: 4 }} />
              {t('dashboard.accountTotalEquity')}
            </div>
          </Card>
        </Col>

        <Col xs={24} sm={12} lg={6} xl={5} xxl={5}>
          <Card variant="borderless" size="small" style={{ height: '100%' }}>
            <div style={{ marginBottom: 8 }}>
              <div className="pro-card-header">{t('dashboard.unrealizedPnl').toUpperCase()}</div>
            </div>
            <Statistic
              value={totalUpl}
              precision={2}
              prefix={totalUpl >= 0 ? <TrendingUp size={16} /> : <TrendingDown size={16} />}
              valueStyle={{
                fontSize: 28,
                fontWeight: 700,
                color: totalUpl >= 0 ? '#22c55e' : '#ef4444',
                fontFamily: 'monospace',
              }}
            />
            <div style={{ marginTop: 8 }}>
              <Progress
                percent={Math.abs(uplPercent)}
                strokeColor={uplPercent >= 0 ? '#22c55e' : '#ef4444'}
                showInfo={false}
                size="small"
              />
              <div style={{ fontSize: 11, color: '#737373', marginTop: 4 }}>
                {uplPercent >= 0 ? '+' : ''}
                {formatPercent(uplPercent)}% {t('dashboard.unrealizedPnlPercent')}
              </div>
            </div>
          </Card>
        </Col>

        <Col xs={24} sm={12} lg={6} xl={5} xxl={5}>
          <Card variant="borderless" size="small" style={{ height: '100%' }}>
            <div style={{ marginBottom: 8 }}>
              <div className="pro-card-header">策略总盈亏</div>
            </div>
            <Statistic
              value={totalStrategyProfit}
              precision={2}
              prefix={totalStrategyProfit >= 0 ? <TrendingUp size={16} /> : <TrendingDown size={16} />}
              valueStyle={{
                fontSize: 28,
                fontWeight: 700,
                color: totalStrategyProfit >= 0 ? '#22c55e' : '#ef4444',
                fontFamily: 'monospace',
              }}
            />
            <div style={{ marginTop: 8, fontSize: 11, color: '#737373' }}>
              {runningStrategies.length} 个策略运行中
            </div>
          </Card>
        </Col>

        <Col xs={24} sm={12} lg={6} xl={5} xxl={5}>
          <Card variant="borderless" size="small" style={{ height: '100%' }}>
            <div style={{ marginBottom: 8 }}>
              <div className="pro-card-header">{t('dashboard.positions').toUpperCase()}</div>
            </div>
            <Statistic
              value={positionsWithPrice.length}
              valueStyle={{ fontSize: 28, fontWeight: 700, fontFamily: 'monospace' }}
              suffix={
                <span style={{ fontSize: 14, color: '#737373' }}>
                  /{positionsWithPrice.length}
                </span>
              }
            />
            <div style={{ marginTop: 8, fontSize: 11, color: '#737373' }}>
              {t('dashboard.positionCount')}
            </div>
          </Card>
        </Col>

        <Col xs={24} sm={12} lg={6} xl={5} xxl={5}>
          <Card variant="borderless" size="small" style={{ height: '100%' }}>
            <div style={{ marginBottom: 8 }}>
              <div className="pro-card-header">{t('dashboard.positionValue').toUpperCase()}</div>
            </div>
            <Statistic
              value={totalPositionValue}
              precision={2}
              prefix="$"
              valueStyle={{ fontSize: 28, fontWeight: 700, fontFamily: 'monospace' }}
            />
            <div style={{ marginTop: 8, fontSize: 11, color: '#737373' }}>
              {t('dashboard.positionValue')}
            </div>
          </Card>
        </Col>
      </Row>

      {/* 持仓列表 */}
      <Card
        title={
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div className="pro-card-header" style={{ margin: 0 }}>
              {t('dashboard.positions').toUpperCase()}
            </div>
            <Tag
              style={{
                margin: 0,
                fontSize: 10,
                padding: '1px 6px',
                fontWeight: 600,
                border: 'none',
                background: 'rgba(24, 144, 255, 0.15)',
                color: '#1890ff',
              }}
            >
              {positionsWithPrice.length}
            </Tag>
          </div>
        }
        extra={
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            {/* WebSocket连接状态 */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: '50%',
                  backgroundColor: wsConnected ? '#22c55e' : '#ef4444',
                  animation: wsConnected ? 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite' : 'none',
                }}
              />
              <Wifi size={12} style={{ color: wsConnected ? '#22c55e' : '#ef4444' }} />
              <span style={{ fontSize: 11, color: '#a3a3a3' }}>
                {wsConnected ? '实时推送' : '已断线'}
              </span>
            </div>

            {/* 最后更新时间 */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <Clock size={11} style={{ color: '#a3a3a3' }} />
              <span style={{ fontSize: 11, color: '#a3a3a3' }}>
                {getRelativeTime(lastUpdateTime)}
              </span>
            </div>

            {/* 刷新按钮 */}
            <Button
              type="text"
              size="small"
              icon={<RefreshCw size={14} className={loading ? 'animate-spin' : ''} />}
              onClick={fetchDashboardData}
              style={{ color: '#a3a3a3' }}
            >
              {t('common.refresh')}
            </Button>
          </div>
        }
        variant="borderless"
        size="small"
        style={{ marginTop: 16 }}
      >
        <Table
          columns={positionColumns}
          dataSource={positionsWithPrice}
          loading={loading}
          pagination={false}
          size="small"
          scroll={{ x: 800 }}
          locale={{
            emptyText: (
              <div style={{ padding: '40px 0', color: '#737373' }}>
                <div style={{ fontSize: 48, marginBottom: 8 }}>📊</div>
                <div>{t('dashboard.noPositions')}</div>
              </div>
            ),
          }}
        />
      </Card>

      {/* 策略状态 */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={24} md={12}>
          <Card
            title={
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div className="pro-card-header" style={{ margin: 0 }}>
                  {t('strategy.strategies').toUpperCase()}
                </div>
                <Tag
                  style={{
                    margin: 0,
                    fontSize: 10,
                    padding: '1px 6px',
                    fontWeight: 600,
                    border: 'none',
                    background: 'rgba(34, 197, 94, 0.15)',
                    color: '#22c55e',
                  }}
                >
                  {runningStrategies.length} RUNNING
                </Tag>
              </div>
            }
            variant="borderless"
            size="small"
          >
            {runningStrategies.length === 0 ? (
              <div style={{ padding: '20px 0', textAlign: 'center', color: '#737373' }}>
                <div style={{ fontSize: 32, marginBottom: 8 }}>⚡</div>
                <div>{t('dashboard.noRunningStrategies')}</div>
              </div>
            ) : (
              <div>
                {runningStrategies.map((strategy: any) => (
                  <div
                    key={strategy.id}
                    style={{
                      padding: '12px',
                      marginBottom: 8,
                      background: '#1a1a1a',
                      borderRadius: 4,
                      border: '1px solid #2a2a2a',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: 8 }}>
                      <div>
                        <div style={{ fontWeight: 600, marginBottom: 4 }}>{strategy.name}</div>
                        <div style={{ fontSize: 12, color: '#737373' }}>
                          {strategy.symbol} · {strategy.type.toUpperCase()}
                        </div>
                      </div>
                      <Tag
                        style={{
                          margin: 0,
                          fontSize: 10,
                          padding: '2px 8px',
                          fontWeight: 600,
                          border: 'none',
                          background: 'rgba(34, 197, 94, 0.15)',
                          color: '#22c55e',
                        }}
                      >
                        RUNNING
                      </Tag>
                    </div>
                    <Row gutter={8}>
                      <Col span={12}>
                        <div style={{ fontSize: 11, color: '#737373' }}>盈亏</div>
                        <div
                          className={`font-mono ${(strategy.total_profit || 0) >= 0 ? 'text-up' : 'text-down'}`}
                          style={{ fontSize: 14, fontWeight: 600 }}
                        >
                          {(strategy.total_profit || 0) >= 0 ? '+' : ''}$
                          {formatAmount(strategy.total_profit || 0)}
                        </div>
                      </Col>
                      <Col span={12}>
                        <div style={{ fontSize: 11, color: '#737373' }}>交易次数</div>
                        <div className="font-mono" style={{ fontSize: 14, fontWeight: 600 }}>
                          {strategy.total_trades || 0}
                        </div>
                      </Col>
                    </Row>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </Col>

        <Col xs={24} md={12}>
          <Card
            title={
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div className="pro-card-header" style={{ margin: 0 }}>
                  {t('dashboard.recentTrades').toUpperCase()}
                </div>
                <Tag
                  style={{
                    margin: 0,
                    fontSize: 10,
                    padding: '1px 6px',
                    fontWeight: 600,
                    border: 'none',
                    background: 'rgba(34, 197, 94, 0.15)',
                    color: '#22c55e',
                  }}
                >
                  {recentOrders.length}
                </Tag>
              </div>
            }
            variant="borderless"
            size="small"
          >
            {recentOrders.length > 0 ? (
              <div style={{ maxHeight: 300, overflowY: 'auto' }}>
                {recentOrders.map((order: any, index: number) => (
                  <div
                    key={order.id || index}
                    style={{
                      padding: '8px 0',
                      borderBottom: index < recentOrders.length - 1 ? '1px solid #f0f0f0' : 'none',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                    }}
                  >
                    <div style={{ flex: 1 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                        <Tag
                          color={order.side === 'buy' ? 'green' : 'red'}
                          style={{ margin: 0, fontSize: 11, padding: '0 4px' }}
                        >
                          {order.side === 'buy' ? '买入' : '卖出'}
                        </Tag>
                        <span style={{ fontSize: 13, fontWeight: 500 }}>{order.symbol}</span>
                        {order.strategy_name && (
                          <Tag style={{ margin: 0, fontSize: 10, padding: '0 4px' }}>
                            {order.strategy_name}
                          </Tag>
                        )}
                      </div>
                      <div style={{ fontSize: 11, color: '#a3a3a3' }}>
                        {new Date(order.created_at).toLocaleString('zh-CN', {
                          month: '2-digit',
                          day: '2-digit',
                          hour: '2-digit',
                          minute: '2-digit',
                        })}
                      </div>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <div style={{ fontSize: 13, fontWeight: 500 }}>
                        {formatPrice(order.avg_price || order.price)}
                      </div>
                      <div style={{ fontSize: 11, color: '#a3a3a3' }}>
                        {formatQuantityDisplay(order.filled_size || order.size || order.amount)}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div style={{ padding: '20px 0', textAlign: 'center', color: '#737373' }}>
                <div style={{ fontSize: 32, marginBottom: 8 }}>📈</div>
                <div>{t('dashboard.noRecentTrades')}</div>
              </div>
            )}
          </Card>
        </Col>
      </Row>
    </div>
  )
}

export default Dashboard
