import { Modal, Descriptions, Statistic, Row, Col, Card, Table, Tag, Space, Spin, Tabs } from 'antd'
import { TrendingUp, TrendingDown, List, BarChart3 } from 'lucide-react'
import type { ColumnsType } from 'antd/es/table'
import { Strategy, Order } from '@/types'
import { useTranslation } from 'react-i18next'
import { useState, useEffect } from 'react'
import { strategyApi } from '@/services/api'
import { wsService, StrategyStatsData, StrategyUpdateData, OrderUpdateData } from '@/services/websocket'
import { formatPrice, formatQuantityDisplay, formatPercent } from '@/utils/format'
import StrategyOrderHistory from './StrategyOrderHistory'

interface StrategyDetailModalProps {
  open: boolean
  strategy: Strategy | null
  onCancel: () => void
}

export default function StrategyDetailModal({ open, strategy, onCancel }: StrategyDetailModalProps) {
  const { t } = useTranslation()
  const [loading, setLoading] = useState(false)
  const [strategyDetail, setStrategyDetail] = useState<any>(null)
  const [pnlData, setPnlData] = useState<any>(null)

  // 获取策略实时统计数据
  const fetchStrategyStats = async () => {
    if (!strategy) return

    try {
      setLoading(true)
      const stats = await strategyApi.getStats(strategy.id)
      setStrategyDetail(stats)
    } catch (error) {
      // 处理错误
    } finally {
      setLoading(false)
    }
  }

  // 获取策略盈亏数据
  const fetchPnlData = async () => {
    if (!strategy) return

    try {
      const pnl = await strategyApi.getPnl(strategy.id)
      setPnlData(pnl)
    } catch (error) {
      // 处理错误
    }
  }

  // 当Modal打开时获取初始数据并订阅WebSocket实时更新
  useEffect(() => {
    if (open && strategy) {
      // 初始数据加载
      fetchStrategyStats()
      fetchPnlData()

      // 订阅该策略的实时更新
      wsService.subscribeStrategy(strategy.id)

      // 监听策略状态更新（每50秒数据库持久化时）
      const unsubscribeUpdate = wsService.onSingleStrategyUpdate(
        strategy.id,
        (data: StrategyUpdateData) => {
          // 可以在这里更新策略的基本信息
        }
      )

      // 监听策略实时统计（每5秒一次）
      const unsubscribeStats = wsService.onSingleStrategyStats(
        strategy.id,
        (data: StrategyStatsData) => {
          // 实时更新策略统计数据
          setStrategyDetail(data)
        }
      )

      // 监听订单更新
      const unsubscribeOrder = wsService.onSingleOrderUpdate(
        strategy.id,
        (orderData: OrderUpdateData) => {
          // 订单状态变化，立即刷新盈亏数据
          fetchPnlData()
        }
      )

      // 定时刷新盈亏数据（每30秒一次）
      const pnlInterval = setInterval(() => {
        fetchPnlData()
      }, 30000)

      return () => {
        unsubscribeUpdate()
        unsubscribeStats()
        unsubscribeOrder()
        wsService.unsubscribeStrategy(strategy.id)
        clearInterval(pnlInterval)
      }
    }
  }, [open, strategy])

  if (!strategy) return null

  // 合并真实数据和默认数据
  const displayData = strategyDetail || {
    is_running: false,
    position_size: 0,
    position_cost: 0,
    realized_pnl: 0,
    total_trades: 0,
    total_buy_volume: 0,
    total_sell_volume: 0,
    grid_orders: 0,
  }

  // 计算显示数据 - 优先使用PNL API返回的数据
  const realized_pnl = pnlData?.realized_pnl ?? displayData.realized_pnl ?? 0
  const unrealized_pnl = pnlData?.unrealized_pnl ?? 0
  const total_pnl = pnlData?.total_pnl ?? (realized_pnl + unrealized_pnl)
  const pnl_rate = pnlData?.pnl_rate ?? 0
  const total_fee = pnlData?.total_fee ?? 0

  // 持仓信息 - 优先使用PNL API返回的精确数据
  const current_position = pnlData?.current_position ?? displayData.position_size ?? 0
  const position_value = pnlData?.position_value ?? displayData.position_cost ?? 0
  const avg_buy_price = pnlData?.avg_buy_price ?? 0
  const avg_sell_price = pnlData?.avg_sell_price ?? 0
  const avg_cost = current_position > 0 && position_value > 0
    ? position_value / current_position
    : avg_buy_price

  // 交易统计 - 优先使用PNL API返回的数据
  const buy_count = pnlData?.buy_count ?? 0
  const sell_count = pnlData?.sell_count ?? 0
  const total_trades = buy_count + sell_count
  const total_buy_amount = pnlData?.total_buy_amount ?? displayData.total_buy_volume ?? 0
  const total_sell_amount = pnlData?.total_sell_amount ?? displayData.total_sell_volume ?? 0

  const gridOrderColumns: ColumnsType<any> = [
    {
      title: t('strategy.gridIndex'),
      dataIndex: 'grid_index',
      key: 'grid_index',
      width: 100,
    },
    {
      title: t('strategy.buyPrice'),
      dataIndex: 'buy_price',
      key: 'buy_price',
      width: 120,
      render: (price) => <span className="font-mono">${formatPrice(price)}</span>,
    },
    {
      title: t('strategy.buyStatus'),
      dataIndex: 'buy_status',
      key: 'buy_status',
      width: 100,
      render: (status) => {
        if (!status) return <Tag>-</Tag>
        const color = status === 'filled' ? 'success' : status === 'open' ? 'processing' : 'default'
        return <Tag color={color}>{status.toUpperCase()}</Tag>
      },
    },
    {
      title: t('strategy.sellPrice'),
      dataIndex: 'sell_price',
      key: 'sell_price',
      width: 120,
      render: (price) => price ? <span className="font-mono">${formatPrice(price)}</span> : '-',
    },
    {
      title: t('strategy.sellStatus'),
      dataIndex: 'sell_status',
      key: 'sell_status',
      width: 100,
      render: (status) => {
        if (!status) return <Tag>-</Tag>
        const color = status === 'filled' ? 'success' : status === 'open' ? 'processing' : 'default'
        return <Tag color={color}>{status.toUpperCase()}</Tag>
      },
    },
  ]

  // Tab标签页配置
  const tabItems = [
    {
      key: 'stats',
      label: (
        <span>
          <BarChart3 size={14} />
          统计概览
        </span>
      ),
      children: (
        <div>
          {/* 盈亏统计 */}
          <Card title="实时盈亏" variant="borderless" style={{ marginBottom: 16 }}>
            <Row gutter={16} style={{ marginBottom: 16 }}>
              <Col span={6}>
                <Statistic
                  title="总盈亏"
                  value={total_pnl}
                  precision={2}
                  valueStyle={{
                    color: total_pnl >= 0 ? '#22c55e' : '#ef4444',
                    fontWeight: 600,
                    fontSize: 20,
                  }}
                  prefix={total_pnl >= 0 ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                  suffix="USDT"
                />
              </Col>
              <Col span={6}>
                <Statistic
                  title="收益率"
                  value={pnl_rate}
                  precision={2}
                  valueStyle={{
                    color: pnl_rate >= 0 ? '#22c55e' : '#ef4444',
                    fontWeight: 600,
                    fontSize: 20,
                  }}
                  prefix={pnl_rate >= 0 ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                  suffix="%"
                />
              </Col>
              <Col span={6}>
                <Statistic
                  title={t('strategy.realizedPnl')}
                  value={realized_pnl}
                  precision={2}
                  valueStyle={{
                    color: realized_pnl >= 0 ? '#22c55e' : '#ef4444',
                    fontSize: 18,
                  }}
                  prefix={realized_pnl >= 0 ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                  suffix="USDT"
                />
              </Col>
              <Col span={6}>
                <Statistic
                  title={t('strategy.unrealizedPnl')}
                  value={unrealized_pnl}
                  precision={2}
                  valueStyle={{
                    color: unrealized_pnl >= 0 ? '#22c55e' : '#ef4444',
                    fontSize: 18,
                  }}
                  prefix={unrealized_pnl >= 0 ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                  suffix="USDT"
                />
              </Col>
            </Row>
            <Row gutter={16}>
              <Col span={6}>
                <Statistic
                  title="总手续费"
                  value={total_fee}
                  precision={2}
                  valueStyle={{
                    color: '#f59e0b',
                    fontSize: 16,
                  }}
                  suffix="USDT"
                />
              </Col>
              <Col span={6}>
                <Statistic
                  title="买入次数"
                  value={pnlData?.buy_count ?? 0}
                  valueStyle={{
                    color: '#22c55e',
                    fontSize: 16,
                  }}
                />
              </Col>
              <Col span={6}>
                <Statistic
                  title="卖出次数"
                  value={pnlData?.sell_count ?? 0}
                  valueStyle={{
                    color: '#ef4444',
                    fontSize: 16,
                  }}
                />
              </Col>
              <Col span={6}>
                <Statistic
                  title="成交次数"
                  value={(pnlData?.buy_count ?? 0) + (pnlData?.sell_count ?? 0)}
                  valueStyle={{
                    color: '#3b82f6',
                    fontSize: 16,
                  }}
                />
              </Col>
            </Row>
          </Card>

          {/* 持仓信息 */}
          <Card title={t('strategy.positionInfo')} variant="borderless" size="small" style={{ marginBottom: 16 }}>
            <Descriptions column={2} size="small">
              <Descriptions.Item label={t('strategy.positionSize')}>
                <span className="font-mono" style={{ fontWeight: 600 }}>
                  {formatQuantityDisplay(current_position) || '0'}
                </span>
              </Descriptions.Item>
              <Descriptions.Item label={t('strategy.positionCost')}>
                <span className="font-mono" style={{ fontWeight: 600 }}>
                  ${position_value ? formatPrice(position_value) : '0.00'}
                </span>
              </Descriptions.Item>
              <Descriptions.Item label={t('strategy.avgCost')}>
                <span className="font-mono" style={{ fontWeight: 600 }}>
                  ${formatPrice(avg_cost)}
                </span>
              </Descriptions.Item>
              <Descriptions.Item label={t('strategy.winRate')}>
                <span style={{
                  fontWeight: 600,
                  color: (strategy.win_rate ?? 0) >= 50 ? '#22c55e' : '#ef4444'
                }}>
                  {formatPercent(strategy.win_rate ?? 0, 1)}%
                </span>
              </Descriptions.Item>
            </Descriptions>
          </Card>

          {/* 交易统计 */}
          <Card title={t('strategy.tradingStats')} variant="borderless" size="small" style={{ marginBottom: 16 }}>
            <Row gutter={16}>
              <Col span={6}>
                <Statistic title={t('strategy.totalTrades')} value={total_trades || 0} />
              </Col>
              <Col span={6}>
                <Statistic
                  title={t('strategy.buyVolume')}
                  value={total_buy_amount || 0}
                  precision={2}
                  valueStyle={{ color: '#22c55e' }}
                  suffix="USDT"
                />
              </Col>
              <Col span={6}>
                <Statistic
                  title={t('strategy.sellVolume')}
                  value={total_sell_amount || 0}
                  precision={2}
                  valueStyle={{ color: '#ef4444' }}
                  suffix="USDT"
                />
              </Col>
              <Col span={6}>
                <Statistic
                  title={t('strategy.gridOrders')}
                  value={displayData.grid_orders || 0}
                  suffix={
                    <span style={{ fontSize: '14px', marginLeft: '4px', whiteSpace: 'nowrap' }}>
                      {displayData.is_running ? t('strategy.active') : t('strategy.inactive')}
                    </span>
                  }
                  valueStyle={{ display: 'flex', alignItems: 'center' }}
                />
              </Col>
            </Row>
          </Card>

          {/* 网格挂单 (仅网格策略显示) */}
          {strategy.type === 'grid' && (
            <Card title={t('strategy.gridOrders')} variant="borderless" size="small">
              <Table
                columns={gridOrderColumns}
                dataSource={displayData.grid_orders_detail || []}
                pagination={false}
                size="small"
                rowKey="grid_index"
                locale={{ emptyText: displayData.is_running ? '暂无订单数据' : '策略未运行' }}
              />
            </Card>
          )}
        </div>
      ),
    },
    {
      key: 'orders',
      label: (
        <span>
          <List size={14} />
          订单历史
        </span>
      ),
      children: <StrategyOrderHistory strategyId={strategy.id} />,
    },
  ]

  return (
    <Modal
      title={
        <div className="pro-card-header" style={{ margin: 0 }}>
          {t('strategy.monitor').toUpperCase()} - {strategy.name}
        </div>
      }
      open={open}
      onCancel={onCancel}
      width={1000}
      footer={null}
    >
      <Spin spinning={loading}>
        <Tabs defaultActiveKey="stats" items={tabItems} />
      </Spin>
    </Modal>
  )
}
