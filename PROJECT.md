# Quan — Binance Spot 网格交易机器人

## 项目概览

- **用户**: 200~300 RMB 小额测试，Windows 本地开发 → GitHub → Ubuntu VPS 部署
- **交易**: BTC/USDT 现货网格，Binance Testnet → 后续 Real
- **原则**: 不做合约/杠杆/做空，优先稳定与安全

## 目录结构

```
Quan/
├── main.py                   # 主入口，信号处理，主循环
├── .env / .env.example       # 环境配置
├── requirements.txt
├── Quan.md                   # 用户需求规格书
├── strategy.md               # 目标策略设计（已实现）
├── config/
│   └── settings.py           # .env 加载，配置项定义，print_config()
├── core/
│   ├── exchange.py           # ccxt 封装，双模式(testnet/real)，_retry 重试，min_notional
│   ├── grid_strategy.py      # 三模式混合策略 (EMA/ATR)
│   ├── indicators.py          # EMA / ATR 技术指标
│   ├── risk_manager.py       # 风控：持仓/回撤/敞口/连续同向
│   └── database.py           # SQLite: orders/trades/daily_pnl/error_logs/bot_state
├── notifier/
│   └── telegram.py           # 通知 + 命令轮询(getUpdates)
├── utils/
│   └── logger.py             # logging 配置，按日分文件
├── deploy/
│   ├── quan-bot.service      # systemd
│   └── DEPLOY.md
├── README.md                 # 用户文档
└── PROJECT.md                # 本文件
```

## 当前策略（已实现 strategy.md）

**三模式混合策略**，基于 EMA/ATR 动态驱动：

| 模式 | 条件 | 行为 |
|------|------|------|
| 🟡 震荡网格 | \|EMA20 - EMA50\| / price < 0.8% | 动态网格(ATR×0.6 间距)，双向买卖 |
| 🟢 上涨趋势 | EMA20 > EMA50 | 只做多，回调 ATR×0.8 买入，分批止盈(+1%/+2%/+3%) |
| 🔴 下跌避险 | EMA20 < EMA50 | 停止新买单，取消挂单，仅持有现金 |

**K线驱动**: 15m 主周期 (100 条回溯) / 1h 辅助周期

**风控体系** (`risk_manager.py`):
- 策略净持仓上限（DB 统计，非钱包余额）
- 单笔仓位 ≤ 2% 总资产
- 总敞口 ≤ 40%
- 最低现金 60%
- 回撤 > 6% 熔断
- 连续同向 > 6 笔告警
- 价格异常波动(>5%)暂停
- 防重复下单 / 最大挂单数限制

## 关键架构决策

### 持仓限制 → 策略净持仓
`risk_manager.py:check_position_limit()` **不用**钱包总余额(BTC)，改用 `db.get_net_btc_position()` 统计已成交买单 - 已成交卖单。因为 Testnet 账户自带 1 BTC，用钱包余额会永久触发上限。

### API 重试 → 仅临时性错误
`exchange.py:_retry` 装饰器 3 次指数退避重试。只对 `NetworkError` 和特定 `ExchangeError`（频率限制 -1015、时间戳 -1021 等）重试。参数错误（NOTIONAL、LOT_SIZE 等）直接抛，不重试。

### 最小名义价值 → 自动补齐
Binance BTC/USDT minNotional=5.0 USDT，用 `applyMinToMarket: True` + `avgPriceMins: 5` 均价校验。`grid_strategy.py:_execute_buy/_execute_sell` 计算时自动 `max(ORDER_AMOUNT_USDT, minNotional * 1.2)` 留 20% 余量。

### 通知频率
- **Telegram**: 启动/停止/错误 + 每 6 小时状态推送 + 每日午夜报告 + 命令交互
- **单笔成交/挂单**: 不通知，仅写日志
- **命令**: `/status` `/report` `/help`，30s 轮询 `getUpdates`，启动时跳过旧消息

### 模式隔离
`settings.py` 中 `IS_TESTNET` / `IS_REAL` 全局可用。`exchange.py` 根据模式切换 URL 和 sandbox 模式。main.py 启动时 real 模式打印警告。

## 配置要点 (.env)

```
TRADE_MODE=testnet                        # testnet | real
ORDER_AMOUNT_USDT=5                       # 每格买入金额
MAX_POSITION_BTC=0.00035                 # 策略净持仓上限（约 200 RMB）
GRID_LOW_PRICE=80000
GRID_HIGH_PRICE=120000
GRID_COUNT=10
MAX_OPEN_ORDERS=5
LOOP_INTERVAL_SECONDS=30
```

## 数据库表

| 表 | 用途 |
|----|------|
| orders | 订单记录 (open→closed/cancelled) |
| trades | 成交记录 (目前未填充) |
| daily_pnl | 每日收益 |
| error_logs | 错误日志 |
| bot_state | key-value 状态持久化 |

## 修复记录 (2026-05-17)

1. 持仓限制误判 → `db.get_net_btc_position()` 替代 `fetch_balance("BTC")`
2. `ORDER_AMOUNT_USDT`: 12→5, `MAX_POSITION_BTC`: 0.001→0.00035 (适配 200 RMB)
3. `exchange.py`: 加 `_retry` 装饰器，仅重试临时错误
4. NOTIONAL 错误 → `effective_usdt = max(ORDER_AMOUNT_USDT, minNotional * 1.2)`
5. `.gitignore`: 移除 `*.service` 排除
6. `grid_strategy.py`: `print()` → `logger.info/warning/error`
7. `main.py`: 加每日报告 + 6 小时定时摘要
8. Telegram 命令: `/status` `/report` `/help`
9. Telegram 启动跳过旧消息（`_get_latest_update_id()`）
10. 注释修正: "每 60 轮" → "每小时"
11. 策略升级 → EMA/ATR 三模式混合（新增 indicators.py，重写 grid_strategy.py）
12. 风控升级 → 回撤熔断 + 连续同向保护 + 单笔/总敞口/现金储备检查
13. Telegram 命令增强 → /status 显示模式/回撤/连续同向
