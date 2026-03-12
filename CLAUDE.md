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
│   ├── ai_configs.py   # AI配置管理
│   ├── ai_analysis.py  # AI市场分析接口
│   ├── alerts.py       # 告警历史
│   └── risk_control.py # 风控规则管理
├── core/
│   ├── config.py       # 环境变量配置（pydantic-settings）
│   ├── database.py     # SQLAlchemy session工厂
│   └── process_lock.py # 进程锁机制（防止重复启动）
├── models/             # SQLAlchemy ORM模型（含ai_config.py）
├── services/
│   ├── exchange/       # 交易所抽象层（base.py + okx.py）
│   ├── strategy/       # 策略引擎（基类 + 具体策略）
│   ├── backtest/       # 回测引擎和指标计算
│   ├── risk/           # 风控管理器
│   ├── ai/             # DeepSeek AI增强分析
│   ├── notification/   # 多渠道推送通知
│   │   └── channels/   # 渠道实现子目录
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
   - 已实现策略（可用）：
     - `GridStrategy` - 网格策略 (`grid_strategy.py`)
     - `DualSideStrategy` - 双向持仓策略，EMA双均线金叉/死叉信号，支持多空切换，含移动止损 (`dual_side_strategy.py`)
     - `TrendFollowStrategy` - 趋势跟踪策略 (`trend_follow.py`)
     - `OrderBookImbalanceStrategy` - 订单簿不平衡高频策略 (`order_book_imbalance.py`)
   - 已移除策略（manager.py 中 raise NotImplementedError）：`SwingLong`、`SwingShort`、`AISwingLong`

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
├── /market-analysis     # AI市场分析
├── /api-config          # OKX API配置管理
└── /settings            # 系统设置（含AI配置管理）
```

**状态管理:**
- Zustand stores: `src/stores/useWebSocketStore.ts`（WebSocket状态）、`src/stores/useUserStore.ts`（用户状态）
- TanStack Query: API数据缓存和同步

**核心功能模块:**
- `features/dashboard/` - 仪表盘
- `features/strategy/` - 策略管理（列表、详情、性能模态框）
- `features/trading/` - 交易相关（K线图、交易面板、订单簿）
- `features/backtest/` - 回测系统（含K线管理）
- `features/ai/` - AI市场分析页面
- `features/settings/` - 设置（OKX API配置 + AI配置管理）

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
- 路径别名: `@/` → `src/`
- 开发服务器端口: 5173

### 数据库管理

```bash
# 使用Docker启动TimescaleDB
docker run -d \
  --name okk_postgres \
  -p 5432:5432 \
  -e POSTGRES_USER=okk_user \
  -e POSTGRES_PASSWORD=okk_pass \
  -e POSTGRES_DB=okk_quant \
  timescale/timescaledb:latest-pg15

# 初始化所有数据库表（使用完整初始化脚本）
cd backend
psql postgresql://okk_user:okk_pass@localhost:5432/okk_quant -f init_complete.sql
# 或使用Python脚本
python init_db.py

# 连接数据库
docker exec -it okk_postgres psql -U okk_user -d okk_quant

# 运行Alembic迁移
alembic upgrade head

# 手动运行SQL迁移（按顺序执行，当前最新为009）
psql ... -f migrations/001_create_alerts_table.sql
# ... 006_add_ioc_post_only_order_types.sql
# ... 007_add_strategy_position_state.sql
# ... 008_add_position_side.sql
psql ... -f migrations/009_add_dual_side_strategy_type.sql
```

### Docker生产部署

```bash
# 启动生产环境（所有服务）
docker-compose -f docker-compose.prod.yml up -d

# 中国区域（含代理配置）
docker-compose -f docker-compose.china.yml up -d

# 一键部署
bash deploy.sh
```

### 维护脚本

```bash
cd backend

# 同步订单状态（与交易所对账）
python sync_order_status.py

# 取消所有待处理订单
python cancel_pending_orders.py

# 紧急平仓（生产异常时使用）
python emergency_stop_positions.py

# 激活API配置
python activate_api_config.py
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
     - `GridBacktestEngine` - 网格策略 (`grid_backtest.py`)
     - `DualSideBacktestEngine` - 双向持仓策略，支持多空双向，含止损止盈和移动止损统计 (`dual_side_backtest.py`)
     - `MACrossBacktest` - 均线交叉策略 (`ma_cross_backtest.py`)
   - 调用引擎的 `run(klines, progress_callback)` 方法
   - 计算性能指标（`BacktestMetrics`）：总收益率、年化收益率、最大回撤、夏普比率、胜率、盈亏比
   - 保存结果到 `backtests` 和 `backtest_trades` 表

### 3. 风控触发流程

**风控类型** (`services/risk/risk_manager.py`):
- `capital` - 资金风控（最小可用资金、最大持仓价值）
- `position` - 持仓风控（单币种上限、集中度）
- `loss` - 亏损风控（日亏损、总亏损、连续亏损）
- `drawdown` - 回撤风控（最大回撤百分比）
- `frequency` - 频率风控（时间窗口内交易次数）

**触发动作:** `warn`（告警）→ `limit`（限制下单）→ `pause`（暂停策略）→ `close`（平仓并暂停）

**检查点:** 策略监控循环中定期检查 + 下单前检查（`check_before_order()`）

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
   - 订阅频道: `account`、`positions:{instType}:{instId}`、`orders:{instType}`
   - 将OKX推送转换为Socket.IO事件广播给前端

## AI增强功能

### DeepSeek集成

**位置:** `services/ai/`

**核心组件:**
- `llm_client.py` - DeepSeek API客户端
- `ai_analyzer.py` - 市场分析器（新闻、情绪分析）
- `llm_enhanced_analyzer.py` - LLM增强分析
- `multi_factor_analyzer.py` - 多因子分析器
- `news_fetcher.py` / `sentiment_analysis.py` / `technical_analysis.py` - 辅助分析模块

**AI增强策略:** `AISwingLongStrategy` 继承 `SwingLongStrategy`，定期调用AI分析市场情绪，根据建议调整止盈止损参数。

**AI配置管理:** AI的API密钥和模型参数通过 `ai_configs` 数据库表持久化（`api/endpoints/ai_configs.py`），支持通过Web界面配置，无需重启服务。

## 通知推送系统

### 多渠道支持

**位置:** `services/notification/channels/`（渠道实现在子目录）

**渠道实现:** `serverchan.py`、`pushplus.py`、`wecom.py`、`telegram.py`

**配置文件:** `backend/notification_config.json`（参考 `notification_config.example.json`）
```json
{
  "channels": {
    "serverchan": { "enabled": true, "sendkey": "your_key" },
    "telegram": { "enabled": true, "bot_token": "your_token", "chat_id": "your_chat_id" }
  }
}
```

## 环境变量配置

**关键环境变量** (`backend/.env`，参考 `backend/.env.example`):

```env
DATABASE_URL=postgresql+psycopg://okk_user:okk_pass@localhost:5432/okk_quant
REDIS_HOST=localhost
REDIS_PORT=6379
SECRET_KEY=your-secret-key-change-in-production
CORS_ORIGINS=["http://localhost:5173"]
DEEPSEEK_API_KEY=your_deepseek_api_key  # 可选，也可通过Web界面配置
OKX_PROXY=http://127.0.0.1:7897         # OKX API在某些地区需要代理
```

**常见代理端口:** Clash `7890`、V2Ray `10809`、Shadowsocks `1080`

## 数据库表结构

**核心表:**

| 表名 | 说明 |
|------|------|
| `users` | 用户表（id, username, hashed_password） |
| `strategies` | 策略配置（type: grid/dual_side/trend/order_book_imbalance，含 position_side/position_entry_price 等持仓状态字段） |
| `orders` | 订单记录（含filled_amount, avg_price, fee, realized_pnl） |
| `backtests` | 回测记录（含equity_curve JSON数组） |
| `backtest_trades` | 回测交易记录 |
| `api_configs` | OKX API配置（is_simulated, is_active） |
| `ai_configs` | AI模型配置（API密钥、模型参数） |
| `risk_controls` | 风控规则（level: global/strategy） |
| `alerts` | 告警记录（severity, is_read） |
| `klines` | K线数据（TimescaleDB hypertable，按timestamp分区） |

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

    async def on_tick(self, ticker: Dict):
        """处理实时tick行情 - 每5秒调用一次"""
        pass

    async def on_order_update(self, order: Dict):
        """处理订单状态更新"""
        pass

    async def stop(self, cancel_orders: bool = True):
        """策略停止 - 清理资源、撤销订单"""
        self.is_running = False
```

**关键属性:** `self.strategy_id`、`self.symbol`、`self.exchange`、`self.is_running`

**交易所方法:** `get_ticker()`、`create_order()`、`cancel_order()`、`get_order()`、`get_balance()`、`get_positions()`

### 注册新策略类型

在 `services/strategy/manager.py` 的 `create_strategy()` 方法中添加对应分支，并在 `models/strategy.py` 的 `StrategyType` 枚举中添加类型。

**持仓状态持久化（DualSide/Trend类策略必须实现）:** 策略需将持仓状态写入 `strategies` 表的专用字段（`position_side`、`position_entry_price`、`position_qty`、`position_open_time`、`position_highest_price`、`position_trail_stop_px`），并在 `start()` 中从数据库恢复，支持重启后继续运行。

## API端点开发

1. 在 `backend/app/api/endpoints/` 创建新文件
2. 在 `backend/app/api/__init__.py` 注册路由（prefix `/api/v1`）

## 前端开发指南

### 添加新页面

1. 在 `frontend/src/features/` 创建功能模块目录
2. 在 `App.tsx` 添加路由，在 `src/services/api.ts` 添加API调用函数

### 组件开发规范

- 函数组件 + Hooks，Ant Design组件库，TailwindCSS处理样式
- `useRequest` (ahooks) 或 `useQuery` 处理异步请求
- Zustand管理全局状态，i18next处理国际化

## 项目状态

- ✅ 核心架构和OKX API对接完成
- ✅ 网格、双向持仓、趋势跟踪、订单簿不平衡四种策略实现（swing_long/swing_short/ai_swing_long 已废弃移除）
- ✅ 回测系统完成（Grid、DualSide、MACross 三种引擎）
- ✅ 风控系统完成（5种类型 + 4级触发动作）
- ✅ WebSocket实时推送完成（Socket.IO + OKX WS）
- ✅ 多渠道通知推送完成
- ✅ AI市场分析功能完成（DeepSeek集成）
- ✅ 前端深色金融主题UI完成
- ⏳ Celery异步任务（代码中有引用但未完全集成）

## 调试技巧

**后端日志** (loguru):
```python
from loguru import logger
logger.debug("调试信息")
logger.info("常规信息")
logger.error("错误信息")
```

OKX请求详情在 `services/exchange/okx.py` 中已启用完整日志。

**前端:** 浏览器DevTools Network面板查看API请求，React DevTools查看组件状态。

## 文档参考

- `backend/API接口文档.md` - API完整接口文档
- `backend/代理连接故障排查.md` - 代理配置故障排查
- `backend/docs/BACKTEST_QUICKSTART.md` - 回测快速开始
- `backend/docs/RISK_CONTROL_QUICKSTART.md` - 风控快速开始
- `backend/docs/WEBSOCKET_RISK_ALERTS.md` - WebSocket和风控告警
- `1panel-deploy-guide.md` - 1Panel生产部署指南
- **OKX API文档**: https://www.okx.com/docs-v5/zh/
