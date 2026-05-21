/**
 * 风控管理API服务
 */
import api from './api'

const BASE_URL = '/risk-control'

export interface RiskRule {
  id?: number
  user_id?: number
  strategy_id?: number | null
  level: 'global' | 'strategy'
  risk_type: 'capital' | 'position' | 'loss' | 'drawdown' | 'frequency'
  name: string
  description?: string
  is_enabled: boolean

  // 资金风控
  min_available_balance?: number
  max_position_value?: number
  max_order_amount?: number

  // 盈亏风控
  max_drawdown_percent?: number
  daily_loss_limit?: number
  total_loss_limit?: number
  max_consecutive_losses?: number

  // 持仓风控
  max_position_per_symbol?: number
  max_concentration_ratio?: number

  // 频率风控
  max_trades_per_period?: number
  period_seconds?: number

  // 动作配置
  action_on_trigger: 'warn' | 'limit' | 'pause' | 'close'
  warning_threshold?: number
  auto_resume?: boolean

  // 状态
  is_triggered?: boolean
  trigger_count?: number
}

// 获取风控规则列表
export const getRiskRules = async (params?: {
  strategy_id?: number
  level?: string
  risk_type?: string
  is_enabled?: boolean
}) => {
  return api.get(BASE_URL + '/rules', { params })
}

// 创建风控规则
export const createRiskRule = async (data: RiskRule) => {
  return api.post(BASE_URL + '/rules', data)
}

// 更新风控规则
export const updateRiskRule = async (id: number, data: Partial<RiskRule>) => {
  return api.put(`${BASE_URL}/rules/${id}`, data)
}

// 删除风控规则
export const deleteRiskRule = async (id: number) => {
  await api.delete(`${BASE_URL}/rules/${id}`)
}

// 检查策略风控状态
export const checkStrategyRisk = async (strategyId: number) => {
  return api.get(`${BASE_URL}/check/${strategyId}`)
}

// 紧急停止
export const emergencyStop = async (data: {
  action: 'pause_all' | 'close_all'
  strategy_ids?: number[]
}) => {
  return api.post(`${BASE_URL}/emergency-stop`, data)
}

// 获取风控动作日志
export const getRiskActions = async (params?: {
  strategy_id?: number
  action_type?: string
  limit?: number
}) => {
  return api.get(BASE_URL + '/actions', { params })
}
