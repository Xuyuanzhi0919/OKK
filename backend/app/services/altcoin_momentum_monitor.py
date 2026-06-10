"""
山寨币短线异动监控。

定期扫描 OKX USDT 永续行情，发现 1 分钟涨幅超过阈值时通过通知服务推送。
"""
import asyncio
import time
from collections import defaultdict, deque
from typing import Any, Deque, Dict, Optional, Set

from loguru import logger

from app.core.config import settings
from app.services.exchange.okx import OKXExchange
from app.services.notification.notification_service import NotificationLevel, notification_service


MAJOR_AND_STABLE_COINS = {
    "BTC", "ETH", "USDT", "USDC", "DAI", "FDUSD", "TUSD", "USDD", "USD",
}


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def base_ccy_from_inst_id(inst_id: str) -> str:
    return inst_id.split("-")[0].upper() if inst_id else ""


class AltcoinMomentumMonitor:
    """1分钟山寨币涨幅监控器。"""

    def __init__(self):
        self.enabled = False
        self.interval_seconds = 15
        self.window_seconds = 60
        self.threshold_pct = 5.0
        self.windows = [{"window_seconds": 60, "threshold_pct": 5.0}]
        self.cooldown_seconds = 600
        self.inst_type = "SWAP"
        self.quote_ccy = "USDT"
        self.min_volume_usdt = 1000000
        self.exclude_majors = True
        self.user_id = 1
        self._task: Optional[asyncio.Task] = None
        self._exchange: Optional[OKXExchange] = None
        self._price_history: Dict[str, Deque[tuple[float, float]]] = defaultdict(deque)
        self._last_alert_at: Dict[str, float] = {}
        self._seen_symbols: Set[str] = set()

    def configure(self, config: Dict[str, Any]):
        self.enabled = bool(config.get("enabled", False))
        self.interval_seconds = int(config.get("interval_seconds", self.interval_seconds))
        self.window_seconds = int(config.get("window_seconds", self.window_seconds))
        self.threshold_pct = float(config.get("threshold_pct", self.threshold_pct))
        configured_windows = config.get("windows")
        if isinstance(configured_windows, list) and configured_windows:
            self.windows = []
            for item in configured_windows:
                if not isinstance(item, dict):
                    continue
                window_seconds = int(item.get("window_seconds", self.window_seconds))
                threshold_pct = float(item.get("threshold_pct", self.threshold_pct))
                if window_seconds > 0 and threshold_pct > 0:
                    self.windows.append({
                        "window_seconds": window_seconds,
                        "threshold_pct": threshold_pct,
                    })
            if not self.windows:
                self.windows = [{"window_seconds": self.window_seconds, "threshold_pct": self.threshold_pct}]
        else:
            self.windows = [{"window_seconds": self.window_seconds, "threshold_pct": self.threshold_pct}]
        self.cooldown_seconds = int(config.get("cooldown_seconds", self.cooldown_seconds))
        self.inst_type = str(config.get("inst_type", self.inst_type)).upper()
        self.quote_ccy = str(config.get("quote_ccy", self.quote_ccy)).upper()
        self.min_volume_usdt = float(config.get("min_volume_usdt", self.min_volume_usdt))
        self.exclude_majors = bool(config.get("exclude_majors", self.exclude_majors))
        self.user_id = int(config.get("user_id", self.user_id))

    async def start(self):
        if not self.enabled:
            logger.info("山寨币短线异动监控未启用")
            return
        bark = notification_service.channels.get("bark")
        if not bark or not bark.is_enabled():
            logger.warning("Bark渠道未启用，山寨币短线异动监控不启动")
            return
        if self._task and not self._task.done():
            logger.warning("山寨币短线异动监控已在运行")
            return

        self._exchange = OKXExchange(
            api_key="",
            secret_key="",
            passphrase="",
            simulated=False,
            proxy=settings.OKX_PROXY,
        )
        self._task = asyncio.create_task(self._monitor_loop())
        windows_text = ", ".join(
            f"{item['window_seconds']}s>={item['threshold_pct']}%" for item in self.windows
        )
        logger.info(
            f"山寨币短线异动监控已启动: windows=[{windows_text}], "
            f"interval={self.interval_seconds}s"
        )

    async def stop(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        if self._exchange:
            try:
                await self._exchange.close()
            except Exception:
                pass
            self._exchange = None

        logger.info("山寨币短线异动监控已停止")

    async def _monitor_loop(self):
        while True:
            try:
                await self._scan_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(f"山寨币短线异动监控出错: {exc}")

            await asyncio.sleep(self.interval_seconds)

    async def _scan_once(self):
        if not self._exchange:
            return

        now = time.time()
        tickers = await self._exchange.get_tickers(self.inst_type)
        for ticker in tickers:
            symbol = str(ticker.get("instId") or "")
            if not self._is_supported_symbol(symbol):
                continue

            last = safe_float(ticker.get("last"))
            if last <= 0:
                continue

            volume_usdt = self._volume_usdt(ticker)
            if volume_usdt < self.min_volume_usdt:
                continue

            history = self._price_history[symbol]
            history.append((now, last))
            max_window_seconds = max(item["window_seconds"] for item in self.windows)
            while history and now - history[0][0] > max_window_seconds * 2:
                history.popleft()

            for window in self.windows:
                window_seconds = window["window_seconds"]
                threshold_pct = window["threshold_pct"]
                baseline = self._find_baseline(history, now, window_seconds)
                if not baseline:
                    continue

                baseline_ts, baseline_price = baseline
                if baseline_price <= 0 or now - baseline_ts < window_seconds * 0.8:
                    continue

                change_pct = (last - baseline_price) / baseline_price * 100
                if change_pct >= threshold_pct:
                    await self._maybe_alert(
                        symbol,
                        last,
                        baseline_price,
                        change_pct,
                        volume_usdt,
                        now,
                        window_seconds,
                        threshold_pct,
                    )

    def _is_supported_symbol(self, symbol: str) -> bool:
        if self.inst_type == "SWAP":
            suffix = f"-{self.quote_ccy}-SWAP"
        else:
            suffix = f"-{self.quote_ccy}"

        if not symbol.endswith(suffix):
            return False

        base_ccy = base_ccy_from_inst_id(symbol)
        if self.exclude_majors and base_ccy in MAJOR_AND_STABLE_COINS:
            return False

        return True

    def _volume_usdt(self, ticker: Dict[str, Any]) -> float:
        volume_ccy = safe_float(ticker.get("volCcy24h"))
        last = safe_float(ticker.get("last"))
        return max(
            volume_ccy,
            volume_ccy * last,
            safe_float(ticker.get("vol24h")) * last,
        )

    def _find_baseline(
        self,
        history: Deque[tuple[float, float]],
        now: float,
        window_seconds: int,
    ) -> Optional[tuple[float, float]]:
        target_ts = now - window_seconds
        baseline = None
        for item in history:
            if item[0] <= target_ts:
                baseline = item
            else:
                break
        return baseline

    async def _maybe_alert(
        self,
        symbol: str,
        last: float,
        baseline_price: float,
        change_pct: float,
        volume_usdt: float,
        now: float,
        window_seconds: int,
        threshold_pct: float,
    ):
        alert_key = f"{symbol}:{window_seconds}"
        last_alert_at = self._last_alert_at.get(alert_key, 0)
        if now - last_alert_at < self.cooldown_seconds:
            return

        self._last_alert_at[alert_key] = now
        self._seen_symbols.add(symbol)

        window_label = "1分钟" if window_seconds == 60 else f"{round(window_seconds / 60)}分钟"
        title = f"山寨币{window_label}急涨: {symbol}"
        content = f"{symbol} 约{window_label}上涨 {change_pct:.2f}%"
        data = {
            "交易对": symbol,
            f"{window_label}前价格": f"{baseline_price:.8g}",
            "当前价格": f"{last:.8g}",
            f"{window_label}涨幅": f"{change_pct:.2f}%",
            "24h成交额估算": f"{volume_usdt:,.0f} USDT",
            "阈值": f"{threshold_pct:.2f}%",
            "冷却": f"{self.cooldown_seconds}秒",
        }

        sent = await notification_service.send_bark_notification(
            title=title,
            message=content,
            level=NotificationLevel.WARNING,
            data=data,
        )
        if sent:
            logger.warning(f"山寨币急涨Bark提醒已发送: {symbol} {window_label} {change_pct:.2f}%")


altcoin_momentum_monitor = AltcoinMomentumMonitor()
