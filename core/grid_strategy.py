"""
预挂单型网格策略
启动后立即将 LIMIT 订单挂到 Binance，市场自动成交
成交后自动补充网格缺口
"""

import math
import time
import logging
from config.settings import (
    ORDER_AMOUNT_USDT,
    GRID_LOW_PRICE,
    GRID_HIGH_PRICE,
    GRID_COUNT,
    MAX_OPEN_ORDERS,
    MAX_POSITION_BTC,
    GRID_MODE_EMA_THRESHOLD,
    EMA_FAST_PERIOD,
    EMA_SLOW_PERIOD,
    ATR_PERIOD,
    GRID_STEP_ATR_MULT,
    TREND_ENTRY_ATR_MULT,
    TAKE_PROFIT_LEVELS,
    PRIMARY_TIMEFRAME,
    OHLCV_LOOKBACK,
)
from core.exchange import (
    fetch_ticker,
    fetch_open_orders,
    fetch_balance,
    fetch_ohlcv,
    create_limit_buy_order,
    create_limit_sell_order,
    cancel_order,
    get_min_order_amount,
    get_min_notional,
    format_price,
    format_amount,
)
from core.indicators import ema, atr, extract_ohlcv_columns
from core.risk_manager import risk
from core.database import db

logger = logging.getLogger("quan")


class GridStrategy:
    """预挂单型网格策略 — 订单长期挂在 Binance，成交自动补充"""

    def __init__(self):
        self.mode = "grid"
        self.grid_lines: list[float] = []
        self.buy_lines: list[float] = []
        self.sell_lines: list[float] = []
        self._grid_step: float = 0.0
        self._last_indicators_update = 0.0
        self._init_static_grid()
        self._reconcile_on_startup()

    def _reconcile_on_startup(self):
        """启动时对账：DB 中标记为 open 但 Binance 已不存在的订单，标记为 closed"""
        local_open = db.get_open_orders()
        if not local_open:
            return
        try:
            exchange_ids = {o["id"] for o in fetch_open_orders()}
            fixed = 0
            for loc in local_open:
                if loc["order_id"] not in exchange_ids:
                    db.update_order_status(loc["order_id"], "closed")
                    fixed += 1
            if fixed > 0:
                logger.info(f"启动对账: {fixed} 条本地挂单已不在交易所，标记为已成交")
        except Exception as e:
            logger.warning(f"启动对账失败: {e}")

    # ============================================
    # 静态网格计算（主方案）
    # ============================================

    def _init_static_grid(self):
        """从配置区间计算固定网格"""
        step = (GRID_HIGH_PRICE - GRID_LOW_PRICE) / GRID_COUNT

        self.grid_lines = []
        for i in range(GRID_COUNT + 1):
            price = format_price(GRID_LOW_PRICE + i * step)
            self.grid_lines.append(price)

        mid = (GRID_LOW_PRICE + GRID_HIGH_PRICE) / 2
        self.buy_lines = sorted(
            [p for p in self.grid_lines if p < mid], reverse=True
        )
        self.sell_lines = sorted(
            [p for p in self.grid_lines if p >= mid]
        )
        self._grid_step = step

        logger.info(f"静态网格: {len(self.grid_lines)} 条线, step={step:.1f}, "
                     f"买入线 [{GRID_LOW_PRICE}-{mid:.0f}] {len(self.buy_lines)} 条, "
                     f"卖出线 [{mid:.0f}-{GRID_HIGH_PRICE}] {len(self.sell_lines)} 条")

    # ============================================
    # 动态网格（基于 ATR，趋势模式下使用）
    # ============================================

    def _calc_dynamic_grid(self, current_price: float, atr_val: float):
        """按 ATR 重新计算网格"""
        grid_step = max(atr_val * GRID_STEP_ATR_MULT, 10.0)
        half_range = grid_step * (GRID_COUNT // 2)

        low = current_price - half_range
        high = current_price + half_range
        mid = (low + high) / 2

        self.grid_lines = []
        for i in range(GRID_COUNT + 1):
            price = format_price(low + i * grid_step)
            self.grid_lines.append(price)

        self.buy_lines = sorted(
            [p for p in self.grid_lines if p < mid], reverse=True
        )
        self.sell_lines = sorted(
            [p for p in self.grid_lines if p >= mid]
        )
        self._grid_step = grid_step

        logger.info(f"动态网格: {len(self.grid_lines)} 条, step={grid_step:.1f}, "
                     f"买区 {self.buy_lines[0] if self.buy_lines else 'N/A'}~"
                     f"{self.buy_lines[-1] if self.buy_lines else 'N/A'}, "
                     f"卖区 {self.sell_lines[0] if self.sell_lines else 'N/A'}~"
                     f"{self.sell_lines[-1] if self.sell_lines else 'N/A'}")

    # ============================================
    # 市场模式判断
    # ============================================

    def _determine_mode(self, ema_fast: float | None, ema_slow: float | None,
                        current_price: float) -> str:
        if ema_fast is None or ema_slow is None:
            return "grid"
        diff_pct = abs(ema_fast - ema_slow) / current_price
        if diff_pct < GRID_MODE_EMA_THRESHOLD:
            return "grid"
        elif ema_fast > ema_slow:
            return "trend_long"
        else:
            return "risk_off"

    # ============================================
    # 订单格式化
    # ============================================

    def _calc_order_amount(self, price: float) -> float:
        """计算符合 Binance 精度要求的下单数量"""
        min_notional = get_min_notional()
        effective_usdt = max(ORDER_AMOUNT_USDT, min_notional * 1.2)
        amount = effective_usdt / price
        min_amount = get_min_order_amount()
        amount = max(amount, min_amount)
        return format_amount(amount)

    # ============================================
    # 挂单状态查询
    # ============================================

    def _get_open_orders_map(self) -> dict:
        """
        返回当前 Binance 挂单的价格映射
        {"buy": {price1, price2, ...}, "sell": {price3, ...}}
        """
        buy_prices = set()
        sell_prices = set()
        try:
            for o in fetch_open_orders():
                if o["side"].lower() == "buy":
                    buy_prices.add(o["price"])
                else:
                    sell_prices.add(o["price"])
        except Exception as e:
            logger.error(f"读取挂单失败: {e}")
        return {"buy": buy_prices, "sell": sell_prices}

    # ============================================
    # 网格缺口填充（核心）
    # ============================================

    def _fill_grid_gaps(self, current_price: float):
        """
        检查每个网格线，缺单就补挂
        不依赖当前价格判断 — 预挂单型网格的核心
        """
        open_orders = self._get_open_orders_map()
        existing_buys = open_orders["buy"]
        existing_sells = open_orders["sell"]
        total_open = len(existing_buys) + len(existing_sells)

        net_btc = db.get_net_btc_position()
        usdt_balance = fetch_balance("USDT")

        buy_count = 0
        sell_count = 0

        # ---------- 补买单 ----------
        for bl in self.buy_lines:
            if total_open >= MAX_OPEN_ORDERS:
                break
            if bl in existing_buys:
                continue  # 已挂

            # 风控：持仓检查
            if net_btc >= MAX_POSITION_BTC:
                logger.debug(f"持仓已达上限 {net_btc:.6f} >= {MAX_POSITION_BTC}，不再补买")
                break

            # 风控：余额
            amount = self._calc_order_amount(bl)
            if usdt_balance < bl * amount * 1.001:
                logger.debug(f"USDT 余额不足下单 {bl}，跳过")
                continue

            # 风控：综合检查
            allowed, reason = risk.can_buy(bl, amount)
            if not allowed:
                logger.debug(f"补买拒绝 [{bl}]: {reason}")
                continue

            try:
                order = create_limit_buy_order(bl, amount)
                if order:
                    db.insert_order(order["id"], "BUY", bl, amount, "open")
                    existing_buys.add(bl)
                    total_open += 1
                    buy_count += 1
                    logger.info(f"✅ 挂买单 [{self.mode}]: "
                                f"{amount:.6f} BTC @ {bl} USDT | "
                                f"ID: {order['id']}")
            except Exception as e:
                logger.error(f"挂买单失败 [{bl}]: {e}")

        # ---------- 补卖单 ----------
        if net_btc <= 0:
            return  # 无持仓不挂卖单

        for sl in self.sell_lines:
            if total_open >= MAX_OPEN_ORDERS:
                break
            if sl in existing_sells:
                continue

            # 控制卖出量：卖出量不超过策略净持仓
            already_selling = 0.0
            for o in fetch_open_orders():
                if o["side"].lower() == "sell":
                    already_selling += o["amount"]
            available_to_sell = max(0, net_btc - already_selling)

            amount = self._calc_order_amount(sl)
            amount = min(amount, available_to_sell * 0.99)

            if amount < get_min_order_amount():
                logger.debug(f"卖出量过小 [{sl}]: {amount:.6f}，跳过")
                continue

            allowed, reason = risk.can_sell(sl, amount)
            if not allowed:
                logger.debug(f"补卖拒绝 [{sl}]: {reason}")
                continue

            try:
                order = create_limit_sell_order(sl, amount)
                if order:
                    db.insert_order(order["id"], "SELL", sl, amount, "open")
                    existing_sells.add(sl)
                    total_open += 1
                    sell_count += 1
                    logger.info(f"✅ 挂卖单 [{self.mode}]: "
                                f"{amount:.6f} BTC @ {sl} USDT | "
                                f"ID: {order['id']}")
            except Exception as e:
                logger.error(f"挂卖单失败 [{sl}]: {e}")

        if buy_count > 0 or sell_count > 0:
            logger.info(f"网格补充: +{buy_count} 买 +{sell_count} 卖, "
                         f"当前挂单 {total_open}/{MAX_OPEN_ORDERS}")

    # ============================================
    # 订单清理
    # ============================================

    def _cancel_off_grid_orders(self):
        """取消不在当前网格线上的挂单"""
        try:
            open_orders = fetch_open_orders()
        except Exception as e:
            logger.error(f"获取挂单失败: {e}")
            return

        # 允许的挂单价（1% 容差内算匹配）
        tolerance_pct = 0.01
        for order in open_orders:
            order_price = order["price"]
            order_side = order["side"].lower()

            target_lines = self.buy_lines if order_side == "buy" else self.sell_lines
            is_on_grid = any(
                abs(order_price - line) / line < tolerance_pct
                for line in target_lines
            )

            if not is_on_grid:
                try:
                    cancel_order(order["id"])
                    db.update_order_status(order["id"], "cancelled")
                    logger.info(f"取消离网格订单: {order_side.upper()} @ {order_price} "
                                f"({order['amount']:.6f} BTC)")
                except Exception as e:
                    logger.error(f"取消订单失败 {order['id']}: {e}")

    # ============================================
    # 订单成交同步
    # ============================================

    def sync_orders(self):
        """检测成交并更新数据库"""
        local_open = db.get_open_orders()
        if not local_open:
            return

        try:
            exchange_orders = fetch_open_orders()
            exchange_ids = {o["id"] for o in exchange_orders}

            for loc in local_open:
                oid = loc["order_id"]
                if oid not in exchange_ids:
                    db.update_order_status(oid, "closed")
                    logger.info(f"💸 订单成交: {loc['side']} "
                                f"{loc['amount']:.6f} BTC @ {loc['price']} USDT")
                    risk.record_direction(loc["side"])
        except Exception as e:
            logger.error(f"同步订单失败: {e}")

    # ============================================
    # 主循环
    # ============================================

    def tick(self):
        """单次策略迭代 — 同步成交 → 取消离网订单 → 补充网格缺口"""

        # 1. 获取行情
        try:
            ticker = fetch_ticker()
            current_price = ticker["last"]
        except Exception as e:
            logger.error(f"获取行情失败: {e}")
            return

        risk.update_drawdown()

        # 2. K线指标更新（每 5 分钟一次，减少 API 调用）
        now = time.time()
        ema_fast = ema_slow = atr_val = None
        if now - self._last_indicators_update >= 300:
            self._last_indicators_update = now
            try:
                ohlcv = fetch_ohlcv(PRIMARY_TIMEFRAME, OHLCV_LOOKBACK)
                closes, highs, lows, _ = extract_ohlcv_columns(ohlcv)
                ema_fast = ema(closes, EMA_FAST_PERIOD)[-1]
                ema_slow = ema(closes, EMA_SLOW_PERIOD)[-1]
                atr_val = atr(highs, lows, closes, ATR_PERIOD)[-1]
            except Exception as e:
                logger.warning(f"K线分析失败: {e}")

        # 3. 判断模式
        prev_mode = self.mode
        if ema_fast is not None and ema_slow is not None:
            self.mode = self._determine_mode(ema_fast, ema_slow, current_price)
        if self.mode != prev_mode:
            logger.warning(f"模式切换: {prev_mode} → {self.mode}")

        # 4. 如果网格需要更新（趋势模式下只加趋势入场单，不清网格）
        if self.mode != prev_mode:
            if self.mode == "grid":
                self._init_static_grid()
            elif self.mode == "trend_long" and atr_val:
                self._calc_dynamic_grid(current_price, atr_val)
            # risk_off: 保留网格但只补卖单

        # 5. 同步成交
        self.sync_orders()

        # 6. 清理不在网格线的订单
        self._cancel_off_grid_orders()

        # 7. 补充网格缺口（核心：不依赖价格触发）
        self._fill_grid_gaps(current_price)

        # 8. 状态日志：每 5 分钟输出一次摘要，其余静默
        if not hasattr(self, '_last_status_log'):
            self._last_status_log = 0.0
        if now - self._last_status_log >= 300:
            open_count = len(fetch_open_orders())
            net_btc = db.get_net_btc_position()
            _ema = f"EMA_f={ema_fast:.0f}/EMA_s={ema_slow:.0f}" if ema_fast else "N/A"
            _atr = f"ATR={atr_val:.0f}" if atr_val else "N/A"
            logger.info(f"[{self.mode}] price={current_price:.2f} {_ema} {_atr} | "
                         f"挂单: {open_count}/{MAX_OPEN_ORDERS} | 持仓: {net_btc:.6f} BTC")
            self._last_status_log = now

    # ============================================
    # 状态快照
    # ============================================

    def get_status(self) -> dict:
        btc_balance = fetch_balance("BTC")
        usdt_balance = fetch_balance("USDT")
        open_orders = fetch_open_orders()
        net_btc = db.get_net_btc_position()

        try:
            ticker = fetch_ticker()
            equity = btc_balance * ticker["last"] + usdt_balance
        except Exception:
            equity = usdt_balance

        drawdown_pct = 0.0
        if risk._peak_value is not None and risk._peak_value > 0:
            drawdown_pct = max(0, (risk._peak_value - equity) / risk._peak_value)

        return {
            "mode": self.mode,
            "btc_balance": btc_balance,
            "usdt_balance": usdt_balance,
            "equity": equity,
            "net_btc": net_btc,
            "open_orders": len(open_orders),
            "drawdown": drawdown_pct,
            "consecutive_dir": risk._consecutive_same_dir,
            "grid_low": GRID_LOW_PRICE,
            "grid_high": GRID_HIGH_PRICE,
            "grid_count": GRID_COUNT,
        }
