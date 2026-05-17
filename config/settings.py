"""
配置加载模块
从 .env 文件读取所有配置项
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent

# 加载 .env 文件
env_path = BASE_DIR / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    # 首次运行没有 .env，使用 .env.example 的默认值
    load_dotenv(BASE_DIR / ".env.example")


def _get_env(key: str, default: str = "") -> str:
    """读取环境变量，去除首尾空白"""
    return os.getenv(key, default).strip()


# ============================================
# 交易模式（核心安全开关）
# ============================================

TRADE_MODE = _get_env("TRADE_MODE", "testnet").lower()

if TRADE_MODE not in ("testnet", "real"):
    raise ValueError(f"TRADE_MODE 必须为 testnet 或 real，当前值: {TRADE_MODE}")

IS_TESTNET = TRADE_MODE == "testnet"
IS_REAL = TRADE_MODE == "real"


# ============================================
# Binance API
# ============================================

BINANCE_API_KEY = _get_env("BINANCE_API_KEY")
BINANCE_SECRET = _get_env("BINANCE_SECRET")

if not BINANCE_API_KEY or not BINANCE_SECRET:
    raise ValueError("BINANCE_API_KEY 和 BINANCE_SECRET 未配置，请检查 .env 文件")


# ============================================
# Telegram
# ============================================

TELEGRAM_BOT_TOKEN = _get_env("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = _get_env("TELEGRAM_CHAT_ID")


# ============================================
# 交易对
# ============================================

SYMBOL = "BTC/USDT"          # 交易对
BASE_ASSET = "BTC"           # 基础资产
QUOTE_ASSET = "USDT"         # 计价资产

# ============================================
# 策略参数 — EMA 趋势指标
# ============================================

EMA_FAST_PERIOD = int(_get_env("EMA_FAST_PERIOD", "20"))
EMA_SLOW_PERIOD = int(_get_env("EMA_SLOW_PERIOD", "50"))
GRID_MODE_EMA_THRESHOLD = float(_get_env("GRID_MODE_EMA_THRESHOLD", "0.008"))  # 0.8% → 震荡

# ============================================
# 策略参数 — ATR 波动率
# ============================================

ATR_PERIOD = int(_get_env("ATR_PERIOD", "14"))
GRID_STEP_ATR_MULT = float(_get_env("GRID_STEP_ATR_MULT", "0.6"))
TREND_ENTRY_ATR_MULT = float(_get_env("TREND_ENTRY_ATR_MULT", "0.8"))

# ============================================
# 策略参数 — 止盈
# ============================================

# 趋势模式分批止盈（逗号分隔的百分比，如 "1,2,3" 表示 +1%、+2%、+3%）
_tp_str = _get_env("TAKE_PROFIT_LEVELS", "1,2,3")
TAKE_PROFIT_LEVELS = [float(x.strip()) / 100 for x in _tp_str.split(",") if x.strip()]

# 网格模式止盈
GRID_TAKE_PROFIT_PCT = float(_get_env("GRID_TAKE_PROFIT_PCT", "0.005"))  # 0.5%

# ============================================
# 策略参数 — K线周期
# ============================================

PRIMARY_TIMEFRAME = _get_env("PRIMARY_TIMEFRAME", "15m")
SECONDARY_TIMEFRAME = _get_env("SECONDARY_TIMEFRAME", "1h")
OHLCV_LOOKBACK = int(_get_env("OHLCV_LOOKBACK", "100"))   # K线回溯条数

# ============================================
# 网格交易参数
# ============================================

GRID_LOW_PRICE = float(_get_env("GRID_LOW_PRICE", "80000"))
GRID_HIGH_PRICE = float(_get_env("GRID_HIGH_PRICE", "120000"))
GRID_COUNT = int(_get_env("GRID_COUNT", "10"))
ORDER_AMOUNT_USDT = float(_get_env("ORDER_AMOUNT_USDT", "5"))
MAX_POSITION_BTC = float(_get_env("MAX_POSITION_BTC", "0.00035"))
MAX_OPEN_ORDERS = int(_get_env("MAX_OPEN_ORDERS", "5"))
PRICE_SURGE_THRESHOLD = float(_get_env("PRICE_SURGE_THRESHOLD", "5"))
LOOP_INTERVAL_SECONDS = int(_get_env("LOOP_INTERVAL_SECONDS", "30"))

# ============================================
# 风险控制参数
# ============================================

MAX_POSITION_PER_TRADE_PCT = float(_get_env("MAX_POSITION_PER_TRADE_PCT", "0.02"))   # 单笔 2%
MAX_TOTAL_EXPOSURE_PCT = float(_get_env("MAX_TOTAL_EXPOSURE_PCT", "0.40"))            # 总敞口 40%
MIN_CASH_RESERVE_PCT = float(_get_env("MIN_CASH_RESERVE_PCT", "0.60"))                # 最低现金 60%
DRAWDOWN_LIMIT_PCT = float(_get_env("DRAWDOWN_LIMIT_PCT", "0.06"))                   # 回撤 6%
MAX_CONSECUTIVE_SAME_DIR = int(_get_env("MAX_CONSECUTIVE_SAME_DIR", "6"))             # 同向 6 笔


# ============================================
# 路径配置
# ============================================

LOG_DIR = BASE_DIR / "logs"
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "quan.db"


# ============================================
# 启动时打印关键配置（不含敏感信息）
# ============================================

def print_config():
    """打印非敏感配置信息，用于启动确认"""
    print("=" * 55)
    print(f"  交易模式   : {'TESTNET (测试网)' if IS_TESTNET else 'REAL (真实交易!!!  )'}")
    print(f"  交易对     : {SYMBOL}")
    print(f"  策略       : EMA({EMA_FAST_PERIOD}/{EMA_SLOW_PERIOD}) + ATR({ATR_PERIOD}) 三模式")
    print(f"  K线周期    : {PRIMARY_TIMEFRAME} / {SECONDARY_TIMEFRAME}")
    print(f"  网格区间   : {GRID_LOW_PRICE} - {GRID_HIGH_PRICE} USDT")
    print(f"  每格金额   : {ORDER_AMOUNT_USDT} USDT")
    print(f"  策略持仓上限: {MAX_POSITION_BTC} BTC")
    print(f"  最大挂单   : {MAX_OPEN_ORDERS}")
    print(f"  止盈档位   : {[f'+{x*100:.0f}%' for x in TAKE_PROFIT_LEVELS]}")
    print(f"  总敞口上限 : {MAX_TOTAL_EXPOSURE_PCT*100:.0f}%")
    print(f"  回撤熔断   : {DRAWDOWN_LIMIT_PCT*100:.0f}%")
    print(f"  循环间隔   : {LOOP_INTERVAL_SECONDS}s")
    print(f"  Telegram   : {'已配置' if TELEGRAM_BOT_TOKEN else '未配置'}")
    print("=" * 55)


if __name__ == "__main__":
    print_config()
