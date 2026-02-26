import { Modal, Form, Input, InputNumber, Select, message, Row, Col, Divider, Button, Alert, Tag, Switch, Tooltip } from 'antd'
import { TrendingUp, TrendingDown, RotateCcw, Zap, AlertTriangle, DollarSign, TrendingUp as LineChart } from 'lucide-react'
import { useState, useEffect } from 'react'
import { strategyApi, marketApi } from '@/services/api'
import { useTranslation } from 'react-i18next'
import type { Instrument } from '@/types'
import { formatPrice, formatAmount } from '@/utils/format'

interface CreateSwingLongStrategyModalProps {
  open: boolean
  onCancel: () => void
  onSuccess: () => void
  editMode?: boolean
  initialData?: any
}

export default function CreateSwingLongStrategyModal({ open, onCancel, onSuccess, editMode = false, initialData }: CreateSwingLongStrategyModalProps) {
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

  // 计算实际可开仓金额
  const effectiveAmount = initialAmount && leverage ? initialAmount * leverage : null

  // 新逻辑: 计算基于杠杆后总仓位的盈亏金额
  const profitAmount = initialAmount && leverage && takeProfitPct ? initialAmount * leverage * (takeProfitPct / 100) : null
  const lossAmount = initialAmount && leverage && stopLossPct ? initialAmount * leverage * (stopLossPct / 100) : null

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
          limit_order_offset_pct: params.limit_order_offset_pct || 0.1
        })
      } else {
        // 创建模式:设置默认值(优化后的参数)
        form.setFieldsValue({
          initial_amount: 1000,
          leverage: 5,
          take_profit_pct: 15,
          stop_loss_pct: 5,
          reentry_pct: 5,
          margin_mode: 'isolated',
          use_limit_orders: true,
          min_volatility: 3,
          limit_order_offset_pct: 0.1
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

    return `${baseCcy}波段 | ${leverage || 5}x | ${dateStr}`
  }

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      setLoading(true)

      // 构建策略参数
      const strategyData = {
        name: values.name || generateStrategyName(),
        type: 'swing_long',
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
          limit_order_offset_pct: values.limit_order_offset_pct
        },
        description: `波段做多 - ${values.leverage}x杠杆 止盈${values.take_profit_pct}% 止损${values.stop_loss_pct}% ${values.use_limit_orders ? '(限价单)' : '(市价单)'}`
      }

      if (editMode && initialData) {
        // 编辑模式
        await strategyApi.update(initialData.id, strategyData)
        message.success('策略更新成功!')
      } else {
        // 创建模式
        await strategyApi.create(strategyData)
        message.success('策略创建成功!')
      }

      form.resetFields()
      onSuccess()
    } catch (error) {
      message.error((error as any)?.response?.data?.detail || (editMode ? '更新策略失败' : '创建策略失败'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <Modal
      title={
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Zap size={14} style={{ color: '#1890ff' }} />
          <span>{editMode ? '编辑波段做多策略' : '创建波段做多策略'}</span>
          <Tag color="processing">永续合约</Tag>
        </div>
      }
      open={open}
      onCancel={onCancel}
      width={700}
      footer={[
        <Button key="cancel" onClick={onCancel}>
          取消
        </Button>,
        <Button key="submit" type="primary" loading={loading} onClick={handleSubmit}>
          {editMode ? '更新策略' : '创建策略'}
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
          limit_order_offset_pct: 0.1
        }}
      >
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
                币价止盈比例 (%)
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
            tooltip="币价上涨达到此比例时止盈。例如，输入0.5，表示币价上涨0.5%时触发止盈。"
            style={{ marginBottom: 16 }}
          >
            <InputNumber
              min={0.1}
              max={100}
              step={0.1}
              precision={2}
              style={{ width: '100%' }}
              placeholder="0.5"
              suffix="%"
            />
          </Form.Item>

          {/* 止损比例 */}
          <Form.Item
            label={
              <div>
                <TrendingDown size={14} style={{ color: '#ff4d4f', marginRight: 4 }} />
                币价止损比例 (%)
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
              { type: 'number', min: 0.1, message: '止损比例不能小于0.1%' }
            ]}
            tooltip="币价下跌达到此比例时止损。例如，输入0.2，表示币价下跌0.2%时触发止损。"
            style={{ marginBottom: 16 }}
          >
            <InputNumber
              min={0.1}
              max={100}
              step={0.1}
              precision={2}
              style={{ width: '100%' }}
              placeholder="0.2"
              suffix="%"
            />
          </Form.Item>

          {/* 回调买入比例 */}
          <Form.Item
            label={
              <div>
                <RotateCcw size={14} style={{ color: '#1890ff', marginRight: 4 }} />
                价格回调比例 (%)
              </div>
            }
            name="reentry_pct"
            rules={[
              { required: true, message: '请输入回调比例' },
              { type: 'number', min: 0.1, message: '回调比例不能小于0.1%' }
            ]}
            tooltip="止盈后，价格从最高点回调此比例时重新开多。例如，输入0.3，表示价格从高点下跌0.3%时买入。"
            style={{ marginBottom: 0 }}
          >
            <InputNumber
              min={0.1}
              max={50}
              step={0.1}
              precision={2}
              style={{ width: '100%' }}
              placeholder="0.3"
              suffix="%"
            />
          </Form.Item>
        </div>

        <Divider style={{ margin: '12px 0 16px 0' }} />

        {/* 策略说明 */}
       
      </Form>
    </Modal>
  )
}
