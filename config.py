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

# 技术指标参数配置
TECHNICAL_INDICATOR_PARAMS = {
    'ma_periods': [5, 10, 20, 60],          # 移动平均线周期
    'ema_short': 12,                          # 短期EMA周期
    'ema_long': 26,                           # 长期EMA周期
    'fib_levels': [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0],  # 斐波那契回撤位
    'fib_lookback': 60,                       # 斐波那契高低点回溯天数
    'vwap_reset': 'daily',                    # VWAP重置周期
    'volume_ma_period': 20,                   # 成交量均线周期
    'price_action_lookback': 20,              # 价格行为回溯天数
    'price_action_swing_threshold': 0.03,     # 摆动高低点阈值 (3%)
    'ohlcv_days': 120,                        # 获取OHLCV数据的天数
}

# 决策模型配置
# 权重分配: 技术指标 70% / 基本面指标 30%
DECISION_MODEL_CONFIG = {
    'indicators': {
        # ===== 技术指标 (高权重, 总计 70%) =====
        'price_action': {
            'weight': 0.15,
            'category': 'technical',
            'thresholds': {'strong_buy': 80, 'buy': 65, 'hold': 45, 'sell': 30}
        },
        'fibonacci': {
            'weight': 0.10,
            'category': 'technical',
            'thresholds': {'strong_buy': 80, 'buy': 65, 'hold': 45, 'sell': 30}
        },
        'volume': {
            'weight': 0.12,
            'category': 'technical',
            'thresholds': {'strong_buy': 80, 'buy': 65, 'hold': 45, 'sell': 30}
        },
        'vwap': {
            'weight': 0.11,
            'category': 'technical',
            'thresholds': {'strong_buy': 75, 'buy': 60, 'hold': 40, 'sell': 25}
        },
        'ema': {
            'weight': 0.11,
            'category': 'technical',
            'thresholds': {'strong_buy': 80, 'buy': 65, 'hold': 40, 'sell': 25}
        },
        'ma': {
            'weight': 0.11,
            'category': 'technical',
            'thresholds': {'strong_buy': 80, 'buy': 65, 'hold': 40, 'sell': 25}
        },

        # ===== 基本面指标 (辅助参考, 总计 30%) =====
        'pe': {
            'weight': 0.10,
            'category': 'fundamental',
            'thresholds': {'strong_buy': 10, 'buy': 15, 'hold': 20, 'sell': 25}
        },
        'roe': {
            'weight': 0.08,
            'category': 'fundamental',
            'thresholds': {'strong_buy': 15, 'buy': 10, 'hold': 5, 'sell': 0}
        },
        'turnover': {
            'weight': 0.05,
            'category': 'fundamental',
            'thresholds': {'strong_buy': 2, 'buy': 5, 'hold': 10, 'sell': 15}
        },
        'fund_flow': {
            'weight': 0.07,
            'category': 'fundamental',
            'thresholds': {'strong_buy': 5000, 'buy': 1000, 'hold': -1000, 'sell': -5000}
        },
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
    'title': 'AI 指数基金分析系统',
    'description': '技术分析 + 基本面分析双引擎，AI 多因子加权评分决策支持',
    'default_index': '000001',  # 默认上证指数
    'max_history_days': 365 * 5  # 最大历史数据天数
}

# 基金配置
FUND_CONFIG = {
    # 主动基金/QDII 取前 N 大重仓股
    'active_top_n': 10,
    # 最低权重覆盖率阈值 (低于此值将发出警告)
    'min_coverage_pct': 50.0,
    # 基金类型关键词 (用于 UI 展示)
    'type_labels': {
        'etf': '场内 ETF',
        'otc_index': '场外指数基金',
        'otc_active': '场外主动基金',
        'qdii': 'QDII 基金',
        'other': '其他基金',
    },
    # 常见指数基金代码前缀 → 跟踪指数
    'known_index_funds': {
        '110003': '上证50',
        '110020': '沪深300',
        '110026': '创业板指',
        '000311': '沪深300',
        '050002': '沪深300',
        '161017': '中证500',
        '159915': '创业板ETF',
        '510050': '上证50ETF',
        '510300': '沪深300ETF',
        '510500': '中证500ETF',
    },
}

# 数据导出配置
EXPORT_CONFIG = {
    'default_folder': 'exports',
    'file_name_pattern': '{code}_{name}_{date}.csv',
    'encoding': 'utf-8-sig'
}
