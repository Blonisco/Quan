# Quan — Binance Spot 网格交易机器人

基于 Python 的 Binance 现货网格交易机器人，专为小额（200~300 RMB）、长期、稳定挂机设计。

**不做合约、不做杠杆、不追求暴利。**

---

## 功能

- 网格自动买卖（BTC/USDT）
- Binance Spot Testnet / Real 双模式，代码级隔离
- 多重风险控制（持仓上限、挂单上限、防重复下单、价格异常暂停）
- Telegram 通知（启动/停止/成交/错误/每日收益）
- SQLite 本地数据库，崩溃后可恢复状态
- systemd 管理，开机自启 + 崩溃自动重启

---

## 项目结构

```
Quan/
├── main.py                   # 主入口
├── .env.example              # 环境变量模板
├── requirements.txt          # Python 依赖
├── config/
│   └── settings.py           # 配置加载
├── core/
│   ├── exchange.py           # Binance API (ccxt)
│   ├── grid_strategy.py      # 网格策略
│   ├── risk_manager.py       # 风险控制
│   └── database.py           # SQLite 数据库
├── notifier/
│   └── telegram.py           # Telegram 通知
├── utils/
│   └── logger.py             # 日志系统
├── deploy/
│   ├── quan-bot.service      # systemd 服务文件
│   └── DEPLOY.md             # VPS 部署教程
├── logs/                     # 日志输出目录
└── data/                     # 数据库文件目录
```

---

## 快速开始（Windows 本地测试）

### 1. 安装依赖

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 配置

```powershell
copy .env.example .env
notepad .env
```

填入你的 Binance Testnet API Key：

```ini
TRADE_MODE=testnet
BINANCE_API_KEY=你的API_KEY
BINANCE_SECRET=你的SECRET
TELEGRAM_BOT_TOKEN=你的BOT_TOKEN      # 可选
TELEGRAM_CHAT_ID=你的CHAT_ID          # 可选
```

> Testnet API 注册地址：https://testnet.binance.vision/

### 3. 运行

```powershell
python main.py
```

看到配置摘要和 "进入主循环" 即为正常。

---

## Telegram 通知设置

### 创建 Bot

1. 在 Telegram 搜索 `@BotFather`
2. 发送 `/newbot`
3. 按提示输入 Bot 名称和用户名
4. 获得 Token（格式：`123456:ABC-DEF1234gh...`）
5. 将 Token 填入 `.env` 的 `TELEGRAM_BOT_TOKEN`

### 获取 Chat ID

1. 在 Telegram 搜索 `@userinfobot`
2. 发送 `/start`
3. 获得你的 Chat ID（一串数字）
4. 将 Chat ID 填入 `.env` 的 `TELEGRAM_CHAT_ID`

### 测试消息

1. 确保 `.env` 中 Token 和 Chat ID 填写正确
2. 启动机器人，应收到启动通知
3. 或运行以下命令测试：

```python
python -c "
from dotenv import load_dotenv; load_dotenv()
import os, requests
token = os.getenv('TELEGRAM_BOT_TOKEN')
chat_id = os.getenv('TELEGRAM_CHAT_ID')
url = f'https://api.telegram.org/bot{token}/sendMessage'
r = requests.post(url, json={'chat_id': chat_id, 'text': '测试消息'})
print(r.status_code, r.json())
"
```

---

## VPS 部署

详见 [deploy/DEPLOY.md](deploy/DEPLOY.md)

```bash
# VPS 上快速启动
git clone <你的仓库> quan
cd quan
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env           # 填写配置
python main.py      # 测试运行
sudo cp deploy/quan-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now quan-bot
```

---

## 安全提醒

- **绝对不要把 `.env` 上传到 GitHub**
- `.gitignore` 已排除 `.env`、`logs/`、`*.db`
- 真实交易 API Key 不要勾选提现权限
- 正式使用前请在 Testnet 测试至少 1 周
- 小额起步，不超过可承受亏损范围

---

## 风险声明

本软件仅用于学习和研究目的。加密货币交易存在风险，使用真实资金交易前请确保你已充分理解风险。作者不对任何交易损失负责。
