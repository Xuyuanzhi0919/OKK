"""
重启策略18并监控日志
"""
import asyncio
import httpx

async def restart_strategy():
    base_url = "http://localhost:8000/api/v1"
    strategy_id = 18

    async with httpx.AsyncClient(timeout=30.0) as client:
        # 1. 停止策略
        print(f"停止策略 {strategy_id}...")
        try:
            response = await client.post(f"{base_url}/strategies/{strategy_id}/stop")
            print(f"停止结果: {response.json()}")
        except Exception as e:
            print(f"停止失败(可能已停止): {e}")

        # 等待2秒
        await asyncio.sleep(2)

        # 2. 启动策略
        print(f"\n启动策略 {strategy_id}...")
        response = await client.post(f"{base_url}/strategies/{strategy_id}/start")
        print(f"启动结果: {response.json()}")

        # 等待10秒让策略运行
        print("\n等待10秒,让策略尝试开仓...")
        await asyncio.sleep(10)

        # 3. 检查订单
        print(f"\n检查策略 {strategy_id} 的订单...")
        response = await client.get(f"{base_url}/strategies/{strategy_id}/orders")
        orders_data = response.json()

        if isinstance(orders_data, dict) and 'data' in orders_data:
            orders = orders_data['data']
        else:
            orders = orders_data

        print(f"订单数量: {len(orders) if isinstance(orders, list) else 0}")

        if orders and len(orders) > 0:
            print("\n最新订单:")
            for order in orders[:3]:
                print(f"  - {order.get('side')} {order.get('amount')} @ {order.get('price')} - {order.get('status')}")
        else:
            print("  无订单")

        # 4. 检查持仓
        print(f"\n检查策略 {strategy_id} 的持仓...")
        response = await client.get(f"{base_url}/strategies/{strategy_id}/positions")
        positions = response.json()

        if positions and len(positions) > 0:
            print(f"持仓数量: {len(positions)}")
            for pos in positions:
                print(f"  - {pos.get('symbol')}: {pos.get('amount')} @ {pos.get('entry_price')}")
        else:
            print("  无持仓")

if __name__ == "__main__":
    asyncio.run(restart_strategy())
