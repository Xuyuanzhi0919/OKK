import { Modal, Form, Input, InputNumber, Select, message, Row, Col, Divider, Radio, Button, Card, Alert, Tag, Spin } from 'antd'
import { Lightbulb, Zap, TrendingUp, Info } from 'lucide-react'
import { useState, useEffect } from 'react'
import { strategyApi, marketApi } from '@/services/api'
import { useTranslation } from 'react-i18next'
import type { Instrument, GridParamsRecommendation } from '@/types'
import { formatPrice, removeTrailingZeros, formatAmount } from '@/utils/format'

interface CreateGridStrategyModalProps {
  open: boolean
  onCancel: () => void
  onSuccess: () => void
}

export default function CreateGridStrategyModal({ open, onCancel, onSuccess }: CreateGridStrategyModalProps) {
  const { t } = useTranslation()
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [currentPrice, setCurrentPrice] = useState<number | null>(null)
  const [priceLoading, setPriceLoading] = useState(false)
  const [priceUpdating, setPriceUpdating] = useState(false)

  // 交易产品列表相关状态
  const [instruments, setInstruments] = useState<Instrument[]>([])
  const [instrumentsLoading, setInstrumentsLoading] = useState(false)
  const [instType, setInstType] = useState<'SPOT' | 'SWAP'>('SPOT')
  const [searchText, setSearchText] = useState('')

  // 智能助手相关状态
  const [recommendation, setRecommendation] = useState<GridParamsRecommendation | null>(null)
  const [recommendLoading, setRecommendLoading] = useState(false)
  const [showRecommendation, setShowRecommendation] = useState(false)

  // 监听表单值变化，用于动态计算
  const priceUpper = Form.useWatch('price_upper', form)
  const priceLower = Form.useWatch('price_lower', form)
  const gridNum = Form.useWatch('grid_num', form)
  const totalAmount = Form.useWatch('total_amount', form)
  const symbol = Form.useWatch('symbol', form)

  // 判断是否为永续合约
  const isSwapOrFutures = symbol && (symbol.endsWith('-SWAP') || symbol.endsWith('-FUTURES'))

  // 获取交易产品列表
  const fetchInstruments = async (type: 'SPOT' | 'SWAP') => {
    try {
      setInstrumentsLoading(true)
      const data = await marketApi.getInstruments({
        inst_type: type,
        quote_ccy: 'USDT' // 只显示 USDT 计价的产品
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

      // 只对SWAP类型进行过滤
      const filteredData = type === 'SWAP'
        ? data.filter(inst => simulatedWhitelist.includes(inst.instId))
        : data

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
      } else {
        setPriceLoading(true)
      }
      const ticker = await marketApi.getTicker(tradingSymbol)
      const price = parseFloat((ticker as any)?.last || '0')
      setCurrentPrice(price)
    } catch (error) {
      setCurrentPrice(null)
    } finally {
      setPriceLoading(false)
      if (isUpdate) {
        setTimeout(() => setPriceUpdating(false), 300)
      }
    }
  }

  // 当modal打开时，获取交易产品列表
  useEffect(() => {
    if (open) {
      fetchInstruments(instType)
      setSearchText('')
    }
  }, [open, instType])

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
      fetchCurrentPrice(symbol, true) // true表示是更新而非首次加载
    }, 5000) // 5秒更新一次

    return () => clearInterval(intervalId)
  }, [open, symbol])

  // 计算每格价差
  const gridSpacing = priceUpper && priceLower && gridNum && priceUpper > priceLower
    ? (priceUpper - priceLower) / gridNum
    : null

  // 计算单格投资额
  const perGridInvestment = totalAmount && gridNum
    ? totalAmount / gridNum
    : null

  // 过滤交易产品 (根据搜索文本)
  const filteredInstruments = instruments.filter(inst => {
    if (!searchText) return true
    const searchLower = searchText.toLowerCase()
    return inst.instId.toLowerCase().includes(searchLower) ||
           inst.baseCcy?.toLowerCase().includes(searchLower)
  })

  // 切换产品类型
  const handleInstTypeChange = (type: 'SPOT' | 'SWAP') => {
    setInstType(type)
    // 重置选择的交易对和价格
    form.setFieldsValue({ symbol: undefined })
    setCurrentPrice(null)
  }

  // 获取智能推荐参数
  const handleGetRecommendation = async () => {
    if (!symbol || !totalAmount) {
      message.warning('请先选择交易对和输入投资金额')
      return
    }

    try {
      setRecommendLoading(true)
      const data = await strategyApi.recommendGridParams(symbol, totalAmount)
      setRecommendation(data)
      setShowRecommendation(true)
      message.success('参数推荐成功!')
    } catch (error) {
      message.error((error as any)?.response?.data?.detail || '获取推荐参数失败')
    } finally {
      setRecommendLoading(false)
    }
  }

  // 生成策略名称
  const generateStrategyName = (rec: GridParamsRecommendation) => {
    const baseCcy = rec.symbol.split('-')[0] // 如 BTC-USDT -> BTC
    const date = new Date()
    const month = (date.getMonth() + 1).toString().padStart(2, '0')
    const day = date.getDate().toString().padStart(2, '0')
    const dateStr = `${month}${day}` // 如: 1026

    // 风险标签
    const riskTag = rec.risk_assessment.risk_level === '低' ? '稳健' :
                    rec.risk_assessment.risk_level === '中' ? '均衡' : '激进'

    // 生成名称: "BTC网格 | 10格 | 稳健 | 1026"
    return `${baseCcy}网格 | ${rec.grid_num}格 | ${riskTag} | ${dateStr}`
  }

  // 应用推荐参数
  const handleApplyRecommendation = () => {
    if (!recommendation) return

    // 生成策略名称
    const strategyName = generateStrategyName(recommendation)

    form.setFieldsValue({
      name: strategyName,
      price_upper: recommendation.price_upper,
      price_lower: recommendation.price_lower,
      grid_num: recommendation.grid_num,
    })

    message.success('已应用推荐参数并生成策略名称!')
    setShowRecommendation(false)
  }

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      setLoading(true)

      // 构建策略参数 - 注意：止盈比例需要转换为0-1
      const strategyData = {
        name: values.name,
        type: 'grid',
        symbol: values.symbol,
        timeframe: '1m',
        description: `${t('strategy.grid')} - ${values.grid_num}${t('strategy.gridNumber')}`,
        parameters: {
          grid_num: values.grid_num,
          price_upper: values.price_upper.toString(),
          price_lower: values.price_lower.toString(),
          total_amount: values.total_amount.toString(),
          min_order_size: '0.001',
          stop_loss: values.stop_loss || 0,
          stop_loss_pct: values.stop_loss_pct || 0,
          take_profit: values.take_profit || 0,
          take_profit_pct: values.take_profit_pct ? values.take_profit_pct / 100 : 0, // 转换为0-1
          max_position: values.max_position || 0,
          margin_mode: values.margin_mode || 'isolated', // 保证金模式（永续合约/交割合约使用）
          leverage: values.leverage || 10, // 杠杆倍数（永续合约/交割合约使用）
        }
      }

      await strategyApi.create(strategyData)

      message.success(t('message.createSuccess'))
      form.resetFields()
      onSuccess()
    } catch (error) {
      console.error(t('message.createFailed'), error)
      const errorDetail = (error as any)?.response?.data?.detail || t('message.createFailed')

      // 如果是余额不足错误，显示更长时间和更醒目的提示
      if (errorDetail.includes('余额不足') || errorDetail.includes('insufficient')) {
        message.error({
          content: errorDetail,
          duration: 8, // 显示8秒
          style: {
            marginTop: '20vh',
          }
        })
      } else {
        message.error(errorDetail)
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <Modal
      title={<div className="pro-card-header" style={{ margin: 0 }}>{t('strategy.createStrategy').toUpperCase()}</div>}
      open={open}
      onCancel={onCancel}
      onOk={handleSubmit}
      confirmLoading={loading}
      width={900}
      okText={t('common.confirm')}
      cancelText={t('common.cancel')}
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={{
          symbol: undefined, // 不设置默认值,让用户选择
          grid_num: 10,
          price_upper: '',
          price_lower: '',
          total_amount: 5000,
          margin_mode: 'isolated', // 默认逐仓模式
          leverage: 10,
          stop_loss: 0,
          stop_loss_pct: 0,
          take_profit: 0,
          take_profit_pct: 10, // 默认10%
          max_position: 0,
        }}
      >
        {/* 基本信息 */}
        <div style={{ marginBottom: 8 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#737373', marginBottom: 12 }}>
            基本信息
          </div>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                label={t('strategy.strategyName')}
                name="name"
                rules={[{ required: true, message: t('message.required') }]}
                style={{ marginBottom: 16 }}
              >
                <Input placeholder="My Grid Strategy" />
              </Form.Item>
            </Col>

            <Col span={12}>
              <Form.Item
                label={
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span>{t('strategy.symbol')}</span>
                    {currentPrice && (
                      <span
                        style={{
                          fontSize: 12,
                          color: '#1890ff',
                          fontWeight: 'normal',
                          transition: 'all 0.3s ease',
                          opacity: priceUpdating ? 0.6 : 1,
                          transform: priceUpdating ? 'scale(1.05)' : 'scale(1)'
                        }}
                      >
                        当前: ${(() => {
                          // 根据价格大小动态调整小数位数
                          if (currentPrice >= 1000) return currentPrice.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
                          if (currentPrice >= 1) return currentPrice.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 })
                          if (currentPrice >= 0.01) return currentPrice.toLocaleString(undefined, { minimumFractionDigits: 4, maximumFractionDigits: 6 })
                          return currentPrice.toLocaleString(undefined, { minimumFractionDigits: 6, maximumFractionDigits: 8 })
                        })()}
                      </span>
                    )}
                    {priceLoading && (
                      <span style={{ fontSize: 12, color: '#999', fontWeight: 'normal' }}>
                        加载中...
                      </span>
                    )}
                  </div>
                }
                name="symbol"
                rules={[{ required: true, message: t('message.required') }]}
                style={{ marginBottom: 8 }}
              >
                <Select
                  placeholder="选择交易对"
                  showSearch
                  loading={instrumentsLoading}
                  filterOption={false}
                  onSearch={setSearchText}
                  notFoundContent={instrumentsLoading ? '加载中...' : '暂无数据'}
                  popupRender={(menu) => (
                    <>
                      <div style={{ padding: '8px 12px', borderBottom: '1px solid #f0f0f0' }}>
                        <Radio.Group
                          value={instType}
                          onChange={(e) => handleInstTypeChange(e.target.value)}
                          buttonStyle="solid"
                          size="small"
                        >
                          <Radio.Button value="SPOT">现货</Radio.Button>
                          <Radio.Button value="SWAP">永续合约</Radio.Button>
                        </Radio.Group>
                        <div style={{ marginTop: 4, fontSize: 12, color: '#999' }}>
                          共 {filteredInstruments.length} 个交易对
                        </div>
                      </div>
                      {menu}
                    </>
                  )}
                >
                  {filteredInstruments.map((inst) => (
                    <Select.Option key={inst.instId} value={inst.instId}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span style={{ fontWeight: 500 }}>{inst.instId}</span>
                        <span style={{ fontSize: 11, color: '#999', marginLeft: 8 }}>
                          {inst.instType === 'SWAP' ? '永续' : '现货'}
                        </span>
                      </div>
                    </Select.Option>
                  ))}
                </Select>
              </Form.Item>
              {/* 提示文字 */}
              <div style={{ marginTop: -4, marginBottom: 8, fontSize: 11, color: '#999' }}>
                支持搜索交易对名称, 如: BTC, ETH, SOL 等
              </div>
              {/* 永续合约风险提示 */}
              {isSwapOrFutures && (
                <Alert
                  message="永续合约风险提示"
                  description={
                    <div style={{ fontSize: 12 }}>
                      • 永续合约支持杠杆交易，收益和风险都会放大<br />
                      • <strong>逐仓模式</strong>: 仅该仓位资金参与，风险隔离（推荐新手）<br />
                      • <strong>全仓模式</strong>: 账户全部资金参与，风险共担<br />
                      • 模拟盘仅支持主流币种 (BTC、ETH、SOL等)<br />
                      • 建议新手使用逐仓+低倍杠杆 (1-5x)
                    </div>
                  }
                  type="warning"
                  showIcon
                  style={{ marginBottom: 8, fontSize: 12 }}
                />
              )}
            </Col>
          </Row>
        </div>

        <Divider style={{ margin: '12px 0 20px 0' }} />

        {/* 网格参数 */}
        <div style={{ marginBottom: 8 }}>
          <div style={{
            fontSize: 13,
            fontWeight: 600,
            color: '#737373',
            marginBottom: 12,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between'
          }}>
            <span>网格参数</span>
            <Button
              type="primary"
              icon={<Lightbulb size={14} />}
              size="small"
              loading={recommendLoading}
              onClick={handleGetRecommendation}
              disabled={!symbol || !totalAmount}
              style={{ fontSize: 12 }}
            >
              智能推荐参数
            </Button>
          </div>

          {/* 推荐参数卡片 - 专业金融配色 */}
          {showRecommendation && recommendation && (
            <div style={{
              marginBottom: 16,
              padding: 0,
              background: '#F0EAF5',
              borderRadius: 8,
              boxShadow: '0 4px 12px rgba(90, 55, 158, 0.1)',
              border: '1px solid #E0D4ED'
            }}>
              {/* 标题栏 */}
              <div style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '16px 20px',
                background: '#fff',
                borderTopLeftRadius: 8,
                borderTopRightRadius: 8,
                borderBottom: '2px solid #5A379E'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Lightbulb size={18} style={{ color: '#5A379E' }} />
                  <span style={{ fontSize: 15, fontWeight: 600, color: '#1E1E2E' }}>智能推荐参数</span>
                </div>
                <Tag color={recommendation.risk_assessment.risk_level === '低' ? 'success' : recommendation.risk_assessment.risk_level === '中' ? 'orange' : 'red'}>
                  {recommendation.risk_assessment.risk_level}风险
                </Tag>
              </div>

              {/* 内容区域 */}
              <div style={{ padding: '20px' }}>
                {/* 核心参数 */}
                <Row gutter={12} style={{ marginBottom: 16 }}>
                  <Col span={8}>
                    <div style={{
                      textAlign: 'center',
                      padding: '12px',
                      background: '#fff',
                      borderRadius: 6,
                      border: '1px solid #E0D4ED'
                    }}>
                      <div style={{ fontSize: 12, color: '#666666', marginBottom: 6 }}>当前价格</div>
                      <div style={{ fontSize: 18, fontWeight: 600, color: '#5A379E' }}>
                        ${formatPrice(recommendation.current_price)}
                      </div>
                    </div>
                  </Col>
                  <Col span={8}>
                    <div style={{
                      textAlign: 'center',
                      padding: '12px',
                      background: '#fff',
                      borderRadius: 6,
                      border: '1px solid #E0D4ED'
                    }}>
                      <div style={{ fontSize: 12, color: '#666666', marginBottom: 6 }}>推荐网格数</div>
                      <div style={{ fontSize: 18, fontWeight: 600, color: '#2196F3', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4 }}>
                        {recommendation.grid_num} <TrendingUp size={14} />
                      </div>
                    </div>
                  </Col>
                  <Col span={8}>
                    <div style={{
                      textAlign: 'center',
                      padding: '12px',
                      background: '#fff',
                      borderRadius: 6,
                      border: '1px solid #E0D4ED'
                    }}>
                      <div style={{ fontSize: 12, color: '#666666', marginBottom: 6 }}>单格利润率</div>
                      <div style={{ fontSize: 18, fontWeight: 600, color: '#4CAF50' }}>
                        ~{recommendation.profit_per_grid_percent}%
                      </div>
                    </div>
                  </Col>
                </Row>

                {/* 价格区间和收益 */}
                <Row gutter={12} style={{ marginBottom: 16 }}>
                  <Col span={12}>
                    <div style={{
                      padding: '14px',
                      background: '#fff',
                      borderRadius: 6,
                      border: '1px solid #E0D4ED'
                    }}>
                      <div style={{ fontSize: 12, color: '#666666', marginBottom: 8 }}>价格区间</div>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                        <span style={{ fontSize: 14, fontWeight: 500, color: '#D9385E' }}>
                          ${formatPrice(recommendation.price_lower)}
                        </span>
                        <span style={{ fontSize: 12, color: '#d9d9d9' }}>━</span>
                        <span style={{ fontSize: 14, fontWeight: 500, color: '#2E8B57' }}>
                          ${formatPrice(recommendation.price_upper)}
                        </span>
                      </div>
                    </div>
                  </Col>
                  <Col span={12}>
                    <div style={{
                      padding: '14px',
                      background: '#fff',
                      borderRadius: 6,
                      border: '1px solid #E0D4ED'
                    }}>
                      <div style={{ fontSize: 12, color: '#666666', marginBottom: 8 }}>收益预估</div>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                        <span style={{ fontSize: 14, fontWeight: 500, color: '#FF9800' }}>
                          日收益 ${formatAmount(recommendation.risk_assessment.estimated_daily_profit)}
                        </span>
                        <span style={{ fontSize: 12, color: '#666666' }}>
                          {recommendation.risk_assessment.estimated_daily_trades}次
                        </span>
                      </div>
                    </div>
                  </Col>
                </Row>

                {/* 使用建议 */}
                {recommendation.recommendations && recommendation.recommendations.length > 0 && (
                  <div style={{
                    padding: '12px 14px',
                    background: '#fff',
                    borderRadius: 6,
                    border: '1px solid #E0D4ED',
                    marginBottom: 16
                  }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: '#1E1E2E', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
                      <Info size={14} style={{ color: '#2196F3' }} />
                      使用建议
                    </div>
                    <div style={{ fontSize: 12, lineHeight: 1.6, color: '#666666' }}>
                      {recommendation.recommendations.slice(0, 2).map((rec, idx) => (
                        <div key={idx} style={{ marginBottom: idx === 0 ? 4 : 0 }}>
                          • {rec.replace(/^[💡✅⚠️📊🔄]\s*/, '')}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* 操作按钮 */}
                <div style={{ display: 'flex', gap: 10 }}>
                  <Button
                    type="primary"
                    icon={<Zap size={14} />}
                    onClick={handleApplyRecommendation}
                    className="apply-recommendation-btn"
                    style={{
                      flex: 1,
                      height: 40,
                      fontSize: 14,
                      fontWeight: 500,
                      background: 'linear-gradient(135deg, #7B42F4 0%, #9C27B0 100%)',
                      border: 'none',
                      boxShadow: '0 2px 8px rgba(123, 66, 244, 0.3)'
                    }}
                  >
                    应用推荐参数
                  </Button>
                  <Button
                    onClick={() => setShowRecommendation(false)}
                    style={{ height: 40, fontSize: 14, color: '#9E9E9E', borderColor: '#9E9E9E' }}
                  >
                    关闭
                  </Button>
                </div>
              </div>
            </div>
          )}

          {/* 价格区间 - 先让用户设置价格区间 */}
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                label={`${t('strategy.priceUpper')} (USDT)`}
                name="price_upper"
                rules={[
                  { required: true, message: t('message.required') },
                  {
                    validator: (_, value) => {
                      const lower = form.getFieldValue('price_lower')
                      if (!value || !lower) {
                        return Promise.resolve()
                      }
                      if (value > lower) {
                        return Promise.resolve()
                      }
                      return Promise.reject(new Error('价格上限必须大于价格下限'))
                    }
                  }
                ]}
                style={{ marginBottom: 16 }}
              >
                <InputNumber
                  min={0}
                  precision={8}
                  step={0.00000001}
                  style={{ width: '100%' }}
                  placeholder="100000"
                  formatter={(value) => removeTrailingZeros(value)}
                  parser={(value) => value ? parseFloat(value) : 0}
                  onChange={() => form.validateFields(['price_lower'])} // 触发下限验证
                />
              </Form.Item>
            </Col>

            <Col span={12}>
              <Form.Item
                label={`${t('strategy.priceLower')} (USDT)`}
                name="price_lower"
                rules={[
                  { required: true, message: t('message.required') },
                  {
                    validator: (_, value) => {
                      const upper = form.getFieldValue('price_upper')
                      if (!value || !upper) {
                        return Promise.resolve()
                      }
                      if (value < upper) {
                        return Promise.resolve()
                      }
                      return Promise.reject(new Error('价格下限必须小于价格上限'))
                    }
                  }
                ]}
                style={{ marginBottom: 16 }}
              >
                <InputNumber
                  min={0}
                  precision={8}
                  step={0.00000001}
                  style={{ width: '100%' }}
                  placeholder="90000"
                  formatter={(value) => removeTrailingZeros(value)}
                  parser={(value) => value ? parseFloat(value) : 0}
                  onChange={() => form.validateFields(['price_upper'])} // 触发上限验证
                />
              </Form.Item>
            </Col>
          </Row>

          {/* 网格数量 - 确定价格区间后再决定分几格 */}
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item
                label={
                  <div>
                    {t('strategy.gridNumber')}
                    {gridSpacing && (
                      <span style={{ marginLeft: 8, fontSize: 12, color: '#52c41a', fontWeight: 'normal' }}>
                        每格价差: ${formatAmount(gridSpacing)}
                      </span>
                    )}
                  </div>
                }
                name="grid_num"
                rules={[{ required: true, message: t('message.required') }]}
                style={{ marginBottom: 16 }}
              >
                <InputNumber min={2} max={100} style={{ width: '100%' }} />
              </Form.Item>
            </Col>

            <Col span={12}>
              <Form.Item
                label={
                  <div>
                    策略总投资 (USDT)
                    {perGridInvestment && (
                      <span style={{ marginLeft: 8, fontSize: 12, color: '#52c41a', fontWeight: 'normal' }}>
                        单格: ${formatAmount(perGridInvestment)}
                      </span>
                    )}
                  </div>
                }
                name="total_amount"
                rules={[
                  { required: true, message: t('message.required') },
                  { type: 'number', min: 1500, message: `${t('message.minValue')}: 1500 USDT` }
                ]}
                tooltip="整个网格策略的总投资金额，将平均分配到各网格"
                style={{ marginBottom: 16 }}
              >
                <InputNumber min={1500} precision={2} style={{ width: '100%' }} placeholder="5000" />
              </Form.Item>
            </Col>
          </Row>

          {/* 杠杆倍数设置（仅永续合约/交割合约） */}
          {isSwapOrFutures && (
            <Row gutter={16} style={{ marginTop: 16 }}>
              <Col span={12}>
                <Form.Item
                  label={
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span>保证金模式</span>
                      <Tag color="blue" style={{ margin: 0, fontSize: 11 }}>永续/交割</Tag>
                    </div>
                  }
                  name="margin_mode"
                  rules={[
                    { required: true, message: '请选择保证金模式' },
                  ]}
                  tooltip={
                    <div>
                      <div>• 全仓: 账户所有可用资金作为保证金，风险共担</div>
                      <div>• 逐仓: 仅使用该仓位的保证金，风险隔离</div>
                      <div style={{ marginTop: 4, color: '#52c41a' }}>推荐新手使用逐仓模式，风险可控</div>
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
              </Col>
              <Col span={12}>
                <Form.Item
                  label={
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span>杠杆倍数</span>
                      <Tag color="orange" style={{ margin: 0, fontSize: 11 }}>永续/交割</Tag>
                    </div>
                  }
                  name="leverage"
                  rules={[
                    { required: true, message: '请选择杠杆倍数' },
                  ]}
                  tooltip="永续合约和交割合约支持杠杆交易。杠杆越高，收益和风险都会放大。建议新手使用低倍杠杆。"
                  style={{ marginBottom: 0 }}
                >
                  <Select placeholder="选择杠杆倍数">
                    <Select.Option value={1}>1x (无杠杆)</Select.Option>
                    <Select.Option value={2}>2x</Select.Option>
                    <Select.Option value={3}>3x</Select.Option>
                    <Select.Option value={5}>5x</Select.Option>
                    <Select.Option value={10}>10x (推荐)</Select.Option>
                    <Select.Option value={20}>20x</Select.Option>
                    <Select.Option value={50}>50x</Select.Option>
                    <Select.Option value={100}>100x (高风险)</Select.Option>
                  </Select>
                </Form.Item>
              </Col>
            </Row>
          )}
        </div>

        <Divider style={{ margin: '12px 0 20px 0' }} />

        {/* 风控设置 */}
        <div style={{ marginBottom: 0 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#737373', marginBottom: 12 }}>
            风控设置（可选）
          </div>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item
                label={`止盈比例 (%)`}
                name="take_profit_pct"
                tooltip="每格盈利达到此比例时自动卖出，例如输入10表示10%"
                style={{ marginBottom: 0 }}
              >
                <InputNumber
                  min={0}
                  max={100}
                  step={1}
                  precision={0}
                  style={{ width: '100%' }}
                  placeholder="10"
                />
              </Form.Item>
            </Col>

            <Col span={8}>
              <Form.Item
                label={`止损金额 (USDT)`}
                name="stop_loss"
                tooltip="策略累计亏损达到此金额时自动停止"
                style={{ marginBottom: 0 }}
              >
                <InputNumber min={0} precision={2} style={{ width: '100%' }} placeholder="0" />
              </Form.Item>
            </Col>

            <Col span={8}>
              <Form.Item
                label={t('settings.maxPosition')}
                name="max_position"
                tooltip="限制最大持仓数量，0表示不限制"
                style={{ marginBottom: 0 }}
              >
                <InputNumber min={0} step={0.001} precision={6} style={{ width: '100%' }} placeholder="0" />
              </Form.Item>
            </Col>
          </Row>
        </div>
      </Form>
    </Modal>
  )
}
