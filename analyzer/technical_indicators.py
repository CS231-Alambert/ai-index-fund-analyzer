"""
技术指标计算引擎

从 OHLCV 时间序列数据计算 6 个核心技术指标，每个返回 0-100 的标准化评分：
  - PRICE ACTION   (价格行为)   — 趋势结构 + 支撑/阻力
  - FIBONACCI      (斐波那契)   — 回撤位信号
  - VOLUME         (成交量)     — 量价关系
  - VWAP           (成交量均价) — 机构成本基准
  - EMA            (指数均线)   — 快慢线交叉
  - MA             (移动均线)   — 多头/空头排列

所有计算均为纯 Python + pandas 实现，无需外部 TA 库依赖。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from config import TECHNICAL_INDICATOR_PARAMS
from utils.logger import logger


class TechnicalIndicators:
    """技术指标计算器"""

    def __init__(self):
        self.params = TECHNICAL_INDICATOR_PARAMS

    # ── Public API ──────────────────────────────────────────────

    def compute_all(self, df: pd.DataFrame) -> dict[str, float]:
        """计算全部 6 个技术指标评分。

        Args:
            df: OHLCV DataFrame，必须包含列:
                open, high, low, close, volume

        Returns:
            {indicator_name: score} 字典，每个 score 在 0-100 之间
        """
        if df.empty or len(df) < 20:
            logger.warning("OHLCV 数据不足（需要至少 20 条），返回默认评分 50")
            return {
                'price_action': 50.0,
                'fibonacci': 50.0,
                'volume': 50.0,
                'vwap': 50.0,
                'ema': 50.0,
                'ma': 50.0,
            }

        self._validate_columns(df)

        return {
            'price_action': self._compute_price_action(df),
            'fibonacci': self._compute_fibonacci(df),
            'volume': self._compute_volume_signal(df),
            'vwap': self._compute_vwap(df),
            'ema': self._compute_ema_signal(df),
            'ma': self._compute_ma_signal(df),
        }

    # ── 1. PRICE ACTION (价格行为) ──────────────────────────────

    def _compute_price_action(self, df: pd.DataFrame) -> float:
        """趋势结构 + K线形态 综合评分。

        趋势结构分析:
          - 在 lookback 窗口内寻找 swing highs 和 swing lows
          - Higher High + Higher Low = 上升趋势 (高分)
          - Lower High + Lower Low = 下降趋势 (低分)

        K线形态分析:
          - 扫描最近 5 根K线检测经典反转/持续形态
          - 看涨形态多 → 加分; 看跌形态多 → 减分

        集成: 趋势分与形态分偏差 > 20% 时加权平均 (趋势60%+形态40%)
        """
        lookback = self.params['price_action_lookback']

        closes = df['close'].values[-lookback:]
        highs = df['high'].values[-lookback:]
        lows = df['low'].values[-lookback:]

        # ── 趋势结构分 ──
        swing_highs = self._find_swing_points(highs, is_high=True)
        swing_lows = self._find_swing_points(lows, is_high=False)

        if len(swing_highs) < 2 or len(swing_lows) < 2:
            trend_score = self._score_from_slope(closes)
        else:
            hh = swing_highs[-1] > swing_highs[-2]
            ll = swing_lows[-1] > swing_lows[-2]
            lh = swing_highs[-1] < swing_highs[-2]
            hl = swing_lows[-1] < swing_lows[-2]
            price_vs_ma = closes[-1] / np.mean(closes) - 1

            if hh and ll:
                base = 75
                trend_strength = min(3.0, abs(price_vs_ma) * 100)
                trend_score = min(100, base + trend_strength * 8)
            elif lh and hl:
                base = 25
                trend_strength = min(3.0, abs(price_vs_ma) * 100)
                trend_score = max(0, base - trend_strength * 8)
            elif hh and not ll:
                trend_score = 55 if price_vs_ma > -0.01 else 45
            elif lh and not hl:
                trend_score = 60 if price_vs_ma > 0 else 50
            else:
                trend_score = self._score_from_slope(closes)

        # ── K线形态分 ──
        pattern_score = self._score_candlestick_patterns(df)

        # 锦上添花: 偏差 > 20% 时加权平均
        if abs(trend_score - pattern_score) > 20:
            return round(trend_score * 0.6 + pattern_score * 0.4, 1)
        return round(trend_score, 1)

    def _find_swing_points(self, series: np.ndarray, is_high: bool) -> list[float]:
        """在序列中找出 swing 极值点（局部峰/谷）。"""
        points = []
        n = len(series)
        window = 3  # 左右比较窗口
        for i in range(window, n - window):
            if is_high:
                if all(series[i] >= series[i - j] for j in range(1, window + 1)) and \
                   all(series[i] >= series[i + j] for j in range(1, window + 1)):
                    points.append(series[i])
            else:
                if all(series[i] <= series[i - j] for j in range(1, window + 1)) and \
                   all(series[i] <= series[i + j] for j in range(1, window + 1)):
                    points.append(series[i])
        return points

    def _score_from_slope(self, closes: np.ndarray) -> float:
        """用简单线性斜率估算趋势得分。"""
        x = np.arange(len(closes))
        slope = np.polyfit(x, closes, 1)[0]
        normalized = np.tanh(slope / np.mean(closes) * 1000)
        return 50 + normalized * 30  # 映射到 [20, 80]

    # ── K线形态识别 ─────────────────────────────────────────

    def _score_candlestick_patterns(self, df: pd.DataFrame) -> float:
        """扫描最近 5 根K线, 识别经典形态并评分。

        Returns:
            0-100 分, 看涨形态多→高分, 看跌形态多→低分, 无形态→50分
        """
        if len(df) < 5:
            return 50.0

        bullish = 0
        bearish = 0

        for i in range(max(2, len(df) - 5), len(df)):
            if self._is_bullish_engulfing(df, i):
                bullish += 3
            if self._is_bearish_engulfing(df, i):
                bearish += 3
            if self._is_morning_star(df, i):
                bullish += 4
            if self._is_evening_star(df, i):
                bearish += 4
            if self._is_hammer(df, i):
                bullish += 2
            if self._is_inverted_hammer(df, i):
                bullish += 2
            if self._is_doji(df, i):
                # 十字星: 上涨后=看跌, 下跌后=看涨
                if i > 0 and df['close'].iloc[i-1] > df['open'].iloc[i-1]:
                    bearish += 1
                elif i > 0:
                    bullish += 1

        if bullish == 0 and bearish == 0:
            return 50.0

        if bullish >= bearish * 2:
            return min(90, 70 + bullish - bearish)
        elif bearish >= bullish * 2:
            return max(10, 30 - (bearish - bullish))
        elif bullish > bearish:
            return 55 + (bullish - bearish) * 3
        elif bearish > bullish:
            return 45 - (bearish - bullish) * 3
        else:
            return 50.0

    # ── 形态检测器 ──

    def _get_ohlc(self, df: pd.DataFrame, i: int) -> dict:
        return {
            'o': float(df['open'].iloc[i]), 'h': float(df['high'].iloc[i]),
            'l': float(df['low'].iloc[i]), 'c': float(df['close'].iloc[i]),
        }

    def _body(self, o: float, c: float) -> float:
        """实体大小。"""
        return abs(c - o)

    def _upper_shadow(self, o: float, c: float, h: float) -> float:
        return h - max(o, c)

    def _lower_shadow(self, o: float, c: float, l: float) -> float:
        return min(o, c) - l

    def _is_bullish(self, o: float, c: float) -> bool:
        return c > o

    # ── 锤子线 ──

    def _is_hammer(self, df: pd.DataFrame, i: int) -> bool:
        """锤子线: 下影 ≥ 实体×2, 上影极小, 出现在下跌后。"""
        if i < 1:
            return False
        k = self._get_ohlc(df, i)
        body = self._body(k['o'], k['c'])
        lower = self._lower_shadow(k['o'], k['c'], k['l'])
        upper = self._upper_shadow(k['o'], k['c'], k['h'])

        # 实体不能太小 (否则就是十字星)
        if body < k['h'] * 0.001:
            return False
        # 下影 ≥ 实体×2
        if lower < body * 2:
            return False
        # 上影极小
        if upper > body * 0.6:
            return False
        # 在下降趋势后出现
        prev = self._get_ohlc(df, i - 1)
        return prev['c'] < prev['o'] or df['close'].iloc[i] < df['close'].iloc[i - 1]

    # ── 倒锤子 ──

    def _is_inverted_hammer(self, df: pd.DataFrame, i: int) -> bool:
        """倒锤子: 上影 ≥ 实体×2, 下影极小, 出现在下跌后。"""
        if i < 1:
            return False
        k = self._get_ohlc(df, i)
        body = self._body(k['o'], k['c'])
        lower = self._lower_shadow(k['o'], k['c'], k['l'])
        upper = self._upper_shadow(k['o'], k['c'], k['h'])

        if body < k['h'] * 0.001:
            return False
        if upper < body * 2:
            return False
        if lower > body * 0.6:
            return False
        prev = self._get_ohlc(df, i - 1)
        return prev['c'] < prev['o'] or df['close'].iloc[i] < df['close'].iloc[i - 2]

    # ── 看涨吞没 ──

    def _is_bullish_engulfing(self, df: pd.DataFrame, i: int) -> bool:
        """看涨吞没: 阴线后跟阳线, 阳线实体完全包住阴线实体。"""
        if i < 1:
            return False
        prev = self._get_ohlc(df, i - 1)
        curr = self._get_ohlc(df, i)

        # 前阴后阳
        if not (prev['c'] < prev['o'] and curr['c'] > curr['o']):
            return False
        # 当前阳线实体包住前一根阴线实体
        return (curr['o'] <= prev['c'] and curr['c'] >= prev['o'] and
                (curr['c'] - curr['o']) > (prev['o'] - prev['c']) * 1.2)

    # ── 看跌吞没 ──

    def _is_bearish_engulfing(self, df: pd.DataFrame, i: int) -> bool:
        """看跌吞没: 阳线后跟阴线, 阴线实体完全包住阳线实体。"""
        if i < 1:
            return False
        prev = self._get_ohlc(df, i - 1)
        curr = self._get_ohlc(df, i)

        # 前阳后阴
        if not (prev['c'] > prev['o'] and curr['c'] < curr['o']):
            return False
        # 当前阴线实体包住前一根阳线实体
        return (curr['o'] >= prev['c'] and curr['c'] <= prev['o'] and
                (curr['o'] - curr['c']) > (prev['c'] - prev['o']) * 1.2)

    # ── 启明星 (Morning Star) ──

    def _is_morning_star(self, df: pd.DataFrame, i: int) -> bool:
        """启明星: 阴线 + 小实体 + 阳线, 三K线底部反转。"""
        if i < 2:
            return False
        k1 = self._get_ohlc(df, i - 2)  # 大阴线
        k2 = self._get_ohlc(df, i - 1)  # 小实体 (星)
        k3 = self._get_ohlc(df, i)      # 大阳线

        # k1: 阴线
        if not (k1['c'] < k1['o']):
            return False
        # k2: 小实体, 跳空低开
        body2 = self._body(k2['o'], k2['c'])
        if body2 > self._body(k1['o'], k1['c']) * 0.5:
            return False
        if max(k2['o'], k2['c']) >= min(k1['o'], k1['c']):
            return False
        # k3: 阳线, 回补到 k1 实体内部
        if not (k3['c'] > k3['o']):
            return False
        if k3['c'] < k1['o'] - (k1['o'] - k1['c']) * 0.5:
            return False

        return True

    # ── 黄昏星 (Evening Star) ──

    def _is_evening_star(self, df: pd.DataFrame, i: int) -> bool:
        """黄昏星: 阳线 + 小实体 + 阴线, 三K线顶部反转。"""
        if i < 2:
            return False
        k1 = self._get_ohlc(df, i - 2)  # 大阳线
        k2 = self._get_ohlc(df, i - 1)  # 小实体 (星)
        k3 = self._get_ohlc(df, i)      # 大阴线

        # k1: 阳线
        if not (k1['c'] > k1['o']):
            return False
        # k2: 小实体, 跳空高开
        body2 = self._body(k2['o'], k2['c'])
        if body2 > self._body(k1['o'], k1['c']) * 0.5:
            return False
        if min(k2['o'], k2['c']) <= max(k1['o'], k1['c']):
            return False
        # k3: 阴线, 回补到 k1 实体内部
        if not (k3['c'] < k3['o']):
            return False
        if k3['c'] > k1['c'] - (k1['c'] - k1['o']) * 0.5:
            return False

        return True

    # ── 十字星 ──

    def _is_doji(self, df: pd.DataFrame, i: int) -> bool:
        """十字星: 开收价差极小, 影线长度适中。"""
        k = self._get_ohlc(df, i)
        body = self._body(k['o'], k['c'])
        total_range = k['h'] - k['l']

        if total_range <= 0:
            return False
        # 实体 ≤ 总振幅的 15%
        return body <= total_range * 0.15

    # ── 2. FIBONACCI (斐波那契) ─────────────────────────────────

    def _compute_fibonacci(self, df: pd.DataFrame) -> float:
        """计算斐波那契回撤位并据此评分。

        逻辑:
          - 在 lookback 内找到最高 swing high 和最低 swing low
          - 计算回撤水平: 0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0
          - 上升趋势中: 价格回调至 0.382/0.5/0.618 = 买入机会 (高分)
          - 下降趋势中: 价格反弹至 0.382/0.5/0.618 = 卖出信号 (低分)
        """
        lookback = self.params['fib_lookback']
        levels = self.params['fib_levels']

        highs = df['high'].values[-lookback:]
        lows = df['low'].values[-lookback:]
        current = df['close'].values[-1]

        swing_high = np.max(highs)
        swing_low = np.min(lows)
        range_val = swing_high - swing_low

        if range_val <= 0:
            return 50.0

        # 确定趋势方向
        high_idx = np.argmax(highs)
        low_idx = np.argmin(lows)
        is_uptrend = high_idx > low_idx  # 低点在前、高点在后 = 上升趋势

        # 计算当前价格在回撤位中的位置
        fib_prices = [swing_low + level * range_val for level in levels]

        # 找到当前价格接近的斐波那契水平
        if is_uptrend:
            # 上升趋势: 价格回调到 0.382-0.618 视为买入机会
            # 价格在 0.382 以下 = 强势（回撤极浅）
            retracement = (current - swing_low) / range_val

            if retracement <= 0.236:
                return 90  # 极浅回撤，趋势极强
            elif retracement <= 0.382:
                return 85  # 浅回撤，强趋势
            elif retracement <= 0.5:
                return 80  # 标准回撤，好的入场点
            elif retracement <= 0.618:
                return 75  # 黄金回撤，经典买点
            elif retracement <= 0.786:
                return 55  # 深回撤，趋势可能反转
            else:
                return 30  # 可能反转
        else:
            # 下降趋势: 价格反弹到 0.382-0.618 视为卖出机会
            retracement = (current - swing_low) / range_val

            if retracement >= 0.786:
                return 15  # 可能反转上行
            elif retracement >= 0.618:
                return 25  # 强反弹，接近阻力
            elif retracement >= 0.5:
                return 30  # 反弹至中点
            elif retracement >= 0.382:
                return 35  # 标准反弹
            elif retracement >= 0.236:
                return 40  # 弱反弹
            else:
                return 20  # 趋势延续中

    # ── 3. VOLUME (成交量) ──────────────────────────────────────

    def _compute_volume_signal(self, df: pd.DataFrame) -> float:
        """量价关系分析。

        逻辑:
          - 计算成交量移动平均
          - 放量上涨 = 多头信号 (高分)
          - 放量下跌 = 空头信号 (低分)
          - 缩量上涨 = 弱多头 (中等偏上)
          - 缩量下跌 = 弱空头 (中等偏下)
        """
        vol_ma_period = self.params['volume_ma_period']

        closes = df['close'].values
        volumes = df['volume'].values

        if len(volumes) < vol_ma_period + 5:
            return 50.0

        # 近期 (5日) 与中期 (20日) 的量和价变化
        recent_vol = np.mean(volumes[-5:])
        avg_vol = np.mean(volumes[-vol_ma_period:])
        vol_ratio = recent_vol / avg_vol if avg_vol > 0 else 1.0

        recent_price_change = (closes[-1] - closes[-5]) / closes[-5] if closes[-5] > 0 else 0

        # 量价组合评分
        if recent_price_change > 0:
            if vol_ratio > 1.3:
                return 90  # 放量上涨 — 强多头
            elif vol_ratio > 1.0:
                return 75  # 温和放量上涨
            else:
                return 60  # 缩量上涨 — 动能不足
        else:
            if vol_ratio > 1.3:
                return 20  # 放量下跌 — 强空头
            elif vol_ratio > 1.0:
                return 35  # 温和放量下跌
            else:
                return 45  # 缩量下跌 — 抛压减轻

    # ── 4. VWAP (成交量加权平均价) ─────────────────────────────

    def _compute_vwap(self, df: pd.DataFrame) -> float:
        """计算 VWAP 并基于价格与 VWAP 的关系评分。

        逻辑:
          - VWAP = Σ(典型价 × 成交量) / Σ(成交量)
          - 价格 > VWAP = 机构平均持仓盈利 → 看涨 (高分)
          - 价格 < VWAP = 机构平均持仓亏损 → 看跌 (低分)
          - VWAP 斜率上升 = 资金持续流入
        """
        # 使用最近 20 个交易日计算 VWAP（更敏感）
        recent = df.tail(20).copy()

        typical_price = (recent['high'] + recent['low'] + recent['close']) / 3
        vwap = np.average(typical_price, weights=recent['volume']) if recent['volume'].sum() > 0 else typical_price.mean()

        current = df['close'].values[-1]
        deviation = (current - vwap) / vwap * 100  # 偏离百分比

        # 分段计分
        if deviation > 2:
            return 90   # 显著高于 VWAP — 强多头
        elif deviation > 1:
            return 75   # 高于 VWAP
        elif deviation > 0:
            return 60   # 略高于 VWAP
        elif deviation > -1:
            return 40   # 略低于 VWAP
        elif deviation > -2:
            return 25   # 低于 VWAP
        else:
            return 10   # 显著低于 VWAP — 强空头

    # ── 5. EMA (指数移动平均) ──────────────────────────────────

    def _compute_ema_signal(self, df: pd.DataFrame) -> float:
        """基于 EMA 快慢线交叉和排列评分。

        逻辑:
          - EMA-12 (快线) 与 EMA-26 (慢线) 比较
          - 快线 > 慢线 = 多头排列 (高分)
          - 金叉 (近期快线上穿慢线) = 强买入信号
          - 死叉 (近期快线下穿慢线) = 强卖出信号
        """
        short_period = self.params['ema_short']
        long_period = self.params['ema_long']

        closes = df['close'].values

        ema_short = self._ema(closes, short_period)
        ema_long = self._ema(closes, long_period)

        if len(ema_short) < 5:
            return 50.0

        current_diff = ema_short[-1] - ema_long[-1]
        current_diff_pct = current_diff / ema_long[-1] * 100 if ema_long[-1] > 0 else 0

        # 检测近期金叉/死叉
        diff_series = ema_short - ema_long
        crossover = self._detect_crossover(diff_series)

        # 基础排列得分
        if current_diff > 0:
            if crossover == 'golden':
                return 95  # 刚刚金叉 — 极强信号
            base = 70
            bonus = min(20, max(0, current_diff_pct * 10))
            return min(100, base + bonus)
        else:
            if crossover == 'death':
                return 5   # 刚刚死叉 — 极弱信号
            base = 30
            penalty = min(20, max(0, abs(current_diff_pct) * 10))
            return max(0, base - penalty)

    def _ema(self, data: np.ndarray, period: int) -> np.ndarray:
        """计算 EMA（使用 pandas 兼容的指数平滑）。"""
        if len(data) < period:
            return np.full_like(data, np.mean(data))
        s = pd.Series(data)
        return s.ewm(span=period, adjust=False).mean().values

    # ── 6. MA (移动平均线) ─────────────────────────────────────

    def _compute_ma_signal(self, df: pd.DataFrame) -> float:
        """基于多周期 MA 排列和交叉评分。

        逻辑:
          - MA5 > MA10 > MA20 > MA60 = 完美多头排列 (95-100 分)
          - 完全反序 = 完美空头排列 (0-5 分)
          - 混合排列 = 按多头均线条数计分
          - 检测 MA5/MA20 金叉死叉
        """
        periods = self.params['ma_periods']  # [5, 10, 20, 60]
        closes = df['close'].values

        mas = {}
        for p in periods:
            if len(closes) >= p:
                mas[f'ma{p}'] = np.mean(closes[-p:])
            else:
                mas[f'ma{p}'] = np.mean(closes)

        current = closes[-1]
        price_above_ma_count = sum(1 for v in mas.values() if current > v)

        # 检查 MA 之间的排列顺序
        ma_values = list(mas.values())
        perfect_bullish = all(
            ma_values[i] > ma_values[i + 1]
            for i in range(len(ma_values) - 1)
        )
        perfect_bearish = all(
            ma_values[i] < ma_values[i + 1]
            for i in range(len(ma_values) - 1)
        )

        # 计算 MA 之间的分离度
        spread = (ma_values[0] - ma_values[-1]) / ma_values[-1] * 100 if ma_values[-1] > 0 else 0

        # 检测 MA 交叉
        ma5_full = np.array([np.mean(closes[max(0, i-4):i+1]) for i in range(len(closes))])
        ma20_full = np.array([np.mean(closes[max(0, i-19):i+1]) for i in range(len(closes))])
        crossover = self._detect_crossover(ma5_full - ma20_full)

        if perfect_bullish:
            base = 85
            bonus = min(15, max(0, spread * 3))
            score = base + bonus
            if crossover == 'golden':
                score = min(100, score + 5)
            return min(100, score)
        elif perfect_bearish:
            base = 15
            penalty = min(15, max(0, abs(spread) * 3))
            score = base - penalty
            if crossover == 'death':
                score = max(0, score - 5)
            return max(0, score)
        else:
            # 混合排列 — 按多头 MA 数量和价格位置计分
            ratio = price_above_ma_count / len(mas)
            score = 50 + (ratio - 0.5) * 60  # 映射到 [20, 80]

            if crossover == 'golden':
                score = min(95, score + 15)
            elif crossover == 'death':
                score = max(5, score - 15)

            return max(0, min(100, score))

    # ── Utilities ───────────────────────────────────────────────

    def _detect_crossover(self, diff_series: np.ndarray) -> str | None:
        """检测最近 5 根 bar 内的交叉信号。

        Returns:
            'golden' — 近期金叉 (上穿零轴)
            'death'  — 近期死叉 (下穿零轴)
            None     — 无近期交叉
        """
        recent = diff_series[-5:]
        for i in range(1, len(recent)):
            if recent[i - 1] < 0 and recent[i] >= 0:
                return 'golden'
            if recent[i - 1] > 0 and recent[i] <= 0:
                return 'death'
        return None

    def _validate_columns(self, df: pd.DataFrame) -> None:
        """验证 DataFrame 是否包含所需列。"""
        required = {'open', 'high', 'low', 'close', 'volume'}
        missing = required - set(col.lower() for col in df.columns)
        if missing:
            # 尝试大小写不敏感匹配
            col_map = {col.lower(): col for col in df.columns}
            still_missing = required - set(col_map.keys())
            if still_missing:
                logger.warning(
                    f"OHLCV DataFrame 缺少列: {still_missing}，将使用 close 列作为 fallback"
                )
