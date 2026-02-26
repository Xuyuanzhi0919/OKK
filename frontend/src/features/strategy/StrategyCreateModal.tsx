import { useState, useEffect } from 'react'
import {
  Modal, Form, Input, Select, Divider,
  Row, Col, Space, Tooltip, Alert,
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
  backtestData?: {
    strategy_type: string
    symbol: string
    parameters: Record<string, any>
    name?: string
  } | null
}

// 当前无可用的实盘策略类型，所有实盘策略均已移除或尚未实现。
// 后续接入真实策略实现后，在此数组中添加对应条目：
// { value: 'xxx', label: 'XXX策略', desc: '策略说明' }
const STRATEGY_TYPES: { value: string; label: string; desc: string }[] = []

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

      await strategyApi.create({
        name: values.name,
        type: values.type as any,
        symbol: values.symbol,
        timeframe: values.timeframe ?? '1H',
        parameters: {},
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
          type: backtestData?.strategy_type,
          symbol: backtestData?.symbol || 'BTC-USDT-SWAP',
          timeframe: '1H',
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
