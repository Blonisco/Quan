"""
SQLite 数据库模块
记录订单、成交、收益、错误日志、程序状态
支持崩溃后恢复
"""

import sqlite3
import json
from datetime import datetime
from config.settings import DB_PATH, DATA_DIR


class Database:
    """数据库管理类"""

    def __init__(self):
        # 确保 data 目录存在
        DATA_DIR.mkdir(parents=True, exist_ok=True)

        self.conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self._create_tables()

    def _create_tables(self):
        """创建所有表（如果不存在）"""
        cursor = self.conn.cursor()

        # 订单表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT UNIQUE NOT NULL,
                side TEXT NOT NULL CHECK(side IN ('BUY', 'SELL')),
                price REAL NOT NULL,
                amount REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        # 成交表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id TEXT UNIQUE NOT NULL,
                order_id TEXT NOT NULL,
                side TEXT NOT NULL CHECK(side IN ('BUY', 'SELL')),
                price REAL NOT NULL,
                amount REAL NOT NULL,
                fee REAL DEFAULT 0,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (order_id) REFERENCES orders(order_id)
            )
        """)

        # 每日收益表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_pnl (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT UNIQUE NOT NULL,
                pnl_usdt REAL DEFAULT 0,
                trade_count INTEGER DEFAULT 0,
                btc_balance REAL DEFAULT 0,
                usdt_balance REAL DEFAULT 0,
                updated_at TEXT NOT NULL
            )
        """)

        # 错误日志表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS error_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                location TEXT NOT NULL,
                message TEXT NOT NULL
            )
        """)

        # 程序状态表（用于崩溃恢复）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bot_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        self.conn.commit()

    # ============================================
    # 订单操作
    # ============================================

    def insert_order(self, order_id: str, side: str, price: float,
                     amount: float, status: str = "open") -> None:
        """记录新订单"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.conn.execute(
            """
            INSERT OR IGNORE INTO orders (order_id, side, price, amount, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (order_id, side, price, amount, status, now, now),
        )
        self.conn.commit()

    def update_order_status(self, order_id: str, status: str) -> None:
        """更新订单状态"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.conn.execute(
            "UPDATE orders SET status = ?, updated_at = ? WHERE order_id = ?",
            (status, now, order_id),
        )
        self.conn.commit()

    def get_open_orders(self) -> list[dict]:
        """获取所有未成交的订单"""
        rows = self.conn.execute(
            "SELECT * FROM orders WHERE status = 'open'"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_order_by_id(self, order_id: str) -> dict | None:
        """根据订单 ID 查找订单"""
        row = self.conn.execute(
            "SELECT * FROM orders WHERE order_id = ?", (order_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_all_orders(self, limit: int = 100) -> list[dict]:
        """获取最近订单"""
        rows = self.conn.execute(
            "SELECT * FROM orders ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ============================================
    # 成交操作
    # ============================================

    def insert_trade(self, trade_id: str, order_id: str, side: str,
                     price: float, amount: float, fee: float,
                     timestamp: str) -> None:
        """记录成交"""
        self.conn.execute(
            """
            INSERT OR IGNORE INTO trades (trade_id, order_id, side, price, amount, fee, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (trade_id, order_id, side, price, amount, fee, timestamp),
        )
        self.conn.commit()

    def get_trades_for_date(self, date: str) -> list[dict]:
        """获取某日的所有成交"""
        rows = self.conn.execute(
            "SELECT * FROM trades WHERE date(timestamp) = ? ORDER BY id ASC",
            (date,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ============================================
    # 收益操作
    # ============================================

    def upsert_daily_pnl(self, date: str, pnl_usdt: float,
                         trade_count: int, btc_balance: float,
                         usdt_balance: float) -> None:
        """插入或更新当日收益"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.conn.execute(
            """
            INSERT INTO daily_pnl (date, pnl_usdt, trade_count, btc_balance, usdt_balance, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                pnl_usdt = excluded.pnl_usdt,
                trade_count = excluded.trade_count,
                btc_balance = excluded.btc_balance,
                usdt_balance = excluded.usdt_balance,
                updated_at = excluded.updated_at
            """,
            (date, pnl_usdt, trade_count, btc_balance, usdt_balance, now),
        )
        self.conn.commit()

    def get_daily_pnl(self, date: str) -> dict | None:
        """获取某日收益"""
        row = self.conn.execute(
            "SELECT * FROM daily_pnl WHERE date = ?", (date,)
        ).fetchone()
        return dict(row) if row else None

    # ============================================
    # 错误日志
    # ============================================

    def log_error(self, location: str, message: str) -> None:
        """记录错误"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.conn.execute(
            "INSERT INTO error_logs (timestamp, location, message) VALUES (?, ?, ?)",
            (now, location, message),
        )
        self.conn.commit()

    def get_recent_errors(self, limit: int = 20) -> list[dict]:
        """获取最近错误"""
        rows = self.conn.execute(
            "SELECT * FROM error_logs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ============================================
    # 程序状态（崩溃恢复）
    # ============================================

    def save_state(self, key: str, value: dict) -> None:
        """保存程序状态"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.conn.execute(
            "INSERT OR REPLACE INTO bot_state (key, value, updated_at) VALUES (?, ?, ?)",
            (key, json.dumps(value), now),
        )
        self.conn.commit()

    def load_state(self, key: str) -> dict | None:
        """读取程序状态"""
        row = self.conn.execute(
            "SELECT value FROM bot_state WHERE key = ?", (key,)
        ).fetchone()
        if row:
            return json.loads(row["value"])
        return None

    def get_all_states(self) -> dict:
        """读取所有状态"""
        rows = self.conn.execute("SELECT key, value FROM bot_state").fetchall()
        return {r["key"]: json.loads(r["value"]) for r in rows}

    def get_weighted_avg_entry_price(self) -> float | None:
        """计算已成交买单的加权均价，用于趋势止盈"""
        rows = self.conn.execute(
            "SELECT price, amount FROM orders WHERE side='BUY' AND status='closed'"
        ).fetchall()
        if not rows:
            return None
        total_cost = sum(r["price"] * r["amount"] for r in rows)
        total_btc = sum(r["amount"] for r in rows)
        if total_btc <= 0:
            return None
        return total_cost / total_btc

    def get_net_btc_position(self) -> float:
        """计算策略的净 BTC 持仓（已成交买单 - 已成交卖单）"""
        buy_row = self.conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM orders WHERE side = 'BUY' AND status = 'closed'"
        ).fetchone()
        sell_row = self.conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM orders WHERE side = 'SELL' AND status = 'closed'"
        ).fetchone()
        return buy_row[0] - sell_row[0]

    # ============================================
    # 清理
    # ============================================

    def close(self):
        """关闭数据库连接"""
        self.conn.close()


# 全局数据库实例
db = Database()
