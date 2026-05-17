"""
技术指标模块
EMA、ATR 等趋势和波动率指标
"""


def ema(data: list[float], period: int) -> list[float]:
    """
    计算指数移动平均线

    Args:
        data: 价格序列（按时间升序）
        period: 周期

    Returns:
        list[float]: 与 data 等长的 EMA 序列（前 period-1 个值为 None）
    """
    if len(data) < period:
        return [None] * len(data)

    multiplier = 2.0 / (period + 1)
    result = [None] * (period - 1)

    # 第一个 EMA 值 = SMA
    sma = sum(data[:period]) / period
    result.append(sma)

    # 后续 EMA = (price - prev_ema) * multiplier + prev_ema
    for i in range(period, len(data)):
        ema_val = (data[i] - result[-1]) * multiplier + result[-1]
        result.append(ema_val)

    return result


def atr(highs: list[float], lows: list[float], closes: list[float],
        period: int = 14) -> list[float]:
    """
    计算平均真实波幅

    Args:
        highs: 最高价序列
        lows: 最低价序列
        closes: 收盘价序列
        period: 周期

    Returns:
        list[float]: 与输入等长的 ATR 序列（前 period 个值为 None）
    """
    n = len(closes)
    if n < period + 1:
        return [None] * n

    # 计算 True Range
    true_ranges = [None]  # 第一个 TR 无意义
    for i in range(1, n):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        true_ranges.append(tr)

    # 第一个 ATR = SMA of first `period` TRs
    result = [None] * period
    first_atr = sum(true_ranges[1:period + 1]) / period
    result.append(first_atr)

    # 后续 ATR = (prev_atr * (period-1) + tr) / period
    for i in range(period + 1, n):
        atr_val = (result[-1] * (period - 1) + true_ranges[i]) / period
        result.append(atr_val)

    return result


def extract_ohlcv_columns(ohlcv: list[list]) -> tuple[list[float], ...]:
    """
    从 OHLCV 数据中提取各列

    Args:
        ohlcv: [[ts, open, high, low, close, vol], ...]

    Returns:
        (closes, highs, lows, volumes)
    """
    closes = [c[4] for c in ohlcv]
    highs = [c[2] for c in ohlcv]
    lows = [c[3] for c in ohlcv]
    volumes = [c[5] for c in ohlcv]
    return closes, highs, lows, volumes
