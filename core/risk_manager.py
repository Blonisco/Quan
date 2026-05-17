"""
风险控制模块
所有风险检查集中在此，任何一项不通过则拒绝交易
"""

from config.settings import (
    MAX_POSITION_BTC,
    ORDER_AMOUNT_USDT,
    MAX_OPEN_ORDERS,
    PRICE_SURGE_THRESHOLD,
    MAX_POSITION_PER_TRADE_PCT,
    MAX_TOTAL_EXPOSURE_PCT,
    MIN_CASH_RESERVE_PCT,
    DRAWDOWN_LIMIT_PCT,
    MAX_CONSECUTIVE_SAME_DIR,
    SYMBOL,
)
from core.exchange import fetch_balance, fetch_open_orders, fetch_ticker
from core.database import db


class RiskManager:
    """风险管理器"""

    def __init__(self):
        self._last_price = None
        self._peak_value = None  # 账户峰值用于回撤
        self._consecutive_same_dir = 0
        self._last_direction = None

    # ============================================
    # 总资产计算
    # ============================================

    def _get_total_capital(self) -> float:
        """估算总资产（USDT）"""
        try:
            btc = fetch_balance("BTC")
            usdt = fetch_balance("USDT")
            ticker = fetch_ticker()
            return usdt + btc * ticker["last"]
        except Exception:
            return ORDER_AMOUNT_USDT * 10

    # ============================================
    # 持仓检查
    # ============================================

    def check_position_limit(self) -> tuple[bool, str]:
        """检查策略净持仓是否超过上限（使用 DB 统计，不用钱包余额）"""
        try:
            net_btc = db.get_net_btc_position()
            if net_btc >= MAX_POSITION_BTC:
                return False, (
                    f"BTC 持仓已达上限: {net_btc:.6f} >= {MAX_POSITION_BTC} "
                    f"(超过最大持仓限制，不再买入)"
                )
            return True, f"持仓正常: {net_btc:.6f} / {MAX_POSITION_BTC} BTC"
        except Exception as e:
            return False, f"查询持仓失败: {e}"

    def check_quote_balance(self, required_usdt: float) -> tuple[bool, str]:
        """检查 USDT 余额是否足够"""
        try:
            usdt_balance = fetch_balance("USDT")
            if usdt_balance < required_usdt:
                return False, (
                    f"USDT 余额不足: {usdt_balance:.2f} < {required_usdt:.2f}"
                )
            return True, f"余额充足: {usdt_balance:.2f} USDT"
        except Exception as e:
            return False, f"查询余额失败: {e}"

    def check_base_balance(self, required_btc: float) -> tuple[bool, str]:
        """检查策略净持仓是否足够卖出（用 DB 统计，不用钱包余额）"""
        try:
            net_btc = db.get_net_btc_position()
            min_amount = 0.00001
            actual_required = max(required_btc, min_amount)
            if net_btc < actual_required:
                return False, (
                    f"策略持仓不足: {net_btc:.6f} < {actual_required:.6f} "
                    f"(卖出数量超过策略净买入)"
                )
            return True, f"策略持仓: {net_btc:.6f} BTC"
        except Exception as e:
            return False, f"查询持仓失败: {e}"

    # ============================================
    # 单笔仓位检查（strategy.md: 单笔最大 2%）
    # ============================================

    def check_position_per_trade(self, price: float, amount_btc: float) -> tuple[bool, str]:
        """检查单笔仓位是否超过总资产的 MAX_POSITION_PER_TRADE_PCT"""
        capital = self._get_total_capital()
        trade_value = price * amount_btc
        if capital > 0 and trade_value / capital > MAX_POSITION_PER_TRADE_PCT:
            return False, (
                f"单笔仓位超限: {trade_value/capital*100:.1f}% > "
                f"{MAX_POSITION_PER_TRADE_PCT*100:.0f}%"
            )
        return True, f"单笔仓位: {trade_value/capital*100:.1f}%"

    # ============================================
    # 总敞口检查（strategy.md: 最大总敞口 40%）
    # ============================================

    def check_total_exposure(self) -> tuple[bool, str]:
        """检查总敞口是否超过上限"""
        try:
            net_btc = db.get_net_btc_position()
            ticker = fetch_ticker()
            capital = self._get_total_capital()
            exposure = net_btc * ticker["last"]
            if capital > 0 and exposure / capital > MAX_TOTAL_EXPOSURE_PCT:
                return False, (
                    f"总敞口超限: {exposure/capital*100:.1f}% > "
                    f"{MAX_TOTAL_EXPOSURE_PCT*100:.0f}%"
                )
            return True, f"总敞口: {exposure/capital*100:.1f}%"
        except Exception as e:
            return False, f"查询敞口失败: {e}"

    # ============================================
    # 现金储备检查（strategy.md: 最低现金 60%）
    # ============================================

    def check_cash_reserve(self) -> tuple[bool, str]:
        """检查是否保留足够现金"""
        try:
            capital = self._get_total_capital()
            usdt = fetch_balance("USDT")
            if capital > 0 and usdt / capital < MIN_CASH_RESERVE_PCT:
                return False, (
                    f"现金储备不足: {usdt/capital*100:.1f}% < "
                    f"{MIN_CASH_RESERVE_PCT*100:.0f}%"
                )
            return True, f"现金储备: {usdt/capital*100:.1f}%"
        except Exception as e:
            return False, f"查询储备失败: {e}"

    # ============================================
    # 回撤保护（strategy.md: 回撤 > 6% 停止新交易）
    # ============================================

    def update_drawdown(self):
        """更新回撤状态（每轮 tick 调用）"""
        capital = self._get_total_capital()
        if self._peak_value is None or capital > self._peak_value:
            self._peak_value = capital

    def check_drawdown(self) -> tuple[bool, str]:
        """检查回撤是否超过限制"""
        if self._peak_value is None:
            return True, "无历史峰值"
        capital = self._get_total_capital()
        drawdown = (self._peak_value - capital) / self._peak_value if self._peak_value > 0 else 0
        if drawdown >= DRAWDOWN_LIMIT_PCT:
            return False, (
                f"回撤超限: {drawdown*100:.1f}% >= {DRAWDOWN_LIMIT_PCT*100:.0f}% "
                f"(熔断，停止新交易)"
            )
        return True, f"回撤正常: {drawdown*100:.1f}%"

    # ============================================
    # 同向连续成交检查（strategy.md: > 6 笔 → 减仓 30%）
    # ============================================

    def record_direction(self, side: str):
        """记录成交方向"""
        if side == self._last_direction:
            self._consecutive_same_dir += 1
        else:
            self._consecutive_same_dir = 1
            self._last_direction = side

    def check_consecutive_same_dir(self) -> tuple[bool, str]:
        """检查同向连续成交是否超限"""
        if self._consecutive_same_dir > MAX_CONSECUTIVE_SAME_DIR:
            return False, (
                f"同向连续成交 {self._consecutive_same_dir} 笔 > "
                f"{MAX_CONSECUTIVE_SAME_DIR}（应减仓 30%）"
            )
        return True, f"同向连续: {self._consecutive_same_dir} 笔"

    # ============================================
    # 订单数量检查
    # ============================================

    def check_open_orders_count(self) -> tuple[bool, str]:
        """检查当前挂单数量是否超过上限"""
        try:
            open_orders = fetch_open_orders()
            count = len(open_orders)
            if count >= MAX_OPEN_ORDERS:
                return False, (
                    f"挂单数量已达上限: {count} >= {MAX_OPEN_ORDERS}"
                )
            return True, f"挂单数量正常: {count}/{MAX_OPEN_ORDERS}"
        except Exception as e:
            return False, f"查询挂单失败: {e}"

    def is_duplicate_order(self, price: float, side: str) -> bool:
        """检查是否已有相同价格和方向的挂单"""
        try:
            for order in fetch_open_orders():
                if order["side"] == side and abs(order["price"] - price) < 0.01:
                    return True
            return False
        except Exception:
            return True

    # ============================================
    # 价格异常检测
    # ============================================

    def check_price_surge(self) -> tuple[bool, str]:
        """检测价格是否异常波动"""
        try:
            ticker = fetch_ticker()
            current_price = ticker["last"]
            if self._last_price is None:
                self._last_price = current_price
                return True, "首次运行，无历史价格"
            change_pct = abs((current_price - self._last_price) / self._last_price * 100)
            self._last_price = current_price
            if change_pct > PRICE_SURGE_THRESHOLD:
                return False, (
                    f"价格异常波动: {change_pct:.2f}% > {PRICE_SURGE_THRESHOLD}%"
                )
            return True, f"价格波动正常: {change_pct:.2f}%"
        except Exception as e:
            return False, f"获取行情失败: {e}"

    # ============================================
    # 综合检查（下单前调用）
    # ============================================

    def can_buy(self, price: float, amount_btc: float) -> tuple[bool, str]:
        """买入前的综合风险检查"""
        # 1. 价格异常
        ok, reason = self.check_price_surge()
        if not ok:
            return False, f"价格波动 → {reason}"

        # 2. 持仓上限
        ok, reason = self.check_position_limit()
        if not ok:
            return False, f"持仓限制 → {reason}"

        # 3. 单笔仓位
        ok, reason = self.check_position_per_trade(price, amount_btc)
        if not ok:
            return False, f"单笔限制 → {reason}"

        # 4. 总敞口
        ok, reason = self.check_total_exposure()
        if not ok:
            return False, f"敞口限制 → {reason}"

        # 5. 余额
        required_usdt = price * amount_btc * 1.001
        ok, reason = self.check_quote_balance(required_usdt)
        if not ok:
            return False, f"余额不足 → {reason}"

        # 6. 回撤
        ok, reason = self.check_drawdown()
        if not ok:
            return False, f"回撤熔断 → {reason}"

        # 7. 挂单数量
        ok, reason = self.check_open_orders_count()
        if not ok:
            return False, f"挂单限制 → {reason}"

        # 8. 重复下单
        if self.is_duplicate_order(price, "buy"):
            return False, f"重复挂单 → 价格 {price} 已有买入挂单"

        return True, "风险检查通过"

    def can_sell(self, price: float, amount_btc: float) -> tuple[bool, str]:
        """卖出前的综合风险检查"""
        # 1. 价格异常
        ok, reason = self.check_price_surge()
        if not ok:
            return False, f"价格波动 → {reason}"

        # 2. BTC 余额
        ok, reason = self.check_base_balance(amount_btc)
        if not ok:
            return False, f"持仓不足 → {reason}"

        # 3. 挂单数量
        ok, reason = self.check_open_orders_count()
        if not ok:
            return False, f"挂单限制 → {reason}"

        # 4. 重复下单
        if self.is_duplicate_order(price, "sell"):
            return False, f"重复挂单 → 价格 {price} 已有卖出挂单"

        return True, "风险检查通过"


# 全局风险管理器实例
risk = RiskManager()
