# 指数市场分析应用配置文件

# 数据来源配置
DATA_SOURCES = {
    'default': {
        'base_url': 'https://finance.sina.com.cn',
        'robots_url': 'https://finance.sina.com.cn/robots.txt',
        'index_data_path': '/realstock/company/{code}/performance.shtml',
        'fund_flow_path': '/realstock/company/{code}/fundflow.shtml'
    },
    'eastmoney': {
        'base_url': 'https://quote.eastmoney.com',
        'robots_url': 'https://quote.eastmoney.com/robots.txt',
        'index_data_path': '/{market}{code}.html',
        'fund_flow_path': '/{market}{code}_2.html'
    }
}

# 缓存配置
CACHE_CONFIG = {
    'db_path': 'cache/index_data.db',
    'default_ttl': 3600,  # 默认缓存过期时间（秒）
    'max_retries': 3,      # 最大重试次数
    'retry_delay': 1       # 重试延迟（秒）
}

# 日志配置
LOG_CONFIG = {
    'level': 'INFO',
    'file_path': 'logs/app.log',
    'max_bytes': 10 * 1024 * 1024,  # 10MB
    'backup_count': 5
}

# 决策模型配置
DECISION_MODEL_CONFIG = {
    'indicators': {
        'pe': {'weight': 0.3, 'thresholds': {'strong_buy': 10, 'buy': 15, 'hold': 20, 'sell': 25}},
        'roe': {'weight': 0.25, 'thresholds': {'strong_buy': 15, 'buy': 10, 'hold': 5, 'sell': 0}},
        'turnover': {'weight': 0.15, 'thresholds': {'strong_buy': 2, 'buy': 5, 'hold': 10, 'sell': 15}},
        'fund_flow': {'weight': 0.3, 'thresholds': {'strong_buy': 5000, 'buy': 1000, 'hold': -1000, 'sell': -5000}}
    },
    'score_levels': {
        'strong_buy': (80, 100),
        'buy': (60, 80),
        'hold': (40, 60),
        'sell': (20, 40),
        'strong_sell': (0, 20)
    }
}

# 应用配置
APP_CONFIG = {
    'title': '指数市场分析应用',
    'description': '基于Python的指数市场分析工具，提供实时数据、估值分析和投资建议',
    'default_index': '000001',  # 默认上证指数
    'max_history_days': 365 * 5  # 最大历史数据天数
}

# 数据导出配置
EXPORT_CONFIG = {
    'default_folder': 'exports',
    'file_name_pattern': '{code}_{name}_{date}.csv',
    'encoding': 'utf-8-sig'
}
