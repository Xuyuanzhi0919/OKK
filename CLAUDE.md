# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

OKK量化交易系统 - 基于OKX交易所的量化交易平台，支持多种交易策略、回测、风控、AI增强等功能。

**技术栈:**
- 后端: FastAPI + Python 3.11+ + PostgreSQL (TimescaleDB) + Redis
- 前端: React 18 + TypeScript + Vite + Ant Design 5 + TailwindCSS

## 核心架构

### 1. 后端架构 (FastAPI)

**目录结构:**
```
backend/app/
├── api/endpoints/      # API端点模块
│   ├── auth.py         # JWT认证
│   ├── strategies.py   # 策略CRUD + 启停控制
│   ├── orders.py       # 订单查询和管理
│   ├── positions.py    # 持仓查询
│   ├── market.py       # 行情数据代理
│   ├── backtest.py     # 回测任务管理
│   ├── api_configs.py  # OKX API配置管理
│   ├── alerts.py       # 告警历史
│   └── risk_control.py # 风控规则管理
├── core/
│   ├── config.py       # 环境变量配置（pydantic-settings）
│   └── database.py     # SQLAlchemy session工厂
├── models/             # SQLAlchemy ORM模型
├── services/
│   ├── exchange/       # 交易所抽象层
│   ├── strategy/       # 策略引擎（基类 + 具体策略）
│   ├── backtest/       # 回测引擎和指标计算
│   ├── risk/           # 风控管理器
│   ├── ai/             # DeepSeek AI增强分析
│   ├── notification/   # 多渠道推送通知
│   └── account_monitor.py # 账户余额/持仓定期推送
├── websocket/
│   ├── manager.py      # Socket.IO管理器（前端连接）
│   └── okx_websocket.py # OKX WebSocket客户端（私有频道）
└── main.py             # FastAPI应用入口
```

**关键设计模式:**

1. **交易所抽象层** (`services/exchange/`)
   - `ExchangeBase` 定义统一接口
   - `OKXExchange` 实现OKX REST API（签名、代理、重试）

2. **策略抽象层** (`services/strategy/`)
   - `StrategyBase` 基类定义生命周期：`start()` → `on_tick()` → `on_order_update()` → `stop()`
   - 已实现策略：
     - `GridStrategy` - 网格策略
     - `SwingLongStrategy` - 波段做多策略
     - `AISwingLongStrategy` - AI增强波段策略

3. **策略管理器** (`services/strategy/manager.py`)
   - 单例模式，管理所有运行中的策略实例
   - 每个策略有独立的监控任务（asyncio task），每5秒循环一次：
     - 调用 `on_tick()` 处理最新行情
     - 查询订单状态，调用 `on_order_update()`
     - 每50秒持久化策略状态到数据库
     - 通过WebSocket广播实时统计

4. **API路由聚合** (`api/__init__.py`)
   - 统一注册所有端点路由，prefix `/api/v1`

### 2. OKX API实现

**关键特性:**
- HMAC SHA256签名认证
- 支持实盘/模拟盘切换（`x-simulated-trading` header）
- HTTP代理支持（`OKX_PROXY` 环境变量）
- 连接池和重试机制

**认证流程** (`services/exchange/okx.py`):
```python
# 签名: timestamp + method + requestPath + body
signature = base64(HMAC_SHA256(secret_key, message))
headers = {
    'OK-ACCESS-KEY': api_key,
    'OK-ACCESS-SIGN': signature,
    'OK-ACCESS-TIMESTAMP': timestamp,
    'OK-ACCESS-PASSPHRASE': passphrase,
    'x-simulated-trading': '1'  # 模拟盘需要
}
```

### 3. 前端架构

**路由结构** (`App.tsx`):
```
/ → 重定向到 /dashboard
├── /dashboard           # 仪表盘（策略统计、账户概览）
├── /strategies          # 策略列表（CRUD + 启停）
├── /trading             # 交易视图（K线图、订单簿、交易面板）
├── /trading-management  # 交易管理（历史订单、成交记录）
├── /backtest            # 回测列表
├── /backtest/:id        # 回测详情（权益曲线、交易记录）
├── /kline-manager       # K线数据管理
├── /alerts              # 告警历史
├── /risk-control        # 风控规则配置
├── /api-config          # OKX API配置管理
└── /settings            # 系统设置
```

**状态管理:**
- Zustand stores: `src/stores/useWebSocketStore.ts`
- TanStack Query: API数据缓存和同步

**核心功能模块:**
- `features/dashboard/` - 仪表盘
- `features/strategy/` - 策略管理（列表、详情、性能模态框）
- `features/trading/` - 交易相关（K线图、交易面板、订单簿）
- `features/backtest/` - 回测系统
- `features/settings/` - 设置和API配置

**API服务层:** `src/services/api.ts` - 封装所有后端API调用

## 常用命令

### 后端开发

```bash
cd backend

# 启动后端 (开发模式)
python -m app.main
# 或使用uvicorn
uvicorn app.main:socket_app --reload --host 0.0.0.0 --port 8000

# 代码格式化
black app/
flake8 app/

# 类型检查
mypy app/
```

**注意:** 项目没有 `test_api.py`、`test_proxy.py` 等测试脚本，README中提到的这些文件不存在。

### 前端开发

```bash
cd frontend

# 启动开发服务器
npm run dev

# 构建生产版本
npm run build

# 代码检查
npm run lint

# 预览生产构建
npm run preview
```

**Vite配置** (`vite.config.ts`):
- API代理: `/api` → `http://localhost:8000`
- 路径别名: `@` → `src/`

### 数据库管理

```bash
# 如果使用Docker启动PostgreSQL
docker run -d \
  -p 5432:5432 \
  -e POSTGRES_USER=okk_user \
  -e POSTGRES_PASSWORD=okk_pass \
  -e POSTGRES_DB=okk_quant \
  timescale/timescaledb:latest-pg15

# 连接数据库
docker exec -it okk_postgres psql -U okk_user -d okk_quant
```

## 核心业务流程

### 1. 策略启动流程

1. **前端调用**: `POST /api/v1/strategies/{id}/start`
2. **后端处理** (`api/endpoints/strategies.py`):
   - 查询策略配置和用户API配置
   - 创建 `OKXExchange` 实例（带API凭证）
   - 调用 `strategy_manager.start_strategy()`
3. **策略管理器** (`services/strategy/manager.py`):
   - 创建策略实例（根据类型）
   - 调用策略的 `start()` 方法（初始化、初始下单）
   - 创建监控任务 `asyncio.create_task(_run_strategy_loop())`
   - 将策略加入 `self.strategies` 字典
4. **监控循环** (每5秒):
   - 获取ticker → `strategy.on_tick()`
   - 查询订单状态 → `strategy.on_order_update()`
   - 每50秒持久化统计到数据库
   - 通过WebSocket广播实时统计

### 2. 回测执行流程

1. **创建回测记录**: `POST /api/v1/backtest/create` → 保存到 `backtests` 表
2. **执行回测**: `POST /api/v1/backtest/{id}/run`
3. **回测服务** (`services/backtest/backtest_service.py`):
   - 从数据库查询K线数据（`KlineService`）
   - 根据策略类型创建回测引擎：
     - `GridBacktestEngine` - 网格策略
     - `GridMarketMakingBacktest` - 网格做市
   - 调用引擎的 `run(klines, progress_callback)` 方法
   - 计算性能指标（`BacktestMetrics`）：
     - 总收益率、年化收益率、最大回撤
     - 夏普比率、胜率、盈亏比
   - 保存结果到 `backtests` 和 `backtest_trades` 表

### 3. 风控触发流程

**风控类型** (`services/risk/risk_manager.py`):
- `capital` - 资金风控（最小可用资金、最大持仓价值）
- `position` - 持仓风控（单币种上限、集中度）
- `loss` - 亏损风控（日亏损、总亏损、连续亏损）
- `drawdown` - 回撤风控（最大回撤百分比）
- `frequency` - 频率风控（时间窗口内交易次数）

**触发动作:**
- `warn` - 仅发送告警
- `limit` - 限制新订单
- `pause` - 暂停策略
- `close` - 平仓并暂停

**检查点:**
1. 策略监控循环中定期检查
2. 下单前检查（`check_before_order()`）

## WebSocket实时通信架构

### 双重WebSocket设计

1. **Socket.IO** (`websocket/manager.py`)
   - 用于前端连接和消息推送
   - 事件类型:
     - `strategy_stats:{strategy_id}` - 策略实时统计
     - `strategy_update:{strategy_id}` - 策略状态更新
     - `notification` - 系统通知（策略启停、异常等）
     - `account_update` - 账户余额/持仓更新

2. **OKX WebSocket** (`websocket/okx_websocket.py`)
   - 连接OKX私有频道（账户、订单、持仓）
   - 需要API认证（在应用启动时从数据库加载）
   - 订阅频道:
     - 账户频道: `account`
     - 持仓频道: `positions:{instType}:{instId}`
     - 订单频道: `orders:{instType}`
   - 将OKX推送转换为Socket.IO事件广播给前端

### 前端WebSocket服务

`src/services/websocket.ts`:
- 封装Socket.IO客户端连接
- 提供类型安全的事件监听器
- Zustand store管理连接状态

## AI增强功能

### DeepSeek集成

**位置:** `services/ai/`

**核心组件:**
- `llm_client.py` - DeepSeek API客户端
- `ai_analyzer.py` - 市场分析器（新闻、情绪分析）
- `llm_enhanced_analyzer.py` - LLM增强分析

**AI增强策略:** `AISwingLongStrategy`
- 继承 `SwingLongStrategy`
- 定期调用AI分析市场情绪
- 根据AI建议调整止盈止损参数
- 参数:
  - `enable_ai`: 是否启用AI
  - `ai_analysis_interval`: 分析间隔（秒）

**配置环境变量:**
```env
DEEPSEEK_API_KEY=your_deepseek_api_key
```

## 通知推送系统

### 多渠道支持

**位置:** `services/notification/`

**渠道实现:**
- `serverchan.py` - Server酱推送
- `pushplus.py` - PushPlus推送
- `wecom.py` - 企业微信机器人
- `telegram.py` - Telegram Bot

**配置文件:** `backend/notification_config.json`
```json
{
  "channels": {
    "serverchan": {
      "enabled": true,
      "sendkey": "your_key"
    },
    "telegram": {
      "enabled": true,
      "bot_token": "your_token",
      "chat_id": "your_chat_id"
    }
  }
}
```

**通知服务:** `notification_service.py`
- 在应用启动时加载配置
- 支持多渠道同时推送
- WebSocket管理器集成（前端实时通知）

## 环境变量配置

**关键环境变量** (`backend/.env`):

```env
# 应用配置
APP_NAME=OKK量化交易系统
APP_VERSION=1.0.0
DEBUG=true

# 数据库
DATABASE_URL=postgresql+psycopg://okk_user:okk_pass@localhost:5432/okk_quant

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# JWT认证
SECRET_KEY=your-secret-key-change-in-production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# Celery（异步任务）
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/1

# CORS
CORS_ORIGINS=["http://localhost:5173"]

# DeepSeek AI（可选）
DEEPSEEK_API_KEY=your_deepseek_api_key

# OKX API（可选，建议通过Web界面配置）
OKX_API_KEY=your_api_key
OKX_SECRET_KEY=your_secret_key
OKX_PASSPHRASE=your_passphrase
OKX_SIMULATED=true
OKX_PROXY=http://127.0.0.1:7897
```

## 网络配置

**重要**: OKX API在某些地区需要代理访问。

### 代理配置

在 `backend/.env` 中设置:
```env
OKX_PROXY=http://127.0.0.1:7897
```

**常见代理端口:**
- Clash: `http://127.0.0.1:7890`
- V2Ray: `http://127.0.0.1:10809`
- Shadowsocks: `http://127.0.0.1:1080`

所有OKX API请求（REST + WebSocket）都支持代理。

## 数据库表结构

### 核心表及字段

**users** - 用户表
- `id`, `username`, `hashed_password`, `is_active`

**strategies** - 策略配置
- `id`, `user_id`, `name`, `type` (grid/swing_long/ai_swing_long)
- `symbol`, `parameters` (JSON), `status` (running/stopped)
- `total_profit`, `total_trades`, `win_rate`
- `created_at`, `updated_at`

**orders** - 订单记录
- `id`, `strategy_id`, `order_id` (交易所返回), `symbol`
- `side` (buy/sell), `order_type`, `price`, `amount`
- `status` (submitted/partial_filled/filled/canceled)
- `filled_amount`, `avg_price`, `fee`, `realized_pnl`
- `created_at`, `filled_at`, `canceled_at`

**positions** - 持仓记录（可选，主要用于记录历史持仓快照）

**backtests** - 回测记录
- `id`, `user_id`, `name`, `strategy_type`, `symbol`
- `start_time`, `end_time`, `initial_capital`, `final_capital`
- `total_return`, `annualized_return`, `max_drawdown`, `sharpe_ratio`
- `total_trades`, `win_rate`, `profit_factor`
- `status` (pending/running/completed/failed), `progress`
- `equity_curve` (JSON数组)

**backtest_trades** - 回测交易记录
- `id`, `backtest_id`, `timestamp`, `side`, `price`, `amount`
- `fee`, `pnl`, `pnl_percent`

**api_configs** - API配置
- `id`, `user_id`, `name`, `api_key`, `secret_key`, `passphrase`
- `is_simulated`, `is_active`

**risk_controls** - 风控规则
- `id`, `user_id`, `strategy_id`, `level` (global/strategy)
- `risk_type`, `is_enabled`, `action_on_trigger`

**alerts** - 告警记录
- `id`, `user_id`, `strategy_id`, `alert_type`, `severity`
- `title`, `message`, `data` (JSON), `is_read`

**klines** - K线数据（TimescaleDB hypertable）
- `timestamp`, `symbol`, `interval`
- `open`, `high`, `low`, `close`, `volume`

## 策略开发指南

### 创建新策略

1. 在 `backend/app/services/strategy/` 创建新文件
2. 继承 `StrategyBase` 基类
3. 实现生命周期方法:

```python
from app.services.strategy.base import StrategyBase

class MyStrategy(StrategyBase):
    async def start(self):
        """策略启动 - 初始化、初始下单"""
        self.is_running = True
        # TODO: 初始化逻辑

    async def on_tick(self, ticker: Dict):
        """处理实时tick行情 - 每5秒调用一次"""
        # TODO: 交易逻辑
        pass

    async def on_order_update(self, order: Dict):
        """处理订单状态更新 - 订单成交/取消时调用"""
        # TODO: 订单成交后的处理
        pass

    async def stop(self, cancel_orders: bool = True):
        """策略停止 - 清理资源、撤销订单"""
        self.is_running = False
        # TODO: 清理逻辑
```

**关键属性:**
- `self.strategy_id` - 策略ID
- `self.symbol` - 交易对
- `self.exchange` - 交易所实例
- `self.is_running` - 运行状态

**交易所方法:**
- `await self.exchange.get_ticker(symbol)` - 获取ticker
- `await self.exchange.create_order(...)` - 创建订单
- `await self.exchange.cancel_order(...)` - 取消订单
- `await self.exchange.get_order(...)` - 查询订单
- `await self.exchange.get_balance()` - 获取余额
- `await self.exchange.get_positions()` - 获取持仓

### 注册新策略类型

在 `services/strategy/manager.py` 的 `create_strategy()` 方法中添加:

```python
elif strategy_type_enum == StrategyType.MY_STRATEGY:
    strategy = MyStrategy(
        strategy_id=strategy_id,
        exchange=exchange,
        symbol=symbol,
        parameters=parameters,
        user_id=user_id
    )
```

并在 `models/strategy.py` 的 `StrategyType` 枚举中添加类型。

## API端点开发

### 添加新的API端点

1. 在 `backend/app/api/endpoints/` 创建新文件 `my_module.py`:

```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db

router = APIRouter()

@router.get("/list")
async def list_items(db: Session = Depends(get_db)):
    """获取列表"""
    return {"data": []}

@router.post("/create")
async def create_item(item: ItemCreate, db: Session = Depends(get_db)):
    """创建项目"""
    return {"id": 1}
```

2. 在 `backend/app/api/__init__.py` 注册路由:

```python
from .endpoints import my_module

api_router.include_router(my_module.router, prefix="/my-module", tags=["我的模块"])
```

## 前端开发指南

### 添加新页面

1. 在 `frontend/src/features/` 创建功能模块目录
2. 创建页面组件（使用TypeScript + Ant Design）
3. 在 `App.tsx` 添加路由:

```tsx
<Route path="my-page" element={<MyPage />} />
```

4. 在 `src/services/api.ts` 添加API调用函数:

```typescript
export const myAPI = {
  list: () => request.get('/api/v1/my-module/list'),
  create: (data: ItemCreate) => request.post('/api/v1/my-module/create', data),
}
```

### 组件开发规范

- 使用函数组件 + Hooks
- 使用Ant Design组件库
- 使用TailwindCSS处理样式
- 使用 `useRequest` (ahooks) 或 `useQuery` 处理异步请求
- 使用Zustand管理全局状态
- 使用i18next处理国际化

## 安全注意事项

1. **永远不要提交** `.env` 文件或包含API密钥的文件
2. **API密钥权限**: 只授予交易、查询权限，**不要授予提现权限**
3. **生产环境** 必须修改 `SECRET_KEY`
4. **优先使用模拟盘**测试策略 (`OKX_SIMULATED=true`)
5. **风控规则**: 生产环境务必配置合理的风控规则
6. **代理安全**: 确保代理服务器可信，避免API密钥泄露

## 项目状态

- ✅ 核心架构和OKX API对接完成
- ✅ 网格策略、波段策略、AI增强策略实现
- ✅ 回测系统完成
- ✅ 风控系统完成
- ✅ WebSocket实时推送完成（Socket.IO + OKX WS）
- ✅ 多渠道通知推送完成
- ✅ 前端深色金融主题UI完成
- ⏳ Celery异步任务（代码中有引用但未完全集成）

## 调试技巧

### 后端日志

使用 `loguru` 库:
```python
from loguru import logger

logger.debug("调试信息")
logger.info("常规信息")
logger.warning("警告信息")
logger.error("错误信息")
```

### 查看OKX请求详情

在 `services/exchange/okx.py` 中已启用详细日志:
```
请求 GET https://www.okx.com/api/v5/market/ticker - params: {...}
响应: 200 - {"code": "0", ...}
```

### 前端调试

- 浏览器DevTools Network面板查看API请求
- Console查看日志
- React DevTools查看组件状态
- WebSocket连接状态查看: Zustand DevTools

## 文档参考

- **OKX API文档**: https://www.okx.com/docs-v5/zh/
- **FastAPI文档**: https://fastapi.tiangolo.com/
- **React文档**: https://react.dev/
- **Ant Design 5**: https://ant.design/
- **TradingView Lightweight Charts**: https://tradingview.github.io/lightweight-charts/
- **TanStack Query**: https://tanstack.com/query/latest
- **Zustand**: https://zustand-demo.pmnd.rs/

## 相关文档

- `README.md` - 项目完整说明
- `网络连接问题解决方案.md` - 代理配置详细指南
- `公共数据.md` / `行情数据.md` / `交易账户.md` / `撮合交易.md` - OKX API接口文档
