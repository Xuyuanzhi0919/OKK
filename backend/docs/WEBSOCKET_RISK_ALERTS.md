# WebSocket实时风控预警集成指南

## 概述

OKK量化交易系统的WebSocket已完成风控预警实时推送功能集成。

## 新增WebSocket事件

### 订阅事件

#### 1. `subscribe_risk_control`
订阅全局风控预警

**客户端发送：**
```javascript
socket.emit('subscribe_risk_control')
```

**服务器响应：**
```javascript
socket.on('subscribed_risk_control', () => {
  console.log('已订阅风控预警')
})
```

#### 2. `unsubscribe_risk_control`
取消订阅风控预警

**客户端发送：**
```javascript
socket.emit('unsubscribe_risk_control')
```

### 推送事件

#### 1. `risk_alert`
风控预警推送

**数据格式：**
```javascript
{
  id: 1,
  alert_type: "risk_warning",
  severity: "error" | "warning" | "info",
  title: "日亏损超限",
  message: "策略ETH网格 日亏损: -520.50 USDT > -500.00 USDT",
  strategy_id: 34,  // 可选
  rule_id: 5,       // 可选
  metrics: {
    today_loss: -520.50,
    daily_limit: 500.0
  },
  timestamp: "2025-10-27T19:45:00Z"
}
```

**客户端接收：**
```javascript
socket.on('risk_alert', (data) => {
  console.log('风控预警:', data)
  // 显示通知
  showNotification({
    type: data.severity,
    title: data.title,
    message: data.message
  })
})
```

#### 2. `risk_action`
风控动作执行推送

**数据格式：**
```javascript
{
  id: 1,
  action_type: "pause" | "warn" | "limit" | "close" | "resume",
  trigger_reason: "日亏损超限",
  execution_status: "success" | "failed" | "partial",
  strategy_id: 34,  // 可选
  rule_id: 5,       // 可选
  timestamp: "2025-10-27T19:45:01Z"
}
```

**客户端接收：**
```javascript
socket.on('risk_action', (data) => {
  console.log('风控动作:', data)
  if (data.action_type === 'pause') {
    // 更新策略状态为已暂停
    updateStrategyStatus(data.strategy_id, 'stopped')
  }
})
```

## 使用示例

### React前端集成

```typescript
// websocket.ts
import io from 'socket.io-client'

const socket = io('http://localhost:8000')

// 订阅风控预警
export const subscribeRiskAlerts = () => {
  socket.emit('subscribe_risk_control')

  socket.on('subscribed_risk_control', () => {
    console.log('已订阅风控预警')
  })
}

// 监听风控预警
export const onRiskAlert = (callback: (data: any) => void) => {
  socket.on('risk_alert', callback)
}

// 监听风控动作
export const onRiskAction = (callback: (data: any) => void) => {
  socket.on('risk_action', callback)
}

// 取消订阅
export const unsubscribeRiskAlerts = () => {
  socket.emit('unsubscribe_risk_control')
  socket.off('risk_alert')
  socket.off('risk_action')
}
```

### 在组件中使用

```typescript
// RiskMonitor.tsx
import { useEffect } from 'react'
import { subscribeRiskAlerts, onRiskAlert, onRiskAction } from '@/services/websocket'
import { notification } from 'antd'

const RiskMonitor = () => {
  useEffect(() => {
    // 订阅风控预警
    subscribeRiskAlerts()

    // 监听风控预警
    onRiskAlert((data) => {
      notification[data.severity]({
        message: data.title,
        description: data.message,
        duration: 0, // 不自动关闭
      })
    })

    // 监听风控动作
    onRiskAction((data) => {
      if (data.action_type === 'pause') {
        notification.warning({
          message: '策略已暂停',
          description: `原因: ${data.trigger_reason}`,
        })
      }
    })

    return () => {
      unsubscribeRiskAlerts()
    }
  }, [])

  return <div>风控监控中...</div>
}
```

## WebSocket房间机制

风控预警使用以下房间结构：

1. **`risk_control`** - 全局风控房间，所有订阅用户都会收到
2. **`strategy_{id}`** - 策略房间，订阅特定策略的用户会收到该策略的风控预警
3. **`strategies`** - 全局策略房间，监控所有策略的用户会收到

## 推送触发时机

风控预警会在以下情况下推送：

1. 风控规则被触发时（通过RiskManager.check_all_risks()）
2. 风控动作被执行时（通过RiskManager.execute_risk_action()）
3. 紧急停止API被调用时
4. 策略手动触发风控检查时

## 后端集成

### 在RiskManager中使用

```python
from app.websocket.manager import broadcast_risk_alert, broadcast_risk_action

class RiskManager:
    async def _send_alert(self, triggered_risk: Dict):
        """发送风控预警"""
        try:
            rule: RiskControl = triggered_risk["rule"]

            # 保存到数据库
            alert = Alert(...)
            self.db.add(alert)
            self.db.commit()

            # WebSocket实时推送
            alert_data = {
                "id": alert.id,
                "alert_type": "risk_warning",
                "severity": triggered_risk["severity"],
                "title": f"风控预警: {rule.name}",
                "message": triggered_risk["message"],
                "strategy_id": rule.strategy_id,
                "rule_id": rule.id,
                "metrics": triggered_risk["metrics"],
                "timestamp": alert.created_at.isoformat()
            }
            await broadcast_risk_alert(alert_data)

        except Exception as e:
            logger.error(f"发送风控预警失败: {e}")
```

## 测试

### 使用浏览器控制台测试

1. 打开前端页面
2. F12打开开发者工具
3. 在Console中执行：

```javascript
// 连接WebSocket
const socket = io('http://localhost:8000')

// 订阅风控预警
socket.emit('subscribe_risk_control')

// 监听订阅成功
socket.on('subscribed_risk_control', () => {
  console.log('已订阅风控预警')
})

// 监听风控预警
socket.on('risk_alert', (data) => {
  console.log('收到风控预警:', data)
})

// 监听风控动作
socket.on('risk_action', (data) => {
  console.log('收到风控动作:', data)
})
```

4. 通过API触发风控规则，观察Console输出

## 注意事项

1. **重连机制** - Socket.IO会自动处理断线重连，重连后需要重新订阅
2. **认证** - 生产环境应添加WebSocket认证
3. **房间管理** - 用户断开连接时会自动退出所有房间
4. **消息持久化** - 风控预警会同时保存到数据库和通过WebSocket推送

## API文档

完整的WebSocket事件列表请参考：
- [WebSocket Manager源码](../app/websocket/manager.py)
- [API文档](http://localhost:8000/docs)

## 相关文档

- [风控系统快速入门](RISK_CONTROL_QUICKSTART.md)
- [回测系统快速入门](BACKTEST_QUICKSTART.md)
