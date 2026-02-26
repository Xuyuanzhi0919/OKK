import { Card, Table, Button, Tag, Space, App, Modal, Input, Select, Row, Col, Dropdown } from 'antd'
import {
  Play,
  Pause,
  Trash2,
  Eye,
  AlertCircle,
  BarChart3,
  Plus,
  Search,
  Copy,
  Edit3,
} from 'lucide-react'
import type { ColumnsType } from 'antd/es/table'
import { StrategyStatus, Strategy } from '@/types'
import { useState, useEffect, useMemo } from 'react'
import StrategyDetailModal from './StrategyDetailModal'
import StrategyPerformanceModal from './StrategyPerformanceModal'
import StrategyCreateModal from './StrategyCreateModal'
import { strategyApi } from '@/services/api'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { wsService, StrategyUpdateData } from '@/services/websocket'
import { formatPrice, formatPercent } from '@/utils/format'

const { Search: AntSearch } = Input

// 常用 OKX 合约交易对（USDT 本位永续）
const SYMBOL_OPTIONS = [
  'BTC-USDT-SWAP', 'ETH-USDT-SWAP', 'SOL-USDT-SWAP', 'BNB-USDT-SWAP',
  'XRP-USDT-SWAP', 'DOGE-USDT-SWAP', 'ADA-USDT-SWAP', 'AVAX-USDT-SWAP',
  'LINK-USDT-SWAP', 'DOT-USDT-SWAP', 'MATIC-USDT-SWAP', 'UNI-USDT-SWAP',
  'LTC-USDT-SWAP', 'ATOM-USDT-SWAP', 'ETC-USDT-SWAP', 'FIL-USDT-SWAP',
  'ARB-USDT-SWAP', 'OP-USDT-SWAP', 'APT-USDT-SWAP', 'NEAR-USDT-SWAP',
  'SUI-USDT-SWAP', 'TRX-USDT-SWAP', 'TON-USDT-SWAP', 'KSM-USDT-SWAP',
  'WLD-USDT-SWAP', 'INJ-USDT-SWAP', 'TIA-USDT-SWAP', 'JTO-USDT-SWAP',
  'SEI-USDT-SWAP', 'ORDI-USDT-SWAP', 'STX-USDT-SWAP', 'MEME-USDT-SWAP',
  'PEPE-USDT-SWAP', 'SHIB-USDT-SWAP', 'FLOKI-USDT-SWAP', 'BONK-USDT-SWAP',
].map(s => ({ label: s, value: s }))

// 策略类型中文标签（用于表格展示已有历史策略）
const STRATEGY_TYPE_LABELS: Record<string, string> = {
  grid: '网格策略',
  swing_long: '波段做多',
  swing_short: '波段做空',
  ai_swing_long: 'AI波段做多',
  martin: '马丁格尔',
  trend: '趋势跟踪',
  arbitrage: '套利',
  custom: '自定义',
}

// 可用实盘策略过滤选项
const STRATEGY_TYPE_OPTIONS: { label: string; value: string }[] = [
  { label: 'EMA趋势跟踪', value: 'trend' },
]

// 状态选项
const STATUS_OPTIONS = [
  { label: '运行中', value: StrategyStatus.RUNNING },
  { label: '已停止', value: StrategyStatus.STOPPED },
  { label: '已暂停', value: StrategyStatus.PAUSED },
  { label: '错误', value: StrategyStatus.ERROR },
]

// 创建策略下拉菜单（与 STRATEGY_TYPES 保持一致）
const CREATE_MENU_ITEMS = [
  { key: 'trend', label: 'EMA 趋势跟踪' },
]

const StrategyList = () => {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const navigate = useNavigate()
  const [strategies, setStrategies] = useState<Strategy[]>([])
  const [loading, setLoading] = useState(false)
  const [detailModalOpen, setDetailModalOpen] = useState(false)
  const [performanceModalOpen, setPerformanceModalOpen] = useState(false)
  const [selectedStrategy, setSelectedStrategy] = useState<Strategy | null>(null)
  const [actionLoading, setActionLoading] = useState<{ [key: number]: boolean }>({})
  const [createModalOpen, setCreateModalOpen] = useState(false)  // 保留：用于编辑/复制
  
  // 筛选状态
  const [searchText, setSearchText] = useState('')
  const [filterStatus, setFilterStatus] = useState<string | null>(null)
  const [filterType, setFilterType] = useState<string | null>(null)
  
  // 编辑/复制策略状态
  const [editModalOpen, setEditModalOpen] = useState(false)
  const [editingStrategy, setEditingStrategy] = useState<Strategy | null>(null)
  const [isCopyMode, setIsCopyMode] = useState(false)

  // 过滤后的策略列表
  const filteredStrategies = useMemo(() => {
    return strategies.filter(s => {
      // 搜索过滤
      if (searchText && !s.name.toLowerCase().includes(searchText.toLowerCase()) &&
          !s.symbol.toLowerCase().includes(searchText.toLowerCase())) {
        return false
      }
      // 状态过滤
      if (filterStatus && s.status !== filterStatus) {
        return false
      }
      // 类型过滤
      if (filterType && s.type !== filterType) {
        return false
      }
      return true
    })
  }, [strategies, searchText, filterStatus, filterType])

  const fetchStrategies = async (silent = false) => {
    try {
      if (!silent) setLoading(true)
      const response = await strategyApi.getList()
      // 处理响应数据
      const items = (response as any)?.data?.items || (response as any)?.items || []
      setStrategies(Array.isArray(items) ? items : [])
    } catch (error) {
      if (!silent) {
        message.error((error as Error).message || t('strategy.fetchStrategiesFailed'))
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchStrategies()

    // 订阅策略更新
    const unsubscribe = wsService.onStrategyUpdate((data: StrategyUpdateData) => {
      fetchStrategies(true)
    })

    return () => {
      unsubscribe()
    }
  }, [])

  // 启动策略
  const handleStartStrategy = async (id: number) => {
    try {
      setActionLoading({ ...actionLoading, [id]: true })
      await strategyApi.start(id)
      await fetchStrategies(true)
    } catch (error) {
      message.error((error as any)?.response?.data?.message || t('strategy.startStrategyFailed'))
    } finally {
      setActionLoading({ ...actionLoading, [id]: false })
    }
  }

  // 停止策略
  const handleStopStrategy = (id: number, name: string) => {
    Modal.confirm({
      title: '停止策略',
      icon: <AlertCircle size={24} />,
      content: <p>确定要停止策略 <strong>{name}</strong> 吗？</p>,
      okText: '确定停止',
      okType: 'primary',
      cancelText: '取消',
      onOk: async () => {
        try {
          setActionLoading({ ...actionLoading, [id]: true })
          await strategyApi.stop(id, true)
          await fetchStrategies(true)
        } catch (error) {
          message.error((error as any)?.response?.data?.message || t('strategy.stopStrategyFailed'))
        } finally {
          setActionLoading({ ...actionLoading, [id]: false })
        }
      },
    })
  }

  // 删除策略
  const handleDeleteStrategy = (id: number, name: string) => {
    Modal.confirm({
      title: '删除策略',
      icon: <AlertCircle size={24} />,
      content: <p>确定要删除策略 <strong>{name}</strong> 吗？此操作不可恢复。</p>,
      okText: '确定删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        try {
          await strategyApi.delete(id)
          message.success('策略已删除')
          await fetchStrategies(true)
        } catch (error) {
          message.error((error as any)?.response?.data?.message || '删除策略失败')
        }
      },
    })
  }

  // 查看详情
  const handleViewDetail = (strategy: Strategy) => {
    setSelectedStrategy(strategy)
    setDetailModalOpen(true)
  }

  // 编辑策略
  const handleEditStrategy = (strategy: Strategy) => {
    setEditingStrategy(strategy)
    setIsCopyMode(false)
    setEditModalOpen(true)
  }

  // 复制策略
  const handleCopyStrategy = (strategy: Strategy) => {
    setEditingStrategy(strategy)
    setIsCopyMode(true)
    setEditModalOpen(true)
  }

  // 清空筛选
  const handleClearFilters = () => {
    setSearchText('')
    setFilterStatus(null)
    setFilterType(null)
    setDetailModalOpen(true)
  }

  // 查看绩效
  const handleViewPerformance = (strategy: Strategy) => {
    setSelectedStrategy(strategy)
    setPerformanceModalOpen(true)
  }

  const statusColorMap: Record<string, string> = {
    [StrategyStatus.RUNNING]: 'green',
    [StrategyStatus.STOPPED]: 'default',
    [StrategyStatus.PAUSED]: 'orange',
    [StrategyStatus.ERROR]: 'red',
  }
  const statusTextMap: Record<string, string> = {
    [StrategyStatus.RUNNING]: 'RUNNING',
    [StrategyStatus.STOPPED]: 'STOPPED',
    [StrategyStatus.PAUSED]: 'PAUSED',
    [StrategyStatus.ERROR]: 'ERROR',
  }

  const columns: ColumnsType<Strategy> = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      width: 180,
      render: (text) => <span style={{ fontWeight: 600 }}>{text}</span>,
    },
    {
      title: '类型',
      dataIndex: 'type',
      key: 'type',
      width: 100,
      render: (type) => <Tag>{STRATEGY_TYPE_LABELS[type] || String(type).toUpperCase()}</Tag>,
    },
    {
      title: '交易对',
      dataIndex: 'symbol',
      key: 'symbol',
      width: 130,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (status) => (
        <Tag color={statusColorMap[status] || 'default'}>
          {statusTextMap[status] || status}
        </Tag>
      ),
    },
    {
      title: '总盈亏',
      dataIndex: 'total_profit',
      key: 'total_profit',
      width: 110,
      align: 'right',
      render: (profit) => {
        const value = profit || 0
        const color = value >= 0 ? '#22c55e' : '#ef4444'
        return (
          <span style={{ color, fontWeight: 600, fontFamily: 'monospace' }}>
            {value >= 0 ? '+' : ''}{formatPrice(value)} USDT
          </span>
        )
      },
    },
    {
      title: '总交易',
      dataIndex: 'total_trades',
      key: 'total_trades',
      width: 80,
      align: 'right',
      render: (trades) => trades || 0,
    },
    {
      title: '胜率',
      dataIndex: 'win_rate',
      key: 'win_rate',
      width: 70,
      align: 'right',
      render: (rate) => {
        const value = rate || 0
        const color = value >= 50 ? '#22c55e' : '#ef4444'
        return <span style={{ color }}>{formatPercent(value)}%</span>
      },
    },
    {
      title: '操作',
      key: 'actions',
      width: 280,
      fixed: 'right',
      render: (_, record) => (
        <Space size="small">
          {record.status === StrategyStatus.RUNNING ? (
            <Button
              type="text"
              size="small"
              icon={<Pause size={14} />}
              onClick={() => handleStopStrategy(record.id, record.name)}
              loading={actionLoading[record.id]}
              danger
            >
              {t('strategy.stop')}
            </Button>
          ) : (
            <Button
              type="text"
              size="small"
              icon={<Play size={14} />}
              onClick={() => handleStartStrategy(record.id)}
              loading={actionLoading[record.id]}
            >
              {t('strategy.start')}
            </Button>
          )}
          <Button
            type="text"
            size="small"
            icon={<Eye size={14} />}
            onClick={() => handleViewDetail(record)}
          >
            {t('common.detail')}
          </Button>
          <Button
            type="text"
            size="small"
            icon={<BarChart3 size={14} />}
            onClick={() => handleViewPerformance(record)}
          >
            {t('strategy.performance')}
          </Button>
          {record.status !== StrategyStatus.RUNNING && (
            <>
              <Button
                type="text"
                size="small"
                icon={<Edit3 size={14} />}
                onClick={() => handleEditStrategy(record)}
              >
                编辑
              </Button>
              <Button
                type="text"
                size="small"
                icon={<Copy size={14} />}
                onClick={() => handleCopyStrategy(record)}
              >
                复制
              </Button>
              <Button
                type="text"
                size="small"
                icon={<Trash2 size={14} />}
                onClick={() => handleDeleteStrategy(record.id, record.name)}
                danger
              >
                {t('common.delete')}
              </Button>
            </>
          )}
        </Space>
      ),
    },
  ]

  return (
    <div style={{ padding: 24 }}>
      <Card
        title={
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>{t('strategy.strategyList')}</span>
            <Space>
              <Button onClick={() => fetchStrategies()}>
                {t('common.refresh')}
              </Button>
              <Dropdown
                menu={{
                  items: CREATE_MENU_ITEMS,
                  onClick: ({ key }) => navigate(`/strategies/create/${key}`),
                }}
                placement="bottomRight"
              >
                <Button type="primary" icon={<Plus size={14} />}>
                  创建策略
                </Button>
              </Dropdown>
            </Space>
          </div>
        }
      >
        {/* 筛选栏 */}
        <Row gutter={16} style={{ marginBottom: 16 }}>
          <Col span={8}>
            <AntSearch
              placeholder="搜索策略名称/交易对"
              allowClear
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              onSearch={(v) => setSearchText(v)}
            />
          </Col>
          <Col span={6}>
            <Select
              style={{ width: '100%' }}
              placeholder="筛选状态"
              allowClear
              value={filterStatus}
              onChange={(v) => setFilterStatus(v)}
              options={STATUS_OPTIONS}
            />
          </Col>
          <Col span={6}>
            <Select
              style={{ width: '100%' }}
              placeholder="筛选策略类型"
              allowClear
              disabled={STRATEGY_TYPE_OPTIONS.length === 0}
              value={filterType}
              onChange={(v) => setFilterType(v)}
              options={STRATEGY_TYPE_OPTIONS}
            />
          </Col>
          <Col span={4}>
            <Button onClick={handleClearFilters} disabled={!searchText && !filterStatus && !filterType}>
              清空筛选
            </Button>
          </Col>
        </Row>

        <Table
          columns={columns}
          dataSource={filteredStrategies}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 10, showSizeChanger: true, showTotal: (total) => `共 ${total} 条` }}
          scroll={{ x: 1200 }}
          locale={{ emptyText: '暂无策略' }}
        />
      </Card>

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

      {/* 创建策略：已改为跳转到独立页面 /strategies/create/:type，Modal 不再使用 */}

      {/* 编辑/复制策略 Modal */}
      <StrategyCreateModal
        open={editModalOpen}
        onCancel={() => {
          setEditModalOpen(false)
          setEditingStrategy(null)
          setIsCopyMode(false)
        }}
        onSuccess={() => {
          setEditModalOpen(false)
          setEditingStrategy(null)
          setIsCopyMode(false)
          fetchStrategies(true)
        }}
        backtestData={editingStrategy ? {
          strategy_type: editingStrategy.type,
          symbol: editingStrategy.symbol,
          parameters: editingStrategy.parameters || {},
          name: isCopyMode ? `${editingStrategy.name} (副本)` : editingStrategy.name,
        } : null}
      />
    </div>
  )
}

export default StrategyList
