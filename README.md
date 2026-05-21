# OKK量化交易系统

一个基于OKX交易所的量化交易系统，支持多种交易策略、回测、风控等功能。

## 技术栈

### 后端
- **框架**: FastAPI 0.110+
- **数据库**: PostgreSQL 15 + TimescaleDB (时序数据)
- **缓存**: Redis 7+
- **异步任务**: Celery
- **语言**: Python 3.11+

### 前端
- **框架**: React 18 + TypeScript
- **构建工具**: Vite 5
- **UI库**: Ant Design 5
- **样式**: TailwindCSS
- **状态管理**: Zustand
- **数据请求**: TanStack Query
- **图表**: TradingView Lightweight Charts + ECharts

## 项目结构

```
OKK/
├── backend/              # Python后端
│   ├── app/
│   │   ├── api/          # API路由
│   │   ├── core/         # 核心配置
│   │   ├── models/       # 数据模型
│   │   ├── services/     # 业务逻辑
│   │   │   ├── exchange/ # 交易所接口
│   │   │   ├── strategy/ # 策略引擎
│   │   │   ├── risk/     # 风控
│   │   │   └── backtest/ # 回测
│   │   └── main.py       # 主应用
│   ├── requirements.txt  # Python依赖
│   └── Dockerfile
│
├── frontend/             # React前端
│   ├── src/
│   │   ├── components/   # 通用组件
│   │   ├── features/     # 功能模块
│   │   ├── services/     # API调用
│   │   ├── stores/       # 状态管理
│   │   └── types/        # TypeScript类型
│   ├── package.json
│   └── Dockerfile
│
└── docker-compose.yml    # Docker编排
```

## 功能特性

### 已完成
- ✅ 项目基础架构搭建
- ✅ 前后端框架配置
- ✅ 数据库表设计
- ✅ API接口框架
- ✅ 交易所抽象层设计
- ✅ 策略引擎基础框架
- ✅ 前端UI界面（深色金融风格）
- ✅ Docker开发环境

### ✅ 已实现核心功能
- ✅ **OKX API完整对接** (16个接口)
  - ✅ 公共数据: ticker、K线、订单簿
  - ✅ 账户管理: 余额、持仓查询
  - ✅ 交易功能: 下单、撤单、查询订单
- ✅ **前端组件**
  - ✅ 实时行情展示 (MarketTicker)
  - ✅ 专业交易面板 (TradingPanel)
  - ✅ 完整API服务层
- ✅ **认证系统**
  - ✅ HMAC SHA256签名
  - ✅ 模拟盘/实盘切换
- ✅ **测试和文档**
  - ✅ API测试脚本
  - ✅ 完整API文档

### ⏳ 开发中
- ⏳ WebSocket实时推送
- ⏳ K线图集成 (TradingView)
- ⏳ 策略引擎完善
- ⏳ 回测系统
- ⏳ 风控模块

## 快速开始

### 方式一：使用Docker（推荐）

1. **克隆项目**
```bash
git clone <repository-url>
cd OKK
```

2. **配置环境变量**
```bash
# 复制后端环境变量模板
cp backend/.env.example backend/.env

# 编辑.env文件，填写必要配置
# 注意：OKX API配置需要等待API文档后填写
```

3. **启动服务**
```bash
docker-compose up -d
```

4. **访问应用**
- 前端：http://localhost:5173
- 后端API：http://localhost:8000
- API文档：http://localhost:8000/docs

5. **查看日志**
```bash
docker-compose logs -f backend
docker-compose logs -f frontend
```

### 方式二：本地开发

#### 后端

1. **安装Python依赖**
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

2. **启动PostgreSQL和Redis**
```bash
# 使用Docker启动数据库
docker run -d -p 5432:5432 -e POSTGRES_USER=okk_user -e POSTGRES_PASSWORD=okk_pass -e POSTGRES_DB=okk_quant timescale/timescaledb:latest-pg15
docker run -d -p 6379:6379 redis:7-alpine
```

3. **初始化数据库**
```bash
psql -h localhost -U okk_user -d okk_quant -f init_db.sql
```

4. **配置环境变量**
```bash
cp .env.example .env
# 编辑.env文件
```

5. **启动后端**
```bash
python -m app.main
# 或使用uvicorn
uvicorn app.main:socket_app --reload
```

#### 前端

1. **安装依赖**
```bash
cd frontend
npm install
```

2. **启动开发服务器**
```bash
npm run dev
```

3. **访问应用**
```
http://localhost:5173
```

## 配置OKX API

> ⚠️ **重要提示**：OKX API相关功能需要等待您提供OKX API官方文档后实现。

当您获取到OKX API文档后，需要：

1. 在OKX官网申请API密钥
2. 将API密钥配置到 `backend/.env` 文件：
```env
OKX_API_KEY=your_api_key
OKX_SECRET_KEY=your_secret_key
OKX_PASSPHRASE=your_passphrase
OKX_BASE_URL=待填写
OKX_WS_URL=待填写
```

3. 或在前端设置页面配置（推荐）

## 数据库管理

### 查看数据库
```bash
docker exec -it okk_postgres psql -U okk_user -d okk_quant
```

### 常用SQL
```sql
-- 查看所有表
\dt

-- 查看用户
SELECT * FROM users;

-- 查看策略
SELECT * FROM strategies;
```

## API文档

启动后端后访问：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 开发指南

### 添加新策略

1. 在 `backend/app/services/strategy/` 创建新策略文件
2. 继承 `StrategyBase` 基类
3. 实现必要的方法：`on_tick`, `on_kline`, `start`, `stop`

示例：参考 `grid_strategy.py`

### 添加新API端点

1. 在 `backend/app/api/endpoints/` 创建新端点文件
2. 在 `backend/app/api/__init__.py` 注册路由

### 添加新页面

1. 在 `frontend/src/features/` 创建新功能模块
2. 在 `frontend/src/App.tsx` 添加路由

## 安全注意事项

1. ⚠️ **不要将API密钥提交到Git**
2. ⚠️ **使用环境变量存储敏感信息**
3. ⚠️ **API密钥只授予必要的权限（交易、查询），不要授予提现权限**
4. ⚠️ **定期更换API密钥**
5. ⚠️ **在生产环境修改默认的SECRET_KEY**

## 常见问题

### 1. 端口被占用
```bash
# 查看端口占用
netstat -ano | findstr :5432
netstat -ano | findstr :6379
netstat -ano | findstr :8000
netstat -ano | findstr :5173

# 修改docker-compose.yml中的端口映射
```

### 2. Docker容器无法启动
```bash
# 查看日志
docker-compose logs

# 重新构建
docker-compose up --build
```

### 3. 数据库连接失败
- 检查PostgreSQL是否启动
- 检查环境变量配置是否正确
- 检查网络连接

## 下一步计划

- [ ] 提供OKX API文档，实现交易所接口
- [ ] 实现WebSocket实时行情推送
- [ ] 完善策略回测功能
- [ ] 集成TradingView K线图
- [ ] 实现风控模块
- [ ] 添加用户认证功能
- [ ] 添加策略性能分析
- [ ] 部署到生产环境

## 贡献

欢迎提交Issue和Pull Request！

## 许可证

MIT License

---

**开发状态**: 🚧 开发中

**最后更新**: 2025-10-24
