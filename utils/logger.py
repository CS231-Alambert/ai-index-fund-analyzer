import logging
from logging.handlers import RotatingFileHandler
import os
from config import LOG_CONFIG
from utils.file_utils import ensure_dir


def setup_logger(name=None):
    """设置日志记录器"""
    # 确保日志目录存在
    log_dir = os.path.dirname(LOG_CONFIG['file_path'])
    ensure_dir(log_dir)
    
    # 创建日志记录器
    logger = logging.getLogger(name or __name__)
    logger.setLevel(LOG_CONFIG['level'])
    
    # 避免重复添加处理器
    if not logger.handlers:
        # 创建控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(LOG_CONFIG['level'])
        
        # 创建文件处理器（带轮转）
        file_handler = RotatingFileHandler(
            LOG_CONFIG['file_path'],
            maxBytes=LOG_CONFIG['max_bytes'],
            backupCount=LOG_CONFIG['backup_count'],
            encoding='utf-8'
        )
        file_handler.setLevel(LOG_CONFIG['level'])
        
        # 创建日志格式
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # 添加格式到处理器
        console_handler.setFormatter(formatter)
        file_handler.setFormatter(formatter)
        
        # 添加处理器到日志记录器
        logger.addHandler(console_handler)
        logger.addHandler(file_handler)
    
    return logger


# 创建默认日志记录器
logger = setup_logger()
