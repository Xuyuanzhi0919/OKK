"""
自动给波段策略添加推送通知
快速集成脚本
"""
import sys
import io
import re

# 修复Windows控制台Unicode编码问题
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

strategy_file = 'F:\\Cluade Code Project\\OKK\\backend\\app\\services\\strategy\\swing_long_strategy.py'

print("=" * 80)
print("给波段策略添加推送通知")
print("=" * 80)

# 读取文件
with open(strategy_file, 'r', encoding='utf-8') as f:
    content = f.read()

# 检查是否已经导入notification_service
if 'from app.services.notification import notification_service' in content:
    print("\n✅ notification_service 已导入")
else:
    print("\n❌ notification_service 未导入,请手动添加import")
    print("   添加位置: 文件顶部import区域")
    print("   添加内容: from app.services.notification import notification_service")

# 检查strategy_name属性
if 'self.strategy_name' not in content:
    print("\n⚠️ 策略缺少 strategy_name 属性")
    print("   需要在 __init__ 中添加:")
    print("   self.strategy_name = parameters.get('name', f'波段策略{strategy_id}')")
else:
    print("\n✅ strategy_name 属性存在")

print("\n" + "=" * 80)
print("需要添加推送的位置:")
print("=" * 80)

# 查找开仓成功位置
open_pattern = r'logger\.info\(f"✅ 开仓订单提交成功:'
if re.search(open_pattern, content):
    print("\n1. ✅ 找到开仓成功位置")
    print("   在 'logger.info(f\"✅ 开仓订单提交成功...' 后添加:")
    print("""
    # 发送开仓通知
    try:
        await notification_service.notify_position_opened(
            user_id=self.user_id,
            strategy_id=self.strategy_id,
            strategy_name=getattr(self, 'strategy_name', f'波段策略{self.strategy_id}'),
            symbol=self.symbol,
            side="buy",
            entry_price=float(entry_price),
            amount=float(contract_amount),
            leverage=self.leverage,
            margin=float(margin)
        )
    except Exception as e:
        logger.error(f"发送开仓通知失败: {e}")
    """)
else:
    print("\n1. ❌ 未找到开仓成功位置")

# 查找平仓成功位置
close_pattern = r'logger\.info\(f"✅ 平仓订单提交成功:'
if re.search(close_pattern, content):
    print("\n2. ✅ 找到平仓成功位置")
    print("   在 'logger.info(f\"✅ 平仓订单提交成功...' 和 'self.position = None' 之间添加:")
    print("""
    # 计算盈亏
    entry_price = self.position["entry_price"]
    coin_amount = self.position.get("amount", contract_amount * self.ct_val)
    pnl = (current_price - entry_price) * coin_amount * self.leverage
    pnl_pct = ((current_price - entry_price) / entry_price) * 100 * self.leverage

    # 发送平仓通知
    try:
        await notification_service.notify_position_closed(
            user_id=self.user_id,
            strategy_id=self.strategy_id,
            strategy_name=getattr(self, 'strategy_name', f'波段策略{self.strategy_id}'),
            symbol=self.symbol,
            side="buy",
            entry_price=float(entry_price),
            exit_price=float(current_price),
            amount=float(coin_amount),
            pnl=float(pnl),
            pnl_pct=float(pnl_pct),
            reason=reason
        )
    except Exception as e:
        logger.error(f"发送平仓通知失败: {e}")
    """)
else:
    print("\n2. ❌ 未找到平仓成功位置")

# 查找风险预警位置
risk_pattern = r'logger\.error\(f"❌ 达到最大止损次数'
if re.search(risk_pattern, content):
    print("\n3. ✅ 找到风险预警位置")
    print("   在 'logger.error(f\"❌ 达到最大止损次数...' 后添加:")
    print("""
    # 发送风险预警通知
    try:
        await notification_service.notify_risk_warning(
            user_id=self.user_id,
            strategy_id=self.strategy_id,
            strategy_name=getattr(self, 'strategy_name', f'波段策略{self.strategy_id}'),
            symbol=self.symbol,
            warning_type="max_stop_loss",
            message_text=f"达到最大止损次数({self.max_stop_loss_count}次),策略已停止",
            data={
                "stop_loss_count": self.stop_loss_count,
                "max_stop_loss_count": self.max_stop_loss_count
            }
        )
    except Exception as e:
        logger.error(f"发送风险预警失败: {e}")
    """)
else:
    print("\n3. ❌ 未找到风险预警位置")

print("\n" + "=" * 80)
print("✨ 请根据以上提示手动添加推送代码")
print("   或查看 '交易推送集成说明.md' 了解详细集成方法")
print("=" * 80)
