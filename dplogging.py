#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import sys
from pathlib import Path

def setup_logger(name: str = 'my_app', file_level: int = logging.DEBUG, console_level: int = logging.INFO) -> logging.Logger:
    """
    配置并返回一个 logger 实例，该实例同时输出到控制台和文件。

    Args:
        name (str): logger 的名称。
        level (int): logger 的日志级别 (例如 logging.INFO, logging.DEBUG)。

    Returns:
        logging.Logger: 配置好的 logger 实例。
    """
    # 确保日志文件所在的目录存在
    log_path = Path(f"{name}.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # 创建一个 logger
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # 如果 logger 已有 handlers，先清除，防止重复输出
    if logger.hasHandlers():
        logger.handlers.clear()

    # 创建一个 formatter，定义日志的格式
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 创建一个 handler，用于写入日志文件
    file_handler = logging.FileHandler(log_path, encoding='utf-8', mode='a')
    file_handler.setLevel(file_level)
    file_handler.setFormatter(formatter)

    # 创建一个 handler，用于输出到控制台 (标准输出)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(console_level)
    stream_handler.setFormatter(formatter)

    # 给 logger 添加 handler
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)

    return logger

# 示例用法
if __name__ == '__main__':
    # 创建一个名为 'logs' 的子目录来存放日志文件
    log_directory = Path(__file__).parent / "logs"

    # 获取 logger
    # 您可以为不同的模块设置不同的 logger
    main_logger = setup_logger('main_module', file_level=logging.DEBUG, console_level=logging.INFO)

    main_logger.debug("这是一条 debug 消息。它会出现在文件和控制台。")
    main_logger.info("这是一条 info 消息。")
    main_logger.warning("这是一条 warning 消息。")
    main_logger.error("发生了一个错误。")
    main_logger.critical("发生了一个严重错误。")

    print(f"\n日志已写入到: main_module.log")