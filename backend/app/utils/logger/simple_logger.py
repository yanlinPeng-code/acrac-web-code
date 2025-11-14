"""
简单日志模块
提供统一的日志记录功能
"""

import logging
import sys
from pathlib import Path
from typing import Optional


def setup_logging(
    level: str = "INFO",
    log_to_file: bool = False,
    log_dir: str = "logs"
) -> None:
    """
    配置全局日志
    
    Args:
        level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_to_file: 是否输出到文件
        log_dir: 日志文件目录
    """
    # 日志格式
    log_format = "[%(asctime)s] %(levelname)s [%(name)s] %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    
    # 配置根日志器
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format=log_format,
        datefmt=date_format,
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    
    # 可选：输出到文件
    if log_to_file:
        log_path = Path(log_dir)
        log_path.mkdir(exist_ok=True)
        
        file_handler = logging.FileHandler(
            log_path / "app.log",
            encoding="utf-8"
        )
        file_handler.setFormatter(
            logging.Formatter(log_format, datefmt=date_format)
        )
        logging.getLogger().addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """
    获取日志记录器
    
    Args:
        name: 日志记录器名称（通常使用 __name__）
    
    Returns:
        日志记录器实例
    
    使用示例:
        logger = get_logger(__name__)
        logger.info("这是一条信息日志")
        logger.error("这是一条错误日志")
    """
    return logging.getLogger(name)


# 预定义的日志记录器
app_logger = get_logger("app")
api_logger = get_logger("api")
db_logger = get_logger("db")
