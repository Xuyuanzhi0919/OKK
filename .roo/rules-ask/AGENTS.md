# Ask Mode Rules

## 文档位置

- 完整项目文档：[`CLAUDE.md`](CLAUDE.md)
- 回测系统：[`backend/docs/BACKTEST_QUICKSTART.md`](backend/docs/BACKTEST_QUICKSTART.md)
- 风控系统：[`backend/docs/RISK_CONTROL_QUICKSTART.md`](backend/docs/RISK_CONTROL_QUICKSTART.md)
- WebSocket告警：[`backend/docs/WEBSOCKET_RISK_ALERTS.md`](backend/docs/WEBSOCKET_RISK_ALERTS.md)

## 架构要点

- **双重WebSocket**：Socket.IO（前端）+ OKX WebSocket（交易所私有频道）
- **策略监控循环**：每5秒执行一次（tick处理 + 订单状态查询）
- **通知配置**：[`notification_config.json`](backend/notification_config.json) 而非环境变量

## API参考

- OKX API文档：https://www.okx.com/docs-v5/zh/
- 内部API端点前缀：`/api/v1`
