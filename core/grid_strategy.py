"""
网格 + 趋势混合策略模块
EMA/ATR 驱动：震荡网格 → 趋势回调买入 → 下跌暂停
"""

import math
import time
import logging
from config.settings import (
    ORDER_AMOUNT_USDT,
    GRID_LOW_PRICE,
    GRID_HIGH_PRICE,
    GRID_COUNT,
    EMA_FAST_PERIOD,
    EMA_SLOW_PERIOD,
    ATR_PERIOD,
    GRID_MODE_EMA_THRESHOLD,
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
)
from core.indicators import ema, atr, extract_ohlcv_columns
from core.risk_manager import risk
from core.database import db

logger = logging.getLogger("quan")


class GridStrategy:
    """EMA/ATR 三模式混合策略"""

    def __init__(self):
        self.mode = "grid"  # grid | trend_long | risk_off
        self.grid_lines: list[float] = []
        self.buy_lines: list[float] = []
        self.sell_lines: list[float] = []
        self._init_grid_lines()

    # ============================================
    # 固定网格（回退方案）
    # ============================================

    def _init_grid_lines(self):
        """固定价格网格，作为无 ATR 时的回退"""
        step = (GRID_HIGH_PRICE - GRID_LOW_PRICE) / GRID_COUNT
        self.grid_lines = []
        for i in range(GRID_COUNT + 1):
            self.grid_lines.append(round(GRID_LOW_PRICE + i * step, 2))
        mid = (GRID_LOW_PRICE + GRID_HIGH_PRICE) / 2
        self.buy_lines = sorted(
            [p for p in self.grid_lines if p < mid], reverse=True
        )
        self.sell_lines = sorted(
            [p for p in self.grid_lines if p >= mid]
        )
        logger.info(f"固定网格初始化: {len(self.grid_lines)} 条线, "
                     f"买入区 {len(self.buy_lines)} 条, 卖出区 {len(self.sell_lines)} 条")

    # ============================================
    # 动态网格（基于 ATR）
    # ============================================

    def _calc_dynamic_grid(self, current_price: float, atr_val: float):
        """根据当前价格和 ATR 动态计算网格线"""
        grid_step = max(atr_val * GRID_STEP_ATR_MULT, 10.0)  # 最小间距 10 USDT
        half_range = grid_step * (GRID_COUNT // 2)

        low = current_price - half_range
        high = current_price + half_range

        self.grid_lines = []
        for i in range(GRID_COUNT + 1):
            self.grid_lines.append(round(low + i * grid_step, 2))

        mid = (low + high) / 2
        self.buy_lines = sorted(
            [p for p in self.grid_lines if p < mid], reverse=True
        )
        self.sell_lines = sorted(
            [p for p in self.grid_lines if p >= mid]
        )

        logger.info(f"动态网格: {len(self.grid_lines)} 条线, "
                     f"step={grid_step:.1f}, "
                     f"买入区 {self.buy_lines[0] if self.buy_lines else 'N/A'}~"
                     f"{self.buy_lines[-1] if self.buy_lines else 'N/A'}, "
                     f"卖出区 {self.sell_lines[0] if self.sell_lines else 'N/A'}~"
                     f"{self.sell_lines[-1] if self.sell_lines else 'N/A'}")

    # ============================================
    # 市场模式判断
    # ============================================

    def _determine_mode(self, ema_fast: float, ema_slow: float,
                        current_price: float) -> str:
        """
        根据 EMA 快慢线关系判断市场状态

        Returns:
            "grid" | "trend_long" | "risk_off"
        """
        if ema_fast is None or ema_slow is None:
            return "grid"  # 数据不足，默认震荡

        diff_pct = abs(ema_fast - ema_slow) / current_price

        # EMA 接近 → 震荡
        if diff_pct < GRID_MODE_EMA_THRESHOLD:
            return "grid"

        # EMA 快线 > 慢线 → 上升趋势
        if ema_fast > ema_slow:
            return "trend_long"

        # EMA 快线 < 慢线 → 下降趋势
        return "risk_off"

    # ============================================
    # 买卖目标计算
    # ============================================

    def _find_buy_target(self, current_price: float,
                         atr_val: float) -> float | None:
        """根据模式找买入目标价"""
        if self.mode == "grid":
            for line in self.buy_lines:
                if current_price <= line:
                    return line
            return None

        elif self.mode == "trend_long":
            # 回调到 EMA20 下方 ATR×0.8 位置时买入
            entry_step = atr_val * TREND_ENTRY_ATR_MULT
            target = current_price - entry_step
            return round(target, 2)

        else:
            return None  # risk_off 不买入

    def _find_sell_target(self, current_price: float,
                          entry_price: float | None = None) -> float | None:
        """根据模式找卖出目标价"""
        if self.mode == "grid":
            for line in self.sell_lines:
                if current_price >= line:
                    return line
            return None

        elif self.mode == "trend_long":
            if entry_price is None:
                return None
            # 按止盈档位找最近的目标
            for tp_pct in TAKE_PROFIT_LEVELS:
                target = round(entry_price * (1 + tp_pct), 2)
                if current_price >= target:
                    return target
            return None

        else:
            # risk_off: 有持仓可卖出
            net_btc = db.get_net_btc_position()
            if net_btc > 0:
                return round(current_price * 1.005, 2)  # 市价上方止盈
            return None

    # ============================================
    # 订单清理
    # ============================================

    def _cancel_out_of_range_orders(self, current_price: float):
        """取消不在当前网格/策略范围的挂单"""
        open_orders = fetch_open_orders()

        for order in open_orders:
            order_price = order["price"]
            order_side = order["side"]
            should_cancel = False

            if order_side == "buy":
                if self.mode == "risk_off":
                    should_cancel = True  # 下跌模式取消所有买单
                elif current_price > order_price * 1.03:
                    should_cancel = True
                elif self.mode == "grid" and not any(
                    abs(order_price - bl) < 0.01 for bl in self.buy_lines
                ):
                    should_cancel = True

            elif order_side == "sell":
                if current_price < order_price * 0.97:
                    should_cancel = True
                elif self.mode == "grid" and not any(
                    abs(order_price - sl) < 0.01 for sl in self.sell_lines
                ):
                    should_cancel = True

            if should_cancel:
                try:
                    cancel_order(order["id"])
                except Exception as e:
                    logger.error(f"取消订单失败 {order['id']}: {e}")
                    continue
                db.update_order_status(order["id"], "cancelled")
                logger.info(f"取消过期订单: {order_side} @ {order_price} "
                            f"(模式: {self.mode})")

    # ============================================
    # 买卖执行
    # ============================================

    def _calc_order_amount(self, price: float) -> float:
        """计算下单数量（BTC），满足 minNotional 和精度"""
        min_notional = get_min_notional()
        effective_usdt = max(ORDER_AMOUNT_USDT, min_notional * 1.2)
        amount = effective_usdt / price
        min_amount = get_min_order_amount()
        amount = max(amount, min_amount)
        amount = math.floor(amount * 1_000_000) / 1_000_000
        return amount

    def _execute_buy(self, price: float) -> bool:
        """执行买入"""
        amount_btc = self._calc_order_amount(price)

        allowed, reason = risk.can_buy(price, amount_btc)
        if not allowed:
            logger.warning(f"买入被拒绝: {reason}")
            return False

        try:
            order = create_limit_buy_order(price, amount_btc)
        except Exception as e:
            logger.error(f"买入下单失败: {e}")
            return False

        db.insert_order(order["id"], "BUY", price, amount_btc, "open")
        db.save_state("last_buy_grid", {"price": price, "time": time.time()})
        logger.info(f"✅ 买入挂单 [{self.mode}]: {amount_btc:.6f} BTC @ {price} USDT")
        return True

    def _execute_sell(self, price: float) -> bool:
        """执行卖出"""
        net_btc = db.get_net_btc_position()
        if net_btc <= 0:
            logger.warning("策略无持仓，跳过卖出")
            return False
        amount_btc = self._calc_order_amount(price)
        amount_btc = min(amount_btc, net_btc * 0.99)

        if amount_btc < get_min_order_amount():
            logger.warning(f"卖出数量过小: {amount_btc:.6f}")
            return False

        allowed, reason = risk.can_sell(price, amount_btc)
        if not allowed:
            logger.warning(f"卖出被拒绝: {reason}")
            return False

        try:
            order = create_limit_sell_order(price, amount_btc)
        except Exception as e:
            logger.error(f"卖出下单失败: {e}")
            return False

        db.insert_order(order["id"], "SELL", price, amount_btc, "open")
        db.save_state("last_sell_grid", {"price": price, "time": time.time()})
        logger.info(f"✅ 卖出挂单 [{self.mode}]: {amount_btc:.6f} BTC @ {price} USDT")
        return True

    # ============================================
    # 订单状态同步
    # ============================================

    def sync_orders(self):
        """同步成交状态，更新连续同向计数"""
        local_open = db.get_open_orders()
        if not local_open:
            return

        try:
            exchange_orders = fetch_open_orders()
            exchange_order_ids = {o["id"] for o in exchange_orders}

            for local_order in local_open:
                order_id = local_order["order_id"]
                if order_id not in exchange_order_ids:
                    db.update_order_status(order_id, "closed")
                    logger.info(f"订单已成交: {local_order['side']} "
                                f"{local_order['amount']} @ {local_order['price']}")
                    risk.record_direction(local_order["side"])
        except Exception as e:
            logger.error(f"同步订单失败: {e}")

    # ============================================
    # 主循环迭代
    # ============================================

    def tick(self):
        """单次策略迭代"""
        # 1. 获取行情和 K线
        try:
            ticker = fetch_ticker()
            current_price = ticker["last"]
        except Exception as e:
            logger.error(f"获取行情失败，跳过本轮: {e}")
            return

        # 更新权益峰值（用于回撤计算）
        risk.update_drawdown()

        # 读取历史订单计算加权买入均价（趋势止盈用）
        entry_price = db.get_weighted_avg_entry_price()

        # 2. K线分析 → EMA / ATR
        atr_val = None
        try:
            ohlcv = fetch_ohlcv(PRIMARY_TIMEFRAME, OHLCV_LOOKBACK)
            closes, highs, lows, _ = extract_ohlcv_columns(ohlcv)

            ema_fast_list = ema(closes, EMA_FAST_PERIOD)
            ema_slow_list = ema(closes, EMA_SLOW_PERIOD)
            ema_fast = ema_fast_list[-1] if ema_fast_list[-1] is not None else None
            ema_slow = ema_slow_list[-1] if ema_slow_list[-1] is not None else None

            atr_list = atr(highs, lows, closes, ATR_PERIOD)
            atr_val = atr_list[-1] if atr_list[-1] is not None else None
        except Exception as e:
            logger.warning(f"K线分析失败，使用固定网格: {e}")
            ema_fast = ema_slow = None

        # 3. 判断市场模式
        if ema_fast is not None and ema_slow is not None:
            prev_mode = self.mode
            self.mode = self._determine_mode(ema_fast, ema_slow, current_price)
            if self.mode != prev_mode:
                logger.warning(f"模式切换: {prev_mode} → {self.mode} "
                               f"(EMA_f={ema_fast:.2f} EMA_s={ema_slow:.2f})")
        else:
            self.mode = "grid"

        # 4. 动态网格计算
        if self.mode == "grid" and atr_val is not None:
            self._calc_dynamic_grid(current_price, atr_val)
        elif atr_val is None:
            self._init_grid_lines()

        # 5. 同步成交 + 清理过期订单
        self.sync_orders()
        self._cancel_out_of_range_orders(current_price)

        # 6. 检查买入
        if self.mode != "risk_off":
            buy_target = self._find_buy_target(current_price, atr_val or 1000)
            if buy_target is not None:
                if not risk.is_duplicate_order(buy_target, "buy"):
                    self._execute_buy(buy_target)
                else:
                    logger.debug(f"已有买入挂单 @ {buy_target}，跳过")

        # 7. 检查卖出
        sell_target = self._find_sell_target(current_price, entry_price)
        if sell_target is not None:
            if not risk.is_duplicate_order(sell_target, "sell"):
                self._execute_sell(sell_target)
            else:
                logger.debug(f"已有卖出挂单 @ {sell_target}，跳过")

        # 8. 状态日志（每小时由 main.py 统一输出，此处仅 debug）
        _ema_f = f"EMA_f={ema_fast:.2f}" if ema_fast else "EMA_f=N/A"
        _ema_s = f"EMA_s={ema_slow:.2f}" if ema_slow else "EMA_s=N/A"
        _atr = f"ATR={atr_val:.1f}" if atr_val else "ATR=N/A"
        logger.debug(
            f"[{self.mode}] price={current_price} {_ema_f} {_ema_s} {_atr}"
        )

    # ============================================
    # 状态快照
    # ============================================

    def get_status(self) -> dict:
        """获取当前策略状态"""
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
