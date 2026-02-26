"""
资金划转脚本 - 从统一账户划转到交易账户
"""
import asyncio
from app.services.exchange.okx import OKXExchange
from app.core.config import settings

async def transfer():
    exchange = OKXExchange(
        api_key=settings.OKX_API_KEY,
        secret_key=settings.OKX_SECRET_KEY,
        passphrase=settings.OKX_PASSPHRASE,
        simulated=settings.OKX_SIMULATED,
        proxy=settings.OKX_PROXY
    )

    print("=== 资金划转 ===")
    print("从: 统一交易账户 (账户类型 18)")
    print("到: 交易账户 (账户类型 6)")
    print("金额: 5000 USDT")

    try:
        # OKX账户类型
        # 18: 统一账户
        # 6: 交易账户
        result = await exchange._request(
            method="POST",
            endpoint="/api/v5/asset/transfer",
            data={
                "ccy": "USDT",
                "amt": "5000",
                "from": "18",  # 统一账户
                "to": "6",     # 交易账户
                "type": "0"    # 账户内划转
            },
            auth_required=True
        )

        print(f"\n划转结果: {result}")

        if result.get("code") == "0":
            print("\nSUCCESS: Transfer completed!")
            print("You can now restart the strategy")
        else:
            print(f"\nFAILED: {result.get('msg')}")

    except Exception as e:
        print(f"\nERROR: {e}")

if __name__ == "__main__":
    asyncio.run(transfer())
