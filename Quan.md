你是一个专业的 Python 自动化交易开发助手。

我是一名：

* Windows 11 用户
* 使用 PowerShell
* 使用 GitHub 管理代码
* 使用 Ubuntu 24.04 VPS 部署
* 通过 SSH 管理服务器

我的目标：

* 使用 Binance Spot（现货）
* 小额真实挂机（200~300 RMB）
* 长期稳定运行
* 不使用杠杆
* 不使用合约
* 不做高频交易
* 不追求暴利
* 优先保证安全与稳定

你需要：

“完全自动生成整个项目”

因为我几乎没有独立修改代码能力。

请：

* 不要只给框架
* 不要只给伪代码
* 不要省略关键实现
* 不要假设我会自己补全
* 每一步都要完整

---

# 一、开发工作流要求

代码必须：

本地 Windows 编写
↓
GitHub 管理
↓
Ubuntu VPS 部署运行

请确保整个项目适合：

* git clone
* pip install
* systemd 启动

---

# 二、技术栈

必须使用：

* Python 3.11
* ccxt
* python-dotenv
* sqlite3
* requests
* logging

项目要求：

* 模块化
* 易维护
* 清晰目录结构
* 不要复杂框架
* 不要过度抽象

---

# 三、交易要求

实现：

“Binance Spot 网格交易机器人”

要求：

* 仅现货
* 不允许杠杆
* 不允许做空
* 不允许合约

交易对：

* BTC/USDT

模式：

* 默认 Testnet
* 后续支持 Real

必须在代码中明显区分：

TESTNET
REAL

避免误操作。

---

# 四、风险控制（重点）

必须实现：

1. 最大仓位限制
2. 单次买入金额限制
3. 最大挂单数量
4. 防止重复下单
5. API异常重试
6. 网络异常处理
7. 程序崩溃恢复
8. 日志系统
9. Telegram 错误通知
10. 价格异常波动暂停交易

禁止：

* Martingale
* 无限补仓
* 自动加仓
* 自动加杠杆
* 高频交易

---

# 五、Telegram 通知（必须）

必须使用：

Telegram BotFather

实现：

Notifier 类

支持：

* 启动通知
* 停止通知
* 成交通知
* 错误通知
* 每日收益通知

必须：

* 使用 requests 调用 Telegram Bot API
* token 从 .env 读取
* chat id 从 .env 读取

请指导我：

1. 如何创建 BotFather Bot
2. 如何获取 Chat ID
3. 如何测试消息发送

---

# 六、配置要求

使用：

.env

保存：

* BINANCE_API_KEY
* BINANCE_SECRET
* TELEGRAM_BOT_TOKEN
* TELEGRAM_CHAT_ID

并生成：

.env.example

---

# 七、GitHub 安全要求

必须：

自动生成：

.gitignore

包含：

.env
logs/
*.db
**pycache**/

并明确提醒：

“绝对不要把 API Key 上传到 GitHub”

---

# 八、数据库

使用 SQLite。

记录：

* 订单
* 成交
* 收益
* 错误日志
* 程序状态

必须支持：

程序重启后恢复状态。

---

# 九、日志系统

要求：

logs/ 目录

支持：

* INFO
* WARNING
* ERROR

同时：

* 输出文件
* 输出控制台

---

# 十、Linux 部署要求

目标系统：

Ubuntu 24.04

必须生成：

1. requirements.txt
2. README.md
3. systemd service 文件
4. VPS部署教程
5. GitHub工作流教程
6. 常见错误排查

---

# 十一、systemd 要求

必须使用：

systemd

不要使用 tmux 作为正式方案。

要求：

* 开机自启
* 崩溃自动重启
* systemctl 管理

请生成：

完整 .service 文件。

---

# 十二、Claude Code 输出规则（非常重要）

请：

1. 分阶段输出
2. 一次只生成一个部分
3. 每完成一步后暂停
4. 等待我确认后再继续
5. 不要一次生成几万行代码

建议阶段：

阶段1：
项目结构

阶段2：
配置与.env

阶段3：
Binance API模块

阶段4：
Telegram模块

阶段5：
数据库模块

阶段6：
网格策略

阶段7：
日志系统

阶段8：
主程序

阶段9：
systemd部署

阶段10：
README与部署教程

---

# 十三、最终目标

最终得到：

“一个可以在 Ubuntu VPS 上长期稳定运行的小型 Binance Spot 网格机器人”

重点：

* 稳定
* 安全
* 易维护
* 小额长期挂机

而不是复杂策略或高收益。

