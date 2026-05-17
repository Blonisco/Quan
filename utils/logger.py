"""
日志系统模块
同时输出到控制台和文件，支持 INFO / WARNING / ERROR 级别
"""

import logging
import sys
from pathlib import Path
from datetime import datetime
from config.settings import LOG_DIR

# Windows 控制台可能使用 GBK 编码，设置 stdout 为 UTF-8 避免乱码
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def setup_logger(
    name: str = "quan",
    level: int = logging.INFO,
) -> logging.Logger:
    """
    配置并返回 Logger 实例

    Args:
        name: Logger 名称
        level: 日志级别

    Returns:
        logging.Logger: 配置好的 Logger
    """

    # 确保日志目录存在
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # 避免重复添加 handler
    if logger.handlers:
        return logger

    # ---------- 日志格式 ----------
    # 文件格式：带时间戳和级别
    file_fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # 控制台格式：简洁
    console_fmt = logging.Formatter(
        "%(asctime)s [%(levelname)-5s] %(message)s",
        datefmt="%H:%M:%S",
    )

    # ---------- 文件 Handler ----------
    # 按日期分文件：logs/quan_2026-05-17.log
    today = datetime.now().strftime("%Y-%m-%d")
    file_handler = logging.FileHandler(
        LOG_DIR / f"quan_{today}.log",
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)  # 文件记录所有级别
    file_handler.setFormatter(file_fmt)
    logger.addHandler(file_handler)

    # ---------- 控制台 Handler ----------
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_fmt)
    logger.addHandler(console_handler)

    # ---------- 错误日志单独文件 ----------
    error_handler = logging.FileHandler(
        LOG_DIR / f"error_{today}.log",
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(file_fmt)
    logger.addHandler(error_handler)

    return logger


def get_logger(name: str = "quan") -> logging.Logger:
    """获取已配置的 Logger（如果不存在则创建）"""
    logger = logging.getLogger(name)
    if not logger.handlers:
        return setup_logger(name)
    return logger


# 全局默认 Logger
logger = setup_logger()
