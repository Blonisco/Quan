"""
Quan - Binance Spot 网格交易机器人
主入口程序
"""

import sys
import time
import signal
import traceback
from datetime import datetime

from utils.logger import setup_logger
from config.settings import (
    IS_TESTNET,
    SYMBOL,
    GRID_LOW_PRICE,
    GRID_HIGH_PRICE,
    GRID_COUNT,
    ORDER_AMOUNT_USDT,
    LOOP_INTERVAL_SECONDS,
    print_config,
)
from core.exchange import test_connection, fetch_balance
from core.grid_strategy import GridStrategy
from core.database import db
from notifier.telegram import notifier

# 初始化日志
logger = setup_logger()

# 运行标志
_running = True


def signal_handler(sig, frame):
    """处理 Ctrl+C 和终止信号"""
    global _running
    logger.info("收到停止信号，准备退出...")
    _running = False


def main():
    """主函数"""
    global _running

    # ============================================
    # 1. 打印配置
    # ============================================
    print_config()

    mode_label = "TESTNET (测试网)" if IS_TESTNET else "REAL (真实交易!!!)"
    logger.info(f"当前模式: {mode_label}")

    # 真实模式二次确认
    if not IS_TESTNET:
        logger.warning("!!! 当前为 REAL 模式，真金白银！")
        logger.warning("请确认 .env 中 TRADE_MODE=real 是有意设定的")
        logger.warning("如需测试请改为 TRADE_MODE=testnet")

    # ============================================
    # 2. 测试 API 连接
    # ============================================
    logger.info("正在测试 Binance API 连接...")
    if not test_connection():
        logger.error("Binance API 连接失败，请检查 API Key 和网络")
        notifier.error("API 连接失败", "main.startup")
        sys.exit(1)
    logger.info("Binance API 连接成功")

    # ============================================
    # 3. 查询余额
    # ============================================
    try:
        btc_balance = fetch_balance("BTC")
        usdt_balance = fetch_balance("USDT")
        logger.info(f"账户余额: {btc_balance:.6f} BTC, {usdt_balance:.2f} USDT")
    except Exception as e:
        logger.error(f"查询余额失败: {e}")
        notifier.error(str(e), "main.balance")

    # ============================================
    # 4. 初始化网格策略
    # ============================================
    logger.info("初始化网格策略...")
    strategy = GridStrategy()
    logger.info("网格策略初始化完成")

    # ============================================
    # 5. 发送启动通知
    # ============================================
    notifier.startup(
        mode=mode_label,
        symbol=SYMBOL,
        low=GRID_LOW_PRICE,
        high=GRID_HIGH_PRICE,
        grid_count=GRID_COUNT,
        amount=ORDER_AMOUNT_USDT,
    )

    # ============================================
    # 6. 保存启动状态
    # ============================================
    db.save_state("last_startup", {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "mode": mode_label,
    })

    # ============================================
    # 7. 主循环
    # ============================================
    logger.info(f"进入主循环（间隔 {LOOP_INTERVAL_SECONDS}s），按 Ctrl+C 停止")
    logger.info("-" * 40)

    tick_count = 0
    last_status_time = time.time()
    last_summary_time = time.time()
    last_report_date = datetime.now().strftime("%Y-%m-%d")

    while _running:
        tick_count += 1
        loop_start = time.time()

        try:
            strategy.tick()

            # Telegram 命令处理
            for cmd in notifier.check_commands():
                try:
                    if cmd["command"] == "/status":
                        status = strategy.get_status()
                        net_btc = db.get_net_btc_position()
                        notifier.reply_status(
                            cmd["message_id"], mode_label,
                            status["btc_balance"], status["usdt_balance"],
                            status["open_orders"],
                            status["grid_low"], status["grid_high"],
                            status["grid_count"], net_btc,
                            status["mode"], status["drawdown"],
                            status["consecutive_dir"],
                        )
                    elif cmd["command"] == "/report":
                        status = strategy.get_status()
                        net_btc = db.get_net_btc_position()
                        today = datetime.now().strftime("%Y-%m-%d")
                        trades = db.get_trades_for_date(today)
                        notifier.reply_report(
                            cmd["message_id"], today,
                            len(trades), net_btc,
                            status["btc_balance"], status["usdt_balance"],
                            status["mode"],
                        )
                    elif cmd["command"] == "/help":
                        notifier.reply_help(cmd["message_id"])
                    else:
                        notifier._send(
                            f"未知命令: {cmd['command']}\n发送 /help 查看可用命令",
                            reply_to=cmd["message_id"],
                        )
                except Exception as e:
                    logger.error(f"处理命令 {cmd['command']} 失败: {e}")

            # 每 6 小时推送一次状态摘要
            if time.time() - last_summary_time >= 21600:  # 6 小时
                last_summary_time = time.time()
                try:
                    status = strategy.get_status()
                    today = datetime.now().strftime("%Y-%m-%d")
                    trades = db.get_trades_for_date(today)
                    notifier.reply_report(
                        0, today,  # message_id=0 不回复任何消息
                        len(trades), db.get_net_btc_position(),
                        status["btc_balance"], status["usdt_balance"],
                        status["mode"],
                    )
                except Exception as e:
                    logger.error(f"定时摘要发送失败: {e}")

            # 每日收益报告（日期变更时触发）
            today = datetime.now().strftime("%Y-%m-%d")
            if today != last_report_date:
                report_date = last_report_date  # 报告刚过去的那天
                last_report_date = today
                try:
                    status = strategy.get_status()
                    trades = db.get_trades_for_date(report_date)
                    trade_count = len(trades)
                    pnl_data = db.get_daily_pnl(report_date)
                    pnl = pnl_data["pnl_usdt"] if pnl_data else 0.0
                    notifier.reply_report(
                        0, report_date, trade_count,
                        db.get_net_btc_position(),
                        status["btc_balance"], status["usdt_balance"],
                        status["mode"],
                    )
                    logger.info(f"已发送每日收益报告 ({report_date})")
                except Exception as e:
                    logger.error(f"每日报告发送失败: {e}")

            # 每小时打印一次状态摘要
            if time.time() - last_status_time >= 3600:
                status = strategy.get_status()
                logger.info(
                    f"[{status['mode']}] BTC: {status['btc_balance']:.6f} | "
                    f"USDT: {status['usdt_balance']:.2f} | "
                    f"挂单: {status['open_orders']} | "
                    f"回撤: {status['drawdown']*100:.1f}% | "
                    f"同向: {status['consecutive_dir']}笔"
                )
                last_status_time = time.time()

        except KeyboardInterrupt:
            logger.info("用户中断")
            break
        except Exception as e:
            tb = traceback.format_exc()
            logger.error(f"主循环异常:\n{tb}")
            db.log_error("main.loop", str(e))
            notifier.error(str(e), "main.loop")

        # 控制循环间隔
        elapsed = time.time() - loop_start
        sleep_time = max(LOOP_INTERVAL_SECONDS - elapsed, 1)
        time.sleep(sleep_time)

    # ============================================
    # 8. 退出清理
    # ============================================
    logger.info(f"共运行 {tick_count} 轮")
    logger.info("正在退出...")

    db.save_state("last_shutdown", {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "tick_count": tick_count,
    })

    notifier.shutdown("正常关闭")
    db.close()
    logger.info("已退出，再见。")


if __name__ == "__main__":
    # 注册信号处理
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    main()
