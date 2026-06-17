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
        self._financial_cache: dict[str, dict] = {}

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
        if self._spot_cache is not None:
            return self._spot_cache
        import time; time.sleep(1.0)
        try:
            import akshare as ak
            df = ak.stock_zh_a_spot_em()
            if df is not None and not df.empty:
                self._spot_cache = df
                return df
        except Exception as e:
            logger.debug(f"全市场行情不可用: {e}")
        return None

    def _get_financial_data(self, stock_code: str) -> dict:
        """从财报获取个股 ROE/EPS/PB (不依赖实时API, 盘后可用)。"""
        if stock_code in self._financial_cache:
            return self._financial_cache[stock_code]

        import time; time.sleep(0.3)
        try:
            import akshare as ak
            # 注意: 此API要原始代码 '600519', 不是 'sh600519'
            df = ak.stock_financial_analysis_indicator(
                symbol=str(stock_code).strip(), start_year='2025')
            if df is not None and not df.empty:
                latest = df.iloc[-1]
                data = {
                    'roe': float(latest.get('加权净资产收益率(%)', 10) or 10),
                    'eps': float(latest.get('摊薄每股收益(元)', 0) or 0),
                    'bps': float(latest.get('每股净资产_调整前(元)', 0) or 0),
                    'pb_fin': float(latest.get('市净率', 0) or 0),
                }
                self._financial_cache[stock_code] = data
                return data
        except Exception as e:
            logger.debug(f"财报数据获取失败: {stock_code}, {e}")

        self._financial_cache[stock_code] = {}
        return {}

    def get_fundamentals(self, stock_code: str) -> dict:
        """获取个股基本面估值数据。

        盘中: spot 快照 (实时 PE/PB) + 财报 ROE
        盘后: 财报推算 PE/PB + 财报 ROE
        """
        defaults = {'pe': 15.0, 'pb': 2.0, 'roe': 10.0, 'turnover': 2.0}

        try:
            fin = self._get_financial_data(stock_code)
            spot = self._get_spot_cache()

            pe = defaults['pe']
            pb = defaults['pb']
            turnover = defaults['turnover']
            roe = fin.get('roe', defaults['roe'])

            # PE/PB: 盘中从 spot, 盘后从财报推算
            if spot is not None:
                code_col = next((c for c in ['代码','code','股票代码'] if c in spot.columns), None)
                if code_col:
                    matched = spot[spot[code_col].astype(str).str.strip() == str(stock_code).strip()]
                    if not matched.empty:
                        row = matched.iloc[0]
                        for col in ['市盈率-动态','动态市盈率']:
                            v = row.get(col); v = float(v) if v and float(v) > 0 else 0
                            if v > 0: pe = v; break
                        for col in ['市净率']:
                            v = row.get(col); v = float(v) if v and float(v) > 0 else 0
                            if v > 0: pb = v; break
                        for col in ['换手率']:
                            v = row.get(col); v = float(v) if v and float(v) > 0 else 0
                            if v > 0: turnover = v; break

            # 盘后 fallback: PE = close / (EPS × 4 annualized)
            if pe == defaults['pe'] and fin.get('eps', 0) > 0:
                import time
                ohlcv = self.get_ohlcv(stock_code, days=5)
                if ohlcv is not None and len(ohlcv) > 0:
                    close = ohlcv['close'].iloc[-1]
                    eps_annual = fin['eps'] * 4  # 季报 EPS × 4 = 年化
                    if eps_annual > 0:
                        pe = round(close / eps_annual, 1)

            # PB fallback: close / bps
            if pb == defaults['pb'] and fin.get('bps', 0) > 0:
                ohlcv = self.get_ohlcv(stock_code, days=5)
                if ohlcv is not None and len(ohlcv) > 0:
                    close = ohlcv['close'].iloc[-1]
                    if fin['bps'] > 0:
                        pb = round(close / fin['bps'], 2)

            return {
                'pe': pe if pe > 0 else defaults['pe'],
                'pb': pb if pb > 0 else defaults['pb'],
                'roe': roe if roe > 0 else defaults['roe'],
                'turnover': turnover if turnover > 0 else defaults['turnover'],
            }

        except Exception as e:
            logger.warning(f"获取个股基本面失败: {stock_code}, {e}")
        return defaults

    # ── 资金流向 (Money Flow) ──────────────────────────────

    def get_fund_flow(self, stock_code: str, days: int = 5,
                      ohlcv: pd.DataFrame | None = None) -> float:
        """个股资金流向 (万元)。

        优先使用外部 API, 不可用时从 OHLCV 计算 Money Flow:
          TP = (H+L+C)/3,  Raw MF = TP × Vol
          近 N 日净 MF = Σ(MF | close↑) - Σ(MF | close↓)
        """
        # 1. 尝试外部 API
        try:
            import akshare as ak
            df = ak.stock_individual_fund_flow(
                stock=str(stock_code).strip(),
                market='sh' if stock_code.startswith(('60','68')) else 'sz')
            if df is not None and not df.empty:
                recent = df.tail(days)
                for col in ['主力净流入','主力净流入-净额']:
                    if col in recent.columns:
                        return float(recent[col].sum())
        except Exception:
            pass

        # 2. Money Flow 从 OHLCV 推算
        if ohlcv is not None and len(ohlcv) >= max(2, days):
            return self._compute_money_flow(ohlcv, days)

        # 3. 尝试获取 OHLCV
        try:
            df = self.get_ohlcv(stock_code, days=max(10, days * 2))
            if df is not None and len(df) >= max(2, days):
                return self._compute_money_flow(df, days)
        except Exception:
            pass

        return 0.0

    def _compute_money_flow(self, df: pd.DataFrame, days: int = 5) -> float:
        """基于 OHLCV 计算 Money Flow (万元)。"""
        recent = df.tail(days + 1)
        tp = (recent['high'] + recent['low'] + recent['close']) / 3
        mf = tp * recent['volume']
        net_mf = 0.0
        for i in range(1, len(recent)):
            if recent['close'].iloc[i] > recent['close'].iloc[i - 1]:
                net_mf += mf.iloc[i]
            else:
                net_mf -= mf.iloc[i]
        return round(net_mf / 10000, 2)  # 转万元
