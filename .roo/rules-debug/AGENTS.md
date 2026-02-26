# Debug Mode Rules

## 后端调试

- 日志使用 loguru：`from loguru import logger`
- OKX请求详情在 [`okx.py`](backend/app/services/exchange/okx.py) 中已启用详细日志

## 常见问题

- **OKX连接失败**：检查代理配置 `OKX_PROXY=http://127.0.0.1:7897`
- **策略不启动**：检查API配置是否正确，查看 `api_configs` 表
- **WebSocket断开**：检查OKX WebSocket认证（需要有效API配置）

## 前端调试

- API代理：`/api` → `http://localhost:8000`
- WebSocket状态：Zustand store [`useWebSocketStore.ts`](frontend/src/stores/useWebSocketStore.ts)

## 数据库调试

```bash
docker exec -it okk_postgres psql -U okk_user -d okk_quant
```
