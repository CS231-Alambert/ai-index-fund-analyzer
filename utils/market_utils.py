"""
A 股市场时间工具

判断当前是否在交易时段, 以及最近的有效交易时间。
"""

from __future__ import annotations

from datetime import datetime, time, timedelta


# A 股交易时段 (北京时间)
_MORNING_START = time(9, 30)
_MORNING_END = time(11, 30)
_AFTERNOON_START = time(13, 0)
_AFTERNOON_END = time(15, 0)


def is_a_market_open(now: datetime | None = None) -> bool:
    """判断 A 股是否当前在交易时段。

    Args:
        now: 当前时间, 默认 datetime.now()

    Returns:
        True 如果在交易时段 (9:30-11:30 或 13:00-15:00, 周一到周五)
    """
    if now is None:
        now = datetime.now()

    # 周末不交易
    if now.weekday() >= 5:
        return False

    t = now.time()
    return (_MORNING_START <= t <= _MORNING_END or
            _AFTERNOON_START <= t <= _AFTERNOON_END)


def is_trading_day(d: datetime | None = None) -> bool:
    """判断是否为交易日 (周一到周五)。"""
    if d is None:
        d = datetime.now()
    return d.weekday() < 5


def get_latest_trading_time(now: datetime | None = None) -> datetime:
    """返回最近的有效交易时间点。

    盘中 → 返回当前时间
    盘后 → 返回当日 15:00
    周末 → 返回上周五 15:00
    """
    if now is None:
        now = datetime.now()

    if is_trading_day(now):
        t = now.time()
        if t >= _AFTERNOON_END:
            return now.replace(hour=15, minute=0, second=0, microsecond=0)
        if t >= _MORNING_START:
            return now
        if t < _MORNING_START:
            return now.replace(hour=9, minute=30, second=0, microsecond=0)

    # 非交易日: 回退到最近周五 15:00
    days_back = 0
    d = now
    while d.weekday() >= 5 or days_back == 0:
        d = d - timedelta(days=1)
        days_back += 1
        if days_back > 7:
            return now  # safety

    return d.replace(hour=15, minute=0, second=0, microsecond=0)


def market_status_text(now: datetime | None = None) -> str:
    """返回当前市场状态描述文本。"""
    if now is None:
        now = datetime.now()

    if not is_trading_day(now):
        return "休市 (非交易日)"

    t = now.time()
    if t < _MORNING_START:
        return "盘前 (等待开盘)"
    elif _MORNING_START <= t <= _MORNING_END:
        return "交易中 (上午盘)"
    elif t < _AFTERNOON_START:
        return "午休"
    elif _AFTERNOON_START <= t <= _AFTERNOON_END:
        return "交易中 (下午盘)"
    else:
        return "已收盘"


def trading_day_fraction(now: datetime | None = None) -> float:
    """返回当日交易时段已过比例。

    0.0 = 9:30 开盘, 0.5 ≈ 12:00, 1.0 = 15:00 收盘
    非交易日或盘前返回 0.0, 盘后返回 1.0

    用于盘中 volume 外推: estimated_full_day_vol = current_vol / fraction
    """
    if now is None:
        now = datetime.now()

    if not is_trading_day(now):
        return 1.0 if now.time() >= _AFTERNOON_END else 0.0

    t = now.time()

    # 上午盘总分钟数
    morning_minutes = (_MORNING_END.hour * 60 + _MORNING_END.minute) - \
                      (_MORNING_START.hour * 60 + _MORNING_START.minute)
    afternoon_minutes = (_AFTERNOON_END.hour * 60 + _AFTERNOON_END.minute) - \
                        (_AFTERNOON_START.hour * 60 + _AFTERNOON_START.minute)
    total_minutes = morning_minutes + afternoon_minutes

    if t < _MORNING_START:
        return 0.0

    elif t <= _MORNING_END:
        elapsed = (t.hour * 60 + t.minute) - \
                  (_MORNING_START.hour * 60 + _MORNING_START.minute)
        return elapsed / total_minutes

    elif t < _AFTERNOON_START:
        return morning_minutes / total_minutes

    elif t <= _AFTERNOON_END:
        elapsed = morning_minutes + \
                  (t.hour * 60 + t.minute) - \
                  (_AFTERNOON_START.hour * 60 + _AFTERNOON_START.minute)
        return elapsed / total_minutes

    else:
        return 1.0


def candle_completeness_pct(now: datetime | None = None) -> float:
    """返回当日 K 线完整度百分比。

    盘中 = trading_day_fraction * 100 (如 14:30 ≈ 87%)
    收盘后 = 100%
    """
    frac = trading_day_fraction(now)
    if frac >= 1.0:
        return 100.0
    return round(frac * 100, 1)
