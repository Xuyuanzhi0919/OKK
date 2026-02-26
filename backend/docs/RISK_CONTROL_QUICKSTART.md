# 风控系统快速入门指南

## 系统概述

OKK风控系统是一个多层级、多维度的风险控制系统，用于保护你的交易资金安全。

### 核心功能

**5类风控规则：**
1. **资金风控** (capital) - 最小可用资金、最大持仓价值、单笔订单限额
2. **持仓风控** (position) - 单币种持仓上限、持仓集中度限制
3. **亏损风控** (loss) - 日亏损限额、总亏损限额、连续亏损次数限制
4. **回撤风控** (drawdown) - 最大回撤百分比限制
5. **频率风控** (frequency) - 交易频率限制

**4种风控动作：**
- **warn** (警告) - 仅发送预警通知
- **limit** (限制) - 限制新订单，但不影响现有持仓
- **pause** (暂停) - 暂停策略，停止所有交易
- **close** (平仓) - 市价卖出所有持仓并暂停策略

**紧急功能：**
- 一键暂停所有策略
- 一键平仓所有策略（待完善）

---

## 快速开始

### 步骤1: 运行数据库迁移

```bash
cd backend
psql -h localhost -U okk_user -d okk_quant -f migrations/004_create_risk_control_tables.sql
```

### 步骤2: 重启后端服务

```bash
cd backend
python -m app.main
```

### 步骤3: 访问API文档

打开浏览器访问: http://localhost:8000/docs

找到 **"风控管理"** 标签查看所有API端点

---

## API使用示例

### 1. 创建资金风控规则

**示例：账户可用资金低于5000 USDT时发出警告**

```bash
curl -X POST "http://localhost:8000/api/v1/risk-control/rules" \
  -H "Content-Type: application/json" \
  -d '{
    "level": "global",
    "risk_type": "capital",
    "name": "全局资金安全线",
    "description": "账户可用资金低于5000 USDT时发出警告",
    "min_available_balance": 5000.0,
    "action_on_trigger": "warn",
    "warning_threshold": 0.8,
    "is_enabled": true
  }'
```

### 2. 创建策略级回撤风控

**示例：策略最大回撤超过15%时自动暂停**

```bash
curl -X POST "http://localhost:8000/api/v1/risk-control/rules" \
  -H "Content-Type: application/json" \
  -d '{
    "strategy_id": 34,
    "level": "strategy",
    "risk_type": "drawdown",
    "name": "最大回撤保护",
    "description": "回撤超过15%时自动暂停策略",
    "max_drawdown_percent": 0.15,
    "action_on_trigger": "pause",
    "is_enabled": true
  }'
```

### 3. 创建日亏损限额

**示例：策略日亏损超过500 USDT时自动暂停**

```bash
curl -X POST "http://localhost:8000/api/v1/risk-control/rules" \
  -H "Content-Type: application/json" \
  -d '{
    "strategy_id": 34,
    "level": "strategy",
    "risk_type": "loss",
    "name": "日亏损限额",
    "description": "单日亏损超过500 USDT时暂停策略",
    "daily_loss_limit": 500.0,
    "action_on_trigger": "pause",
    "is_enabled": true
  }'
```

### 4. 查询所有风控规则

```bash
curl "http://localhost:8000/api/v1/risk-control/rules"
```

### 5. 查询单个策略的风控规则

```bash
curl "http://localhost:8000/api/v1/risk-control/rules?strategy_id=34"
```

### 6. 检查策略风控状态

```bash
curl "http://localhost:8000/api/v1/risk-control/check/34"
```

**返回示例：**
```json
{
  "strategy_id": 34,
  "has_risk": true,
  "triggered_count": 2,
  "triggered_rules": [
    {
      "risk_type": "loss",
      "severity": "error",
      "message": "日亏损超限: -520.50 USDT < -500.00 USDT",
      "metrics": {
        "today_loss": -520.50,
        "daily_limit": 500.0
      }
    }
  ]
}
```

### 7. 紧急暂停所有策略

```bash
curl -X POST "http://localhost:8000/api/v1/risk-control/emergency-stop" \
  -H "Content-Type: application/json" \
  -d '{
    "action": "pause_all"
  }'
```

### 8. 紧急暂停指定策略

```bash
curl -X POST "http://localhost:8000/api/v1/risk-control/emergency-stop" \
  -H "Content-Type: application/json" \
  -d '{
    "action": "pause_all",
    "strategy_ids": [34, 35]
  }'
```

### 9. 更新风控规则

```bash
curl -X PUT "http://localhost:8000/api/v1/risk-control/rules/1" \
  -H "Content-Type: application/json" \
  -d '{
    "daily_loss_limit": 800.0,
    "is_enabled": true
  }'
```

### 10. 删除风控规则

```bash
curl -X DELETE "http://localhost:8000/api/v1/risk-control/rules/1"
```

### 11. 查看风控动作日志

```bash
curl "http://localhost:8000/api/v1/risk-control/actions?limit=20"
```

---

## 推荐风控规则配置

### 新手保守配置

```json
[
  {
    "level": "global",
    "risk_type": "capital",
    "name": "全局资金安全线",
    "min_available_balance": 3000.0,
    "action_on_trigger": "pause"
  },
  {
    "level": "strategy",
    "risk_type": "loss",
    "name": "日亏损限额",
    "daily_loss_limit": 200.0,
    "action_on_trigger": "pause"
  },
  {
    "level": "strategy",
    "risk_type": "drawdown",
    "name": "最大回撤保护",
    "max_drawdown_percent": 0.10,
    "action_on_trigger": "pause"
  },
  {
    "level": "strategy",
    "risk_type": "loss",
    "name": "连续亏损保护",
    "max_consecutive_losses": 5,
    "action_on_trigger": "pause"
  }
]
```

### 进阶配置

```json
[
  {
    "level": "global",
    "risk_type": "capital",
    "name": "全局资金安全线",
    "min_available_balance": 5000.0,
    "action_on_trigger": "warn"
  },
  {
    "level": "strategy",
    "risk_type": "loss",
    "name": "日亏损限额",
    "daily_loss_limit": 500.0,
    "action_on_trigger": "pause"
  },
  {
    "level": "strategy",
    "risk_type": "drawdown",
    "name": "最大回撤保护",
    "max_drawdown_percent": 0.15,
    "action_on_trigger": "pause"
  },
  {
    "level": "strategy",
    "risk_type": "position",
    "name": "持仓集中度限制",
    "max_concentration_ratio": 0.5,
    "action_on_trigger": "limit"
  },
  {
    "level": "strategy",
    "risk_type": "frequency",
    "name": "交易频率限制",
    "max_trades_per_period": 50,
    "period_seconds": 3600,
    "action_on_trigger": "limit"
  }
]
```

---

## 常见问题

### Q: 风控规则多久检查一次？

A: 目前风控检查需要手动调用或集成到策略引擎中。建议在每次下单前、订单成交后、定时任务中调用检查。

### Q: 触发风控后如何恢复交易？

A:
1. 手动修复触发原因（如充值、减少持仓等）
2. 将风控规则的 `is_enabled` 设为 `false` 暂时禁用
3. 重新启动策略

### Q: 可以为不同策略设置不同的风控规则吗？

A: 可以！每个风控规则都可以指定 `strategy_id`，也可以设为 `null` 作为全局规则。

### Q: 风控规则的优先级是什么？

A:
1. 所有触发的规则都会被执行
2. 如果有多个规则，取最严格的动作（close > pause > limit > warn）

### Q: 如何测试风控规则是否生效？

A: 可以调用检查API: `GET /api/v1/risk-control/check/{strategy_id}`

---

## 下一步

1. **配置风控规则** - 根据你的风险偏好创建风控规则
2. **集成到策略引擎** - 在策略下单前、订单成交后调用风控检查
3. **添加WebSocket推送** - 实时推送风控预警到前端
4. **开发前端界面** - 可视化配置和监控风控规则

## API完整文档

访问 http://localhost:8000/docs 查看完整的API文档和在线测试工具。
