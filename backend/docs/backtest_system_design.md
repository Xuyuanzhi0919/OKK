# 回测系统架构设计

## 1. 系统概述

回测系统是量化交易平台的核心组件，用于在历史数据上验证策略的有效性，优化参数配置，评估风险收益特征。

### 核心目标
- 提供准确的历史数据回放
- 模拟真实的交易环境（滑点、手续费、订单延迟）
- 计算全面的性能指标
- 支持多策略、多币种回测
- 生成详细的回测报告

## 2. 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                    回测系统 (Backtest System)              │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐   │
│  │ 数据层      │  │ 引擎层      │  │ 分析层       │   │
│  │ (Data)      │  │ (Engine)    │  │ (Analytics)  │   │
│  └──────┬──────┘  └──────┬──────┘  └──────┬───────┘   │
│         │                 │                 │           │
│  ┌──────▼──────────────────▼─────────────────▼──────┐  │
│  │            存储层 (TimescaleDB + Redis)          │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### 2.1 数据层 (Data Layer)

**职责**：管理历史K线数据的下载、存储和查询

**核心模块**：
- `HistoricalDataDownloader` - OKX历史数据下载器
- `KlineDataManager` - K线数据管理器
- `DataCache` - 数据缓存（Redis）

**数据表设计**（TimescaleDB）：
```sql
CREATE TABLE klines (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,         -- 交易对
    interval VARCHAR(10) NOT NULL,       -- 时间周期 (1m, 5m, 15m, 1h, 4h, 1d)
    open_time TIMESTAMP NOT NULL,        -- 开盘时间
    open DECIMAL(20, 8) NOT NULL,        -- 开盘价
    high DECIMAL(20, 8) NOT NULL,        -- 最高价
    low DECIMAL(20, 8) NOT NULL,         -- 最低价
    close DECIMAL(20, 8) NOT NULL,       -- 收盘价
    volume DECIMAL(20, 8) NOT NULL,      -- 成交量
    quote_volume DECIMAL(20, 8),         -- 成交额
    trades_count INTEGER,                 -- 成交笔数
    created_at TIMESTAMP DEFAULT NOW()
);

-- 创建时序表（TimescaleDB扩展）
SELECT create_hypertable('klines', 'open_time');

-- 创建索引
CREATE INDEX idx_klines_symbol_interval_time
    ON klines (symbol, interval, open_time DESC);
```

### 2.2 引擎层 (Engine Layer)

**职责**：执行回测逻辑，模拟交易环境

**核心模块**：

#### 2.2.1 回测引擎 (BacktestEngine)
```python
class BacktestEngine:
    """
    事件驱动的回测引擎

    工作流程：
    1. 加载历史数据
    2. 逐K线回放，生成事件
    3. 策略处理事件，生成订单
    4. 订单模拟成交
    5. 更新账户和仓位
    6. 记录交易记录
    """

    def __init__(self, strategy, start_date, end_date, initial_capital):
        self.strategy = strategy          # 策略实例
        self.start_date = start_date      # 回测开始时间
        self.end_date = end_date          # 回测结束时间
        self.initial_capital = initial_capital  # 初始资金

        # 核心组件
        self.data_handler = DataHandler()       # 数据处理器
        self.portfolio = Portfolio()            # 投资组合管理
        self.execution = ExecutionHandler()     # 执行处理器
        self.event_queue = Queue()              # 事件队列

    async def run(self):
        """执行回测"""
        # 1. 加载历史数据
        # 2. 事件循环
        # 3. 生成回测报告
```

#### 2.2.2 数据处理器 (DataHandler)
```python
class DataHandler:
    """历史数据处理器，负责数据回放"""

    def get_latest_bars(self, symbol, N=1):
        """获取最新N根K线"""

    def update_bars(self):
        """更新K线数据，推进时间"""
```

#### 2.2.3 投资组合管理 (Portfolio)
```python
class Portfolio:
    """
    管理账户资金和持仓

    功能：
    - 跟踪账户余额
    - 管理持仓信息
    - 计算权益曲线
    - 计算收益率
    """

    def __init__(self, initial_capital):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.positions = {}  # 持仓 {symbol: quantity}
        self.equity_curve = []  # 权益曲线
```

#### 2.2.4 执行处理器 (ExecutionHandler)
```python
class ExecutionHandler:
    """
    订单执行模拟器

    功能：
    - 模拟订单成交
    - 考虑滑点、手续费
    - 模拟订单延迟
    - 处理流动性限制
    """

    def execute_order(self, order, current_price):
        """执行订单"""
        # 计算成交价格（考虑滑点）
        # 计算手续费
        # 更新持仓
```

### 2.3 分析层 (Analytics Layer)

**职责**：计算性能指标，生成回测报告

**核心指标**：

#### 2.3.1 收益指标
- 总收益率 (Total Return)
- 年化收益率 (Annual Return)
- 累计收益率 (Cumulative Return)
- 日收益率 (Daily Return)

#### 2.3.2 风险指标
- 最大回撤 (Max Drawdown)
- 波动率 (Volatility)
- 下行波动率 (Downside Deviation)
- VaR (Value at Risk)

#### 2.3.3 风险调整收益指标
- 夏普比率 (Sharpe Ratio) = (年化收益率 - 无风险利率) / 年化波动率
- 索提诺比率 (Sortino Ratio) = (年化收益率 - 无风险利率) / 下行波动率
- 卡玛比率 (Calmar Ratio) = 年化收益率 / 最大回撤

#### 2.3.4 交易指标
- 胜率 (Win Rate)
- 盈亏比 (Profit/Loss Ratio)
- 平均盈利/亏损 (Average Win/Loss)
- 最大连续盈利/亏损次数
- 总交易次数

```python
class PerformanceMetrics:
    """性能指标计算器"""

    def calculate_sharpe_ratio(self, returns, risk_free_rate=0.02):
        """计算夏普比率"""

    def calculate_max_drawdown(self, equity_curve):
        """计算最大回撤"""

    def calculate_win_rate(self, trades):
        """计算胜率"""
```

## 3. 数据流程

```
历史数据 → DataHandler → 事件队列 → 策略 → 订单 → ExecutionHandler
                                                         ↓
                                                   Portfolio
                                                         ↓
                                                   权益曲线
                                                         ↓
                                              PerformanceMetrics
                                                         ↓
                                                   回测报告
```

## 4. 回测流程

```python
# 伪代码示例
async def backtest_example():
    # 1. 初始化
    engine = BacktestEngine(
        strategy=GridStrategy(params),
        start_date="2024-01-01",
        end_date="2024-10-27",
        initial_capital=10000
    )

    # 2. 运行回测
    result = await engine.run()

    # 3. 分析结果
    metrics = PerformanceMetrics(result)
    print(f"总收益率: {metrics.total_return}")
    print(f"夏普比率: {metrics.sharpe_ratio}")
    print(f"最大回撤: {metrics.max_drawdown}")

    # 4. 生成报告
    report = generate_report(result, metrics)
    save_report(report)
```

## 5. API接口设计

### 5.1 启动回测
```
POST /api/v1/backtest/start
{
    "strategy_type": "grid",
    "strategy_params": {...},
    "symbol": "BTC-USDT",
    "interval": "1h",
    "start_date": "2024-01-01",
    "end_date": "2024-10-27",
    "initial_capital": 10000
}
```

### 5.2 查询回测结果
```
GET /api/v1/backtest/{backtest_id}
```

### 5.3 下载历史数据
```
POST /api/v1/backtest/download-data
{
    "symbol": "BTC-USDT",
    "interval": "1h",
    "start_date": "2024-01-01",
    "end_date": "2024-10-27"
}
```

## 6. 实现优先级

### 阶段1：基础框架（本周）
- [x] 设计架构
- [ ] 创建数据库表结构
- [ ] 实现历史数据下载API
- [ ] 实现基础回测引擎
- [ ] 实现简单的性能指标计算

### 阶段2：功能完善（下周）
- [ ] 添加滑点和手续费模拟
- [ ] 实现完整的性能指标
- [ ] 添加回测报告生成
- [ ] 前端回测界面

### 阶段3：高级功能（后续）
- [ ] 参数优化（网格搜索、遗传算法）
- [ ] 多策略组合回测
- [ ] 风险管理模块
- [ ] 实时回测对比

## 7. 技术选型

- **数据库**: TimescaleDB（时序数据优化）
- **缓存**: Redis（数据缓存）
- **计算**: Pandas + NumPy（数据分析）
- **可视化**: Plotly（前端图表）
- **异步**: asyncio（异步IO）

## 8. 注意事项

1. **数据质量**：确保历史数据的完整性和准确性
2. **性能优化**：大量数据回测需要优化内存使用
3. **前瞻偏差**：避免使用未来数据
4. **过度拟合**：警惕策略对历史数据的过度优化
5. **滑点影响**：真实交易中需考虑滑点和冲击成本
