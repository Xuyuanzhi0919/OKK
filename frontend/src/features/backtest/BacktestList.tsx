import { useState, useEffect } from 'react'
import { Card, Button, Table, Tag, Space, Modal, Form, Input, Select, InputNumber, DatePicker, Spin, Alert, App, Tooltip, Statistic, Row, Col, Steps } from 'antd'
import { Plus, Eye, Trash2, RefreshCw, Database, HelpCircle, Calculator, Pencil } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import dayjs from 'dayjs'
import type { ColumnsType } from 'antd/es/table'
import { BACKTEST_API, API_BASE_URL } from '@/config/api'
import { formatAmount, formatPercent } from '@/utils/format'

const { RangePicker } = DatePicker
const { TextArea } = Input

// 本地存储key
const DRAFT_KEY = 'backtest_create_draft'

interface Backtest {
  id: number
  name: string
  description?: string
  strategy_type: string
  symbol: string
  interval: string
  status: string
  progress: number
  total_return?: number
  max_drawdown?: number
  sharpe_ratio?: number
  total_trades: number
  created_at: string
  completed_at?: string
}

interface CreateBacktestFormData {
  name: string
  strategy_type: string
  symbol: string
  interval: string
  time_range: [dayjs.Dayjs, dayjs.Dayjs]
  initial_capital: number
  // 普通网格策略参数
  grid_lower?: number
  grid_upper?: number
  grid_num?: number
  // 网格做市策略参数
  grid_spread?: number  // 网格间距(百分比)
  grid_levels?: number  // 每侧网格层数
  // 通用参数
  amount_per_grid?: number
  fee_rate: number
  description?: string
  // 均线交叉策略参数
  fast_period?: number
  slow_period?: number
  ma_type?: string
  amount_per_trade?: number
  // 双均线策略参数
  position_ratio?: number
  leverage?: number
  enable_short?: boolean
  stop_loss?: number
  take_profit?: number
}

const BacktestList = () => {
  const { modal, message: messageApi } = App.useApp()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [form] = Form.useForm<CreateBacktestFormData>()
  const [strategyType, setStrategyType] = useState<string>('grid')
  const [gridCalculations, setGridCalculations] = useState<{
    gridSpacing: number
    estimatedFunds: number
    warningMessage: string
  } | null>(null)

  // 当前市场价格参考
  const [priceReference, setPriceReference] = useState<{
    currentPrice: number
    suggestedLower: number
    suggestedUpper: number
  } | null>(null)

  // 筛选和排序状态
  const [filterStatus, setFilterStatus] = useState<string | null>(null)
  const [filterStrategy, setFilterStrategy] = useState<string | null>(null)
  const [sortField, setSortField] = useState<string>('created_at')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc')

  // 分步表单当前步骤
  const [currentStep, setCurrentStep] = useState(0)

  // 批量选择状态
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([])

  // 对比模式状态
  const [compareMode, setCompareMode] = useState(false)
  const [compareModalOpen, setCompareModalOpen] = useState(false)

  // 编辑描述状态
  const [editDescriptionModalOpen, setEditDescriptionModalOpen] = useState(false)
  const [editingBacktest, setEditingBacktest] = useState<Backtest | null>(null)
  const [editDescriptionForm] = Form.useForm<{ description: string }>()

  // 自动生成回测名称
  const generateBacktestName = () => {
    const values = form.getFieldsValue()
    const { strategy_type, symbol, time_range } = values

    if (!symbol || !time_range) return

    const strategyName = strategy_type === 'grid' ? '网格策略' : '网格做市'
    const startDate = time_range[0]?.format('MM-DD')
    const endDate = time_range[1]?.format('MM-DD')

    const name = `${symbol} ${strategyName} ${startDate}~${endDate}`
    form.setFieldsValue({ name })
  }

  // 获取价格参考数据
  const fetchPriceReference = async () => {
    const symbol = form.getFieldValue('symbol')
    const timeRange = form.getFieldValue('time_range')

    if (!symbol || !timeRange) return

    try {
      // 查询该时间范围内的K线数据,获取价格范围
      const params = new URLSearchParams({
        symbol: symbol,
        interval: form.getFieldValue('interval') || '1H',
        start_time: timeRange[0].valueOf().toString(),
        end_time: timeRange[1].valueOf().toString(),
        limit: '100'  // 获取部分数据即可
      })

      const response = await fetch(`${(import.meta as any).env?.VITE_API_BASE_URL || 'http://localhost:8000'}/api/v1/backtest/klines/query?${params}`)

      if (response.ok) {
        const klines = await response.json()
        if (klines && klines.length > 0) {
          // 计算价格范围
          const prices = klines.map((k: any) => [k.low, k.high, k.close]).flat()
          const minPrice = Math.min(...prices)
          const maxPrice = Math.max(...prices)
          const avgPrice = prices.reduce((a: number, b: number) => a + b, 0) / prices.length

          // 建议网格范围:平均价 ± 5%
          const range = avgPrice * 0.05

          setPriceReference({
            currentPrice: avgPrice,
            suggestedLower: Math.floor(avgPrice - range),
            suggestedUpper: Math.ceil(avgPrice + range)
          })

          messageApi.success(`已加载价格参考数据`)
        } else {
          messageApi.warning('该时间范围内暂无K线数据')
        }
      }
    } catch (error) {
      // 处理错误
    }
  }

  // 应用智能网格范围
  const applySmartGridRange = () => {
    if (!priceReference) {
      messageApi.warning('请先选择交易对和时间范围')
      return
    }

    form.setFieldsValue({
      grid_lower: priceReference.suggestedLower,
      grid_upper: priceReference.suggestedUpper
    })
    calculateGridParams()
    messageApi.success('已应用智能网格范围')
  }

  // 应用网格参数模板
  const applyGridTemplate = (template: 'conservative' | 'balanced' | 'aggressive') => {
    const templates = {
      conservative: {
        grid_num: 5,
        description: '保守型: 5个网格,大间距,适合震荡行情'
      },
      balanced: {
        grid_num: 10,
        description: '平衡型: 10个网格,中等间距,适合大多数情况'
      },
      aggressive: {
        grid_num: 20,
        description: '激进型: 20个网格,小间距,适合高频交易'
      }
    }

    const selected = templates[template]
    form.setFieldsValue({
      grid_num: selected.grid_num,
      description: selected.description
    })
    calculateGridParams()
    messageApi.success(`已应用${template === 'conservative' ? '保守' : template === 'balanced' ? '平衡' : '激进'}型模板`)
  }

  // 获取回测列表
  const { data: rawBacktests, isLoading, refetch } = useQuery({
    queryKey: ['backtests'],
    queryFn: async () => {
      const response = await fetch(BACKTEST_API.list)
      if (!response.ok) throw new Error('获取回测列表失败')
      return response.json()
    },
    refetchInterval: 3000, // 每3秒刷新一次,用于更新进度
  })

  // 应用筛选和排序
  const backtests = rawBacktests
    ? rawBacktests
        .filter((item: Backtest) => {
          if (filterStatus && item.status !== filterStatus) return false
          if (filterStrategy && item.strategy_type !== filterStrategy) return false
          return true
        })
        .sort((a: Backtest, b: Backtest) => {
          const aValue = a[sortField as keyof Backtest]
          const bValue = b[sortField as keyof Backtest]

          if (typeof aValue === 'number' && typeof bValue === 'number') {
            return sortOrder === 'asc' ? aValue - bValue : bValue - aValue
          }

          if (typeof aValue === 'string' && typeof bValue === 'string') {
            return sortOrder === 'asc'
              ? aValue.localeCompare(bValue)
              : bValue.localeCompare(aValue)
          }

          return 0
        })
    : []

  // 默认交易对列表：合约（SWAP）优先，后接现货（SPOT）
  // API 请求失败或无 K 线数据时使用；API 有数据时与此列表去重合并
  const DEFAULT_SYMBOLS = [
    // ── 合约（USDT 本位永续）──
    'BTC-USDT-SWAP', 'ETH-USDT-SWAP', 'SOL-USDT-SWAP', 'BNB-USDT-SWAP',
    'XRP-USDT-SWAP', 'DOGE-USDT-SWAP', 'ADA-USDT-SWAP', 'AVAX-USDT-SWAP',
    'LINK-USDT-SWAP', 'DOT-USDT-SWAP', 'LTC-USDT-SWAP', 'ATOM-USDT-SWAP',
    'ETC-USDT-SWAP', 'ARB-USDT-SWAP', 'OP-USDT-SWAP', 'APT-USDT-SWAP',
    'NEAR-USDT-SWAP', 'SUI-USDT-SWAP', 'TRX-USDT-SWAP', 'KSM-USDT-SWAP',
    'INJ-USDT-SWAP', 'SEI-USDT-SWAP', 'ORDI-USDT-SWAP', 'WLD-USDT-SWAP',
    'PEPE-USDT-SWAP', 'SHIB-USDT-SWAP',
    // ── 现货（SPOT）──
    'BTC-USDT', 'ETH-USDT', 'SOL-USDT', 'BNB-USDT', 'XRP-USDT',
    'DOGE-USDT', 'ADA-USDT', 'AVAX-USDT', 'LINK-USDT', 'DOT-USDT',
    'LTC-USDT', 'ATOM-USDT', 'ETC-USDT', 'ARB-USDT', 'OP-USDT',
    'APT-USDT', 'NEAR-USDT', 'KSM-USDT', 'INJ-USDT', 'PEPE-USDT',
  ]

  // 获取可用的交易对列表(从已有K线数据中获取，并与默认列表合并)
  const { data: availableSymbols } = useQuery({
    queryKey: ['available-symbols'],
    queryFn: async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/api/v1/backtest/symbols`)
        if (!response.ok) throw new Error('获取交易对列表失败')
        const symbols: string[] = await response.json()
        // 将 DB 中已有的 K 线交易对排在前面，再追加默认列表（去重）
        const merged = [...new Set([...symbols, ...DEFAULT_SYMBOLS])]
        return merged.length > 0 ? merged : DEFAULT_SYMBOLS
      } catch (error) {
        console.error('获取交易对列表失败:', error)
        return DEFAULT_SYMBOLS
      }
    },
  })

  // 创建回测
  const createMutation = useMutation({
    mutationFn: async (values: CreateBacktestFormData) => {
      const [startTime, endTime] = values.time_range

      const payload = {
        name: values.name,
        strategy_type: values.strategy_type,
        symbol: values.symbol,
        interval: values.interval,
        start_time: startTime.valueOf(),
        end_time: endTime.valueOf(),
        initial_capital: values.initial_capital,
        parameters: {
          grid_lower: values.grid_lower,
          grid_upper: values.grid_upper,
          grid_num: values.grid_num,
          amount_per_grid: values.amount_per_grid,
          fee_rate: values.fee_rate,
        },
        description: values.description,
      }

      const response = await fetch(BACKTEST_API.run, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })

      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.detail || '创建回测失败')
      }

      return response.json()
    },
    onSuccess: (data) => {
      messageApi.success('回测已创建,正在后台执行...')
      // 清空草稿
      localStorage.removeItem(DRAFT_KEY)
      setCreateModalOpen(false)
      form.resetFields()
      setStrategyType('grid')
      queryClient.invalidateQueries({ queryKey: ['backtests'] })

      // 3秒后自动跳转到详情页
      setTimeout(() => {
        modal.info({
          title: '回测正在执行',
          content: '是否前往查看回测详情?',
          okText: '查看详情',
          cancelText: '稍后查看',
          onOk: () => navigate(`/backtest/${data.id}`),
        })
      }, 3000)
    },
    onError: (error: Error) => {
      messageApi.error(error.message)
    },
  })

  // 删除回测
  const deleteMutation = useMutation({
    mutationFn: async (id: number) => {
      const response = await fetch(BACKTEST_API.delete(id), {
        method: 'DELETE',
      })
      if (!response.ok) throw new Error('删除回测失败')
      return response.json()
    },
    onSuccess: () => {
      messageApi.success('回测已删除')
      queryClient.invalidateQueries({ queryKey: ['backtests'] })
    },
    onError: (error: Error) => {
      messageApi.error(error.message)
    },
  })

  // 批量删除回测
  const batchDeleteMutation = useMutation({
    mutationFn: async (ids: number[]) => {
      const results = await Promise.allSettled(
        ids.map(id =>
          fetch(BACKTEST_API.delete(id), { method: 'DELETE' })
            .then(res => {
              if (!res.ok) throw new Error(`删除回测${id}失败`)
              return res.json()
            })
        )
      )

      const failed = results.filter(r => r.status === 'rejected')
      if (failed.length > 0) {
        throw new Error(`${failed.length}个回测删除失败`)
      }

      return results
    },
    onSuccess: (_, ids) => {
      messageApi.success(`成功删除${ids.length}个回测`)
      setSelectedRowKeys([])
      queryClient.invalidateQueries({ queryKey: ['backtests'] })
    },
    onError: (error: Error) => {
      messageApi.error(error.message)
    },
  })

  // 处理批量删除
  const handleBatchDelete = () => {
    if (selectedRowKeys.length === 0) {
      messageApi.warning('请先选择要删除的回测')
      return
    }

    const selectedBacktests = backtests.filter((bt: Backtest) =>
      selectedRowKeys.includes(bt.id)
    )

    const runningCount = selectedBacktests.filter(
      (bt: Backtest) => bt.status === 'running' || bt.status === 'pending'
    ).length

    modal.confirm({
      title: '批量删除确认',
      content: (
        <div>
          <p>确定要删除选中的 <strong>{selectedRowKeys.length}</strong> 个回测吗?</p>
          {runningCount > 0 && (
            <Alert
              message="警告"
              description={`其中有 ${runningCount} 个回测正在运行或等待执行,删除后将立即停止且无法恢复。`}
              type="warning"
              showIcon
              style={{ marginTop: 12 }}
            />
          )}
        </div>
      ),
      okText: '确定删除',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: () => batchDeleteMutation.mutate(selectedRowKeys as number[]),
    })
  }

  // 处理回测对比
  const handleCompare = () => {
    if (selectedRowKeys.length < 2) {
      messageApi.warning('请至少选择2个回测进行对比')
      return
    }
    if (selectedRowKeys.length > 3) {
      messageApi.warning('最多支持对比3个回测')
      return
    }

    const selectedBacktests = backtests.filter((bt: Backtest) =>
      selectedRowKeys.includes(bt.id)
    )

    const incompleteCount = selectedBacktests.filter(
      (bt: Backtest) => bt.status !== 'completed'
    ).length

    if (incompleteCount > 0) {
      messageApi.warning('只能对比已完成的回测')
      return
    }

    setCompareModalOpen(true)
  }

  // 更新描述 mutation
  const updateDescriptionMutation = useMutation({
    mutationFn: async ({ id, description }: { id: number; description: string }) => {
      const response = await fetch(
        `${BACKTEST_API.updateDescription(id)}?description=${encodeURIComponent(description)}`,
        { method: 'PATCH' }
      )
      if (!response.ok) throw new Error('更新描述失败')
      return response.json()
    },
    onSuccess: () => {
      messageApi.success('描述更新成功')
      setEditDescriptionModalOpen(false)
      setEditingBacktest(null)
      editDescriptionForm.resetFields()
      queryClient.invalidateQueries({ queryKey: ['backtests'] })
    },
    onError: (error: Error) => {
      messageApi.error(error.message)
    },
  })

  // 打开编辑描述对话框
  const handleEditDescription = (backtest: Backtest) => {
    setEditingBacktest(backtest)
    editDescriptionForm.setFieldsValue({ description: backtest.description || '' })
    setEditDescriptionModalOpen(true)
  }

  // 提交描述更新
  const handleDescriptionSubmit = () => {
    if (!editingBacktest) return

    editDescriptionForm.validateFields().then((values) => {
      updateDescriptionMutation.mutate({
        id: editingBacktest.id,
        description: values.description || '',
      })
    })
  }

  const columns: ColumnsType<Backtest> = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      width: 200,
    },
    {
      title: '策略',
      dataIndex: 'strategy_type',
      key: 'strategy_type',
      width: 100,
      render: (type: string) => {
        const labels: Record<string, string> = {
          grid: '网格策略',
          grid_mm: '网格做市',
        }
        return <Tag color="blue">{labels[type] || type}</Tag>
      },
    },
    {
      title: '交易对',
      dataIndex: 'symbol',
      key: 'symbol',
      width: 120,
    },
    {
      title: '周期',
      dataIndex: 'interval',
      key: 'interval',
      width: 80,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (status: string, record: Backtest) => {
        const statusConfig: Record<string, { color: string; text: string }> = {
          pending: { color: 'default', text: '等待中' },
          running: { color: 'processing', text: `运行中 ${record.progress}%` },
          completed: { color: 'success', text: '已完成' },
          failed: { color: 'error', text: '失败' },
        }
        const config = statusConfig[status] || { color: 'default', text: status }
        return <Tag color={config.color}>{config.text}</Tag>
      },
    },
    {
      title: '总收益率',
      dataIndex: 'total_return',
      key: 'total_return',
      width: 120,
      render: (value?: number) => {
        if (value === undefined || value === null) return '-'
        const percent = formatPercent(value * 100)
        const color = value >= 0 ? '#52c41a' : '#ff4d4f'
        return <span style={{ color }}>{percent}%</span>
      },
    },
    {
      title: '最大回撤',
      dataIndex: 'max_drawdown',
      key: 'max_drawdown',
      width: 120,
      render: (value?: number) => {
        if (value === undefined || value === null) return '-'
        return <span style={{ color: '#ff4d4f' }}>{formatPercent(value * 100)}%</span>
      },
    },
    {
      title: '夏普比率',
      dataIndex: 'sharpe_ratio',
      key: 'sharpe_ratio',
      width: 100,
      render: (value?: number) => {
        if (value === undefined || value === null) return '-'
        return formatAmount(value)
      },
    },
    {
      title: '交易次数',
      dataIndex: 'total_trades',
      key: 'total_trades',
      width: 100,
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (time: string) => dayjs(time).format('YYYY-MM-DD HH:mm:ss'),
    },
    {
      title: '操作',
      key: 'action',
      width: 200,
      fixed: 'right',
      render: (_: any, record: Backtest) => (
        <Space>
          <Button
            type="link"
            size="small"
            icon={<Eye size={14} />}
            onClick={() => navigate(`/backtest/${record.id}`)}
          >
            详情
          </Button>
          <Button
            type="link"
            size="small"
            icon={<Pencil size={14} />}
            onClick={() => handleEditDescription(record)}
          >
            备注
          </Button>
          <Button
            type="link"
            size="small"
            danger
            icon={<Trash2 size={14} />}
            onClick={() => {
              // 如果回测正在运行,显示警告
              if (record.status === 'running' || record.status === 'pending') {
                modal.confirm({
                  title: '警告',
                  content: (
                    <div>
                      <p>回测"{record.name}"正在{record.status === 'running' ? '运行中' : '等待执行'}。</p>
                      <p style={{ color: '#faad14', marginTop: 8 }}>
                        删除后回测将立即停止,已执行的进度将丢失,且无法恢复。
                      </p>
                      <p style={{ marginTop: 8 }}>确定要删除吗?</p>
                    </div>
                  ),
                  okText: '确定删除',
                  cancelText: '取消',
                  okButtonProps: { danger: true },
                  onOk: () => deleteMutation.mutate(record.id),
                })
              } else {
                modal.confirm({
                  title: '确认删除',
                  content: `确定要删除回测"${record.name}"吗?`,
                  onOk: () => deleteMutation.mutate(record.id),
                })
              }
            }}
          >
            删除
          </Button>
        </Space>
      ),
    },
  ]

  // 草稿保存 - 表单值变化时自动保存
  useEffect(() => {
    if (!createModalOpen) return

    const timer = setInterval(() => {
      const values = form.getFieldsValue()
      if (values.name || values.grid_lower) {
        // 只有填写了内容才保存
        localStorage.setItem(DRAFT_KEY, JSON.stringify({
          ...values,
          time_range: values.time_range ? [
            values.time_range[0]?.valueOf(),
            values.time_range[1]?.valueOf()
          ] : undefined
        }))
      }
    }, 2000) // 每2秒保存一次

    return () => clearInterval(timer)
  }, [createModalOpen, form])

  // 打开模态框时加载草稿
  const handleOpenModal = () => {
    setCreateModalOpen(true)
    setCurrentStep(0) // 重置步骤
    setPriceReference(null) // 重置价格参考

    // 尝试加载草稿
    const draft = localStorage.getItem(DRAFT_KEY)
    if (draft) {
      try {
        const draftData = JSON.parse(draft)
        // 恢复时间范围
        if (draftData.time_range) {
          draftData.time_range = [
            dayjs(draftData.time_range[0]),
            dayjs(draftData.time_range[1])
          ]
        }
        form.setFieldsValue(draftData)
        setStrategyType(draftData.strategy_type || 'grid')
        messageApi.info('已恢复上次编辑的草稿')
      } catch (e) {
        console.error('加载草稿失败:', e)
      }
    }
  }

  // 步骤切换 - 验证当前步骤
  const handleStepChange = async (step: number) => {
    if (step > currentStep) {
      // 前进时验证当前步骤
      try {
        if (currentStep === 0) {
          // 第一步:基础信息
          await form.validateFields(['name', 'strategy_type', 'symbol', 'interval', 'time_range', 'initial_capital'])
        } else if (currentStep === 1) {
          // 第二步:策略参数
          if (strategyType === 'grid') {
            await form.validateFields(['grid_lower', 'grid_upper', 'grid_num', 'amount_per_grid', 'fee_rate'])
          } else if (strategyType === 'grid_mm') {
            await form.validateFields(['grid_spread', 'grid_levels', 'amount_per_grid', 'fee_rate'])
          }
        }
        setCurrentStep(step)
      } catch (error) {
        messageApi.error('请完整填写当前步骤的必填项')
      }
    } else {
      // 后退不需要验证
      setCurrentStep(step)
    }
  }

  // 网格参数实时计算
  const calculateGridParams = () => {
    const values = form.getFieldsValue()
    const { grid_lower, grid_upper, grid_num, amount_per_grid, initial_capital } = values

    if (!grid_lower || !grid_upper || !grid_num || !amount_per_grid || !initial_capital) {
      setGridCalculations(null)
      return
    }

    const gridSpacing = (grid_upper - grid_lower) / grid_num
    const avgPrice = (grid_upper + grid_lower) / 2
    const estimatedFunds = amount_per_grid * grid_num * avgPrice

    let warningMessage = ''
    if (estimatedFunds > initial_capital) {
      warningMessage = `资金不足!估算需要 ${formatAmount(estimatedFunds)} USDT,但初始资金只有 ${initial_capital} USDT`
    } else if (estimatedFunds < initial_capital * 0.5) {
      warningMessage = `资金利用率较低,只使用了 ${formatPercent((estimatedFunds / initial_capital) * 100, 1)}% 的资金`
    }

    setGridCalculations({
      gridSpacing,
      estimatedFunds,
      warningMessage
    })
  }

  // 监听网格参数变化
  useEffect(() => {
    if (createModalOpen && strategyType === 'grid') {
      calculateGridParams()
    }
  }, [createModalOpen, strategyType])

  const handleCreate = async () => {
    try {
      const values = await form.validateFields()
      const [startTime, endTime] = values.time_range

      // 验证数据范围
      const params = new URLSearchParams({
        symbol: values.symbol,
        interval: values.interval,
        start_time: startTime.valueOf().toString(),
        end_time: endTime.valueOf().toString(),
      })
      const validateResponse = await fetch(`${BACKTEST_API.klines.validate}?${params}`)

      if (!validateResponse.ok) {
        messageApi.error('验证数据范围失败')
        return
      }

      const validateResult = await validateResponse.json()

      if (!validateResult.is_sufficient) {
        // 数据不足,显示详细提示并提供多种操作选项
        modal.warning({
          title: '数据不足',
          width: 650,
          content: (
            <div>
              <Alert
                message={validateResult.message}
                type="warning"
                showIcon
                style={{ marginBottom: 16 }}
              />

              {validateResult.has_data && (
                <div style={{ marginBottom: 16 }}>
                  <div style={{ padding: 12, background: '#1a1a1a', borderRadius: 4, marginBottom: 12 }}>
                    <p style={{ margin: '4px 0', fontSize: 13 }}>
                      <strong>请求的时间范围:</strong> {validateResult.requested_start_str} 至 {validateResult.requested_end_str}
                    </p>
                    <p style={{ margin: '4px 0', fontSize: 13 }}>
                      <strong>数据库中的数据:</strong> {validateResult.data_start_str} 至 {validateResult.data_end_str}
                    </p>
                  </div>

                  {/* 提供快捷调整建议 */}
                  <Alert
                    message="快捷操作建议"
                    description={
                      <Space direction="vertical" size={8} style={{ width: '100%' }}>
                        <div>
                          <strong>方案一:</strong> 调整回测时间范围至现有数据区间
                          <br />
                          <Button
                            size="small"
                            type="link"
                            style={{ padding: 0, marginTop: 4 }}
                            onClick={() => {
                              // 调整时间范围到数据库可用范围
                              const dataStart = dayjs(validateResult.data_start_str)
                              const dataEnd = dayjs(validateResult.data_end_str)
                              form.setFieldsValue({ time_range: [dataStart, dataEnd] })
                              Modal.destroyAll()
                              messageApi.success('已自动调整时间范围到可用数据区间')
                              // 返回到第一步让用户确认
                              setCurrentStep(0)
                            }}
                          >
                            点击自动调整时间范围
                          </Button>
                        </div>
                        <div>
                          <strong>方案二:</strong> 前往K线数据管理页面获取所需时间段的数据
                          <br />
                          <span style={{ fontSize: 12, color: '#8c8c8c' }}>
                            (推荐: 可获取完整的历史数据用于回测)
                          </span>
                        </div>
                      </Space>
                    }
                    type="info"
                    showIcon
                  />
                </div>
              )}

              {!validateResult.has_data && (
                <Alert
                  message="该交易对暂无K线数据"
                  description="请先前往K线数据管理页面获取该交易对的历史数据"
                  type="error"
                  showIcon
                  style={{ marginBottom: 16 }}
                />
              )}
            </div>
          ),
          okText: validateResult.has_data ? '前往获取数据' : '前往K线数据管理',
          cancelText: '留在此页',
          onOk: () => {
            navigate('/kline-manager')
          },
          onCancel: () => {
            // 取消时返回到第一步,让用户修改参数
            setCurrentStep(0)
          }
        })
        return
      }

      // 数据充足,继续创建回测
      createMutation.mutate(values)
    } catch (error) {
      // 表单验证失败
    }
  }

  return (
    <div style={{ padding: '24px' }}>
      <Alert
        message="提示"
        description={
          <Space direction="vertical" size={4}>
            <span>回测需要历史K线数据，请先确保已获取所需时间范围的数据。</span>
            <Button
              type="link"
              icon={<Database size={14} />}
              onClick={() => navigate('/kline-manager')}
              style={{ padding: 0, height: 'auto' }}
            >
              前往K线数据管理
            </Button>
          </Space>
        }
        type="info"
        closable
        style={{ marginBottom: 16 }}
      />

      <Card
        title="回测列表"
        extra={
          <Space>
            <Button icon={<RefreshCw size={14} />} onClick={() => refetch()}>
              刷新
            </Button>
            <Button type="primary" icon={<Plus size={14} />} onClick={handleOpenModal}>
              创建回测
            </Button>
          </Space>
        }
      >
        {/* 筛选和排序工具栏 */}
        <Space style={{ marginBottom: 16 }} wrap>
          <span>筛选:</span>
          <Select
            style={{ width: 120 }}
            placeholder="状态"
            allowClear
            value={filterStatus}
            onChange={setFilterStatus}
            options={[
              { label: '等待中', value: 'pending' },
              { label: '运行中', value: 'running' },
              { label: '已完成', value: 'completed' },
              { label: '失败', value: 'failed' },
            ]}
          />
          <Select
            style={{ width: 120 }}
            placeholder="策略类型"
            allowClear
            value={filterStrategy}
            onChange={setFilterStrategy}
            options={[
              { label: '网格策略', value: 'grid' },
              { label: '网格做市', value: 'grid_mm' },
            ]}
          />

          <span style={{ marginLeft: 16 }}>排序:</span>
          <Select
            style={{ width: 140 }}
            value={sortField}
            onChange={setSortField}
            options={[
              { label: '创建时间', value: 'created_at' },
              { label: '总收益率', value: 'total_return' },
              { label: '最大回撤', value: 'max_drawdown' },
              { label: '夏普比率', value: 'sharpe_ratio' },
              { label: '交易次数', value: 'total_trades' },
            ]}
          />
          <Select
            style={{ width: 100 }}
            value={sortOrder}
            onChange={setSortOrder}
            options={[
              { label: '降序', value: 'desc' },
              { label: '升序', value: 'asc' },
            ]}
          />

          <Button
            size="small"
            onClick={() => {
              setFilterStatus(null)
              setFilterStrategy(null)
              setSortField('created_at')
              setSortOrder('desc')
            }}
          >
            重置
          </Button>

          {/* 批量操作 */}
          {selectedRowKeys.length > 0 && (
            <>
              <span style={{ marginLeft: 16, color: '#1890ff' }}>
                已选择 {selectedRowKeys.length} 项
              </span>
              <Button
                size="small"
                type="primary"
                onClick={handleCompare}
                disabled={selectedRowKeys.length < 2 || selectedRowKeys.length > 3}
              >
                对比分析 ({selectedRowKeys.length}/2-3)
              </Button>
              <Button
                size="small"
                danger
                icon={<Trash2 size={14} />}
                onClick={handleBatchDelete}
                loading={batchDeleteMutation.isPending}
              >
                批量删除
              </Button>
            </>
          )}

          <span style={{ marginLeft: 16, color: '#8c8c8c' }}>
            显示 {backtests.length} / {rawBacktests?.length || 0} 条
          </span>
        </Space>

        <Table
          columns={columns}
          dataSource={backtests}
          rowKey="id"
          loading={isLoading}
          rowSelection={{
            selectedRowKeys,
            onChange: setSelectedRowKeys,
            selections: [
              Table.SELECTION_ALL,
              Table.SELECTION_INVERT,
              Table.SELECTION_NONE,
            ],
          }}
          scroll={{ x: 1400 }}
          pagination={{
            showSizeChanger: true,
            showTotal: (total) => `共 ${total} 条`,
          }}
        />
      </Card>

      {/* 创建回测模态框 */}
      <Modal
        title="创建回测"
        open={createModalOpen}
        onCancel={() => {
          setCreateModalOpen(false)
          form.resetFields()
          setStrategyType('grid')
          setGridCalculations(null)
          setPriceReference(null)
          setCurrentStep(0)
        }}
        width={720}
        footer={
          <Space>
            <Button onClick={() => {
              setCreateModalOpen(false)
              form.resetFields()
              setStrategyType('grid')
              setGridCalculations(null)
              setPriceReference(null)
              setCurrentStep(0)
            }}>
              取消
            </Button>
            {currentStep > 0 && (
              <Button onClick={() => setCurrentStep(currentStep - 1)}>
                上一步
              </Button>
            )}
            {currentStep < 2 && (
              <Button type="primary" onClick={() => handleStepChange(currentStep + 1)}>
                下一步
              </Button>
            )}
            {currentStep === 2 && (
              <Button type="primary" loading={createMutation.isPending} onClick={handleCreate}>
                创建回测
              </Button>
            )}
          </Space>
        }
      >
        <Spin spinning={createMutation.isPending}>
          {/* 步骤指示器 */}
          <Steps
            current={currentStep}
            onChange={handleStepChange}
            style={{ marginBottom: 24 }}
            items={[
              {
                title: '基础信息',
                description: '选择交易对和时间范围',
              },
              {
                title: '策略参数',
                description: '配置网格参数',
              },
              {
                title: '确认创建',
                description: '检查参数并创建',
              },
            ]}
          />

          <Form
            form={form}
            layout="vertical"
            initialValues={{
              strategy_type: 'grid',
              symbol: 'BTC-USDT',
              interval: '1H',
              initial_capital: 10000,
              // 普通网格策略默认值
              grid_num: 10,
              // 网格做市策略默认值
              grid_spread: 0.01,  // 1%
              grid_levels: 5,
              // 通用默认值
              amount_per_grid: 0.001,
              fee_rate: 0.001,
            }}
          >
            {/* 第一步: 基础信息 */}
            <div style={{ display: currentStep === 0 ? 'block' : 'none' }}>
              <Form.Item
                name="name"
                label="回测名称"
                rules={[{ required: true, message: '请输入回测名称' }]}
              >
                <Input
                  placeholder="例如: BTC网格策略回测"
                  suffix={
                    <Tooltip title="根据交易对和时间范围自动生成名称">
                      <Button
                        type="link"
                        size="small"
                        onClick={generateBacktestName}
                        style={{ padding: 0 }}
                      >
                        自动生成
                      </Button>
                    </Tooltip>
                  }
                />
              </Form.Item>

              <Form.Item
                name="strategy_type"
                label="策略类型"
                rules={[{ required: true }]}
              >
                <Select onChange={(value) => setStrategyType(value)}>
                  <Select.OptGroup label="网格策略">
                    <Select.Option value="grid">网格策略</Select.Option>
                    <Select.Option value="grid_mm">网格做市</Select.Option>
                  </Select.OptGroup>
                  <Select.OptGroup label="趋势策略">
                    <Select.Option value="ma_cross">均线交叉</Select.Option>
                    <Select.Option value="dual_ma_cross">双均线(多空)</Select.Option>
                  </Select.OptGroup>
                </Select>
              </Form.Item>

              <Form.Item
                name="symbol"
                label={
                  <span>
                    交易对{' '}
                    <Tooltip title="选择您已获取K线数据的交易对">
                      <HelpCircle size={14} style={{ color: '#8c8c8c' }} />
                    </Tooltip>
                  </span>
                }
                rules={[{ required: true, message: '请选择交易对' }]}
              >
                <Select
                  showSearch
                  allowClear
                  placeholder="选择或输入交易对，如 BTC-USDT"
                  filterOption={(input, option) =>
                    String(option?.label ?? '').toLowerCase().includes(input.toLowerCase())
                  }
                  options={(availableSymbols ?? DEFAULT_SYMBOLS).map(sym => ({
                    label: sym,
                    value: sym,
                  }))}
                />
              </Form.Item>

              <Form.Item
                name="interval"
                label="K线周期"
                rules={[{ required: true }]}
              >
                <Select>
                  <Select.Option value="1m">1分钟</Select.Option>
                  <Select.Option value="5m">5分钟</Select.Option>
                  <Select.Option value="15m">15分钟</Select.Option>
                  <Select.Option value="30m">30分钟</Select.Option>
                  <Select.Option value="1H">1小时</Select.Option>
                  <Select.Option value="4H">4小时</Select.Option>
                  <Select.Option value="1D">1天</Select.Option>
                </Select>
              </Form.Item>

              <Form.Item
                name="time_range"
                label={
                  <span>
                    回测时间范围{' '}
                    <Tooltip title="选择回测的起止时间,确保该时间范围内有K线数据">
                      <HelpCircle size={14} style={{ color: '#8c8c8c' }} />
                    </Tooltip>
                  </span>
                }
                rules={[{ required: true, message: '请选择时间范围' }]}
              >
                <RangePicker
                  showTime
                  style={{ width: '100%' }}
                  placement="bottomLeft"
                  classNames={{ popup: { root: 'backtest-range-picker-dropdown' } }}
                  disabledDate={(current) => {
                    // 禁止选择未来时间
                    return current && current > dayjs().endOf('day')
                  }}
                  presets={[
                    {
                      label: '最近7天',
                      value: [dayjs().subtract(7, 'day'), dayjs().subtract(2, 'hour')],
                    },
                    {
                      label: '最近30天',
                      value: [dayjs().subtract(30, 'day'), dayjs().subtract(2, 'hour')],
                    },
                    {
                      label: '最近90天',
                      value: [dayjs().subtract(90, 'day'), dayjs().subtract(2, 'hour')],
                    },
                    {
                      label: '最近180天',
                      value: [dayjs().subtract(180, 'day'), dayjs().subtract(2, 'hour')],
                    },
                  ]}
                />
              </Form.Item>

              <Form.Item
                label={
                  <span>
                    初始资金 (USDT){' '}
                    <Tooltip title="模拟交易的初始资金,建议根据实际投资额度设置">
                      <HelpCircle size={14} style={{ color: '#8c8c8c' }} />
                    </Tooltip>
                  </span>
                }
              >
                <Space.Compact style={{ width: '100%' }}>
                  <Form.Item
                    name="initial_capital"
                    noStyle
                    rules={[{ required: true, message: '请输入初始资金' }]}
                  >
                    <InputNumber min={1} style={{ width: '100%' }} onChange={calculateGridParams} />
                  </Form.Item>
                  <Button onClick={() => { form.setFieldValue('initial_capital', 1000); calculateGridParams(); }}>1千</Button>
                  <Button onClick={() => { form.setFieldValue('initial_capital', 5000); calculateGridParams(); }}>5千</Button>
                  <Button onClick={() => { form.setFieldValue('initial_capital', 10000); calculateGridParams(); }}>1万</Button>
                  <Button onClick={() => { form.setFieldValue('initial_capital', 50000); calculateGridParams(); }}>5万</Button>
                </Space.Compact>
              </Form.Item>
            </div>

            {/* 第二步: 策略参数 */}
            <div style={{ display: currentStep === 1 ? 'block' : 'none' }}>
              {/* ── 网格策略 ── */}
              {strategyType === 'grid' && (
                <>
                  {priceReference ? (
                    <Alert
                      message="价格参考"
                      description={
                        <Space>
                          <span><strong>{priceReference.suggestedLower.toLocaleString()} - {priceReference.suggestedUpper.toLocaleString()} USDT</strong>（基于历史数据）</span>
                          <Button size="small" type="primary" onClick={applySmartGridRange}>一键应用</Button>
                        </Space>
                      }
                      type="success" showIcon closable onClose={() => setPriceReference(null)}
                      style={{ marginBottom: 12 }}
                    />
                  ) : (
                    <Alert
                      message={
                        <Space>
                          <span>智能网格范围</span>
                          <Button size="small" type="primary" onClick={fetchPriceReference}>获取价格参考</Button>
                          <Button size="small" onClick={() => applyGridTemplate('conservative')}>保守型(5格)</Button>
                          <Button size="small" onClick={() => applyGridTemplate('balanced')}>平衡型(10格)</Button>
                          <Button size="small" onClick={() => applyGridTemplate('aggressive')}>激进型(20格)</Button>
                        </Space>
                      }
                      type="info" showIcon style={{ marginBottom: 12 }}
                    />
                  )}

                  <Row gutter={12}>
                    <Col span={12}>
                      <Form.Item
                        name="grid_lower"
                        label={<span>网格下限 <Tooltip title="网格交易的最低价格,建议设置为历史低点附近"><HelpCircle size={14} style={{ color: '#8c8c8c' }} /></Tooltip></span>}
                        rules={[
                          { required: true, message: '请输入网格下限' },
                          ({ getFieldValue }) => ({
                            validator(_, value) {
                              if (!value || !getFieldValue('grid_upper')) return Promise.resolve()
                              if (value >= getFieldValue('grid_upper')) return Promise.reject(new Error('下限必须小于上限'))
                              return Promise.resolve()
                            },
                          }),
                        ]}
                      >
                        <InputNumber min={0} style={{ width: '100%' }} onChange={calculateGridParams} />
                      </Form.Item>
                    </Col>
                    <Col span={12}>
                      <Form.Item
                        name="grid_upper"
                        label={<span>网格上限 <Tooltip title="网格交易的最高价格,建议设置为历史高点附近"><HelpCircle size={14} style={{ color: '#8c8c8c' }} /></Tooltip></span>}
                        rules={[
                          { required: true, message: '请输入网格上限' },
                          ({ getFieldValue }) => ({
                            validator(_, value) {
                              if (!value || !getFieldValue('grid_lower')) return Promise.resolve()
                              if (value <= getFieldValue('grid_lower')) return Promise.reject(new Error('上限必须大于下限'))
                              return Promise.resolve()
                            },
                          }),
                        ]}
                      >
                        <InputNumber min={0} style={{ width: '100%' }} onChange={calculateGridParams} />
                      </Form.Item>
                    </Col>
                  </Row>

                  <Row gutter={12}>
                    <Col span={12}>
                      <Form.Item
                        name="grid_num"
                        label={<span>网格数量 <Tooltip title="将价格区间划分为多少个网格"><HelpCircle size={14} style={{ color: '#8c8c8c' }} /></Tooltip></span>}
                        rules={[{ required: true, message: '请输入网格数量' }]}
                      >
                        <InputNumber min={2} max={100} style={{ width: '100%' }} onChange={calculateGridParams} />
                      </Form.Item>
                    </Col>
                    <Col span={12}>
                      <Form.Item
                        name="amount_per_grid"
                        label={<span>每格数量 <Tooltip title="每个网格买入/卖出的数量（基础币种）"><HelpCircle size={14} style={{ color: '#8c8c8c' }} /></Tooltip></span>}
                        rules={[{ required: true, message: '请输入每格数量' }]}
                      >
                        <InputNumber min={0} step={0.001} style={{ width: '100%' }} onChange={calculateGridParams} />
                      </Form.Item>
                    </Col>
                  </Row>

                  {gridCalculations && (
                    <Alert
                      message={
                        <Row gutter={16}>
                          <Col span={12}>
                            <Statistic title="网格间距" value={formatAmount(gridCalculations.gridSpacing)} suffix="USDT" valueStyle={{ fontSize: 16 }} />
                          </Col>
                          <Col span={12}>
                            <Statistic title="估算资金需求" value={formatAmount(gridCalculations.estimatedFunds)} suffix="USDT" valueStyle={{ fontSize: 16, color: gridCalculations.warningMessage ? '#ff4d4f' : '#52c41a' }} />
                          </Col>
                        </Row>
                      }
                      description={gridCalculations.warningMessage}
                      type={gridCalculations.warningMessage.includes('不足') ? 'error' : gridCalculations.warningMessage ? 'warning' : 'info'}
                      showIcon icon={<Calculator size={14} />} style={{ marginBottom: 12 }}
                    />
                  )}

                  <Row gutter={12}>
                    <Col span={12}>
                      <Form.Item
                        name="fee_rate"
                        label={<span>手续费率 <Tooltip title="OKX现货手续费: Maker 0.08%, Taker 0.1%"><HelpCircle size={14} style={{ color: '#8c8c8c' }} /></Tooltip></span>}
                        rules={[{ required: true, message: '请输入手续费率' }]}
                      >
                        <InputNumber min={0} max={1} step={0.0001} style={{ width: '100%' }} placeholder="0.001" />
                      </Form.Item>
                    </Col>
                  </Row>

                  <Form.Item name="description" label="描述">
                    <TextArea rows={2} placeholder="回测描述(可选)" />
                  </Form.Item>
                </>
              )}

              {/* ── 网格做市策略 ── */}
              {strategyType === 'grid_mm' && (
                <>
                  <Alert
                    message="网格做市策略"
                    description="在当前价格上下挂买卖单，通过价差持续做市获利。适合震荡行情，不适合单边行情。"
                    type="info" showIcon style={{ marginBottom: 12 }}
                  />

                  <Row gutter={12}>
                    <Col span={12}>
                      <Form.Item
                        name="grid_spread"
                        label={<span>网格间距 <Tooltip title="每个网格之间的价差百分比，建议0.5%-2%"><HelpCircle size={14} style={{ color: '#8c8c8c' }} /></Tooltip></span>}
                        rules={[{ required: true, message: '请输入网格间距' }]}
                      >
                        <InputNumber
                          min={0.001} max={0.1} step={0.001} style={{ width: '100%' }} placeholder="0.01 (1%)"
                          addonAfter={<span>{form.getFieldValue('grid_spread') ? `${formatPercent(form.getFieldValue('grid_spread') * 100)}%` : '0%'}</span>}
                        />
                      </Form.Item>
                    </Col>
                    <Col span={12}>
                      <Form.Item
                        name="grid_levels"
                        label={<span>网格层数 <Tooltip title="价格上下各挂多少层，总挂单数 = 层数×2，建议3-10层"><HelpCircle size={14} style={{ color: '#8c8c8c' }} /></Tooltip></span>}
                        rules={[{ required: true, message: '请输入网格层数' }]}
                      >
                        <InputNumber min={1} max={20} style={{ width: '100%' }} placeholder="5" />
                      </Form.Item>
                    </Col>
                  </Row>

                  <Row gutter={12}>
                    <Col span={12}>
                      <Form.Item
                        name="amount_per_grid"
                        label={<span>每格数量 <Tooltip title="每个网格买入/卖出的数量（基础币种）"><HelpCircle size={14} style={{ color: '#8c8c8c' }} /></Tooltip></span>}
                        rules={[{ required: true, message: '请输入每格数量' }]}
                      >
                        <InputNumber min={0} step={0.001} style={{ width: '100%' }} placeholder="0.001" />
                      </Form.Item>
                    </Col>
                    <Col span={12}>
                      <Form.Item
                        name="fee_rate"
                        label={<span>手续费率 <Tooltip title="OKX现货手续费: Maker 0.08%, Taker 0.1%"><HelpCircle size={14} style={{ color: '#8c8c8c' }} /></Tooltip></span>}
                        rules={[{ required: true, message: '请输入手续费率' }]}
                      >
                        <InputNumber min={0} max={1} step={0.0001} style={{ width: '100%' }} placeholder="0.001" />
                      </Form.Item>
                    </Col>
                  </Row>

                  <Form.Item name="description" label="描述">
                    <TextArea rows={2} placeholder="回测描述(可选)" />
                  </Form.Item>
                </>
              )}

              {/* ── 均线交叉 / 双均线策略 ── */}
              {(strategyType === 'ma_cross' || strategyType === 'dual_ma_cross') && (
                <>
                  <Alert
                    message={strategyType === 'ma_cross' ? '均线交叉策略' : '双均线策略'}
                    description={
                      strategyType === 'ma_cross'
                        ? '金叉买入，死叉卖出。适合趋势行情。'
                        : '金叉开多，死叉开空。支持杠杆和止损止盈，适合双向波动市场。'
                    }
                    type="info" showIcon style={{ marginBottom: 12 }}
                  />

                  <Row gutter={12}>
                    <Col span={12}>
                      <Form.Item
                        name="fast_period"
                        label={<span>快线周期 <Tooltip title="快速均线计算周期，建议5-10"><HelpCircle size={14} style={{ color: '#8c8c8c' }} /></Tooltip></span>}
                        rules={[{ required: true, message: '请输入快线周期' }]}
                        initialValue={5}
                      >
                        <InputNumber min={1} max={50} style={{ width: '100%' }} placeholder="5" />
                      </Form.Item>
                    </Col>
                    <Col span={12}>
                      <Form.Item
                        name="slow_period"
                        label={<span>慢线周期 <Tooltip title="慢速均线计算周期，建议20-60"><HelpCircle size={14} style={{ color: '#8c8c8c' }} /></Tooltip></span>}
                        rules={[{ required: true, message: '请输入慢线周期' }]}
                        initialValue={20}
                      >
                        <InputNumber min={1} max={200} style={{ width: '100%' }} placeholder="20" />
                      </Form.Item>
                    </Col>
                  </Row>

                  <Row gutter={12}>
                    <Col span={12}>
                      <Form.Item
                        name="ma_type"
                        label={<span>均线类型 <Tooltip title="SMA为简单移动平均，EMA对近期价格更敏感"><HelpCircle size={14} style={{ color: '#8c8c8c' }} /></Tooltip></span>}
                        initialValue="EMA"
                      >
                        <Select>
                          <Select.Option value="EMA">EMA（指数移动平均）</Select.Option>
                          <Select.Option value="SMA">SMA（简单移动平均）</Select.Option>
                        </Select>
                      </Form.Item>
                    </Col>
                    <Col span={12}>
                      <Form.Item
                        name="amount_per_trade"
                        label={<span>每次交易量 <Tooltip title="每次开仓的交易数量（基础币种）"><HelpCircle size={14} style={{ color: '#8c8c8c' }} /></Tooltip></span>}
                        rules={[{ required: strategyType === 'ma_cross', message: '请输入每次交易数量' }]}
                        initialValue={0.01}
                      >
                        <InputNumber min={0.001} step={0.001} style={{ width: '100%' }} placeholder="0.01" />
                      </Form.Item>
                    </Col>
                  </Row>

                  {/* 双均线策略特有参数 */}
                  {strategyType === 'dual_ma_cross' && (
                    <>
                      <Row gutter={12}>
                        <Col span={12}>
                          <Form.Item
                            name="position_ratio"
                            label={<span>仓位比例 <Tooltip title="每次开仓使用资金的比例，0.9=90%"><HelpCircle size={14} style={{ color: '#8c8c8c' }} /></Tooltip></span>}
                            initialValue={0.9}
                          >
                            <InputNumber min={0.1} max={1} step={0.1} style={{ width: '100%' }} placeholder="0.9" />
                          </Form.Item>
                        </Col>
                        <Col span={12}>
                          <Form.Item
                            name="leverage"
                            label={<span>杠杆倍数 <Tooltip title="1表示不使用杠杆"><HelpCircle size={14} style={{ color: '#8c8c8c' }} /></Tooltip></span>}
                            initialValue={1}
                          >
                            <InputNumber min={1} max={125} style={{ width: '100%' }} placeholder="1" />
                          </Form.Item>
                        </Col>
                      </Row>

                      <Row gutter={12}>
                        <Col span={12}>
                          <Form.Item
                            name="stop_loss"
                            label={<span>止损比例 <Tooltip title="亏损达到该比例时止损，0表示不启用"><HelpCircle size={14} style={{ color: '#8c8c8c' }} /></Tooltip></span>}
                            initialValue={0}
                          >
                            <InputNumber min={0} max={0.5} step={0.01} style={{ width: '100%' }} placeholder="0.05 (5%)" />
                          </Form.Item>
                        </Col>
                        <Col span={12}>
                          <Form.Item
                            name="take_profit"
                            label={<span>止盈比例 <Tooltip title="盈利达到该比例时止盈，0表示不启用"><HelpCircle size={14} style={{ color: '#8c8c8c' }} /></Tooltip></span>}
                            initialValue={0}
                          >
                            <InputNumber min={0} max={1} step={0.01} style={{ width: '100%' }} placeholder="0.1 (10%)" />
                          </Form.Item>
                        </Col>
                      </Row>

                      <Row gutter={12}>
                        <Col span={12}>
                          <Form.Item
                            name="enable_short"
                            label={<span>启用做空 <Tooltip title="是否在死叉时开空仓"><HelpCircle size={14} style={{ color: '#8c8c8c' }} /></Tooltip></span>}
                            valuePropName="checked"
                            initialValue={true}
                          >
                            <Select>
                              <Select.Option value={true}>是</Select.Option>
                              <Select.Option value={false}>否</Select.Option>
                            </Select>
                          </Form.Item>
                        </Col>
                        <Col span={12}>
                          <Form.Item
                            name="fee_rate"
                            label={<span>手续费率 <Tooltip title="OKX现货手续费: Maker 0.08%, Taker 0.1%"><HelpCircle size={14} style={{ color: '#8c8c8c' }} /></Tooltip></span>}
                            rules={[{ required: true, message: '请输入手续费率' }]}
                          >
                            <InputNumber min={0} max={1} step={0.0001} style={{ width: '100%' }} placeholder="0.001" />
                          </Form.Item>
                        </Col>
                      </Row>
                    </>
                  )}

                  {strategyType === 'ma_cross' && (
                    <Row gutter={12}>
                      <Col span={12}>
                        <Form.Item
                          name="fee_rate"
                          label={<span>手续费率 <Tooltip title="OKX现货手续费: Maker 0.08%, Taker 0.1%"><HelpCircle size={14} style={{ color: '#8c8c8c' }} /></Tooltip></span>}
                          rules={[{ required: true, message: '请输入手续费率' }]}
                        >
                          <InputNumber min={0} max={1} step={0.0001} style={{ width: '100%' }} placeholder="0.001" />
                        </Form.Item>
                      </Col>
                    </Row>
                  )}

                  <Form.Item name="description" label="描述">
                    <TextArea rows={2} placeholder="回测描述(可选)" />
                  </Form.Item>
                </>
              )}
            </div>

            {/* 第三步: 确认信息 */}
            <div style={{ display: currentStep === 2 ? 'block' : 'none' }}>
              <Alert
                message="请确认回测参数"
                description="请仔细核对以下参数,确认无误后点击创建回测按钮"
                type="info"
                showIcon
                style={{ marginBottom: 16 }}
              />

              {(() => {
                const values = form.getFieldsValue()
                const getStrategyName = (type: string) => {
                  const names: Record<string, string> = {
                    'grid': '网格策略',
                    'grid_mm': '网格做市',
                    'ma_cross': '均线交叉',
                    'dual_ma_cross': '双均线(多空)'
                  }
                  return names[type] || type
                }
                const strategyName = getStrategyName(values.strategy_type)
                const startTime = values.time_range?.[0]?.format('YYYY-MM-DD HH:mm')
                const endTime = values.time_range?.[1]?.format('YYYY-MM-DD HH:mm')

                return (
                  <div style={{ padding: '16px 0' }}>
                    <Row gutter={[16, 16]}>
                      <Col span={24}>
                        <Card size="small" title="基础信息" style={{ marginBottom: 16 }}>
                          <Row gutter={[16, 12]}>
                            <Col span={12}>
                              <div style={{ color: '#8c8c8c' }}>回测名称</div>
                              <div style={{ fontSize: 14, marginTop: 4 }}>{values.name || '-'}</div>
                            </Col>
                            <Col span={12}>
                              <div style={{ color: '#8c8c8c' }}>策略类型</div>
                              <div style={{ fontSize: 14, marginTop: 4 }}>{strategyName}</div>
                            </Col>
                            <Col span={12}>
                              <div style={{ color: '#8c8c8c' }}>交易对</div>
                              <div style={{ fontSize: 14, marginTop: 4 }}>{values.symbol || '-'}</div>
                            </Col>
                            <Col span={12}>
                              <div style={{ color: '#8c8c8c' }}>K线周期</div>
                              <div style={{ fontSize: 14, marginTop: 4 }}>{values.interval || '-'}</div>
                            </Col>
                            <Col span={24}>
                              <div style={{ color: '#8c8c8c' }}>时间范围</div>
                              <div style={{ fontSize: 14, marginTop: 4 }}>
                                {startTime && endTime ? `${startTime} 至 ${endTime}` : '-'}
                              </div>
                            </Col>
                            <Col span={12}>
                              <div style={{ color: '#8c8c8c' }}>初始资金</div>
                              <div style={{ fontSize: 14, marginTop: 4 }}>{values.initial_capital ? `${values.initial_capital.toLocaleString()} USDT` : '-'}</div>
                            </Col>
                          </Row>
                        </Card>
                      </Col>

                      {values.strategy_type === 'grid' && (
                        <Col span={24}>
                          <Card size="small" title="网格参数">
                            <Row gutter={[16, 12]}>
                              <Col span={12}>
                                <Statistic
                                  title="网格下限"
                                  value={values.grid_lower || 0}
                                  suffix="USDT"
                                  valueStyle={{ fontSize: 18 }}
                                />
                              </Col>
                              <Col span={12}>
                                <Statistic
                                  title="网格上限"
                                  value={values.grid_upper || 0}
                                  suffix="USDT"
                                  valueStyle={{ fontSize: 18 }}
                                />
                              </Col>
                              <Col span={12}>
                                <Statistic
                                  title="网格数量"
                                  value={values.grid_num || 0}
                                  suffix="格"
                                  valueStyle={{ fontSize: 18 }}
                                />
                              </Col>
                              <Col span={12}>
                                <Statistic
                                  title="每格数量"
                                  value={values.amount_per_grid || 0}
                                  valueStyle={{ fontSize: 18 }}
                                />
                              </Col>
                              <Col span={12}>
                                <Statistic
                                  title="手续费率"
                                  value={formatPercent(values.fee_rate * 100)}
                                  suffix="%"
                                  valueStyle={{ fontSize: 18 }}
                                />
                              </Col>
                              {gridCalculations && (
                                <>
                                  <Col span={12}>
                                    <Statistic
                                      title="网格间距"
                                      value={formatAmount(gridCalculations.gridSpacing)}
                                      suffix="USDT"
                                      valueStyle={{ fontSize: 18, color: '#1890ff' }}
                                    />
                                  </Col>
                                  <Col span={24}>
                                    <Statistic
                                      title="估算资金需求"
                                      value={formatAmount(gridCalculations.estimatedFunds)}
                                      suffix="USDT"
                                      valueStyle={{
                                        fontSize: 18,
                                        color: gridCalculations.warningMessage.includes('不足') ? '#ff4d4f' : '#52c41a'
                                      }}
                                    />
                                    {gridCalculations.warningMessage && (
                                      <div style={{ marginTop: 8, color: gridCalculations.warningMessage.includes('不足') ? '#ff4d4f' : '#faad14' }}>
                                        {gridCalculations.warningMessage}
                                      </div>
                                    )}
                                  </Col>
                                </>
                              )}
                            </Row>

                            {values.description && (
                              <div style={{ marginTop: 16, paddingTop: 16, borderTop: '1px solid #303030' }}>
                                <div style={{ color: '#8c8c8c', marginBottom: 8 }}>描述</div>
                                <div style={{ fontSize: 14 }}>{values.description}</div>
                              </div>
                            )}
                          </Card>
                        </Col>
                      )}

                      {/* 网格做市策略参数确认 */}
                      {values.strategy_type === 'grid_mm' && (
                        <Col span={24}>
                          <Card size="small" title="网格做市参数">
                            <Row gutter={[16, 12]}>
                              <Col span={12}>
                                <Statistic
                                  title="网格间距"
                                  value={formatPercent((values.grid_spread || 0) * 100)}
                                  suffix="%"
                                  valueStyle={{ fontSize: 18 }}
                                />
                              </Col>
                              <Col span={12}>
                                <Statistic
                                  title="网格层数"
                                  value={values.grid_levels || 0}
                                  suffix="层/侧"
                                  valueStyle={{ fontSize: 18 }}
                                />
                              </Col>
                              <Col span={12}>
                                <Statistic
                                  title="总挂单数"
                                  value={(values.grid_levels || 0) * 2}
                                  suffix="单"
                                  valueStyle={{ fontSize: 18, color: '#1890ff' }}
                                />
                              </Col>
                              <Col span={12}>
                                <Statistic
                                  title="每格数量"
                                  value={values.amount_per_grid || 0}
                                  valueStyle={{ fontSize: 18 }}
                                />
                              </Col>
                              <Col span={12}>
                                <Statistic
                                  title="手续费率"
                                  value={formatPercent(values.fee_rate * 100)}
                                  suffix="%"
                                  valueStyle={{ fontSize: 18 }}
                                />
                              </Col>
                            </Row>

                            {values.description && (
                              <div style={{ marginTop: 16, paddingTop: 16, borderTop: '1px solid #303030' }}>
                                <div style={{ color: '#8c8c8c', marginBottom: 8 }}>描述</div>
                                <div style={{ fontSize: 14 }}>{values.description}</div>
                              </div>
                            )}
                          </Card>
                        </Col>
                      )}

                      {/* 均线交叉策略参数确认 */}
                      {(values.strategy_type === 'ma_cross' || values.strategy_type === 'dual_ma_cross') && (
                        <Col span={24}>
                          <Card size="small" title="均线交叉参数">
                            <Row gutter={[16, 12]}>
                              <Col span={12}>
                                <Statistic
                                  title="快线周期"
                                  value={values.fast_period || 5}
                                  suffix={values.ma_type || 'EMA'}
                                  valueStyle={{ fontSize: 18 }}
                                />
                              </Col>
                              <Col span={12}>
                                <Statistic
                                  title="慢线周期"
                                  value={values.slow_period || 20}
                                  suffix={values.ma_type || 'EMA'}
                                  valueStyle={{ fontSize: 18 }}
                                />
                              </Col>
                              <Col span={12}>
                                <Statistic
                                  title="每次交易数量"
                                  value={values.amount_per_trade || 0.01}
                                  valueStyle={{ fontSize: 18 }}
                                />
                              </Col>
                              <Col span={12}>
                                <Statistic
                                  title="手续费率"
                                  value={formatPercent(values.fee_rate * 100)}
                                  suffix="%"
                                  valueStyle={{ fontSize: 18 }}
                                />
                              </Col>
                              {values.strategy_type === 'dual_ma_cross' && (
                                <>
                                  <Col span={12}>
                                    <Statistic
                                      title="仓位比例"
                                      value={formatPercent((values.position_ratio || 0.9) * 100)}
                                      suffix="%"
                                      valueStyle={{ fontSize: 18 }}
                                    />
                                  </Col>
                                  <Col span={12}>
                                    <Statistic
                                      title="杠杆倍数"
                                      value={values.leverage || 1}
                                      suffix="x"
                                      valueStyle={{ fontSize: 18, color: values.leverage > 1 ? '#ff4d4f' : undefined }}
                                    />
                                  </Col>
                                  <Col span={12}>
                                    <Statistic
                                      title="启用做空"
                                      value={values.enable_short ? '是' : '否'}
                                      valueStyle={{ fontSize: 18 }}
                                    />
                                  </Col>
                                  <Col span={12}>
                                    <Statistic
                                      title="止损/止盈"
                                      value={`${formatPercent((values.stop_loss || 0) * 100)}% / ${formatPercent((values.take_profit || 0) * 100)}%`}
                                      valueStyle={{ fontSize: 18 }}
                                    />
                                  </Col>
                                </>
                              )}
                            </Row>

                            {values.description && (
                              <div style={{ marginTop: 16, paddingTop: 16, borderTop: '1px solid #303030' }}>
                                <div style={{ color: '#8c8c8c', marginBottom: 8 }}>描述</div>
                                <div style={{ fontSize: 14 }}>{values.description}</div>
                              </div>
                            )}
                          </Card>
                        </Col>
                      )}
                    </Row>
                  </div>
                )
              })()}
            </div>
          </Form>
        </Spin>
      </Modal>

      {/* 回测对比模态框 */}
      <Modal
        title="回测对比分析"
        open={compareModalOpen}
        onCancel={() => setCompareModalOpen(false)}
        width={1200}
        footer={null}
      >
        {compareModalOpen && (() => {
          const selectedBacktests = backtests.filter((bt: Backtest) =>
            selectedRowKeys.includes(bt.id)
          )

          return (
            <div>
              {/* 基本信息对比 */}
              <Card size="small" title="基本信息对比" style={{ marginBottom: 16 }}>
                <Table
                  dataSource={selectedBacktests}
                  rowKey="id"
                  pagination={false}
                  size="small"
                  scroll={{ x: 800 }}
                  columns={[
                    { title: '名称', dataIndex: 'name', key: 'name', width: 200, fixed: 'left' },
                    {
                      title: '策略类型',
                      dataIndex: 'strategy_type',
                      key: 'strategy_type',
                      width: 120,
                      render: (type: string) => type === 'grid' ? '网格策略' : '网格做市'
                    },
                    { title: '交易对', dataIndex: 'symbol', key: 'symbol', width: 120 },
                    { title: '周期', dataIndex: 'interval', key: 'interval', width: 80 },
                    {
                      title: '创建时间',
                      dataIndex: 'created_at',
                      key: 'created_at',
                      width: 180,
                      render: (date: string) => dayjs(date).format('YYYY-MM-DD HH:mm:ss')
                    },
                  ]}
                />
              </Card>

              {/* 性能指标对比 */}
              <Card size="small" title="性能指标对比">
                <Row gutter={16}>
                  {selectedBacktests.map((bt: Backtest) => (
                    <Col span={24 / selectedBacktests.length} key={bt.id}>
                      <Card
                        size="small"
                        title={bt.name}
                        style={{ marginBottom: 16 }}
                        headStyle={{ backgroundColor: '#1a1a1a' }}
                      >
                        <Row gutter={[8, 16]}>
                          <Col span={24}>
                            <Statistic
                              title="总收益率"
                              value={formatPercent((bt.total_return || 0) * 100)}
                              suffix="%"
                              valueStyle={{
                                color: (bt.total_return || 0) >= 0 ? '#52c41a' : '#ff4d4f',
                                fontSize: 20,
                                fontWeight: 600
                              }}
                            />
                          </Col>
                          <Col span={24}>
                            <Statistic
                              title="最大回撤"
                              value={formatPercent((bt.max_drawdown || 0) * 100)}
                              suffix="%"
                              valueStyle={{ color: '#ff4d4f' }}
                            />
                          </Col>
                          <Col span={24}>
                            <Statistic
                              title="夏普比率"
                              value={formatAmount(bt.sharpe_ratio || 0)}
                              valueStyle={{
                                color: (bt.sharpe_ratio || 0) > 1 ? '#52c41a' : '#8c8c8c'
                              }}
                            />
                          </Col>
                          <Col span={24}>
                            <Statistic
                              title="总交易次数"
                              value={bt.total_trades || 0}
                            />
                          </Col>
                        </Row>
                      </Card>
                    </Col>
                  ))}
                </Row>
              </Card>
            </div>
          )
        })()}
      </Modal>

      {/* 编辑描述 Modal */}
      <Modal
        title="编辑回测备注"
        open={editDescriptionModalOpen}
        onOk={handleDescriptionSubmit}
        onCancel={() => {
          setEditDescriptionModalOpen(false)
          setEditingBacktest(null)
          editDescriptionForm.resetFields()
        }}
        confirmLoading={updateDescriptionMutation.isPending}
        okText="保存"
        cancelText="取消"
        width={600}
      >
        <Form
          form={editDescriptionForm}
          layout="vertical"
          style={{ marginTop: 16 }}
        >
          <Form.Item label="回测名称">
            <Input value={editingBacktest?.name} disabled />
          </Form.Item>
          <Form.Item
            label="备注描述"
            name="description"
          >
            <TextArea
              rows={6}
              placeholder="请输入回测的备注信息，如策略思路、参数选择原因、预期结果等..."
              maxLength={1000}
              showCount
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}

export default BacktestList
