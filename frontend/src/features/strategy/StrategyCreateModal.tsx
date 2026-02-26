import { useState, useEffect } from 'react'
import { Modal, Form, Input, Select, InputNumber, Switch, Card, Alert, Spin, Divider, Space, Button, Tag, Tooltip } from 'antd'
import { RefreshCw } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { strategyApi } from '@/services/api'
import { API_BASE_URL } from '@/config/api'
import { useTranslation } from 'react-i18next'

const { TextArea } = Input
const { Option } = Select

interface StrategyCreateModalProps {
  open: boolean
  onCancel: () => void
  onSuccess: () => void
  // 从回测结果创建时的预设数据
  backtestData?: {
    strategy_type: string
    symbol: string
    parameters: Record<string, any>
    name?: string
  } | null
}

// 策略类型配置
const STRATEGY_TYPES = [
  { value: 'grid', label: '网格策略', description: '在价格区间内自动低买高卖', icon: '📊' },
  { value: 'grid_mm', label: '网格做市策略', description: '围绕当前价格对称布置网格', icon: '📈' },
  { value: 'ma_cross', label: '均线交叉策略', description: '快慢均线金叉/死叉信号交易', icon: '〰️' },
  { value: 'dual_ma_cross', label: '双均线策略', description: '支持做多做空的双均线策略', icon: '🔀' },
  { value: 'swing_long', label: '波段做多策略', description: '逢低买入，波段持有', icon: '📈' },
  { value: 'swing_short', label: '波段做空策略', description: '逢高卖出，波段持有', icon: '📉' },
  { value: 'ai_swing_long', label: 'AI波段做多', description: 'AI增强的波段做多策略', icon: '🤖' },
  { value: 'trend', label: '趋势跟踪策略', description: '追踪市场趋势进行交易', icon: '➡️' },
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

// K线周期
const TIMEFRAMES = [
  { value: '1m', label: '1分钟' },
  { value: '5m', label: '5分钟' },
  { value: '15m', label: '15分钟' },
  { value: '30m', label: '30分钟' },
  { value: '1H', label: '1小时' },
  { value: '4H', label: '4小时' },
  { value: '1D', label: '1天' },
]

const StrategyCreateModal: React.FC<StrategyCreateModalProps> = ({
  open,
  onCancel,
  onSuccess,
  backtestData
}) => {
  const { t } = useTranslation()
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [strategyType, setStrategyType] = useState<string>(backtestData?.strategy_type || 'grid')
  const [gridCalculations, setGridCalculations] = useState<{
    gridSpacing: number
    estimatedFunds: number
  } | null>(null)

  // 获取可用交易对：DB 中已有 K 线的排在前面，再合并默认列表（去重）
  const { data: availableSymbols } = useQuery({
    queryKey: ['available-symbols-strategy'],
    queryFn: async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/api/v1/backtest/symbols`)
        if (!response.ok) throw new Error('获取交易对失败')
        const symbols: string[] = await response.json()
        return [...new Set([...symbols, ...DEFAULT_SYMBOLS])]
      } catch {
        return DEFAULT_SYMBOLS
      }
    },
  })

  // 监听策略类型变化
  useEffect(() => {
    if (backtestData) {
      form.setFieldsValue({
        strategy_type: backtestData.strategy_type,
        symbol: backtestData.symbol,
        name: backtestData.name || `${backtestData.symbol} ${backtestData.strategy_type}策略`,
        ...backtestData.parameters
      })
      setStrategyType(backtestData.strategy_type)
    }
  }, [backtestData, form])

  // 计算网格参数
  const calculateGridParams = () => {
    const values = form.getFieldsValue()
    const { grid_lower, grid_upper, grid_num, amount_per_grid } = values

    if (grid_lower && grid_upper && grid_num) {
      const spacing = (grid_upper - grid_lower) / grid_num
      const estimatedFunds = amount_per_grid ? amount_per_grid * grid_num : 0
      
      setGridCalculations({
        gridSpacing: spacing,
        estimatedFunds
      })
    }
  }

  // 获取推荐网格参数
  const getRecommendedParams = async () => {
    const symbol = form.getFieldValue('symbol')
    const totalAmount = form.getFieldValue('total_amount') || 1000

    if (!symbol) {
      return
    }

    try {
      const result = await strategyApi.recommendGridParams(symbol, totalAmount)
      if (result) {
        form.setFieldsValue({
          grid_lower: result.grid_lower,
          grid_upper: result.grid_upper,
          grid_num: result.grid_num,
          amount_per_grid: result.amount_per_grid,
        })
        calculateGridParams()
      }
    } catch (error) {
      console.error('获取推荐参数失败:', error)
    }
  }

  // 提交创建
  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      setLoading(true)

      // 构建参数对象
      const parameters: Record<string, any> = {}
      
      // 根据策略类型收集参数
      if (strategyType === 'grid' || strategyType === 'grid_mm') {
        parameters.grid_lower = values.grid_lower
        parameters.grid_upper = values.grid_upper
        parameters.grid_num = values.grid_num
        parameters.amount_per_grid = values.amount_per_grid
        parameters.total_amount = values.total_amount
        parameters.fee_rate = values.fee_rate || 0.001
        if (strategyType === 'grid_mm') {
          parameters.grid_spread = values.grid_spread
          parameters.grid_levels = values.grid_levels
        }
      } else if (strategyType === 'ma_cross' || strategyType === 'dual_ma_cross') {
        parameters.fast_period = values.fast_period || 5
        parameters.slow_period = values.slow_period || 20
        parameters.ma_type = values.ma_type || 'EMA'
        parameters.amount_per_trade = values.amount_per_trade || 0.01
        if (strategyType === 'dual_ma_cross') {
          parameters.position_ratio = values.position_ratio || 0.5
          parameters.leverage = values.leverage || 1
          parameters.enable_short = values.enable_short || false
          parameters.stop_loss = values.stop_loss
          parameters.take_profit = values.take_profit
        }
      } else if (strategyType === 'swing_long' || strategyType === 'swing_short' || strategyType === 'ai_swing_long') {
        parameters.entry_amount = values.entry_amount || 100
        parameters.stop_loss_percent = values.stop_loss_percent || 5
        parameters.take_profit_percent = values.take_profit_percent || 10
        parameters.max_position = values.max_position || 1000
      } else if (strategyType === 'trend') {
        parameters.atr_period = values.atr_period || 14
        parameters.atr_multiplier = values.atr_multiplier || 2.0
        parameters.breakout_period = values.breakout_period || 20
        parameters.position_size = values.position_size || 0.1
      }

      const payload = {
        name: values.name,
        type: strategyType as any,  // 类型转换
        symbol: values.symbol,
        timeframe: values.timeframe || '1H',
        parameters,
        description: values.description,
      }

      await strategyApi.create(payload as any)
      form.resetFields()
      onSuccess()
    } catch (error: any) {
      console.error('创建策略失败:', error)
    } finally {
      setLoading(false)
    }
  }

  // 渲染策略类型选择卡片
  const renderStrategyTypeCard = (type: typeof STRATEGY_TYPES[0]) => (
    <div
      key={type.value}
      className={`strategy-type-card ${strategyType === type.value ? 'selected' : ''}`}
      onClick={() => setStrategyType(type.value)}
      style={{
        padding: '12px',
        border: `1px solid ${strategyType === type.value ? '#1890ff' : '#d9d9d9'}`,
        borderRadius: '8px',
        cursor: 'pointer',
        marginBottom: '8px',
        backgroundColor: strategyType === type.value ? '#e6f7ff' : '#fff',
        transition: 'all 0.3s',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <span style={{ fontSize: '20px' }}>{type.icon}</span>
        <div>
          <div style={{ fontWeight: 600 }}>{type.label}</div>
          <div style={{ fontSize: '12px', color: '#666' }}>{type.description}</div>
        </div>
      </div>
    </div>
  )

  // 渲染网格策略参数
  const renderGridParams = () => (
    <>
      <Divider orientation="left">网格参数</Divider>
      <Form.Item label="价格下限" name="grid_lower" rules={[{ required: true, message: '请输入价格下限' }]}>
        <InputNumber
          style={{ width: '100%' }}
          placeholder="网格价格区间下限"
          min={0}
          precision={4}
          onChange={calculateGridParams}
        />
      </Form.Item>
      <Form.Item label="价格上限" name="grid_upper" rules={[{ required: true, message: '请输入价格上限' }]}>
        <InputNumber
          style={{ width: '100%' }}
          placeholder="网格价格区间上限"
          min={0}
          precision={4}
          onChange={calculateGridParams}
        />
      </Form.Item>
      <Form.Item label="网格数量" name="grid_num" rules={[{ required: true, message: '请输入网格数量' }]}>
        <InputNumber
          style={{ width: '100%' }}
          placeholder="网格数量"
          min={2}
          max={100}
          onChange={calculateGridParams}
        />
      </Form.Item>
      <Form.Item label="每格投入" name="amount_per_grid" rules={[{ required: true, message: '请输入每格投入金额' }]}>
        <InputNumber
          style={{ width: '100%' }}
          placeholder="每格投入金额(USDT)"
          min={1}
          precision={2}
          onChange={calculateGridParams}
        />
      </Form.Item>
      <Form.Item label="总投入金额" name="total_amount">
        <InputNumber
          style={{ width: '100%' }}
          placeholder="总投入金额(USDT)"
          min={10}
          precision={2}
        />
      </Form.Item>
      <Form.Item label="手续费率" name="fee_rate" initialValue={0.001}>
        <InputNumber
          style={{ width: '100%' }}
          placeholder="手续费率"
          min={0}
          max={0.01}
          step={0.0001}
          precision={4}
        />
      </Form.Item>
      <Button icon={<RefreshCw size={14} />} onClick={getRecommendedParams}>
        获取推荐参数
      </Button>
      {gridCalculations && (
        <Card size="small" style={{ marginTop: 16 }}>
          <p>网格间距: {gridCalculations.gridSpacing.toFixed(4)}</p>
          <p>预估资金: {gridCalculations.estimatedFunds.toFixed(2)} USDT</p>
        </Card>
      )}
    </>
  )

  // 渲染网格做市策略参数
  const renderGridMMParams = () => (
    <>
      <Divider orientation="left">网格做市参数</Divider>
      <Form.Item label="网格间距(%)" name="grid_spread" rules={[{ required: true, message: '请输入网格间距' }]}>
        <InputNumber
          style={{ width: '100%' }}
          placeholder="网格间距百分比"
          min={0.1}
          max={10}
          step={0.1}
          precision={2}
        />
      </Form.Item>
      <Form.Item label="每侧层数" name="grid_levels" rules={[{ required: true, message: '请输入每侧层数' }]}>
        <InputNumber
          style={{ width: '100%' }}
          placeholder="每侧网格层数"
          min={1}
          max={20}
        />
      </Form.Item>
      <Form.Item label="每格投入" name="amount_per_grid" rules={[{ required: true, message: '请输入每格投入金额' }]}>
        <InputNumber
          style={{ width: '100%' }}
          placeholder="每格投入金额(USDT)"
          min={1}
          precision={2}
        />
      </Form.Item>
      <Form.Item label="总投入金额" name="total_amount">
        <InputNumber
          style={{ width: '100%' }}
          placeholder="总投入金额(USDT)"
          min={10}
          precision={2}
        />
      </Form.Item>
    </>
  )

  // 渲染均线交叉策略参数
  const renderMACrossParams = () => (
    <>
      <Divider orientation="left">均线参数</Divider>
      <Form.Item label="快速均线周期" name="fast_period" initialValue={5}>
        <InputNumber style={{ width: '100%' }} min={1} max={100} />
      </Form.Item>
      <Form.Item label="慢速均线周期" name="slow_period" initialValue={20}>
        <InputNumber style={{ width: '100%' }} min={1} max={200} />
      </Form.Item>
      <Form.Item label="均线类型" name="ma_type" initialValue="EMA">
        <Select style={{ width: '100%' }}>
          <Option value="SMA">简单移动平均(SMA)</Option>
          <Option value="EMA">指数移动平均(EMA)</Option>
        </Select>
      </Form.Item>
      <Form.Item label="每次交易数量" name="amount_per_trade" initialValue={0.01}>
        <InputNumber
          style={{ width: '100%' }}
          placeholder="每次交易数量(币)"
          min={0.001}
          precision={4}
        />
      </Form.Item>
    </>
  )

  // 渲染双均线策略参数
  const renderDualMACrossParams = () => (
    <>
      {renderMACrossParams()}
      <Form.Item label="仓位比例" name="position_ratio" initialValue={0.5}>
        <InputNumber
          style={{ width: '100%' }}
          placeholder="每次交易的仓位比例"
          min={0.1}
          max={1}
          step={0.1}
          precision={1}
        />
      </Form.Item>
      <Form.Item label="杠杆倍数" name="leverage" initialValue={1}>
        <InputNumber style={{ width: '100%' }} min={1} max={20} />
      </Form.Item>
      <Form.Item label="启用做空" name="enable_short" valuePropName="checked" initialValue={false}>
        <Switch />
      </Form.Item>
      <Form.Item label="止损比例(%)" name="stop_loss">
        <InputNumber style={{ width: '100%' }} min={0} max={50} step={1} />
      </Form.Item>
      <Form.Item label="止盈比例(%)" name="take_profit">
        <InputNumber style={{ width: '100%' }} min={0} max={100} step={1} />
      </Form.Item>
    </>
  )

  // 渲染波段策略参数
  const renderSwingParams = () => (
    <>
      <Divider orientation="left">波段策略参数</Divider>
      <Form.Item label="入场金额" name="entry_amount" initialValue={100}>
        <InputNumber
          style={{ width: '100%' }}
          placeholder="每次入场金额(USDT)"
          min={10}
          precision={2}
        />
      </Form.Item>
      <Form.Item label="止损比例(%)" name="stop_loss_percent" initialValue={5}>
        <InputNumber style={{ width: '100%' }} min={1} max={50} />
      </Form.Item>
      <Form.Item label="止盈比例(%)" name="take_profit_percent" initialValue={10}>
        <InputNumber style={{ width: '100%' }} min={1} max={100} />
      </Form.Item>
      <Form.Item label="最大持仓" name="max_position" initialValue={1000}>
        <InputNumber
          style={{ width: '100%' }}
          placeholder="最大持仓金额(USDT)"
          min={100}
          precision={2}
        />
      </Form.Item>
    </>
  )

  // 渲染趋势策略参数
  const renderTrendParams = () => (
    <>
      <Divider orientation="left">趋势跟踪参数</Divider>
      <Form.Item label="ATR周期" name="atr_period" initialValue={14}>
        <InputNumber style={{ width: '100%' }} min={1} max={100} />
      </Form.Item>
      <Form.Item label="ATR倍数" name="atr_multiplier" initialValue={2.0}>
        <InputNumber style={{ width: '100%' }} min={0.5} max={5} step={0.1} precision={1} />
      </Form.Item>
      <Form.Item label="突破周期" name="breakout_period" initialValue={20}>
        <InputNumber style={{ width: '100%' }} min={5} max={100} />
      </Form.Item>
      <Form.Item label="仓位比例" name="position_size" initialValue={0.1}>
        <InputNumber
          style={{ width: '100%' }}
          placeholder="每次交易仓位比例"
          min={0.01}
          max={1}
          step={0.01}
          precision={2}
        />
      </Form.Item>
    </>
  )

  // 根据策略类型渲染参数表单
  const renderStrategyParams = () => {
    switch (strategyType) {
      case 'grid':
        return renderGridParams()
      case 'grid_mm':
        return renderGridMMParams()
      case 'ma_cross':
        return renderMACrossParams()
      case 'dual_ma_cross':
        return renderDualMACrossParams()
      case 'swing_long':
      case 'swing_short':
      case 'ai_swing_long':
        return renderSwingParams()
      case 'trend':
        return renderTrendParams()
      default:
        return null
    }
  }

  return (
    <Modal
      title={backtestData ? '从回测创建策略' : '创建新策略'}
      open={open}
      onCancel={onCancel}
      onOk={handleSubmit}
      okText="创建策略"
      cancelText="取消"
      width={700}
      confirmLoading={loading}
      destroyOnClose
    >
      {backtestData && (
        <Alert
          message="基于回测结果创建"
          description="已自动填充回测的策略类型和参数，您可以根据需要调整"
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
        />
      )}

      <Form
        form={form}
        layout="vertical"
        initialValues={{
          strategy_type: backtestData?.strategy_type || 'grid',
          symbol: backtestData?.symbol || 'BTC-USDT',
          timeframe: '1H',
          fee_rate: 0.001,
        }}
      >
        <Form.Item
          label="策略名称"
          name="name"
          rules={[{ required: true, message: '请输入策略名称' }]}
        >
          <Input placeholder="为您的策略起一个名字" />
        </Form.Item>

        <Form.Item label="策略类型" name="strategy_type" rules={[{ required: true }]}>
          <div style={{ maxHeight: '300px', overflowY: 'auto' }}>
            {STRATEGY_TYPES.map(renderStrategyTypeCard)}
          </div>
        </Form.Item>

        <Form.Item
          label="交易对"
          name="symbol"
          rules={[{ required: true, message: '请选择交易对' }]}
        >
          <Select
            showSearch
            placeholder="选择交易对"
            optionFilterProp="children"
          >
            {(availableSymbols || DEFAULT_SYMBOLS).map((s: string) => (
              <Option key={s} value={s}>{s}</Option>
            ))}
          </Select>
        </Form.Item>

        <Form.Item label="K线周期" name="timeframe">
          <Select placeholder="选择K线周期">
            {TIMEFRAMES.map(tf => (
              <Option key={tf.value} value={tf.value}>{tf.label}</Option>
            ))}
          </Select>
        </Form.Item>

        {renderStrategyParams()}

        <Form.Item label="策略描述" name="description">
          <TextArea
            placeholder="描述您的策略目标和注意事项"
            rows={3}
          />
        </Form.Item>
      </Form>
    </Modal>
  )
}

export default StrategyCreateModal
