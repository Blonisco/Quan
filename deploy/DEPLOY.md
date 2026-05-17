# Quan VPS 部署教程

> 目标系统：Ubuntu 24.04

---

## 第 1 步：安装 Python 3.11

```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3-pip git
```

## 第 2 步：从 GitHub 拉取代码

```bash
cd ~
git clone https://github.com/你的用户名/你的仓库名.git quan
cd quan
```

## 第 3 步：创建虚拟环境并安装依赖

```bash
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 第 4 步：配置 .env 文件

```bash
cp .env.example .env
nano .env
```

填写以下内容：

```ini
# 测试网模式（安全）
TRADE_MODE=testnet

# Binance API（注册地址见下方）
BINANCE_API_KEY=你的API_KEY
BINANCE_SECRET=你的SECRET

# Telegram 通知
TELEGRAM_BOT_TOKEN=你的BOT_TOKEN
TELEGRAM_CHAT_ID=你的CHAT_ID
```

**Testnet API 获取：** https://testnet.binance.vision/

---

## 第 5 步：测试运行（确保一切正常）

```bash
source venv/bin/activate
python main.py
```

看到以下输出说明成功：

```
==================================================
  交易模式   : TESTNET (测试网)
  交易对     : BTC/USDT
  网格区间   : 80000.0 - 120000.0 USDT
  ...
==================================================
```

如果报错 `BINANCE_API_KEY 和 BINANCE_SECRET 未配置`，说明 .env 没有填对。

按 Ctrl+C 停止。

---

## 第 6 步：安装 systemd 服务

### 6.1 修改 service 文件中的路径和用户名

```bash
nano deploy/quan-bot.service
```

确认以下两行路径正确：

```
User=ubuntu                            # 你的 Linux 用户名
WorkingDirectory=/home/ubuntu/quan     # 你的项目路径
ExecStart=/home/ubuntu/quan/venv/bin/python main.py
```

### 6.2 复制到 systemd 目录

```bash
sudo cp deploy/quan-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
```

### 6.3 启动服务

```bash
sudo systemctl start quan-bot
sudo systemctl enable quan-bot    # 开机自启
```

---

## 第 7 步：日常管理命令

```bash
# 查看运行状态
sudo systemctl status quan-bot

# 查看实时日志
sudo journalctl -u quan-bot -f

# 查看最近 50 条日志
sudo journalctl -u quan-bot -n 50

# 停止机器人
sudo systemctl stop quan-bot

# 重启机器人
sudo systemctl restart quan-bot

# 查看今日错误
sudo journalctl -u quan-bot --since today | grep ERROR
```

---

## 第 8 步：切换到真实交易

> **⚠️ 警告：真金白银，确认以下所有项后再切换！**

1. 在 Testnet 测试至少 **1 周**，确认逻辑正确
2. 前往 https://www.binance.com/ 创建现货 API Key（**不要勾选提现权限**）
3. 修改 `.env`：

```ini
TRADE_MODE=real
BINANCE_API_KEY=你的真实API_KEY
BINANCE_SECRET=你的真实SECRET
```

4. 重启：

```bash
sudo systemctl restart quan-bot
```

---

## 常见问题排查

| 问题 | 解决方法 |
|------|----------|
| `BINANCE_API_KEY 未配置` | `.env` 文件不存在或格式错误，检查 `nano .env` |
| `ccxt.NetworkError` | VPS 网络问题，检查能否 `ping api.binance.com` |
| `TRADE_MODE 必须为 testnet 或 real` | `.env` 中 TRADE_MODE 值不正确 |
| 服务启动后立即退出 | `sudo journalctl -u quan-bot -n 20` 查看错误日志 |
| 权限错误 | `chmod 600 .env` 确保 .env 只有当前用户可读 |

### 查看日志文件（程序内部日志，非 systemd）

```bash
ls logs/              # 查看日志文件列表
tail -f logs/quan_*.log   # 实时查看今日日志
tail -f logs/error_*.log  # 查看错误日志
```

---

## GitHub 工作流

```bash
# 本地开发（Windows PowerShell）
git add .
git commit -m "描述修改内容"
git push

# VPS 拉取更新
ssh ubuntu@你的VPS_IP
cd ~/quan
git pull
sudo systemctl restart quan-bot
```
