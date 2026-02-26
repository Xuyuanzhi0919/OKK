import { Modal, Form, Input, InputNumber, Select, message, Row, Col, Divider, Button, Alert, Tag, Switch, Tooltip, Slider } from 'antd'
import { TrendingUp, TrendingDown, RotateCcw, Zap, AlertTriangle, DollarSign, LineChart, Bot, Lightbulb, Flame } from 'lucide-react'
import { useState, useEffect } from 'react'
import { strategyApi, marketApi } from '@/services/api'
// import { useTranslation } from 'react-i18next'
import type { Instrument } from '@/types'
import { StrategyType } from '@/types'
import { formatPrice, formatAmount } from '@/utils/format'

interface CreateAISwingLongStrategyModalProps {
  open: boolean
  onCancel: () => void
  onSuccess: () => void
  editMode?: boolean
  initialData?: any
}

export default function CreateAISwingLongStrategyModal({ open, onCancel, onSuccess, editMode = false, initialData }: CreateAISwingLongStrategyModalProps) {
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [currentPrice, setCurrentPrice] = useState<number | null>(null)
  const [priceUpdating, setPriceUpdating] = useState(false)

  // 交易产品列表相关状态
  const [instruments, setInstruments] = useState<Instrument[]>([])
  const [instrumentsLoading, setInstrumentsLoading] = useState(false)
  const [searchText, setSearchText] = useState('')

  // 监听表单值变化
  const symbol = Form.useWatch('symbol', form)
  const initialAmount = Form.useWatch('initial_amount', form)
  const leverage = Form.useWatch('leverage', form)
  const takeProfitPct = Form.useWatch('take_profit_pct', form)
  const stopLossPct = Form.useWatch('stop_loss_pct', form)
  const useLimitOrders = Form.useWatch('use_limit_orders', form)
  const enableAI = Form.useWatch('enable_ai', form)
  const aiConfidenceThreshold = Form.useWatch('ai_confidence_threshold', form)
  const enableSmartPosition = Form.useWatch('enable_smart_position', form)
  const maxPositionRatio = Form.useWatch('max_position_ratio', form)
  const minVolatility = Form.useWatch('min_volatility', form)
  const reentryPct = Form.useWatch('reentry_pct', form)
  const aiAnalysisInterval = Form.useWatch('ai_analysis_interval', form)
  const enableLLM = Form.useWatch('enable_llm', form)
  const enableNewsAnalysis = Form.useWatch('enable_news_analysis', form)

  // 计算实际可开仓金额
  const effectiveAmount = initialAmount && leverage ? initialAmount * leverage : null

  // 计算盈亏金额
  const profitAmount = initialAmount && takeProfitPct ? initialAmount * (takeProfitPct / 100) : null
  const lossAmount = initialAmount && stopLossPct ? initialAmount * (stopLossPct / 100) : null

  // 计算手续费 (限价单Maker 0.02% vs 市价单Taker 0.05%)
  const feeRate = useLimitOrders ? 0.0002 : 0.0005
  const estimatedFee = effectiveAmount ? effectiveAmount * feeRate * 2 : null  // 开仓+平仓
  const netProfit = profitAmount && estimatedFee ? profitAmount - estimatedFee : null

  // 获取交易产品列表(仅SWAP永续合约)
  const fetchInstruments = async () => {
    try {
      setInstrumentsLoading(true)
      const data = await marketApi.getInstruments({
        inst_type: 'SWAP',
        quote_ccy: 'USDT'
      })

      // 模拟盘支持的交易对白名单
      const simulatedWhitelist = [
        'BTC-USDT-SWAP',
        'ETH-USDT-SWAP',
        'SOL-USDT-SWAP',
        'DOGE-USDT-SWAP',
        'XRP-USDT-SWAP',
        'ADA-USDT-SWAP',
        'AVAX-USDT-SWAP',
        'DOT-USDT-SWAP',
        'MATIC-USDT-SWAP',
        'LINK-USDT-SWAP',
        'UNI-USDT-SWAP',
        'LTC-USDT-SWAP',
        'BCH-USDT-SWAP',
        'ETC-USDT-SWAP',
        'XLM-USDT-SWAP'
      ]

      const filteredData = data.filter(inst =>
        simulatedWhitelist.includes(inst.instId)
      )

      setInstruments(filteredData)
    } catch (error) {
      message.error('获取交易产品列表失败')
    } finally {
      setInstrumentsLoading(false)
    }
  }

  // 获取当前市场价格
  const fetchCurrentPrice = async (tradingSymbol: string, isUpdate: boolean = false) => {
    try {
      if (isUpdate) {
        setPriceUpdating(true)
      }
      const ticker = await marketApi.getTicker(tradingSymbol)
      const price = parseFloat((ticker as any)?.last || '0')
      setCurrentPrice(price)
    } catch (error) {
      setCurrentPrice(null)
    } finally {
      if (isUpdate) {
        setTimeout(() => setPriceUpdating(false), 300)
      }
    }
  }

  // 当modal打开时，获取交易产品列表
  useEffect(() => {
    if (open) {
      fetchInstruments()
      setSearchText('')

      if (editMode && initialData) {
        // 编辑模式:加载策略数据
        const params = initialData.parameters || {}
        form.setFieldsValue({
          name: initialData.name,
          symbol: initialData.symbol,
          initial_amount: params.initial_amount || 1000,
          leverage: params.leverage || 5,
          take_profit_pct: params.take_profit_pct || 15,
          stop_loss_pct: params.stop_loss_pct || 5,
          reentry_pct: params.reentry_pct || 5,
          margin_mode: params.margin_mode || 'isolated',
          use_limit_orders: params.use_limit_orders !== undefined ? params.use_limit_orders : true,
          min_volatility: params.min_volatility || 3,
          limit_order_offset_pct: params.limit_order_offset_pct || 0.1,
          // AI配置
          enable_ai: params.enable_ai !== undefined ? params.enable_ai : true,
          ai_confidence_threshold: (params.ai_confidence_threshold || 0.7) * 100,
          ai_analysis_interval: params.ai_analysis_interval || 300,
          enable_smart_position: params.enable_smart_position !== undefined ? params.enable_smart_position : true,
          max_position_ratio: params.max_position_ratio || 2.0,
          // LLM配置
          enable_llm: params.enable_llm !== undefined ? params.enable_llm : true,
          enable_news_analysis: params.enable_news_analysis !== undefined ? params.enable_news_analysis : true
        })
      } else {
        // 创建模式:设置默认值
        form.setFieldsValue({
          initial_amount: 1000,
          leverage: 5,
          take_profit_pct: 15,
          stop_loss_pct: 5,
          reentry_pct: 5,
          margin_mode: 'isolated',
          use_limit_orders: true,
          min_volatility: 3,
          limit_order_offset_pct: 0.1,
          // AI配置默认值
          enable_ai: true,
          ai_confidence_threshold: 70,
          ai_analysis_interval: 300,
          enable_smart_position: true,
          max_position_ratio: 2.0,
          // LLM配置默认值
          enable_llm: true,
          enable_news_analysis: true
        })
      }
    }
  }, [open, editMode, initialData])

  // 当symbol变化时，获取价格
  useEffect(() => {
    if (open && symbol) {
      fetchCurrentPrice(symbol)
    }
  }, [open, symbol])

  // 实时更新价格 (每5秒刷新一次)
  useEffect(() => {
    if (!open || !symbol) return

    const intervalId = setInterval(() => {
      fetchCurrentPrice(symbol, true)
    }, 5000)

    return () => clearInterval(intervalId)
  }, [open, symbol])

  // 过滤交易产品
  const filteredInstruments = instruments.filter(inst => {
    if (!searchText) return true
    const searchLower = searchText.toLowerCase()
    return inst.instId.toLowerCase().includes(searchLower) ||
           inst.baseCcy?.toLowerCase().includes(searchLower)
  })

  // 生成策略名称
  const generateStrategyName = () => {
    if (!symbol) return ''
    const baseCcy = symbol.split('-')[0]
    const date = new Date()
    const month = (date.getMonth() + 1).toString().padStart(2, '0')
    const day = date.getDate().toString().padStart(2, '0')
    const dateStr = `${month}${day}`

    return `${baseCcy}AI波段 | ${leverage || 5}x | ${dateStr}`
  }

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      setLoading(true)

      // 构建策略参数
      const strategyData = {
        name: values.name || generateStrategyName(),
        type: StrategyType.AI_SWING_LONG,
        symbol: values.symbol,
        timeframe: '1m',
        parameters: {
          initial_amount: values.initial_amount,
          leverage: values.leverage,
          take_profit_pct: values.take_profit_pct,
          stop_loss_pct: values.stop_loss_pct,
          reentry_pct: values.reentry_pct,
          margin_mode: values.margin_mode,
          use_limit_orders: values.use_limit_orders,
          min_volatility: values.min_volatility,
          limit_order_offset_pct: values.limit_order_offset_pct,
          // AI配置
          enable_ai: values.enable_ai,
          ai_confidence_threshold: values.ai_confidence_threshold / 100, // 转换为0-1
          ai_analysis_interval: values.ai_analysis_interval,
          enable_smart_position: values.enable_smart_position,
          max_position_ratio: values.max_position_ratio,
          // LLM配置
          enable_llm: values.enable_llm,
          enable_news_analysis: values.enable_news_analysis
        },
        description: `AI波段做多 - ${values.leverage}x杠杆 止盈${values.take_profit_pct}% 止损${values.stop_loss_pct}% ${values.enable_ai ? '(AI增强)' : ''}`
      }

      if (editMode && initialData) {
        // 编辑模式
        await strategyApi.update(initialData.id, strategyData)
        message.success('AI策略更新成功!')
      } else {
        // 创建模式
        await strategyApi.create(strategyData)
        message.success('AI策略创建成功!')
      }

      form.resetFields()
      onSuccess()
    } catch (error) {
      message.error((error as any)?.response?.data?.detail || (editMode ? '更新AI策略失败' : '创建AI策略失败'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <Modal
      title={
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Bot size={18} style={{ color: '#722ed1' }} />
          <span>{editMode ? '编辑AI增强策略' : '创建AI增强策略'}</span>
          <Tag
            style={{
              margin: 0,
              background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
              border: 'none',
              color: '#fff',
              fontWeight: 600,
              fontSize: 11,
              padding: '2px 8px'
            }}
          >
            AI POWERED
          </Tag>
        </div>
      }
      open={open}
      onCancel={onCancel}
      width={750}
      footer={[
        <Button key="cancel" onClick={onCancel}>
          取消
        </Button>,
        <Button
          key="submit"
          type="primary"
          loading={loading}
          onClick={handleSubmit}
          style={{
            background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
            border: 'none'
          }}
        >
          {editMode ? '更新AI策略' : '创建AI策略'}
        </Button>
      ]}
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={{
          initial_amount: 1000,
          leverage: 5,
          take_profit_pct: 15,
          stop_loss_pct: 5,
          reentry_pct: 5,
          margin_mode: 'isolated',
          use_limit_orders: true,
          min_volatility: 3,
          limit_order_offset_pct: 0.1,
          enable_ai: true,
          ai_confidence_threshold: 70,
          ai_analysis_interval: 300,
          enable_smart_position: true,
          max_position_ratio: 2.0
        }}
      >
        {/* AI功能说明 */}
        <Alert
          message={
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Bot size={16} />
              <span style={{ fontWeight: 600 }}>AI增强策略 - 智能市场分析与仓位管理</span>
            </div>
          }
          description={
            <div style={{ fontSize: 12, marginTop: 8 }}>
              <div style={{ marginBottom: 6, color: '#722ed1', fontWeight: 600 }}>
                ✨ AI将自动分析市场并给出加仓/减仓建议，提高交易胜率
              </div>
              <div>• <strong>市场情绪分析</strong>: 基于24h涨跌幅、波动率、成交量判断市场方向</div>
              <div>• <strong>智能仓位管理</strong>: 盈利时加仓，市场转弱时减仓止盈</div>
              <div>• <strong>风险评估</strong>: 实时评估市场风险，动态调整操作策略</div>
              <div>• <strong>信心度机制</strong>: 仅在AI信心度达标时执行建议，避免盲目操作</div>
            </div>
          }
          type="info"
          showIcon
          icon={<Lightbulb size={14} />}
          style={{
            marginBottom: 20,
            background: 'linear-gradient(135deg, rgba(102, 126, 234, 0.1) 0%, rgba(118, 75, 162, 0.1) 100%)',
            border: '1px solid rgba(102, 126, 234, 0.3)'
          }}
        />

        {/* 基础配置 */}
        <div style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#737373', marginBottom: 12 }}>
            基础配置
          </div>

          {/* 策略名称 */}
          <Form.Item
            label="策略名称"
            name="name"
            tooltip="留空将自动生成名称"
            style={{ marginBottom: 16 }}
          >
            <Input placeholder={generateStrategyName() || "自动生成"} />
          </Form.Item>

          {/* 交易对选择 */}
          <Form.Item
            label={
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span>选择交易对</span>
                {currentPrice && (
                  <span style={{
                    fontSize: 12,
                    color: priceUpdating ? '#52c41a' : '#8c8c8c',
                    fontWeight: priceUpdating ? 600 : 'normal',
                    transition: 'all 0.3s ease'
                  }}>
                    当前价格: ${formatPrice(currentPrice)}
                  </span>
                )}
              </div>
            }
            name="symbol"
            rules={[{ required: true, message: '请选择交易对' }]}
            style={{ marginBottom: 16 }}
          >
            <Select
              showSearch
              placeholder="搜索交易对 (仅永续合约)"
              loading={instrumentsLoading}
              onSearch={setSearchText}
              filterOption={false}
              notFoundContent={instrumentsLoading ? '加载中...' : '暂无数据'}
            >
              {filteredInstruments.map((inst) => (
                <Select.Option key={inst.instId} value={inst.instId}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span>{inst.instId}</span>
                    <Tag color="blue" style={{ margin: 0, fontSize: 11 }}>SWAP</Tag>
                  </div>
                </Select.Option>
              ))}
            </Select>
          </Form.Item>

          {/* 初始投入和杠杆 */}
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                label={
                  <div>
                    初始投入 (USDT)
                    {effectiveAmount && (
                      <span style={{ marginLeft: 8, fontSize: 12, color: '#1890ff', fontWeight: 'normal' }}>
                        可开: ${formatAmount(effectiveAmount)}
                      </span>
                    )}
                  </div>
                }
                name="initial_amount"
                rules={[
                  { required: true, message: '请输入投入金额' },
                  { type: 'number', min: 100, message: '最低投入 100 USDT' }
                ]}
                tooltip="您的保证金本金，不是开仓金额"
                style={{ marginBottom: 16 }}
              >
                <InputNumber min={100} precision={2} style={{ width: '100%' }} placeholder="1000" />
              </Form.Item>
            </Col>

            <Col span={12}>
              <Form.Item
                label={
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span>杠杆倍数</span>
                    <Tag color={leverage && leverage > 20 ? 'red' : 'orange'} style={{ margin: 0, fontSize: 11 }}>
                      {leverage && leverage > 20 ? '高风险' : '中风险'}
                    </Tag>
                  </div>
                }
                name="leverage"
                rules={[{ required: true, message: '请选择杠杆倍数' }]}
                tooltip="杠杆越高，收益和风险都会放大"
                style={{ marginBottom: 16 }}
              >
                <Select placeholder="选择杠杆倍数">
                  <Select.Option value={1}>1x (无杠杆)</Select.Option>
                  <Select.Option value={2}>2x</Select.Option>
                  <Select.Option value={3}>3x</Select.Option>
                  <Select.Option value={5}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span>5x</span>
                      <Tag color="green" style={{ margin: 0, fontSize: 11 }}>推荐</Tag>
                    </div>
                  </Select.Option>
                  <Select.Option value={10}>10x</Select.Option>
                  <Select.Option value={20}>20x</Select.Option>
                  <Select.Option value={50}>50x (高风险)</Select.Option>
                  <Select.Option value={100}>100x (极高风险)</Select.Option>
                </Select>
              </Form.Item>
            </Col>
          </Row>

          {/* 保证金模式 */}
          <Form.Item
            label={
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span>保证金模式</span>
              </div>
            }
            name="margin_mode"
            rules={[{ required: true, message: '请选择保证金模式' }]}
            tooltip={
              <div>
                <div>• 逐仓: 仅使用该仓位的保证金，风险隔离(推荐)</div>
                <div>• 全仓: 账户所有可用资金作为保证金，风险共担</div>
              </div>
            }
            style={{ marginBottom: 0 }}
          >
            <Select placeholder="选择保证金模式">
              <Select.Option value="isolated">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span>逐仓</span>
                  <Tag color="green" style={{ margin: 0, fontSize: 11 }}>推荐</Tag>
                </div>
              </Select.Option>
              <Select.Option value="cross">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span>全仓</span>
                  <Tag color="orange" style={{ margin: 0, fontSize: 11 }}>高风险</Tag>
                </div>
              </Select.Option>
            </Select>
          </Form.Item>
        </div>

        <Divider style={{ margin: '12px 0 20px 0' }} />

        {/* 交易优化 */}
        <div style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#737373', marginBottom: 12 }}>
            <DollarSign size={14} style={{ marginRight: 6, color: '#52c41a' }} />
            交易优化设置
          </div>

          {/* 使用限价单开关 */}
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={12}>
              <Form.Item
                label={
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span>使用限价单交易</span>
                    <Tooltip title="限价单Maker费率0.02%, 市价单Taker费率0.05%, 限价单可节省60%手续费">
                      <Tag color="green" style={{ margin: 0, fontSize: 11, cursor: 'help' }}>省手续费</Tag>
                    </Tooltip>
                  </div>
                }
                name="use_limit_orders"
                valuePropName="checked"
                tooltip="开启后以限价单挂单交易，享受Maker费率(0.02%)，比市价单(0.05%)节省60%手续费"
                style={{ marginBottom: 0 }}
              >
                <Switch checkedChildren="开启" unCheckedChildren="关闭" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item
                label="限价单价格偏移 (%)"
                name="limit_order_offset_pct"
                rules={[{ type: 'number', min: 0.01, max: 1, message: '偏移范围0.01%-1%' }]}
                tooltip="买入时低于市价，卖出时高于市价的百分比，默认0.1%"
                style={{ marginBottom: 0 }}
              >
                <InputNumber
                  min={0.01}
                  max={1}
                  step={0.05}
                  precision={2}
                  style={{ width: '100%' }}
                  placeholder="0.1"
                  suffix="%"
                  disabled={!useLimitOrders}
                />
              </Form.Item>
            </Col>
          </Row>

          {/* 最低波动率过滤 */}
          <Form.Item
            label={
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <LineChart size={14} style={{ marginRight: 4, color: '#1890ff' }} />
                <span>最低波动率要求 (%)</span>
              </div>
            }
            name="min_volatility"
            rules={[{ type: 'number', min: 0, max: 20, message: '波动率范围0-20%' }]}
            tooltip="24h波动率低于此值将不开仓，避免在低波动市场频繁交易"
            style={{ marginBottom: 0 }}
          >
            <InputNumber
              min={0}
              max={20}
              step={0.5}
              precision={1}
              style={{ width: '100%' }}
              placeholder="3"
              suffix="%"
            />
          </Form.Item>

          {/* 手续费和盈利预估 */}
          {effectiveAmount && estimatedFee && (
            <Alert
              message="费用与收益预估"
              description={
                <div style={{ fontSize: 12 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                    <span>开仓金额:</span>
                    <span style={{ fontWeight: 600 }}>${formatAmount(effectiveAmount)}</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                    <span>预估手续费 ({useLimitOrders ? 'Maker 0.02%' : 'Taker 0.05%'}):</span>
                    <span style={{ color: '#ff4d4f', fontWeight: 600 }}>-${formatAmount(estimatedFee)}</span>
                  </div>
                  {profitAmount && (
                    <>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                        <span>止盈毛收益 ({takeProfitPct}%):</span>
                        <span style={{ color: '#52c41a', fontWeight: 600 }}>+${formatAmount(profitAmount)}</span>
                      </div>
                      {netProfit && (
                        <div style={{ display: 'flex', justifyContent: 'space-between', paddingTop: 4, borderTop: '1px dashed #d9d9d9' }}>
                          <span><strong>止盈净收益:</strong></span>
                          <span style={{ color: '#52c41a', fontWeight: 700, fontSize: 13 }}>+${formatAmount(netProfit)}</span>
                        </div>
                      )}
                    </>
                  )}
                </div>
              }
              type="info"
              showIcon
              style={{ marginTop: 16, marginBottom: 0 }}
            />
          )}
        </div>

        <Divider style={{ margin: '12px 0 20px 0' }} />

        {/* 策略参数 */}
        <div style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#737373', marginBottom: 12 }}>
            止盈止损参数
          </div>

          {/* 止盈比例 */}
          <Form.Item
            label={
              <div>
                <TrendingUp size={14} style={{ color: '#52c41a', marginRight: 4 }} />
                止盈比例 (%)
                {profitAmount && (
                  <span style={{ marginLeft: 8, fontSize: 12, color: '#52c41a', fontWeight: 'normal' }}>
                    预期盈利: +${formatAmount(profitAmount)}
                  </span>
                )}
              </div>
            }
            name="take_profit_pct"
            rules={[
              { required: true, message: '请输入止盈比例' },
              { type: 'number', min: 0.1, message: '止盈比例不能小于0.1%' }
            ]}
            tooltip="价格上涨达到此比例时平仓止盈，例如5表示盈利5%时卖出"
            style={{ marginBottom: 16 }}
          >
            <InputNumber
              min={0.1}
              max={100}
              step={0.5}
              precision={1}
              style={{ width: '100%' }}
              placeholder="15"
              suffix="%"
            />
          </Form.Item>

          {/* 止损比例 */}
          <Form.Item
            label={
              <div>
                <TrendingDown size={14} style={{ color: '#ff4d4f', marginRight: 4 }} />
                止损比例 (%)
                {lossAmount && (
                  <span style={{ marginLeft: 8, fontSize: 12, color: '#ff4d4f', fontWeight: 'normal' }}>
                    最大亏损: -${formatAmount(lossAmount)}
                  </span>
                )}
              </div>
            }
            name="stop_loss_pct"
            rules={[
              { required: true, message: '请输入止损比例' },
              { type: 'number', min: 1, message: '止损比例不能小于1%' }
            ]}
            tooltip="价格下跌达到此比例时平仓止损，例如10表示亏损10%时卖出"
            style={{ marginBottom: 16 }}
          >
            <InputNumber
              min={1}
              max={100}
              step={1}
              precision={1}
              style={{ width: '100%' }}
              placeholder="5"
              suffix="%"
            />
          </Form.Item>

          {/* 回调买入比例 */}
          <Form.Item
            label={
              <div>
                <RotateCcw size={14} style={{ color: '#1890ff', marginRight: 4 }} />
                回调买入比例 (%)
              </div>
            }
            name="reentry_pct"
            rules={[
              { required: true, message: '请输入回调比例' },
              { type: 'number', min: 0.5, message: '回调比例不能小于0.5%' }
            ]}
            tooltip="止盈后，价格从最高点回调此比例时重新开多，例如3表示回调3%时买入"
            style={{ marginBottom: 0 }}
          >
            <InputNumber
              min={0.5}
              max={50}
              step={0.5}
              precision={1}
              style={{ width: '100%' }}
              placeholder="5"
              suffix="%"
            />
          </Form.Item>
        </div>

        <Divider style={{ margin: '12px 0 20px 0' }} />

        {/* AI增强配置 */}
        <div
          style={{
            marginBottom: 20,
            padding: 16,
            background: 'linear-gradient(135deg, rgba(102, 126, 234, 0.05) 0%, rgba(118, 75, 162, 0.05) 100%)',
            borderRadius: 8,
            border: '2px solid rgba(102, 126, 234, 0.2)'
          }}
        >
          <div style={{
            fontSize: 14,
            fontWeight: 600,
            color: '#722ed1',
            marginBottom: 16,
            display: 'flex',
            alignItems: 'center',
            gap: 8
          }}>
            <Bot size={18} />
            AI增强配置
            <Tag
              style={{
                background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                border: 'none',
                color: '#fff',
                fontSize: 10,
                margin: 0
              }}
            >
              BETA
            </Tag>
          </div>

          {/* 启用AI */}
          <Form.Item
            label={
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <Flame size={14} style={{ color: '#722ed1' }} />
                <span style={{ fontWeight: 600 }}>启用AI智能分析</span>
              </div>
            }
            name="enable_ai"
            valuePropName="checked"
            tooltip="开启后AI将自动分析市场并给出交易建议"
            style={{ marginBottom: 16 }}
          >
            <Switch
              checkedChildren="AI已启用"
              unCheckedChildren="AI已禁用"
              style={{
                background: enableAI ? 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)' : undefined
              }}
            />
          </Form.Item>

          {enableAI && (
            <>
              {/* AI信心度阈值 */}
              <Form.Item
                label={
                  <div style={{ display: 'flex', justifyContent: 'space-between', width: '100%' }}>
                    <span>AI信心度阈值</span>
                    <span style={{
                      fontSize: 12,
                      color: aiConfidenceThreshold >= 80 ? '#52c41a' : aiConfidenceThreshold >= 60 ? '#1890ff' : '#ff4d4f',
                      fontWeight: 600
                    }}>
                      {aiConfidenceThreshold}% {aiConfidenceThreshold >= 80 ? '(保守)' : aiConfidenceThreshold >= 60 ? '(适中)' : '(激进)'}
                    </span>
                  </div>
                }
                name="ai_confidence_threshold"
                tooltip="只有当AI分析信心度≥此阈值时才会执行建议。阈值越高越保守，越低越激进"
                style={{ marginBottom: 16 }}
              >
                <Slider
                  min={50}
                  max={95}
                  step={5}
                  marks={{
                    50: '50%',
                    60: '60%',
                    70: {
                      label: <span style={{ color: '#1890ff', fontWeight: 600 }}>70%(推荐)</span>
                    },
                    80: '80%',
                    90: '90%'
                  }}
                  tooltip={{ formatter: (value) => `${value}%` }}
                />
              </Form.Item>

              {/* AI分析间隔 */}
              <Form.Item
                label={
                  <div>
                    AI分析间隔 (秒)
                    <span style={{ marginLeft: 8, fontSize: 12, color: '#8c8c8c', fontWeight: 'normal' }}>
                      每{aiAnalysisInterval || 300}秒分析一次
                    </span>
                  </div>
                }
                name="ai_analysis_interval"
                rules={[
                  { required: true, message: '请输入分析间隔' },
                  { type: 'number', min: 60, max: 3600, message: '间隔范围60-3600秒' }
                ]}
                tooltip="AI分析市场的时间间隔，避免过于频繁分析。建议300秒(5分钟)"
                style={{ marginBottom: 16 }}
              >
                <InputNumber
                  min={60}
                  max={3600}
                  step={60}
                  style={{ width: '100%' }}
                  placeholder="300"
                  suffix="秒"
                  formatter={(value) => {
                    const seconds = Number(value) || 0
                    if (seconds >= 60) {
                      const minutes = Math.floor(seconds / 60)
                      return `${seconds} (${minutes}分钟)`
                    }
                    return `${seconds}`
                  }}
                />
              </Form.Item>

              <Divider style={{ margin: '12px 0 16px 0', borderColor: 'rgba(102, 126, 234, 0.2)' }} />

              {/* LLM增强功能 */}
              <Form.Item
                label={
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <Lightbulb size={14} style={{ color: '#722ed1' }} />
                    <span style={{ fontWeight: 600 }}>启用LLM增强分析</span>
                    <Tag
                      style={{
                        background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                        border: 'none',
                        color: '#fff',
                        fontSize: 10,
                        margin: 0
                      }}
                    >
                      Phase 2
                    </Tag>
                  </div>
                }
                name="enable_llm"
                valuePropName="checked"
                tooltip="开启后将使用DeepSeek大语言模型增强AI分析能力，提供更智能的市场情绪判断和交易建议"
                style={{ marginBottom: 16 }}
              >
                <Switch
                  checkedChildren="LLM已启用"
                  unCheckedChildren="LLM已禁用"
                  style={{
                    background: enableLLM ? 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)' : undefined
                  }}
                />
              </Form.Item>

              {enableLLM && (
                <Form.Item
                  label={
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      📰
                      <span>启用新闻情绪分析</span>
                    </div>
                  }
                  name="enable_news_analysis"
                  valuePropName="checked"
                  tooltip="开启后LLM将分析最新加密货币新闻，结合市场情绪给出更准确的判断"
                  style={{ marginBottom: 16 }}
                >
                  <Switch
                    checkedChildren="新闻分析已启用"
                    unCheckedChildren="新闻分析已禁用"
                    style={{
                      background: enableNewsAnalysis ? 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)' : undefined
                    }}
                  />
                </Form.Item>
              )}

              {enableLLM && (
                <Alert
                  message="LLM增强功能说明"
                  type="info"
                  showIcon
                  icon={<Lightbulb size={14} style={{ color: '#722ed1' }} />}
                  description={
                    <div style={{ fontSize: 12 }}>
                      <div>• <strong>DeepSeek LLM</strong>: 使用先进的大语言模型进行市场分析</div>
                      <div>• <strong>新闻监控</strong>: 实时抓取CoinGecko、CryptoPanic等新闻源</div>
                      <div>• <strong>情绪分析</strong>: LLM自动分析新闻情绪(看涨/看跌/中性)</div>
                      <div>• <strong>智能融合</strong>: 结合规则AI和LLM分析，综合决策</div>
                      <div style={{ marginTop: 4, color: '#ff4d4f' }}>
                        ⚠️ 需要在后端配置DEEPSEEK_API_KEY才能使用LLM功能
                      </div>
                    </div>
                  }
                  style={{ marginBottom: 16 }}
                />
              )}

              <Divider style={{ margin: '12px 0 16px 0', borderColor: 'rgba(102, 126, 234, 0.2)' }} />

              {/* 智能仓位管理 */}
              <Form.Item
                label={
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <Zap size={14} style={{ color: '#722ed1' }} />
                    <span style={{ fontWeight: 600 }}>启用智能仓位管理</span>
                  </div>
                }
                name="enable_smart_position"
                valuePropName="checked"
                tooltip="开启后AI将根据市场情况自动加仓或减仓"
                style={{ marginBottom: 16 }}
              >
                <Switch
                  checkedChildren="已启用"
                  unCheckedChildren="已禁用"
                  style={{
                    background: enableSmartPosition ? 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)' : undefined
                  }}
                />
              </Form.Item>

              {enableSmartPosition && (
                <Form.Item
                  label={
                    <div>
                      最大仓位倍数
                      <span style={{ marginLeft: 8, fontSize: 12, color: '#8c8c8c', fontWeight: 'normal' }}>
                        最多可加仓至初始仓位的{maxPositionRatio}倍
                      </span>
                    </div>
                  }
                  name="max_position_ratio"
                  rules={[
                    { required: true, message: '请输入最大仓位倍数' },
                    { type: 'number', min: 1, max: 5, message: '倍数范围1-5' }
                  ]}
                  tooltip="限制AI最多能加仓到初始仓位的多少倍，防止过度加仓"
                  style={{ marginBottom: 0 }}
                >
                  <InputNumber
                    min={1}
                    max={5}
                    step={0.5}
                    precision={1}
                    style={{ width: '100%' }}
                    placeholder="2.0"
                    suffix="倍"
                  />
                </Form.Item>
              )}

              {/* AI功能说明 */}
              <Alert
                message="AI工作原理"
                description={
                  <div style={{ fontSize: 12 }}>
                    <div>• <strong>市场分析</strong>: AI会分析24h涨跌幅、波动率、成交量等指标</div>
                    <div>• <strong>加仓时机</strong>: 盈利10%+ 且市场强势时，建议加仓30%</div>
                    <div>• <strong>减仓时机</strong>: 盈利10%+ 但市场转弱时，建议减仓50%止盈</div>
                    <div>• <strong>止损建议</strong>: 亏损接近止损线且市场弱势时，强烈建议止损</div>
                    <div style={{ marginTop: 8, padding: 8, background: 'rgba(102, 126, 234, 0.1)', borderRadius: 4 }}>
                      <div style={{ color: '#722ed1', fontWeight: 600, marginBottom: 4 }}>💡 提示</div>
                      <div>AI建议仅供参考，您可以通过调整信心度阈值来控制AI的执行频率</div>
                    </div>
                  </div>
                }
                type="info"
                showIcon
                icon={<Lightbulb size={14} />}
                style={{
                  marginTop: 16,
                  marginBottom: 0,
                  background: 'rgba(255, 255, 255, 0.6)',
                  border: '1px solid rgba(102, 126, 234, 0.3)'
                }}
              />
            </>
          )}
        </div>

        <Divider style={{ margin: '12px 0 16px 0' }} />

        {/* 策略说明 */}
      
      </Form>
    </Modal>
  )
}
