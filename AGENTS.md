# AGENTS.md

This file provides guidance to agents when working with code in this repository.

## 项目关键信息

**技术栈:** FastAPI + Python 3.11+ + PostgreSQL (TimescaleDB) | React 18 + TypeScript + Vite + Ant Design 5

## 非显而易见的命令

```bash
# 后端启动（必须从backend目录）
cd backend && python -m app.main
# 或使用 uvicorn（支持热重载）
cd backend && uvicorn app.main:socket_app --reload --host 0.0.0.0 --port 8000

# 前端开发
cd frontend && npm run dev    # http://localhost:5173
```

## 关键架构约束

- **策略基类** [`StrategyBase`](backend/app/services/strategy/base.py:18) - 所有策略必须继承并实现 `start()`, `on_tick()`, `on_order_update()`, `stop()`
- **策略管理器** [`manager.py`](backend/app/services/strategy/manager.py) - 单例模式，监控循环每5秒执行一次
- **交易所抽象** [`ExchangeBase`](backend/app/services/exchange/base.py) - OKX实现包含HMAC签名和代理支持

## 非显而易见的配置

- **OKX代理必需** - 中国地区必须设置 `OKX_PROXY=http://127.0.0.1:7897`（或本地代理端口）
- **通知配置** - [`notification_config.json`](backend/notification_config.json) 而非环境变量
- **Vite别名** - `@` 映射到 `src/`，API代理 `/api` → `http://localhost:8000`

## 策略开发关键点

```python
# 策略注册：在 manager.py 的 create_strategy() 添加类型映射
# 枚举扩展：在 models/strategy.py 的 StrategyType 添加新类型
# 交易所方法：get_ticker(), create_order(), cancel_order(), get_order(), get_balance()
```

## WebSocket双重设计

1. **Socket.IO** ([`manager.py`](backend/app/websocket/manager.py)) - 前端通信
2. **OKX WebSocket** ([`okx_websocket.py`](backend/app/websocket/okx_websocket.py)) - 交易所私有频道

## 日志规范

使用 `loguru`：`from loguru import logger`

## 安全注意

- API密钥只授予交易/查询权限，**禁止提现权限**
- 生产环境必须修改 `SECRET_KEY`
- 优先使用模拟盘测试 (`OKX_SIMULATED=true`)
