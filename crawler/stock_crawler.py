"""
个股数据爬虫 — 获取单只股票的 OHLCV K线、基本面估值、资金流向

数据来源: akshare
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from config import TECHNICAL_INDICATOR_PARAMS
from utils.logger import logger


class StockCrawler:
    """个股数据爬虫"""

    # 数据源优先级: 腾讯 → 新浪 → 东方财富 → mock
    _SOURCES = ['tx', 'sina', 'em']

    def __init__(self):
        self.ohlcv_days = TECHNICAL_INDICATOR_PARAMS['ohlcv_days']
        self._spot_cache: pd.DataFrame | None = None
        self._source_failures: dict[str, int] = {}
        self._source_cooldown: dict[str, float] = {}

    # ── 代码规范化 ────────────────────────────────────────────

    @staticmethod
    def normalize_code(stock_code: str) -> str:
        """将股票代码转为 akshare 格式 (sh600519 / sz000858)。

        上海: 6xxxxx → sh6xxxxx
        深圳: 0xxxxx, 3xxxxx → sz0xxxxx / sz3xxxxx
        科创板: 688xxx → sh688xxx
        """
        code = str(stock_code).strip()
        if code.startswith(('60', '68')):
            return f"sh{code}"
        elif code.startswith(('00', '30')):
            return f"sz{code}"
        else:
            # 猜测: 6位且以6开头 = SH
            if len(code) >= 2 and code[0] == '6':
                return f"sh{code}"
            else:
                return f"sz{code}"

    # ── OHLCV 数据 (多源 fallback) ──────────────────────────

    def get_ohlcv(self, stock_code: str, days: int | None = None) -> pd.DataFrame | None:
        """多源 fallback 获取个股 OHLCV。

        优先级: 腾讯(tx) → 新浪(sina) → 东方财富(em) → mock
        连续失败 3 次自动冷却 60s, 避免反复撞限流墙。
        """
        if days is None:
            days = self.ohlcv_days

        import time
        time.sleep(0.2)

        symbol = self.normalize_code(stock_code)
        end_date = pd.Timestamp.now().strftime('%Y%m%d')
        start_date = (pd.Timestamp.now() - pd.Timedelta(days=days * 2)).strftime('%Y%m%d')

        for source in self._SOURCES:
            if self._is_source_cooling(source):
                continue

            try:
                df = None
                if source == 'tx':
                    df = self._fetch_tx(symbol, start_date, end_date)
                elif source == 'sina':
                    df = self._fetch_sina(symbol)
                elif source == 'em':
                    df = self._fetch_em(symbol, start_date, end_date)

                if df is not None and not df.empty:
                    df = self._normalize_ohlcv(df, stock_code)
                    df = df.tail(days).reset_index(drop=True)
                    self._source_failures[source] = 0
                    logger.debug(f"OHLCV 源={source} {stock_code} {len(df)}条")
                    return df
            except Exception as e:
                logger.debug(f"源 {source} 失败: {stock_code}, {e}")

            self._source_failures[source] = self._source_failures.get(source, 0) + 1
            if self._source_failures[source] >= 3:
                self._source_cooldown[source] = time.time() + 60
                logger.warning(f"源 {source} 连续失败{self._source_failures[source]}次, 冷却60s")

        return self._generate_mock_ohlcv(stock_code, days)

    def _is_source_cooling(self, source: str) -> bool:
        import time
        return time.time() < self._source_cooldown.get(source, 0)

    # ── 各数据源 ──

    def _fetch_tx(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        import akshare as ak
        return ak.stock_zh_a_hist_tx(symbol=symbol, start_date=start, end_date=end)

    def _fetch_sina(self, symbol: str) -> pd.DataFrame:
        import akshare as ak
        return ak.stock_zh_a_daily(symbol=symbol, adjust='qfq')

    def _fetch_em(self, symbol: str, start: str, end: str) -> pd.DataFrame:
        import akshare as ak
        return ak.stock_zh_a_hist(symbol=symbol, period='daily',
                                   start_date=start, end_date=end, adjust='qfq')

    # ── 列标准化 ──

    def _normalize_ohlcv(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        col_map = {
            '日期': 'date', '开盘': 'open', '最高': 'high',
            '最低': 'low', '收盘': 'close', '成交量': 'volume', '成交额': 'amount',
            'date': 'date', 'open': 'open', 'high': 'high',
            'low': 'low', 'close': 'close', 'volume': 'volume', 'amount': 'amount',
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

        if 'amount' in df.columns and 'volume' not in df.columns:
            df['volume'] = df['amount'] / df['close'].replace(0, 1)

        for col, fallback in [('open', 'close'), ('high', 'close'), ('low', 'close'),
                               ('close', None), ('volume', None)]:
            if col not in df.columns:
                if fallback and fallback in df.columns:
                    df[col] = df[fallback]
                elif col == 'volume':
                    df[col] = 1e8
                else:
                    df[col] = df.iloc[:, 1:].mean(axis=1)

        keep = ['date', 'open', 'high', 'low', 'close', 'volume']
        df = df[[c for c in keep if c in df.columns]]

        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

        return df

    def _generate_mock_ohlcv(self, stock_code: str, days: int) -> pd.DataFrame:
        """生成模拟 OHLCV (fallback)"""
        import numpy as np

        dates = pd.date_range(end=pd.Timestamp.now(), periods=days, freq='B')
        np.random.seed(hash(stock_code) % 2**31)

        trend = np.linspace(0, np.random.uniform(-0.10, 0.15), days)
        noise = np.random.normal(0, 0.02, days).cumsum()
        base = np.random.uniform(10, 200)
        close = base * (1 + trend + noise * 0.3)

        high = close * (1 + np.abs(np.random.normal(0, 0.015, days)))
        low = close * (1 - np.abs(np.random.normal(0, 0.015, days)))
        open_p = low + np.random.uniform(0, 1, days) * (high - low)

        return pd.DataFrame({
            'date': dates,
            'open': open_p, 'high': high, 'low': low,
            'close': close, 'volume': np.random.uniform(1e6, 5e8, days),
        })

    # ── 基本面数据 ────────────────────────────────────────────

    def _get_spot_cache(self) -> pd.DataFrame | None:
        """获取全市场实时行情 (缓存, 避免重复调用 API)。"""
        if self._spot_cache is not None:
            return self._spot_cache

        import time
        time.sleep(1.0)  # 限速: 避免 akshare 并发限流

        try:
            import akshare as ak
            df = ak.stock_zh_a_spot_em()
            if df is not None and not df.empty:
                self._spot_cache = df
                return df
        except Exception as e:
            logger.warning(f"获取全市场行情失败: {e}")

        return None

    def get_fundamentals(self, stock_code: str) -> dict:
        """获取个股基本面估值数据。

        使用全市场实时行情快照 (stock_zh_a_spot_em)，一次拉取全量数据
        后按代码查找，避免逐个 API 调用导致限流。

        Returns:
            {pe, pb, roe, turnover}
        """
        defaults = {'pe': 15.0, 'pb': 2.0, 'roe': 10.0, 'turnover': 2.0}

        try:
            df = self._get_spot_cache()
            if df is None:
                return defaults

            # 列名兼容: 东方财富接口可能返回中文列名
            code_col = None
            for col in ['代码', 'code', '股票代码']:
                if col in df.columns:
                    code_col = col
                    break

            if code_col is None:
                logger.warning(f"全市场行情中无股票代码列")
                return defaults

            matched = df[df[code_col].astype(str).str.strip() == str(stock_code).strip()]
            if matched.empty:
                logger.debug(f"全市场行情中未找到: {stock_code}")
                return defaults

            row = matched.iloc[0]

            # PE (市盈率-动态)
            pe = 0.0
            for col in ['市盈率-动态', '动态市盈率', 'PE']:
                if col in df.columns:
                    val = row.get(col)
                    if val and float(val) > 0:
                        pe = float(val)
                        break

            # PB (市净率)
            pb = 0.0
            for col in ['市净率', 'PB']:
                if col in df.columns:
                    val = row.get(col)
                    if val and float(val) > 0:
                        pb = float(val)
                        break

            # 换手率
            turnover = 0.0
            for col in ['换手率', 'turnover']:
                if col in df.columns:
                    val = row.get(col)
                    if val and float(val) > 0:
                        turnover = float(val)
                        break

            return {
                'pe': pe if pe > 0 else defaults['pe'],
                'pb': pb if pb > 0 else defaults['pb'],
                'roe': defaults['roe'],  # 实时行情无ROE, 用默认值
                'turnover': turnover if turnover > 0 else defaults['turnover'],
            }

        except ImportError:
            logger.debug("akshare 不可用，返回默认基本面")
        except Exception as e:
            logger.warning(f"获取个股基本面失败: {stock_code}, {e}")

        return defaults

    # ── 资金流向 ──────────────────────────────────────────────

    def get_fund_flow(self, stock_code: str, days: int = 5) -> float:
        """获取个股近 N 日主力资金净流入 (万元)。

        Returns:
            净流入金额 (万元), 正=流入, 负=流出
        """
        try:
            import akshare as ak

            df = ak.stock_individual_fund_flow(
                stock=str(stock_code).strip(), market='sh'
                if stock_code.startswith(('60', '68')) else 'sz'
            )

            if df is not None and not df.empty:
                recent = df.tail(days)
                if '主力净流入' in recent.columns:
                    return float(recent['主力净流入'].sum())
                elif '主力净流入-净额' in recent.columns:
                    return float(recent['主力净流入-净额'].sum())

            return 0.0

        except ImportError:
            return 0.0
        except Exception as e:
            logger.debug(f"获取个股资金流向失败: {stock_code}, {e}")
            return 0.0
