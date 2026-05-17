"""
Binance API 封装模块
基于 ccxt，支持 Testnet / Real 双模式
"""

import time
import ccxt
from config.settings import (
    IS_TESTNET,
    BINANCE_API_KEY,
    BINANCE_SECRET,
    SYMBOL,
)

MAX_RETRIES = 3
RETRY_DELAY = 2  # 秒


def _is_transient_error(error: ccxt.ExchangeError) -> bool:
    """判断是否为临时性错误（值得重试）"""
    msg = str(error)
    # 只对频率限制、服务端临时故障重试；参数错误重试无意义
    transient_keywords = [
        "-1015",  # Too many requests / rate limit
        "-1021",  # Timestamp for this request
        "-2013",  # Order does not exist (可能是同步延迟)
        "-1016",  # This IP is currently rate limited
    ]
    return any(kw in msg for kw in transient_keywords)


def _retry(func):
    """装饰器：API 调用异常时自动重试（仅网络错误和临时性交易所错误）"""
    def wrapper(*args, **kwargs):
        last_error = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                return func(*args, **kwargs)
            except ccxt.NetworkError as e:
                last_error = e
                if attempt < MAX_RETRIES:
                    delay = RETRY_DELAY * attempt
                    print(f"[EXCHANGE] 网络错误，{delay}s 后重试 ({attempt}/{MAX_RETRIES}): {e}")
                    time.sleep(delay)
            except ccxt.ExchangeError as e:
                # 仅临时性错误重试，参数校验类错误直接抛
                if not _is_transient_error(e):
                    raise
                last_error = e
                if attempt < MAX_RETRIES:
                    delay = RETRY_DELAY * attempt
                    print(f"[EXCHANGE] 临时交易所错误，{delay}s 后重试 ({attempt}/{MAX_RETRIES}): {e}")
                    time.sleep(delay)
        raise last_error
    return wrapper


def _create_exchange() -> ccxt.binance:
    """创建并配置 Exchange 实例"""
    exchange_config = {
        "apiKey": BINANCE_API_KEY,
        "secret": BINANCE_SECRET,
        "enableRateLimit": True,  # ccxt 内置限速，防止被 Ban
        "options": {
            "defaultType": "spot",  # 强制现货，杜绝合约
        },
    }

    if IS_TESTNET:
        exchange_config["urls"] = {
            "api": {
                "public": "https://testnet.binance.vision/api/v3",
                "private": "https://testnet.binance.vision/api/v3",
            }
        }

    exchange = ccxt.binance(exchange_config)

    # Testnet 需要显式设置
    if IS_TESTNET:
        exchange.set_sandbox_mode(True)

    return exchange


# 全局 Exchange 实例，模块加载时创建一次
exchange = _create_exchange()


def test_connection() -> bool:
    """
    测试 API 连接是否正常

    Returns:
        True 表示连接成功
    """
    try:
        exchange.fetch_balance()
        return True
    except Exception as e:
        print(f"[EXCHANGE] API 连接测试失败: {e}")
        return False


@_retry
def fetch_ticker():
    """
    获取当前行情

    Returns:
        dict: {"bid": 最高买价, "ask": 最低卖价, "last": 最新成交价}
    """
    ticker = exchange.fetch_ticker(SYMBOL)
    return {
        "bid": ticker["bid"],
        "ask": ticker["ask"],
        "last": ticker["last"],
    }


@_retry
def fetch_balance(asset: str):
    """
    查询指定资产的可用余额

    Args:
        asset: 资产符号，如 "BTC" 或 "USDT"

    Returns:
        float: 可用余额
    """
    balance = exchange.fetch_balance()
    return balance[asset]["free"]


@_retry
def fetch_open_orders():
    """
    获取当前所有未成交订单

    Returns:
        list[dict]: 订单列表
    """
    return exchange.fetch_open_orders(SYMBOL)


@_retry
def create_limit_buy_order(price: float, amount: float) -> dict | None:
    """
    创建限价买单

    Args:
        price: 买入价格
        amount: 买入数量（BTC）

    Returns:
        dict: 订单信息，失败返回 None
    """
    return exchange.create_limit_buy_order(SYMBOL, amount, price)


@_retry
def create_limit_sell_order(price: float, amount: float) -> dict | None:
    """
    创建限价卖单

    Args:
        price: 卖出价格
        amount: 卖出数量（BTC）

    Returns:
        dict: 订单信息，失败返回 None
    """
    return exchange.create_limit_sell_order(SYMBOL, amount, price)


@_retry
def cancel_order(order_id: str) -> bool:
    """
    取消指定订单

    Args:
        order_id: 订单 ID

    Returns:
        bool: 是否成功
    """
    exchange.cancel_order(order_id, SYMBOL)
    return True


@_retry
def fetch_closed_orders(since_ms: int | None = None):
    """
    获取已成交的历史订单

    Args:
        since_ms: 起始时间戳（毫秒），None 则获取最近

    Returns:
        list[dict]: 订单列表
    """
    params = {}
    if since_ms is not None:
        params["startTime"] = since_ms
    return exchange.fetch_closed_orders(SYMBOL, since=since_ms, params=params)


@_retry
def fetch_my_trades(since_ms: int | None = None):
    """
    获取成交记录

    Args:
        since_ms: 起始时间戳（毫秒）

    Returns:
        list[dict]: 成交记录
    """
    params = {}
    if since_ms is not None:
        params["startTime"] = since_ms
    return exchange.fetch_my_trades(SYMBOL, since=since_ms, params=params)


@_retry
def get_min_order_amount() -> float:
    """
    获取交易所对该交易对的最小下单量

    Returns:
        float: 最小下单数量（BTC）
    """
    market = exchange.market(SYMBOL)
    return market["limits"]["amount"]["min"]


@_retry
def get_min_notional() -> float:
    """
    获取交易所对该交易对的最小名义价值（minNotional）

    Returns:
        float: 最小名义价值（USDT）
    """
    market = exchange.market(SYMBOL)
    min_notional = market["limits"]["cost"]["min"]
    return min_notional if min_notional else 5.0


@_retry
def fetch_ohlcv(timeframe: str = "15m", limit: int = 100) -> list[list]:
    """
    获取 K线数据，用于 EMA/ATR 计算

    Args:
        timeframe: K线周期 (1m, 5m, 15m, 1h, 4h, 1d)
        limit: 获取条数

    Returns:
        list[list]: [[timestamp, open, high, low, close, volume], ...]
    """
    return exchange.fetch_ohlcv(SYMBOL, timeframe=timeframe, limit=limit)
