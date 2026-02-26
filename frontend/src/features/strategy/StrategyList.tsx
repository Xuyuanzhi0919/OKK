import { Card, Table, Button, Tag, Space, App, Modal, Checkbox, Dropdown } from 'antd'
import {
  Plus,
  Play,
  Pause,
  Trash2,
  Zap,
  Eye,
  AlertCircle,
  BarChart3,
  ChevronDown,
  TrendingUp,
  TrendingDown,
  AppWindow,
  Pencil,
} from 'lucide-react'
import type { ColumnsType } from 'antd/es/table'
import { StrategyStatus, StrategyType, Strategy } from '@/types'
import { useState, useEffect, useRef } from 'react'
import CreateGridStrategyModal from './CreateGridStrategyModal'
import CreateSwingLongStrategyModal from './CreateSwingLongStrategyModal'
import CreateSwingShortStrategyModal from './CreateSwingShortStrategyModal'
import CreateAISwingLongStrategyModal from './CreateAISwingLongStrategyModal'
import StrategyDetailModal from './StrategyDetailModal'
import StrategyPerformanceModal from './StrategyPerformanceModal'
import { strategyApi } from '@/services/api'
import { useTranslation } from 'react-i18next'
import { wsService, StrategyUpdateData } from '@/services/websocket'
import { formatPrice, formatPercent } from '@/utils/format'

const StrategyList = () => {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const [strategies, setStrategies] = useState<Strategy[]>([])
  const [loading, setLoading] = useState(false)
  const [createGridModalOpen, setCreateGridModalOpen] = useState(false)
  const [createSwingModalOpen, setCreateSwingModalOpen] = useState(false)
  const [createSwingShortModalOpen, setCreateSwingShortModalOpen] = useState(false)
  const [createAISwingModalOpen, setCreateAISwingModalOpen] = useState(false)
  const [editGridModalOpen, setEditGridModalOpen] = useState(false)
  const [editSwingModalOpen, setEditSwingModalOpen] = useState(false)
  const [editSwingShortModalOpen, setEditSwingShortModalOpen] = useState(false)
  const [editAISwingModalOpen, setEditAISwingModalOpen] = useState(false)
  const [detailModalOpen, setDetailModalOpen] = useState(false)
  const [performanceModalOpen, setPerformanceModalOpen] = useState(false)
  const [selectedStrategy, setSelectedStrategy] = useState<Strategy | null>(null)
  const [actionLoading, setActionLoading] = useState<{ [key: number]: boolean }>({})
  const [profitChanges, setProfitChanges] = useState<{ [key: number]: 'up' | 'down' | null }>({})
  const previousProfitsRef = useRef<{ [key: number]: number }>({})

  // 获取策略列表
  const fetchStrategies = async (silent: boolean = false) => {
    try {
      setLoading(true)
      const response = await strategyApi.getList()
      const data = (response as any).data || response
      setStrategies(data.items || [])
    } catch (error) {
      if (!silent) {
        message.error(t('strategy.fetchStrategiesFailed'))
      }
    } finally {
      setLoading(false)
    }
  }

  // 组件挂载时获取数据并订阅WebSocket更新
  useEffect(() => {
    fetchStrategies()

    // 订阅所有策略的实时更新
    wsService.subscribeAllStrategies()

    // 监听策略状态更新（每50秒数据库持久化时）- 包含 total_profit 和 win_rate
    const unsubscribeUpdate = wsService.onStrategyUpdate((data: StrategyUpdateData) => {
      // 检测盈亏变化并触发动画
      const previousProfit = previousProfitsRef.current[data.strategy_id]
      if (previousProfit !== undefined && previousProfit !== data.total_profit) {
        const changeDirection = data.total_profit > previousProfit ? 'up' : 'down'
        setProfitChanges(prev => ({ ...prev, [data.strategy_id]: changeDirection }))

        // 1秒后清除动画状态
        setTimeout(() => {
          setProfitChanges(prev => ({ ...prev, [data.strategy_id]: null }))
        }, 1000)
      }

      // 更新盈亏记录
      previousProfitsRef.current[data.strategy_id] = data.total_profit

      setStrategies((prevStrategies) =>
        prevStrategies.map((strategy) =>
          strategy.id === data.strategy_id
            ? {
                ...strategy,
                total_profit: data.total_profit,
                total_trades: data.total_trades,
                win_rate: data.win_rate,
                status: data.status as StrategyStatus,
              }
            : strategy
        )
      )
    })

    // 监听策略统计数据（每5秒）- 包含 total_trades（更高频更新）
    const unsubscribeStats = wsService.onStrategyStats((data) => {
      setStrategies((prevStrategies) =>
        prevStrategies.map((strategy) =>
          strategy.id === data.strategy_id
            ? {
                ...strategy,
                total_trades: data.total_trades, // 每5秒更新交易次数
                // 注意：strategy_stats 没有 total_profit 和 win_rate，这些由 strategy_update 提供
              }
            : strategy
        )
      )
    })

    // 组件卸载时清理
    return () => {
      unsubscribeUpdate()
      unsubscribeStats()
      wsService.unsubscribeAllStrategies()
    }
  }, [])

  const statusColorMap: Record<string, any> = {
    [StrategyStatus.RUNNING]: { bg: 'rgba(34, 197, 94, 0.15)', color: '#22c55e' },
    [StrategyStatus.STOPPED]: { bg: 'rgba(115, 115, 115, 0.15)', color: '#737373' },
    [StrategyStatus.PAUSED]: { bg: 'rgba(245, 158, 11, 0.15)', color: '#f59e0b' },
    [StrategyStatus.ERROR]: { bg: 'rgba(239, 68, 68, 0.15)', color: '#ef4444' },
  }

  const statusTextMap: Record<string, string> = {
    [StrategyStatus.RUNNING]: 'RUNNING',
    [StrategyStatus.STOPPED]: 'STOPPED',
    [StrategyStatus.PAUSED]: 'PAUSED',
    [StrategyStatus.ERROR]: 'ERROR',
  }

  const typeTextMap: Record<string, string> = {
    [StrategyType.GRID]: 'GRID',
    [StrategyType.MARTIN]: 'MARTINGALE',
    [StrategyType.TREND]: 'TREND',
    [StrategyType.ARBITRAGE]: 'ARBITRAGE',
    [StrategyType.CUSTOM]: 'CUSTOM',
    [StrategyType.SWING_LONG]: 'SWING LONG',
    [StrategyType.SWING_SHORT]: 'SWING SHORT',
    [StrategyType.AI_SWING_LONG]: 'AI SWING',
  }

  // 启动策略
  const handleStartStrategy = async (id: number) => {
    try {
      setActionLoading({ ...actionLoading, [id]: true })
      await strategyApi.start(id)
      // WebSocket会推送启动成功的详细通知,这里不再显示
      await fetchStrategies(true) // 静默刷新列表,不显示错误
    } catch (error) {
      message.error((error as any)?.response?.data?.message || t('strategy.startStrategyFailed'))
    } finally {
      setActionLoading({ ...actionLoading, [id]: false })
    }
  }

  // 停止策略
  const handleStopStrategy = (id: number, name: string) => {
    let cancelOrders = true // 默认撤销订单

    Modal.confirm({
      title: '停止策略',
      icon: <AlertCircle size={24} />,
      content: (
        <div>
          <p>确定要停止策略 <strong>{name}</strong> 吗？</p>
          <Checkbox
            defaultChecked={true}
            onChange={(e) => {
              cancelOrders = e.target.checked
            }}
          >
            同时撤销所有未成交订单（推荐）
          </Checkbox>
          <p style={{ marginTop: 8, color: '#8c8c8c', fontSize: 12 }}>
            提示：如果不撤销订单，未成交订单将继续在交易所挂单
          </p>
        </div>
      ),
      okText: '确定停止',
      okType: 'primary',
      cancelText: '取消',
      onOk: async () => {
        try {
          setActionLoading({ ...actionLoading, [id]: true })
          await strategyApi.stop(id, cancelOrders)
          // WebSocket会推送停止成功的详细通知,这里不再显示
          await fetchStrategies(true) // 静默刷新列表,不显示错误
        } catch (error) {
          message.error((error as any)?.response?.data?.message || t('strategy.stopStrategyFailed'))
        } finally {
          setActionLoading({ ...actionLoading, [id]: false })
        }
      },
    })
  }

  // 编辑策略
  const handleEditStrategy = (strategy: Strategy) => {
    setSelectedStrategy(strategy)
    if (strategy.type === StrategyType.GRID) {
      setEditGridModalOpen(true)
    } else if (strategy.type === StrategyType.SWING_LONG) {
      setEditSwingModalOpen(true)
    } else if (strategy.type === StrategyType.SWING_SHORT) {
      setEditSwingShortModalOpen(true)
    } else if (strategy.type === StrategyType.AI_SWING_LONG) {
      setEditAISwingModalOpen(true)
    } else {
      message.warning('该策略类型暂不支持编辑')
    }
  }

  // 删除策略
  const handleDeleteStrategy = (id: number, name: string) => {
    Modal.confirm({
      title: '删除策略',
      icon: <AlertCircle size={24} />,
      content: (
        <div>
          <p>
            确定要删除策略 <strong>{name}</strong> 吗？
          </p>
          <div
            style={{
              background: '#fff7e6',
              border: '1px solid #ffd666',
              borderRadius: 4,
              padding: '8px 12px',
              marginTop: 12,
            }}
          >
            <p style={{ margin: 0, color: '#d46b08', fontWeight: 500 }}>
              ⚠️ 删除策略将自动撤销所有未成交订单
            </p>
            <p style={{ margin: '4px 0 0', color: '#8c8c8c', fontSize: 12 }}>
              此操作不可恢复，请谨慎操作
            </p>
          </div>
        </div>
      ),
      okText: '确认删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        try {
          await strategyApi.delete(id)
          message.success('策略已删除')
          await fetchStrategies(true) // 静默刷新列表,不显示错误
        } catch (error) {
          message.error((error as any)?.response?.data?.message || t('strategy.deleteStrategyFailed'))
        }
      },
    })
  }

  const columns: ColumnsType<any> = [
    {
      title: t('strategy.name').toUpperCase(),
      dataIndex: 'name',
      key: 'name',
      width: 200,
      render: (text) => (
        <div>
          <div style={{ fontWeight: 600, marginBottom: 2 }}>{text}</div>
        </div>
      ),
    },
    {
      title: t('strategy.type').toUpperCase(),
      dataIndex: 'type',
      key: 'type',
      width: 120,
      render: (type) => {
        const isAI = type === StrategyType.AI_SWING_LONG
        return (
          <Tag
            style={{
              margin: 0,
              fontSize: 10,
              padding: '2px 8px',
              fontWeight: 600,
              border: 'none',
              background: isAI ? 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)' : 'rgba(24, 144, 255, 0.15)',
              color: isAI ? '#fff' : '#1890ff',
            }}
          >
            {typeTextMap[type]}
          </Tag>
        )
      },
    },
    {
      title: t('strategy.status').toUpperCase(),
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (status) => {
        const style = statusColorMap[status]
        const isRunning = status === StrategyStatus.RUNNING
        return (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            {isRunning && (
              <div
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: '50%',
                  backgroundColor: '#22c55e',
                  animation: 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
                }}
              />
            )}
            <Tag
              style={{
                margin: 0,
                fontSize: 10,
                padding: '2px 8px',
                fontWeight: 600,
                border: 'none',
                background: style.bg,
                color: style.color,
              }}
            >
              {statusTextMap[status]}
            </Tag>
          </div>
        )
      },
    },
    {
      title: t('strategy.symbol').toUpperCase(),
      dataIndex: 'symbol',
      key: 'symbol',
      width: 120,
      render: (text) => <span className="font-mono" style={{ fontWeight: 600 }}>{text}</span>,
    },
    {
      title: t('strategy.totalProfit').toUpperCase(),
      dataIndex: 'total_profit',
      key: 'total_profit',
      width: 150,
      align: 'right',
      render: (value, record) => {
        const profit = value ?? 0
        const changeType = profitChanges[record.id]
        const animationClass = changeType === 'up' ? 'profit-change' : changeType === 'down' ? 'loss-change' : ''

        return (
          <div
            className={animationClass}
            style={{
              padding: '4px 8px',
              borderRadius: '4px',
              display: 'inline-block',
              transition: 'all 0.3s ease',
            }}
          >
            <span className={`font-mono ${profit >= 0 ? 'text-up' : 'text-down'}`} style={{ fontSize: 14, fontWeight: 600 }}>
              {profit >= 0 ? '+' : ''}${formatPrice(Math.abs(profit))}
            </span>
          </div>
        )
      },
    },
    {
      title: t('strategy.trades').toUpperCase(),
      dataIndex: 'total_trades',
      key: 'total_trades',
      width: 90,
      align: 'right',
      render: (value) => <span className="font-mono" style={{ fontSize: 13 }}>{value ?? 0}</span>,
    },
    {
      title: t('strategy.winRate').toUpperCase(),
      dataIndex: 'win_rate',
      key: 'win_rate',
      width: 100,
      align: 'right',
      render: (value) => {
        const rate = value ?? 0
        return (
          <span className="font-mono" style={{ fontSize: 13, color: rate >= 50 ? '#22c55e' : '#ef4444' }}>
            {formatPercent(rate, 1)}%
          </span>
        )
      },
    },
    {
      title: t('strategy.actions').toUpperCase(),
      key: 'action',
      width: 240,
      fixed: 'right',
      render: (_, record) => (
        <Space size={4}>
          <Button
            type="text"
            size="small"
            icon={<Eye size={14} />}
            onClick={() => {
              setSelectedStrategy(record)
              setDetailModalOpen(true)
            }}
            style={{ color: '#1890ff' }}
          >
            详情
          </Button>
          <Button
            type="text"
            size="small"
            icon={<BarChart3 size={14} />}
            onClick={() => {
              setSelectedStrategy(record)
              setPerformanceModalOpen(true)
            }}
            style={{ color: '#52c41a' }}
          >
            性能
          </Button>
          <Button
            type="text"
            size="small"
            icon={<Pencil size={14} />}
            onClick={() => handleEditStrategy(record)}
            disabled={record.status === StrategyStatus.RUNNING}
            style={{ color: '#722ed1' }}
          >
            编辑
          </Button>
          {record.status === StrategyStatus.RUNNING ? (
            <Button
              type="text"
              size="small"
              icon={<Pause size={14} />}
              onClick={() => handleStopStrategy(record.id, record.name)}
              loading={actionLoading[record.id]}
              style={{ color: '#f59e0b' }}
            >
              {t('strategy.stop')}
            </Button>
          ) : (
            <Button
              type="text"
              size="small"
              icon={<Play size={14} />}
              style={{ color: '#22c55e' }}
              onClick={() => handleStartStrategy(record.id)}
              loading={actionLoading[record.id]}
            >
              {t('strategy.start')}
            </Button>
          )}
          <Button
            type="text"
            size="small"
            danger
            icon={<Trash2 size={14} />}
            onClick={() => handleDeleteStrategy(record.id, record.name)}
            disabled={record.status === StrategyStatus.RUNNING}
          >
            {t('strategy.delete')}
          </Button>
        </Space>
      ),
    },
  ]

  return (
    <div>
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
                background: 'rgba(24, 144, 255, 0.15)',
                color: '#1890ff',
              }}
            >
              {strategies.length}
            </Tag>
          </div>
        }
        variant="borderless"
        size="small"
        extra={
          <Dropdown
            menu={{
              items: [
                {
                  key: 'grid',
                  label: '网格策略',
                  icon: <AppWindow size={14} />,
                  onClick: () => setCreateGridModalOpen(true)
                },
                {
                  key: 'swing_long',
                  label: '波段做多',
                  icon: <TrendingUp size={14} />,
                  onClick: () => setCreateSwingModalOpen(true)
                },
                {
                  key: 'swing_short',
                  label: '波段做空',
                  icon: <TrendingDown size={14} />,
                  onClick: () => setCreateSwingShortModalOpen(true)
                },
                {
                  key: 'ai_swing_long',
                  label: (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span>AI波段做多</span>
                      <Tag
                        style={{
                          margin: 0,
                          background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                          border: 'none',
                          color: '#fff',
                          fontSize: 10,
                          padding: '0 4px'
                        }}
                      >
                        AI
                      </Tag>
                    </div>
                  ),
                  icon: <Zap size={14} style={{ color: '#722ed1' }} />,
                  onClick: () => setCreateAISwingModalOpen(true)
                }
              ]
            }}
            placement="bottomRight"
          >
            <Button type="primary" icon={<Plus size={14} />}>
              {t('strategy.createStrategy')} <ChevronDown size={14} />
            </Button>
          </Dropdown>
        }
      >
        <Table
          columns={columns}
          dataSource={strategies}
          rowKey="id"
          loading={loading}
          pagination={{
            pageSize: 10,
            showSizeChanger: true,
            showTotal: (total) => (
              <span style={{ fontSize: 12, color: '#737373' }}>
                {t('strategy.totalStrategies')}: {total}
              </span>
            ),
          }}
          scroll={{ x: 1000 }}
          locale={{
            emptyText: (
              <div style={{ padding: '60px 0', textAlign: 'center' }}>
                <Zap size={48} style={{ color: '#2a2a2a', marginBottom: 16 }} />
                <div style={{ color: '#737373', marginBottom: 8 }}>{t('strategy.noStrategiesYet')}</div>
                <div style={{ fontSize: 12, color: '#525252', marginBottom: 20 }}>
                  {t('strategy.createFirstStrategy')}
                </div>
                <Dropdown
                  menu={{
                    items: [
                      {
                        key: 'grid',
                        label: '网格策略',
                        icon: <AppWindow size={14} />,
                        onClick: () => setCreateGridModalOpen(true)
                      },
                      {
                        key: 'swing_long',
                        label: '波段做多',
                        icon: <TrendingUp size={14} />,
                        onClick: () => setCreateSwingModalOpen(true)
                      },
                      {
                        key: 'ai_swing_long',
                        label: (
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <span>AI波段做多</span>
                            <Tag
                              style={{
                                margin: 0,
                                background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                                border: 'none',
                                color: '#fff',
                                fontSize: 10,
                                padding: '0 4px'
                              }}
                            >
                              AI
                            </Tag>
                          </div>
                        ),
                        icon: <Zap size={14} style={{ color: '#722ed1' }} />,
                        onClick: () => setCreateAISwingModalOpen(true)
                      }
                    ]
                  }}
                  placement="bottomRight"
                >
                  <Button type="primary" icon={<Plus size={14} />}>
                    {t('strategy.createStrategy')} <ChevronDown size={14} />
                  </Button>
                </Dropdown>
              </div>
            ),
          }}
        />
      </Card>

      <CreateGridStrategyModal
        open={createGridModalOpen}
        onCancel={() => setCreateGridModalOpen(false)}
        onSuccess={() => {
          setCreateGridModalOpen(false)
          fetchStrategies()
        }}
      />

      <CreateSwingLongStrategyModal
        open={createSwingModalOpen}
        onCancel={() => setCreateSwingModalOpen(false)}
        onSuccess={() => {
          setCreateSwingModalOpen(false)
          fetchStrategies()
        }}
      />

      <CreateSwingShortStrategyModal
        open={createSwingShortModalOpen}
        onCancel={() => setCreateSwingShortModalOpen(false)}
        onSuccess={() => {
          setCreateSwingShortModalOpen(false)
          fetchStrategies()
        }}
      />

      <CreateSwingShortStrategyModal
        open={editSwingShortModalOpen}
        editMode={true}
        initialData={selectedStrategy}
        onCancel={() => {
          setEditSwingShortModalOpen(false)
          setSelectedStrategy(null)
        }}
        onSuccess={() => {
          setEditSwingShortModalOpen(false)
          setSelectedStrategy(null)
          fetchStrategies()
        }}
      />

      <CreateAISwingLongStrategyModal
        open={createAISwingModalOpen}
        onCancel={() => setCreateAISwingModalOpen(false)}
        onSuccess={() => {
          setCreateAISwingModalOpen(false)
          fetchStrategies()
        }}
      />

      <CreateGridStrategyModal
        open={editGridModalOpen}
        editMode={true}
        initialData={selectedStrategy}
        onCancel={() => {
          setEditGridModalOpen(false)
          setSelectedStrategy(null)
        }}
        onSuccess={() => {
          setEditGridModalOpen(false)
          setSelectedStrategy(null)
          fetchStrategies()
        }}
      />

      <CreateSwingLongStrategyModal
        open={editSwingModalOpen}
        editMode={true}
        initialData={selectedStrategy}
        onCancel={() => {
          setEditSwingModalOpen(false)
          setSelectedStrategy(null)
        }}
        onSuccess={() => {
          setEditSwingModalOpen(false)
          setSelectedStrategy(null)
          fetchStrategies()
        }}
      />

      <CreateAISwingLongStrategyModal
        open={editAISwingModalOpen}
        editMode={true}
        initialData={selectedStrategy}
        onCancel={() => {
          setEditAISwingModalOpen(false)
          setSelectedStrategy(null)
        }}
        onSuccess={() => {
          setEditAISwingModalOpen(false)
          setSelectedStrategy(null)
          fetchStrategies()
        }}
      />

      <StrategyDetailModal
        open={detailModalOpen}
        strategy={selectedStrategy}
        onCancel={() => {
          setDetailModalOpen(false)
          setSelectedStrategy(null)
        }}
      />

      <StrategyPerformanceModal
        open={performanceModalOpen}
        strategy={selectedStrategy}
        onCancel={() => {
          setPerformanceModalOpen(false)
          setSelectedStrategy(null)
        }}
      />
    </div>
  )
}

export default StrategyList
