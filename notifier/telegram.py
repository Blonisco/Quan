"""
Telegram 通知模块
通过 BotFather Bot 发送交易通知、错误告警、每日收益等
支持 /status /report 等交互命令
"""

import html
import requests
from datetime import datetime
from config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

# Telegram Bot API 地址
API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


class Notifier:
    """Telegram 通知器"""

    def __init__(self):
        self._enabled = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)
        self._last_update_id = self._get_latest_update_id()
        if not self._enabled:
            print("[NOTIFIER] Telegram 未配置，通知功能已禁用")

    def _get_latest_update_id(self) -> int:
        """获取当前最新 update_id，跳过启动前的旧消息"""
        if not self._enabled:
            return 0
        try:
            resp = requests.get(
                f"{API_URL}/getUpdates",
                params={"offset": -1, "timeout": 2},
                timeout=5,
            )
            if resp.status_code == 200:
                data = resp.json()
                updates = data.get("result", [])
                if updates:
                    return updates[-1]["update_id"]
        except Exception:
            pass
        return 0

    # --------------------------------------------------
    # 底层发送方法
    # --------------------------------------------------

    def _send(self, text: str, reply_to: int | None = None) -> bool:
        """
        发送消息到 Telegram

        Args:
            text: 消息内容，支持 HTML 格式
            reply_to: 回复的消息 ID（用于命令回复）

        Returns:
            bool: 是否发送成功
        """
        if not self._enabled:
            return False

        try:
            payload = {
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text,
                "parse_mode": "HTML",
            }
            if reply_to:
                payload["reply_to_message_id"] = reply_to
            resp = requests.post(
                f"{API_URL}/sendMessage",
                json=payload,
                timeout=10,
            )
            if resp.status_code != 200:
                print(f"[NOTIFIER] 发送失败: HTTP {resp.status_code} - {resp.text}")
                return False
            return True
        except requests.RequestException as e:
            print(f"[NOTIFIER] 网络错误: {e}")
            return False

    @staticmethod
    def _now() -> str:
        """当前时间字符串"""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # --------------------------------------------------
    # 命令轮询
    # --------------------------------------------------

    def check_commands(self) -> list[dict]:
        """
        获取未处理的 Telegram 命令

        Returns:
            list[dict]: [{"command": "/status", "chat_id": ..., "message_id": ...}, ...]
        """
        if not self._enabled:
            return []

        try:
            resp = requests.get(
                f"{API_URL}/getUpdates",
                params={
                    "offset": self._last_update_id + 1,
                    "timeout": 5,
                },
                timeout=10,
            )
            if resp.status_code != 200:
                print(f"[NOTIFIER] getUpdates 失败: HTTP {resp.status_code} - {resp.text[:200]}")
                return []

            data = resp.json()
            if not data.get("ok"):
                print(f"[NOTIFIER] getUpdates 返回错误: {data}")
                return []

            updates = data.get("result", [])
            commands = []
            for upd in updates:
                self._last_update_id = upd["update_id"]
                msg = upd.get("message", {})
                text = msg.get("text", "")
                if text.startswith("/"):
                    commands.append({
                        "command": text.split()[0].lower().strip(),
                        "chat_id": msg["chat"]["id"],
                        "message_id": msg["message_id"],
                    })
            if commands:
                print(f"[NOTIFIER] 收到命令: {[c['command'] for c in commands]}")
            return commands
        except Exception as e:
            print(f"[NOTIFIER] getUpdates 异常: {e}")
            return []

    # --------------------------------------------------
    # 命令响应
    # --------------------------------------------------

    def reply_status(self, message_id: int, trade_mode: str,
                     btc_balance: float, usdt_balance: float,
                     open_orders: int, grid_low: float, grid_high: float,
                     grid_count: int, net_btc: float,
                     strategy_mode: str = "grid",
                     drawdown: float = 0.0,
                     consecutive: int = 0) -> None:
        """响应 /status 命令"""
        mode_map = {"grid": "🟡 震荡网格", "trend_long": "🟢 上涨趋势",
                     "risk_off": "🔴 下跌避险"}
        mode_label = mode_map.get(strategy_mode, strategy_mode)
        text = (
            f"<b>📊 当前状态</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"交易模式: <b>{trade_mode}</b>\n"
            f"策略状态: <b>{mode_label}</b>\n"
            f"BTC 余额: {btc_balance:.6f} BTC\n"
            f"USDT 余额: {usdt_balance:.2f} USDT\n"
            f"策略持仓: {net_btc:.6f} BTC\n"
            f"挂单数量: {open_orders}\n"
            f"回撤幅度: {drawdown*100:.1f}%\n"
            f"连续同向: {consecutive} 笔\n"
            f"网格区间: {grid_low} - {grid_high}\n"
            f"网格数量: {grid_count}\n"
            f"查询时间: {self._now()}\n"
            f"━━━━━━━━━━━━━━━"
        )
        self._send(text, reply_to=message_id)

    def reply_report(self, message_id: int, today: str,
                     trade_count: int, net_btc: float,
                     btc_balance: float, usdt_balance: float,
                     strategy_mode: str = "grid") -> None:
        """响应 /report 命令"""
        mode_map = {"grid": "震荡网格", "trend_long": "上涨趋势",
                     "risk_off": "下跌避险"}
        text = (
            f"<b>📋 今日交易报告 ({today})</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"策略状态: {mode_map.get(strategy_mode, strategy_mode)}\n"
            f"今日成交: {trade_count} 笔\n"
            f"策略持仓: {net_btc:.6f} BTC\n"
            f"BTC 余额: {btc_balance:.6f} BTC\n"
            f"USDT 余额: {usdt_balance:.2f} USDT\n"
            f"查询时间: {self._now()}\n"
            f"━━━━━━━━━━━━━━━"
        )
        self._send(text, reply_to=message_id)

    def reply_help(self, message_id: int) -> None:
        """响应 /help 命令"""
        text = (
            f"<b>🤖 Quan 机器人命令</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"/status - 查看当前状态\n"
            f"/report - 查看今日交易报告\n"
            f"/help   - 显示此帮助\n"
            f"━━━━━━━━━━━━━━━"
        )
        self._send(text, reply_to=message_id)

    # --------------------------------------------------
    # 通知类型
    # --------------------------------------------------

    def startup(self, mode: str, symbol: str, low: float, high: float,
                grid_count: int, amount: float) -> None:
        """启动通知"""
        text = (
            f"<b>🤖 量化机器人已启动</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"模式: <b>{mode}</b>\n"
            f"交易对: {symbol}\n"
            f"网格区间: {low} - {high} USDT\n"
            f"网格数量: {grid_count}\n"
            f"每格金额: {amount} USDT\n"
            f"启动时间: {self._now()}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"发送 /status 查看状态 | /help 查看命令"
        )
        self._send(text)

    def shutdown(self, reason: str = "正常关闭") -> None:
        """停止通知"""
        text = (
            f"<b>🛑 量化机器人已停止</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"原因: {html.escape(reason)}\n"
            f"停止时间: {self._now()}\n"
            f"━━━━━━━━━━━━━━━"
        )
        self._send(text)

    def error(self, error_msg: str, location: str = "unknown") -> None:
        """错误通知"""
        text = (
            f"<b>⚠️ 错误告警</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"位置: {html.escape(location)}\n"
            f"错误: {html.escape(error_msg)}\n"
            f"时间: {self._now()}\n"
            f"━━━━━━━━━━━━━━━"
        )
        self._send(text)

# 全局单例，供各模块引用
notifier = Notifier()
