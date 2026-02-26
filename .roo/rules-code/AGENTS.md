# Code Mode Rules

## 策略开发

- 新策略必须继承 [`StrategyBase`](backend/app/services/strategy/base.py:18) 并实现所有抽象方法
- 策略类型注册：在 [`manager.py`](backend/app/services/strategy/manager.py) 的 `create_strategy()` 添加映射
- 枚举扩展：在 [`models/strategy.py`](backend/app/models/strategy.py) 的 `StrategyType` 添加新类型

## API端点开发

- 路由注册在 [`api/__init__.py`](backend/app/api/__init__.py) 而非 main.py
- 数据库session通过 `Depends(get_db)` 注入

## 前端开发

- 路径别名 `@` 映射到 `src/`
- API调用封装在 [`src/services/api.ts`](frontend/src/services/api.ts)
- 全局状态使用 Zustand（[`useWebSocketStore.ts`](frontend/src/stores/useWebSocketStore.ts)）

## 交易所API

- OKX请求需要HMAC签名（已在 [`okx.py`](backend/app/services/exchange/okx.py) 实现）
- 中国地区必须配置代理 `OKX_PROXY`

## 日志规范

使用 loguru：`from loguru import logger`
