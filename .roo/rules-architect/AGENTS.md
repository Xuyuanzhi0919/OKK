# Architect Mode Rules

## 核心架构约束

- **策略抽象层**：所有策略继承 [`StrategyBase`](backend/app/services/strategy/base.py:18)，生命周期：`start()` → `on_tick()` → `on_order_update()` → `stop()`
- **交易所抽象层**：[`ExchangeBase`](backend/app/services/exchange/base.py) 定义统一接口，OKX实现包含HMAC签名
- **策略管理器**：单例模式，每个策略独立asyncio任务

## WebSocket架构

- **Socket.IO** ([`manager.py`](backend/app/websocket/manager.py))：前端通信，事件如 `strategy_stats:{id}`
- **OKX WebSocket** ([`okx_websocket.py`](backend/app/websocket/okx_websocket.py))：交易所私有频道，需API认证

## 非标准设计

- 通知配置使用JSON文件 [`notification_config.json`](backend/notification_config.json) 而非环境变量
- 策略状态每50秒持久化到数据库（而非实时）
- OKX代理是中国地区必需的（非可选）

## 安全约束

- API密钥禁止提现权限
- 生产环境必须修改 `SECRET_KEY`
