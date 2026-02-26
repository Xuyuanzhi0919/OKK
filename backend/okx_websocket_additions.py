"""
OKX WebSocket私有频道补充代码
这些方法需要添加到 okx_websocket.py 文件中
"""

# ==================== 需要添加的方法 ====================

# 1. 添加订阅orders频道的方法 (在subscribe_kline方法之后添加)
async def subscribe_orders(self, inst_type: str = "SPOT"):
    """
    订阅订单更新频道 (使用private连接)

    Args:
        inst_type: 产品类型 SPOT/SWAP/FUTURES/OPTION
    """
    if not self.private_authenticated:
        logger.warning("Private WebSocket not authenticated, cannot subscribe to orders")
        return

    channel = f"orders:{inst_type}"
    if channel in self.subscribed_channels:
        return

    try:
        subscribe_msg = {
            "op": "subscribe",
            "args": [{
                "channel": "orders",
                "instType": inst_type
            }]
        }
        await self.ws_private.send(json.dumps(subscribe_msg))
        self.subscribed_channels.add(channel)
        logger.info(f"Subscribed to orders channel: {inst_type}")
    except Exception as e:
        logger.error(f"Failed to subscribe orders {inst_type}: {e}")


# 2. 添加处理订单更新的方法 (在handle_kline方法之后添加)
async def handle_order(self, data: dict):
    """
    处理订单更新数据

    OKX订单数据格式:
    {
        "instType": "SPOT",
        "instId": "BTC-USDT",
        "ordId": "312269865356374016",
        "clOrdId": "",
        "tag": "",
        "px": "999",
        "sz": "3",
        "pnl": "5",
        "ordType": "limit",
        "side": "buy",
        "posSide": "long",
        "tdMode": "isolated",
        "tgtCcy": "",
        "fillSz": "0",
        "fillPx": "0",
        "tradeId": "",
        "accFillSz": "323",
        "fillTime": "1597026383085",
        "fillFee": "-0.0008",
        "fillFeeCcy": "BTC",
        "execType": "T",
        "state": "filled",
        "avgPx": "2566.31",
        "lever": "10",
        "tpTriggerPx": "",
        "tpOrdPx": "",
        "slTriggerPx": "",
        "slOrdPx": "",
        "feeCcy": "",
        "fee": "",
        "rebateCcy": "",
        "rebate": "",
        "tgtCcy": "",
        "category": "",
        "uTime": "1597026383085",
        "cTime": "1597026383085"
    }
    """
    try:
        logger.info(f"Received order update: {data.get('ordId')} - {data.get('state')}")

        # 将订单更新广播到相关策略
        # 注意:这里需要与策略管理器集成,将订单更新推送到对应的策略
        # 后续实现时需要添加回调机制或事件系统

        # 临时日志记录
        logger.debug(f"Order update details: Symbol={data.get('instId')}, Side={data.get('side')}, "
                    f"Size={data.get('sz')}, Filled={data.get('accFillSz')}, State={data.get('state')}")

    except Exception as e:
        logger.error(f"Error handling order update: {e}")


# 3. 修改handle_message方法,在处理数据推送部分添加orders处理 (在channel == 'trades'之后添加)
# 在 handle_message 方法的 if channel == 'trades': 代码块之后添加:
elif channel == 'orders':
    # 处理订单更新,data可能包含多个订单
    for order in data:
        await self.handle_order(order)


# 4. 添加listen_private方法 (在listen_business方法之后添加)
async def listen_private(self):
    """监听private WebSocket消息（订单更新等）"""
    while self.running:
        try:
            if not self.ws_private:
                logger.warning("Private WebSocket not connected")
                await asyncio.sleep(self.reconnect_delay)
                continue

            message = await self.ws_private.recv()
            data = json.loads(message)

            # 处理登录响应
            if data.get('event') == 'login':
                if data.get('code') == '0':
                    logger.info("Private WebSocket login success")
                else:
                    logger.error(f"Private WebSocket login failed: {data}")
                continue

            # 处理订阅确认
            if data.get('event') == 'subscribe':
                logger.info(f"Private channel subscription confirmed: {data}")
                continue

            # 处理错误
            if data.get('event') == 'error':
                logger.error(f"Private WebSocket error: {data}")
                continue

            # 处理数据推送
            await self.handle_message(data)

        except websockets.exceptions.ConnectionClosed:
            logger.warning("Private WebSocket connection closed, reconnecting...")
            await self.reconnect()
        except Exception as e:
            logger.error(f"Error in private listen loop: {e}")
            await asyncio.sleep(1)


# 5. 修改start方法,添加listen_private任务 (在已有的两个create_task之后添加)
# 在 start 方法中的 asyncio.create_task(self.listen_business()) 之后添加:
if self.ws_private:
    asyncio.create_task(self.listen_private())
    # 订阅所有SPOT订单更新
    await self.subscribe_orders("SPOT")
