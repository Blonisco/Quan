# 📊 Stable Grid + Trend Hybrid Strategy（200 RMB 小资金优化版）

## 1. 策略目标

- 小资金长期挂机运行
- 在震荡市场赚取网格波动收益
- 在趋势市场避免逆势亏损
- 保持低风险和稳定性
- 不追求暴利

---

## 2. 核心指标

### EMA 趋势指标

```text
EMA_fast = EMA(20)
EMA_slow = EMA(50)
```

---

### ATR 波动率指标

```text
ATR = ATR(14)
```

ATR 用于：

- 动态调整网格间距
- 判断市场波动
- 控制加仓节奏

---

## 3. 市场状态判断

### 🟡 Grid Mode（震荡市场）

触发条件：

```text
abs(EMA20 - EMA50) / price < 1.0%
```

策略行为：

- 启动双向网格
- 通过波动赚差价

---

### 🟢 Trend Long Mode（上涨趋势）

触发条件：

```text
EMA20 > EMA50
```

策略行为：

- 只做多
- 回调买入
- 禁止逆势网格

---

### 🔴 Risk-Off Mode（下降趋势）

触发条件：

```text
EMA20 < EMA50
```

策略行为：

- 停止新增网格
- 不开新多单
- 保持现金

---

## 4. 网格策略逻辑（核心）

### 网格参数

```text
grid_step = ATR × 0.4
position_size = 3% ~ 5%
take_profit = +0.4% ~ +0.8%
```

---

### 网格行为

- 当前价格上下建立网格
- 下跌触发买入
- 上涨触发卖出
- 每次成交后自动重建网格

---

## 5. 趋势策略逻辑

### 回调买入参数

```text
entry_step = ATR × 0.6
```

---

### 分批止盈

```text
take_profit_levels:
  - +1%
  - +2%
  - +3%
```

---

### 趋势行为

- 仅在回调时加仓
- 不追涨
- 分批止盈
- 顺势交易

---

## 6. 风险控制

### 最大单笔仓位

```text
max_position_per_trade = 5%
```

---

### 最大总仓位

```text
max_total_exposure = 50%
```

---

### 最低现金保留

```text
min_cash_reserve = 50%
```

---

### 回撤保护

```python
if drawdown > 8%:
    stop_new_trades()
```

---

### 单边行情保护

```python
if consecutive_same_direction_trades > 8:
    reduce_position(30%)
```

---

## 7. 执行规则

### 市场检查频率

```text
market_check_interval = 1 minute
```

---

### K线周期

```text
primary_timeframe = 15m
secondary_timeframe = 1h
```

---

### 执行原则

- 不做高频
- 不使用杠杆
- 不做马丁
- 不无限补仓
- 使用 K线驱动逻辑

---

## 8. 核心原则

- 不预测市场
- 只赚市场波动
- 趋势顺势
- 震荡网格
- 永远保留现金
- 风控优先于收益

---

## 9. 长期目标

策略目标：

- 长期稳定运行
- 小幅持续收益
- 控制回撤
- 降低人工干预
- 适合小资金实验和长期挂机

---

## 10. 小资金特别说明

本策略针对：

- 100–500 RMB 小资金
- Binance Spot
- 长期运行

设计目标：

- 保证稳定性优先
- 保证不会快速归零
- 保证能持续产生交易
- 不追求短期暴利
