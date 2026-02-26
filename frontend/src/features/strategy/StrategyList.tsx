import { Card, Table, Button, Tag, Space, App, Modal, Form, Input, Select } from 'antd'
import {
  Play,
  Pause,
  Trash2,
  Eye,
  AlertCircle,
  BarChart3,
  Plus,
} from 'lucide-react'
import type { ColumnsType } from 'antd/es/table'
import { StrategyStatus, Strategy } from '@/types'
import { useState, useEffect } from 'react'
import StrategyDetailModal from './StrategyDetailModal'
import StrategyPerformanceModal from './StrategyPerformanceModal'
import { strategyApi } from '@/services/api'
import { useTranslation } from 'react-i18next'
import { wsService, StrategyUpdateData } from '@/services/websocket'
import { formatPrice, formatPercent } from '@/utils/format'

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

const StrategyList = () => {
  const { t } = useTranslation()
  const { message } = App.useApp()
  const [strategies, setStrategies] = useState<Strategy[]>([])
  const [loading, setLoading] = useState(false)
  const [detailModalOpen, setDetailModalOpen] = useState(false)
  const [performanceModalOpen, setPerformanceModalOpen] = useState(false)
  const [selectedStrategy, setSelectedStrategy] = useState<Strategy | null>(null)
  const [actionLoading, setActionLoading] = useState<{ [key: number]: boolean }>({})
  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [createLoading, setCreateLoading] = useState(false)
  const [createForm] = Form.useForm()

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

  // 查看绩效
  const handleViewPerformance = (strategy: Strategy) => {
    setSelectedStrategy(strategy)
    setPerformanceModalOpen(true)
  }

  // 创建策略
  const handleCreate = async () => {
    try {
      const values = await createForm.validateFields()
      setCreateLoading(true)
      await strategyApi.create(values)
      message.success('策略创建成功')
      setCreateModalOpen(false)
      createForm.resetFields()
      await fetchStrategies(true)
    } catch (error: any) {
      if (error?.errorFields) return // 表单校验错误，不提示
      message.error(error?.response?.data?.detail || '创建策略失败')
    } finally {
      setCreateLoading(false)
    }
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
      title: t('strategy.name'),
      dataIndex: 'name',
      key: 'name',
      width: 180,
      render: (text) => <span style={{ fontWeight: 600 }}>{text}</span>,
    },
    {
      title: t('strategy.type'),
      dataIndex: 'type',
      key: 'type',
      width: 120,
      render: (type) => <Tag>{String(type).toUpperCase()}</Tag>,
    },
    {
      title: t('strategy.symbol'),
      dataIndex: 'symbol',
      key: 'symbol',
      width: 130,
    },
    {
      title: t('strategy.status'),
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status) => (
        <Tag color={statusColorMap[status] || 'default'}>
          {statusTextMap[status] || status}
        </Tag>
      ),
    },
    {
      title: t('strategy.totalProfit'),
      dataIndex: 'total_profit',
      key: 'total_profit',
      width: 120,
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
      title: t('strategy.totalTrades'),
      dataIndex: 'total_trades',
      key: 'total_trades',
      width: 100,
      align: 'right',
      render: (trades) => trades || 0,
    },
    {
      title: t('strategy.winRate'),
      dataIndex: 'win_rate',
      key: 'win_rate',
      width: 90,
      align: 'right',
      render: (rate) => {
        const value = rate || 0
        const color = value >= 50 ? '#22c55e' : '#ef4444'
        return <span style={{ color }}>{formatPercent(value)}%</span>
      },
    },
    {
      title: t('common.actions'),
      key: 'actions',
      width: 200,
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
            <Button
              type="text"
              size="small"
              icon={<Trash2 size={14} />}
              onClick={() => handleDeleteStrategy(record.id, record.name)}
              danger
            >
              {t('common.delete')}
            </Button>
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
              <Button
                type="primary"
                icon={<Plus size={14} />}
                onClick={() => setCreateModalOpen(true)}
              >
                创建策略
              </Button>
            </Space>
          </div>
        }
      >
        <Table
          columns={columns}
          dataSource={strategies}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 10 }}
          scroll={{ x: 1000 }}
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

      {/* 创建策略 Modal */}
      <Modal
        title="创建策略"
        open={createModalOpen}
        onOk={handleCreate}
        onCancel={() => { setCreateModalOpen(false); createForm.resetFields() }}
        okText="创建"
        cancelText="取消"
        confirmLoading={createLoading}
        width={520}
        destroyOnClose
      >
        <Form form={createForm} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="name" label="策略名称" rules={[{ required: true, message: '请输入策略名称' }]}>
            <Input placeholder="如：BTC网格策略01" />
          </Form.Item>

          <Form.Item name="type" label="策略类型" rules={[{ required: true, message: '请选择策略类型' }]}>
            <Select placeholder="选择策略类型">
              <Select.Option value="grid">网格交易（Grid）</Select.Option>
              <Select.Option value="swing_long">波段做多（Swing Long）</Select.Option>
              <Select.Option value="swing_short">波段做空（Swing Short）</Select.Option>
              <Select.Option value="ai_swing_long">AI增强波段做多（AI Swing Long）</Select.Option>
            </Select>
          </Form.Item>

          <Form.Item name="symbol" label="交易对" rules={[{ required: true, message: '请选择或输入交易对' }]}>
            <Select
              showSearch
              allowClear
              placeholder="选择或输入交易对，如 BTC-USDT-SWAP"
              options={SYMBOL_OPTIONS}
              filterOption={(input, option) =>
                String(option?.label ?? '').toLowerCase().includes(input.toLowerCase())
              }
            />
          </Form.Item>

          <Form.Item name="timeframe" label="时间周期">
            <Select placeholder="选择时间周期（可选）" allowClear>
              <Select.Option value="1m">1分钟</Select.Option>
              <Select.Option value="3m">3分钟</Select.Option>
              <Select.Option value="5m">5分钟</Select.Option>
              <Select.Option value="15m">15分钟</Select.Option>
              <Select.Option value="30m">30分钟</Select.Option>
              <Select.Option value="1H">1小时</Select.Option>
              <Select.Option value="4H">4小时</Select.Option>
              <Select.Option value="1D">1天</Select.Option>
            </Select>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default StrategyList
