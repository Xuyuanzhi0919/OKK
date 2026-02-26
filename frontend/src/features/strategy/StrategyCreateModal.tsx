import { useState, useEffect } from 'react'
import {
  Modal, Form, Input, Select, Divider,
  Row, Col, Space, Tooltip, Alert, InputNumber, Switch,
} from 'antd'
import { InfoCircleOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import { strategyApi } from '@/services/api'
import { API_BASE_URL } from '@/config/api'

const { TextArea } = Input

interface StrategyCreateModalProps {
  open: boolean
  onCancel: () => void
  onSuccess: () => void
  /** 从下拉菜单预选的策略类型，打开时自动填入 */
  initialType?: string
  backtestData?: {
    strategy_type: string
    symbol: string
    parameters: Record<string, any>
    name?: string
  } | null
}

// 可用实盘策略类型（已通过回测验证）
const STRATEGY_TYPES: { value: string; label: string; desc: string }[] = [
  {
    value: 'trend',
    label: 'EMA趋势跟踪',
    desc: 'EMA(12,40)双均线金叉做多，RSI<65过滤超买，15m时间周期，经256组参数回测验证',
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
  open, onCancel, onSuccess, initialType, backtestData,
}) => {
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)

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

  // 从下拉菜单预选类型
  useEffect(() => {
    if (initialType && open && !backtestData) {
      form.setFieldValue('type', initialType)
    }
  }, [initialType, open, backtestData, form])

  // 从回测预填数据
  useEffect(() => {
    if (backtestData && open) {
      form.setFieldsValue({
        type: backtestData.strategy_type,
        symbol: backtestData.symbol,
        name: backtestData.name || `${backtestData.symbol} ${backtestData.strategy_type}策略`,
        ...backtestData.parameters,
      })
    }
  }, [backtestData, open, form])

  // 提交
  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      setLoading(true)

      // 构建策略参数（根据策略类型提取对应字段）
      const parameters: Record<string, any> = {}
      if (values.type === 'trend') {
        parameters.position_ratio  = (values.position_ratio ?? 40) / 100   // 百分比 → 小数
        parameters.stop_loss       = (values.stop_loss ?? 1) / 100
        parameters.take_profit     = (values.take_profit ?? 8) / 100
        parameters.use_rsi_filter  = values.use_rsi_filter ?? true
        // fast_period / slow_period 使用策略内置最优值（12/40），不对外暴露
      }

      await strategyApi.create({
        name: values.name,
        type: values.type as any,
        symbol: values.symbol,
        timeframe: values.type === 'trend' ? '15m' : (values.timeframe ?? '1H'),
        parameters,
        description: values.description,
      } as any)

      form.resetFields()
      onSuccess()
    } catch (err: any) {
      if (err?.errorFields) return
    } finally {
      setLoading(false)
    }
  }

  const handleCancel = () => { form.resetFields(); onCancel() }

  const compactDivider = { fontSize: 12, color: '#8c8c8c', margin: '12px 0 8px' }
  const compactItem = { marginBottom: 8 }

  const noTypes = STRATEGY_TYPES.length === 0
  const selectedType = Form.useWatch('type', form)

  return (
    <Modal
      title={backtestData ? '从回测创建策略' : '创建策略'}
      open={open}
      onCancel={handleCancel}
      onOk={handleSubmit}
      okText="创建"
      cancelText="取消"
      width={600}
      confirmLoading={loading}
      okButtonProps={{ disabled: noTypes && !backtestData }}
      destroyOnHidden
      styles={{ body: { maxHeight: '65vh', overflowY: 'auto', paddingRight: 4 } }}
    >
      {backtestData && (
        <Alert
          message="已自动填充回测参数，可按需调整"
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
        />
      )}

      {noTypes && !backtestData && (
        <Alert
          message="暂无可用实盘策略类型"
          description="所有实盘策略均在开发中，敬请期待。"
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
        />
      )}

      <Form
        form={form}
        layout="vertical"
        initialValues={{
          type: backtestData?.strategy_type ?? 'trend',
          symbol: backtestData?.symbol || 'BTC-USDT-SWAP',
          timeframe: '15m',
          position_ratio: 40,
          stop_loss: 1,
          take_profit: 8,
          use_rsi_filter: true,
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
            <Form.Item name="type" label="策略类型" rules={[{ required: true, message: '请选择策略类型' }]} style={compactItem}>
              <Select
                placeholder={noTypes ? '暂无可用策略类型' : '选择策略类型'}
                disabled={noTypes && !backtestData}
                options={STRATEGY_TYPES.map(t => ({ value: t.value, label: t.label }))}
              />
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

        {/* ── EMA 趋势跟踪参数 ── */}
        {selectedType === 'trend' && (
          <>
            <Divider orientation="left" style={compactDivider}>
              策略参数
              <Tooltip title="EMA快线=12 慢线=40 已固定（回测最优），无需调整">
                <InfoCircleOutlined style={{ marginLeft: 6, color: '#8c8c8c', fontSize: 12 }} />
              </Tooltip>
            </Divider>
            <Alert
              message="EMA(12,40) 参数已通过 256 组回测验证固定，仅需配置仓位与风控"
              type="info"
              showIcon
              style={{ marginBottom: 10, fontSize: 12 }}
            />
            <Row gutter={12}>
              <Col span={8}>
                <Form.Item
                  name="position_ratio"
                  label={<Space size={4}>仓位比例(%)<Tooltip title="每次开仓占可用余额的百分比"><InfoCircleOutlined style={{ color: '#8c8c8c', fontSize: 12 }} /></Tooltip></Space>}
                  style={compactItem}
                >
                  <InputNumber min={5} max={90} step={5} suffix="%" style={{ width: '100%' }} />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item
                  name="stop_loss"
                  label={<Space size={4}>止损(%)<Tooltip title="持仓亏损达到此比例时触发市价平仓（实时价格）"><InfoCircleOutlined style={{ color: '#8c8c8c', fontSize: 12 }} /></Tooltip></Space>}
                  style={compactItem}
                >
                  <InputNumber min={0.1} max={20} step={0.5} suffix="%" style={{ width: '100%' }} />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item
                  name="take_profit"
                  label={<Space size={4}>止盈(%)<Tooltip title="持仓盈利达到此比例时触发市价平仓（实时价格）"><InfoCircleOutlined style={{ color: '#8c8c8c', fontSize: 12 }} /></Tooltip></Space>}
                  style={compactItem}
                >
                  <InputNumber min={1} max={50} step={1} suffix="%" style={{ width: '100%' }} />
                </Form.Item>
              </Col>
              <Col span={24}>
                <Form.Item
                  name="use_rsi_filter"
                  label={<Space size={4}>RSI 超买过滤<Tooltip title="开启后：金叉信号出现时如果 RSI14 ≥ 65（超买区），则跳过本次开仓。回测验证可将收益从 +3.2% 提升到 +7.7%"><InfoCircleOutlined style={{ color: '#8c8c8c', fontSize: 12 }} /></Tooltip></Space>}
                  style={compactItem}
                  valuePropName="checked"
                >
                  <Switch checkedChildren="开启" unCheckedChildren="关闭" />
                </Form.Item>
              </Col>
            </Row>
          </>
        )}

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
