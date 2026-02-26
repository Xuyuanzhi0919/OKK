import { useState, useEffect } from 'react'
import {
  Modal, Form, Input, Select, InputNumber, Divider,
  Row, Col, Tag, Alert, Space, Button, Tooltip,
} from 'antd'
import { InfoCircleOutlined, ThunderboltOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import { strategyApi } from '@/services/api'
import { API_BASE_URL } from '@/config/api'

const { TextArea } = Input

interface StrategyCreateModalProps {
  open: boolean
  onCancel: () => void
  onSuccess: () => void
  backtestData?: {
    strategy_type: string
    symbol: string
    parameters: Record<string, any>
    name?: string
  } | null
}

// 策略类型（与后端 StrategyType 保持一致）
// 注意：所有策略类型目前都未实现，创建后无法启动
const STRATEGY_TYPES = [
  {
    group: '网格策略',
    items: [
      { value: 'grid', label: '网格策略', desc: '在价格区间内自动低买高卖，适合震荡行情（开发中）', disabled: true },
    ],
  },
  {
    group: '波段策略',
    items: [
      { value: 'swing_long', label: '波段做多', desc: '基于技术指标的波段做多策略（开发中）', disabled: true },
      { value: 'swing_short', label: '波段做空', desc: '基于技术指标的波段做空策略（开发中）', disabled: true },
      { value: 'ai_swing_long', label: 'AI波段做多', desc: 'AI增强的波段做多策略（开发中）', disabled: true },
    ],
  },
  {
    group: '其他策略',
    items: [
      { value: 'martin', label: '马丁格尔', desc: '亏损后加倍仓位的策略（开发中）', disabled: true },
      { value: 'trend', label: '趋势跟踪', desc: '追踪市场趋势进行交易（开发中）', disabled: true },
      { value: 'arbitrage', label: '套利', desc: '利用价格差异进行套利（开发中）', disabled: true },
      { value: 'custom', label: '自定义', desc: '用户自定义策略（开发中）', disabled: true },
    ],
  },
]

// 交易对列表：合约（SWAP）优先，后接现货（SPOT）
const DEFAULT_SYMBOLS = [
  // ── 合约（USDT 本位永续）──
  'BTC-USDT-SWAP', 'ETH-USDT-SWAP', 'SOL-USDT-SWAP', 'BNB-USDT-SWAP',
  'XRP-USDT-SWAP', 'DOGE-USDT-SWAP', 'ADA-USDT-SWAP', 'AVAX-USDT-SWAP',
  'LINK-USDT-SWAP', 'DOT-USDT-SWAP', 'LTC-USDT-SWAP', 'ATOM-USDT-SWAP',
  'ETC-USDT-SWAP', 'ARB-USDT-SWAP', 'OP-USDT-SWAP', 'APT-USDT-SWAP',
  'NEAR-USDT-SWAP', 'SUI-USDT-SWAP', 'TRX-USDT-SWAP', 'TON-USDT-SWAP',
  'KSM-USDT-SWAP', 'INJ-USDT-SWAP', 'SEI-USDT-SWAP', 'ORDI-USDT-SWAP',
  'WLD-USDT-SWAP', 'PEPE-USDT-SWAP',
  // ── 现货（SPOT）──
  'BTC-USDT', 'ETH-USDT', 'SOL-USDT', 'BNB-USDT',
  'XRP-USDT', 'DOGE-USDT', 'ADA-USDT', 'AVAX-USDT',
  'LINK-USDT', 'DOT-USDT', 'LTC-USDT', 'ATOM-USDT',
]

const TIMEFRAMES = [
  { value: '1m', label: '1分钟' }, { value: '5m', label: '5分钟' },
  { value: '15m', label: '15分钟' }, { value: '30m', label: '30分钟' },
  { value: '1H', label: '1小时' }, { value: '4H', label: '4小时' },
  { value: '1D', label: '1天' },
]

const StrategyCreateModal: React.FC<StrategyCreateModalProps> = ({
  open, onCancel, onSuccess, backtestData,
}) => {
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [strategyType, setStrategyType] = useState<string>(backtestData?.strategy_type || 'grid')
  const [gridCalc, setGridCalc] = useState<{ spacing: number; funds: number } | null>(null)

  // 获取可用交易对：DB 中已有 K 线的排前面，再合并默认列表（去重）
  const { data: availableSymbols } = useQuery({
    queryKey: ['available-symbols-strategy'],
    queryFn: async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/api/v1/backtest/symbols`)
        if (!res.ok) throw new Error()
        const symbols: string[] = await res.json()
        return [...new Set([...symbols, ...DEFAULT_SYMBOLS])]
      } catch {
        return DEFAULT_SYMBOLS
      }
    },
  })

  // 自动生成策略名称
  const generateStrategyName = () => {
    const values = form.getFieldsValue()
    const { type, symbol } = values

    if (!symbol) return

    const strategyNameMap: Record<string, string> = {
      'grid': '网格策略',
      'swing_long': '波段做多',
      'swing_short': '波段做空',
      'ai_swing_long': 'AI波段做多',
      'martin': '马丁格尔',
      'trend': '趋势跟踪',
      'arbitrage': '套利',
      'custom': '自定义',
    }
    const strategyName = strategyNameMap[type] || '策略'
    const dateStr = new Date().toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' }).replace(/\//g, '-')

    const name = `${symbol} ${strategyName} ${dateStr}`
    form.setFieldsValue({ name })
  }

  // 从回测预填数据
  useEffect(() => {
    if (backtestData && open) {
      form.setFieldsValue({
        type: backtestData.strategy_type,
        symbol: backtestData.symbol,
        name: backtestData.name || `${backtestData.symbol} ${backtestData.strategy_type}策略`,
        ...backtestData.parameters,
      })
      setStrategyType(backtestData.strategy_type)
    }
  }, [backtestData, open, form])

  // 计算网格预估
  const calcGrid = () => {
    const { grid_lower, grid_upper, grid_num, amount_per_grid } = form.getFieldsValue()
    if (grid_lower && grid_upper && grid_num && grid_num > 0) {
      setGridCalc({
        spacing: (grid_upper - grid_lower) / grid_num,
        funds: amount_per_grid ? amount_per_grid * grid_num : 0,
      })
    }
  }

  // 获取推荐参数
  const fetchRecommended = async () => {
    const symbol = form.getFieldValue('symbol')
    if (!symbol) return
    try {
      const result = await strategyApi.recommendGridParams(symbol, form.getFieldValue('total_amount') || 1000)
      if (result) {
        form.setFieldsValue({
          grid_lower: result.grid_lower, grid_upper: result.grid_upper,
          grid_num: result.grid_num, amount_per_grid: result.amount_per_grid,
        })
        calcGrid()
      }
    } catch {}
  }

  // 提交
  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      setLoading(true)
      const parameters: Record<string, any> = {}
      const t = strategyType

      if (t === 'grid') {
        Object.assign(parameters, {
          grid_lower: values.grid_lower, grid_upper: values.grid_upper,
          grid_num: values.grid_num, amount_per_grid: values.amount_per_grid,
          total_amount: values.total_amount, fee_rate: values.fee_rate ?? 0.001,
        })
      } else if (t === 'swing_long' || t === 'swing_short' || t === 'ai_swing_long') {
        Object.assign(parameters, {
          leverage: values.leverage ?? 1,
          stop_loss: values.stop_loss, take_profit: values.take_profit,
        })
      } else if (t === 'martin') {
        Object.assign(parameters, {
          initial_amount: values.initial_amount ?? 0.01,
          multiplier: values.multiplier ?? 2,
          max_levels: values.max_levels ?? 5,
        })
      } else if (t === 'trend') {
        Object.assign(parameters, {
          fast_period: values.fast_period ?? 5, slow_period: values.slow_period ?? 20,
          amount_per_trade: values.amount_per_trade ?? 0.01,
        })
      } else if (t === 'custom') {
        Object.assign(parameters, values.custom_params ?? {})
      }

      await strategyApi.create({
        name: values.name, type: strategyType as any,
        symbol: values.symbol, timeframe: values.timeframe ?? '1H',
        parameters, description: values.description,
      } as any)

      form.resetFields()
      onSuccess()
    } catch (err: any) {
      if (err?.errorFields) return
    } finally {
      setLoading(false)
    }
  }

  const handleCancel = () => { form.resetFields(); setGridCalc(null); onCancel() }

  // ── 紧凑样式 ──────────────────────────────────────────────
  const compactDivider = { fontSize: 12, color: '#8c8c8c', margin: '12px 0 8px' }
  const compactItem = { marginBottom: 8 }

  // ── 参数区块 ──────────────────────────────────────────────
  const GridParams = () => (
    <>
      <Divider orientation="left" style={compactDivider}>网格参数</Divider>
      <Row gutter={12}>
        <Col span={12}>
          <Form.Item name="grid_lower" label="价格下限" rules={[{ required: true, message: '请输入' }]} style={compactItem}>
            <InputNumber style={{ width: '100%' }} placeholder="下限价格" min={0} precision={4} onChange={calcGrid} />
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item name="grid_upper" label="价格上限" rules={[{ required: true, message: '请输入' }]} style={compactItem}>
            <InputNumber style={{ width: '100%' }} placeholder="上限价格" min={0} precision={4} onChange={calcGrid} />
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item name="grid_num" label="网格数量" rules={[{ required: true, message: '请输入' }]} style={compactItem}>
            <InputNumber style={{ width: '100%' }} placeholder="2 ~ 100" min={2} max={100} onChange={calcGrid} />
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item name="amount_per_grid" label="每格投入 (USDT)" rules={[{ required: true, message: '请输入' }]} style={compactItem}>
            <InputNumber style={{ width: '100%' }} placeholder="金额" min={1} precision={2} onChange={calcGrid} />
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item name="total_amount" label="总投入 (USDT)" style={compactItem}>
            <InputNumber style={{ width: '100%' }} placeholder="可选" min={10} precision={2} />
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item name="fee_rate" label="手续费率" initialValue={0.001} style={compactItem}>
            <InputNumber style={{ width: '100%' }} min={0} max={0.01} step={0.0001} precision={4} />
          </Form.Item>
        </Col>
      </Row>
      <Space style={{ marginBottom: 8 }}>
        <Button size="small" icon={<ThunderboltOutlined />} onClick={fetchRecommended}>
          智能推荐参数
        </Button>
      </Space>
      {gridCalc && (
        <Row gutter={16} style={{ marginBottom: 8 }}>
          <Col span={12}>
            <div style={{ background: '#1f1f1f', borderRadius: 6, padding: '8px 12px', fontSize: 13 }}>
              <span style={{ color: '#8c8c8c' }}>网格间距：</span>
              <span style={{ color: '#e5e5e5', fontFamily: 'monospace' }}>{gridCalc.spacing.toFixed(4)}</span>
            </div>
          </Col>
          <Col span={12}>
            <div style={{ background: '#1f1f1f', borderRadius: 6, padding: '8px 12px', fontSize: 13 }}>
              <span style={{ color: '#8c8c8c' }}>预估资金：</span>
              <span style={{ color: '#e5e5e5', fontFamily: 'monospace' }}>{gridCalc.funds.toFixed(2)} USDT</span>
            </div>
          </Col>
        </Row>
      )}
    </>
  )

  // 波段策略参数
  const SwingParams = () => (
    <>
      <Divider orientation="left" style={compactDivider}>波段参数</Divider>
      <Row gutter={12}>
        <Col span={12}>
          <Form.Item name="leverage" label="杠杆倍数" initialValue={1} style={compactItem}>
            <InputNumber style={{ width: '100%' }} min={1} max={20} />
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item name="stop_loss" label="止损 (%)" style={compactItem}>
            <InputNumber style={{ width: '100%' }} placeholder="可选" min={0} max={50} />
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item name="take_profit" label="止盈 (%)" style={compactItem}>
            <InputNumber style={{ width: '100%' }} placeholder="可选" min={0} max={200} />
          </Form.Item>
        </Col>
      </Row>
    </>
  )

  // 马丁格尔策略参数
  const MartinParams = () => (
    <>
      <Divider orientation="left" style={compactDivider}>马丁格尔参数</Divider>
      <Row gutter={12}>
        <Col span={12}>
          <Form.Item name="initial_amount" label="初始仓位" initialValue={0.01} style={compactItem}>
            <InputNumber style={{ width: '100%' }} placeholder="单位：币" min={0.001} precision={4} />
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item name="multiplier" label="倍数" initialValue={2} style={compactItem}>
            <InputNumber style={{ width: '100%' }} min={1.5} max={5} step={0.5} precision={1} />
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item name="max_levels" label="最大层数" initialValue={5} style={compactItem}>
            <InputNumber style={{ width: '100%' }} min={1} max={10} />
          </Form.Item>
        </Col>
      </Row>
    </>
  )

  // 趋势跟踪策略参数
  const TrendParams = () => (
    <>
      <Divider orientation="left" style={compactDivider}>趋势跟踪参数</Divider>
      <Row gutter={12}>
        <Col span={12}>
          <Form.Item name="fast_period" label="快速均线周期" initialValue={5} style={compactItem}>
            <InputNumber style={{ width: '100%' }} min={1} max={100} />
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item name="slow_period" label="慢速均线周期" initialValue={20} style={compactItem}>
            <InputNumber style={{ width: '100%' }} min={1} max={200} />
          </Form.Item>
        </Col>
        <Col span={12}>
          <Form.Item name="amount_per_trade" label="每次交易数量" initialValue={0.01} style={compactItem}>
            <InputNumber style={{ width: '100%' }} placeholder="单位：币" min={0.001} precision={4} />
          </Form.Item>
        </Col>
      </Row>
    </>
  )

  const renderParams = () => {
    switch (strategyType) {
      case 'grid':          return <GridParams />
      case 'swing_long':    return <SwingParams />
      case 'swing_short':   return <SwingParams />
      case 'ai_swing_long': return <SwingParams />
      case 'martin':        return <MartinParams />
      case 'trend':         return <TrendParams />
      default:              return null
    }
  }

  // 当前策略描述
  const currentType = STRATEGY_TYPES.flatMap(g => g.items).find(i => i.value === strategyType)

  return (
    <Modal
      title={backtestData ? '从回测创建策略' : '创建策略'}
      open={open}
      onCancel={handleCancel}
      onOk={handleSubmit}
      okText="创建"
      cancelText="取消"
      width={680}
      confirmLoading={loading}
      destroyOnHidden
      styles={{ body: { maxHeight: '65vh', overflowY: 'auto', paddingRight: 4 } }}
    >
      {backtestData && (
        <Alert
          message="已自动填充回测参数，可按需调整"
          type="info" showIcon
          style={{ marginBottom: 12 }}
        />
      )}

      <Form
        form={form}
        layout="vertical"
        initialValues={{
          type: backtestData?.strategy_type || 'grid',
          symbol: backtestData?.symbol || 'BTC-USDT-SWAP',
          timeframe: '1H',
          fee_rate: 0.001,
        }}
      >
        {/* ── 基础信息 ── */}
        <Divider orientation="left" style={compactDivider}>基础信息</Divider>
        <Row gutter={12}>
          <Col span={24}>
            <Form.Item name="name" label="策略名称" rules={[{ required: true, message: '请输入策略名称' }]} style={compactItem}>
              <Input placeholder="为策略起一个名字，如：BTC网格01" />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="type" label="策略类型" rules={[{ required: true }]} style={compactItem}>
              <Select
                onChange={(v) => { setStrategyType(v); setGridCalc(null); setTimeout(generateStrategyName, 0) }}
                placeholder="选择策略类型"
              >
                {STRATEGY_TYPES.map(group => (
                  <Select.OptGroup key={group.group} label={group.group}>
                    {group.items.map(item => (
                      <Select.Option key={item.value} value={item.value}>
                        {item.label}
                      </Select.Option>
                    ))}
                  </Select.OptGroup>
                ))}
              </Select>
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="timeframe" label="K线周期" style={compactItem}>
              <Select placeholder="选择周期">
                {TIMEFRAMES.map(tf => (
                  <Select.Option key={tf.value} value={tf.value}>{tf.label}</Select.Option>
                ))}
              </Select>
            </Form.Item>
          </Col>
          <Col span={24}>
            <Form.Item
              name="symbol"
              label={
                <Space size={4}>
                  交易对
                  <Tooltip title="合约策略请选择 XXX-USDT-SWAP 格式；现货策略请选择 XXX-USDT 格式">
                    <InfoCircleOutlined style={{ color: '#8c8c8c', fontSize: 13 }} />
                  </Tooltip>
                </Space>
              }
              rules={[{ required: true, message: '请选择交易对' }]}
              style={compactItem}
            >
              <Select
                showSearch
                allowClear
                placeholder="选择或搜索交易对，如 BTC-USDT-SWAP"
                filterOption={(input, option) =>
                  String(option?.value ?? '').toLowerCase().includes(input.toLowerCase())
                }
                onChange={() => setTimeout(generateStrategyName, 0)}
              >
                <Select.OptGroup label="合约（SWAP）">
                  {(availableSymbols ?? DEFAULT_SYMBOLS)
                    .filter(s => s.endsWith('-SWAP'))
                    .map(s => <Select.Option key={s} value={s}>{s}</Select.Option>)}
                </Select.OptGroup>
                <Select.OptGroup label="现货（SPOT）">
                  {(availableSymbols ?? DEFAULT_SYMBOLS)
                    .filter(s => !s.endsWith('-SWAP'))
                    .map(s => <Select.Option key={s} value={s}>{s}</Select.Option>)}
                </Select.OptGroup>
              </Select>
            </Form.Item>
          </Col>
        </Row>

        {/* 策略类型说明 */}
        {currentType && (
          <div style={{
            background: '#1a1a2e', border: '1px solid #2a2a4a',
            borderRadius: 6, padding: '6px 10px', marginBottom: 12, fontSize: 12,
          }}>
            <Tag color="blue" style={{ marginRight: 6 }}>{currentType.label}</Tag>
            <span style={{ color: '#8c8c8c' }}>{currentType.desc}</span>
          </div>
        )}

        {/* ── 策略参数 ── */}
        {renderParams()}

        {/* ── 备注 ── */}
        <Divider orientation="left" style={compactDivider}>备注</Divider>
        <Form.Item name="description" style={compactItem}>
          <TextArea placeholder="可选：描述策略目标、注意事项等" rows={1} />
        </Form.Item>
      </Form>
    </Modal>
  )
}

export default StrategyCreateModal
