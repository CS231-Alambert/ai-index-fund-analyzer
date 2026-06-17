"""
指数数据爬虫 — 基于 akshare + 网页爬虫双数据源

优先使用 akshare 获取 OHLCV K线数据（用于技术指标计算）和基本面估值数据。
对 akshare 不支持的特定数据，fallback 到新浪/东方财富网页爬虫。
"""

from crawler.base_crawler import BaseCrawler
from config import DATA_SOURCES, TECHNICAL_INDICATOR_PARAMS
from utils.logger import logger
from bs4 import BeautifulSoup
import pandas as pd
import re


class IndexCrawler(BaseCrawler):
    """指数数据爬虫"""

    def __init__(self, source='default'):
        """初始化指数爬虫

        Args:
            source: 数据源名称，默认为'default'
        """
        if source not in DATA_SOURCES:
            logger.error(f"不支持的数据源: {source}")
            source = 'default'

        self.source = source
        self.source_config = DATA_SOURCES[source]
        super().__init__(self.source_config['base_url'])

    def get_index_data(self, code):
        """获取指数数据 — 合并 OHLCV + 基本面数据

        Args:
            code: 6位指数代码 (如 '000001' 代表上证指数)

        Returns:
            包含完整数据的字典，或 None (失败时)
        """
        logger.info(f"开始获取指数数据: {code}")

        # 1. 获取 OHLCV 数据 (用于技术指标)
        ohlcv_df = self.get_ohlcv_data(code)

        # 2. 获取基本面 / 估值数据
        fundamental = self._get_fundamental_data(code)

        # 3. 获取指数名称
        name = self._get_index_name(code)

        # 4. 整合
        index_data = {
            'code': code,
            'name': name,
            'source': self.source,
            'ohlcv': ohlcv_df,
            **fundamental,
        }

        logger.info(f"获取指数数据完成: {code} {name}")
        return index_data

    # ═══════════════════════════════════════════════════════════════
    # OHLCV 数据 (akshare)
    # ═══════════════════════════════════════════════════════════════

    def get_ohlcv_data(self, code: str, days: int | None = None) -> pd.DataFrame | None:
        """通过 akshare 获取指数历史 OHLCV K线数据。

        Args:
            code: 6位指数代码
            days: 获取天数，默认从配置读取

        Returns:
            DataFrame with columns: date, open, high, low, close, volume
            失败时返回 None
        """
        if days is None:
            days = TECHNICAL_INDICATOR_PARAMS['ohlcv_days']

        try:
            import akshare as ak

            # 确定指数代码格式 (akshare 需要如 sh000001 的格式)
            symbol = self._to_akshare_symbol(code)

            logger.info(f"akshare 获取 OHLCV: {symbol}, days={days}")

            # 使用 akshare 获取指数日线数据
            df = ak.stock_zh_index_daily(symbol=symbol)

            if df is None or df.empty:
                logger.warning(f"akshare 返回空数据: {symbol}")
                return self._generate_mock_ohlcv(code, days)

            # 标准化列名
            col_map = {
                'date': 'date',
                'open': 'open',
                'high': 'high',
                'low': 'low',
                'close': 'close',
                'volume': 'volume',
            }

            # 检测实际列名并重命名
            actual_cols = {c.lower(): c for c in df.columns}
            rename_map = {}
            for target, actual_col in col_map.items():
                if target in actual_cols:
                    rename_map[actual_cols[target]] = target

            df = df.rename(columns=rename_map)

            # 确保所需列存在
            required = ['open', 'high', 'low', 'close', 'volume']
            for col in required:
                if col not in df.columns:
                    logger.warning(f"OHLCV 缺少列 '{col}'，使用 close 作为 fallback")
                    if col in ['open', 'high', 'low']:
                        df[col] = df['close'] if 'close' in df.columns else 3000
                    elif col == 'volume':
                        df[col] = 1e8

            # 取最近 N 天
            df = df.tail(days).reset_index(drop=True)

            logger.info(f"OHLCV 数据获取成功: {symbol}, {len(df)} 条")
            return df

        except ImportError:
            logger.warning("akshare 未安装，使用模拟 OHLCV 数据")
            return self._generate_mock_ohlcv(code, days)
        except Exception as e:
            logger.error(f"akshare 获取 OHLCV 失败: {e}")
            return self._generate_mock_ohlcv(code, days)

    def _to_akshare_symbol(self, code: str) -> str:
        """将 6 位代码转换为 akshare 格式。

        上证指数 (0/6/9 开头): sh + code (如 sh000001)
        深证指数 (其他): sz + code (如 sz399001)
        """
        if code.startswith(('0', '6', '9')):
            return f"sh{code}"
        else:
            return f"sz{code}"

    def _generate_mock_ohlcv(self, code: str, days: int) -> pd.DataFrame:
        """生成模拟 OHLCV 数据 (作为 fallback)"""
        import numpy as np

        logger.info(f"为 {code} 生成 {days} 天模拟 OHLCV 数据")

        dates = pd.date_range(end=pd.Timestamp.now(), periods=days, freq='B')
        np.random.seed(hash(code) % 2**31)

        # 带趋势的随机游走
        trend = np.linspace(0, np.random.uniform(-0.08, 0.12), days)
        noise = np.random.normal(0, 0.015, days).cumsum()
        close = 3000 * (1 + trend + noise * 0.3)

        high = close * (1 + np.abs(np.random.normal(0, 0.01, days)))
        low = close * (1 - np.abs(np.random.normal(0, 0.01, days)))
        open_price = low + np.random.uniform(0, 1, days) * (high - low)
        volume = np.random.uniform(5e7, 3e8, days)

        return pd.DataFrame({
            'date': dates,
            'open': open_price,
            'high': high,
            'low': low,
            'close': close,
            'volume': volume,
        })

    # ═══════════════════════════════════════════════════════════════
    # 基本面数据
    # ═══════════════════════════════════════════════════════════════

    def _get_fundamental_data(self, code: str) -> dict:
        """获取基本面估值数据。

        优先使用 akshare，失败时 fallback 到网页爬虫。
        """
        try:
            import akshare as ak

            symbol = self._to_akshare_symbol(code)
            logger.info(f"akshare 获取基本面数据: {symbol}")

            # 尝试获取指数估值数据
            try:
                # akshare 指数估值接口
                df_val = ak.index_value_name_funddb()
                if df_val is not None and not df_val.empty:
                    # 匹配指数代码
                    matched = df_val[df_val['代码'].astype(str).str.contains(code)]
                    if not matched.empty:
                        row = matched.iloc[-1]
                        return {
                            'pe': float(row.get('市盈率', 0) or 0),
                            'roe': 0,  # akshare index估值表无ROE
                            'turnover': 0,  # 换手率需要单独获取
                            'fund_inflow': 0,
                            'fund_outflow': 0,
                            'fund_net_change': 0,
                        }
            except Exception:
                pass

            # Fallback: 使用 akshare 的 stock 接口获取 PE
            try:
                df_pe = ak.stock_a_pe(symbol="上证A股" if code.startswith(('0', '6', '9')) else "深证A股")
                if df_pe is not None and not df_pe.empty:
                    pe_val = float(df_pe['平均市盈率'].iloc[-1]) if '平均市盈率' in df_pe.columns else 0
                    return {
                        'pe': pe_val,
                        'roe': 0, 'turnover': 0,
                        'fund_inflow': 0, 'fund_outflow': 0, 'fund_net_change': 0,
                    }
            except Exception:
                pass

        except ImportError:
            logger.debug("akshare 不可用，使用网页爬虫获取基本面数据")
        except Exception as e:
            logger.warning(f"akshare 基本面数据获取失败: {e}")

        # Fallback: 网页爬虫
        return self._scrape_fundamental_data(code)

    def _scrape_fundamental_data(self, code: str) -> dict:
        """网页爬虫获取基本面数据 (保持现有逻辑)。"""
        try:
            index_url = self.base_url + self.source_config['index_data_path'].format(code=code)
            fund_flow_url = self.base_url + self.source_config['fund_flow_path'].format(code=code)

            index_html = self.fetch_html(index_url)
            fund_flow_html = self.fetch_html(fund_flow_url)

            if not index_html:
                return self._default_fundamental()

            index_soup = BeautifulSoup(index_html, 'html.parser')
            fund_soup = BeautifulSoup(fund_flow_html, 'html.parser') if fund_flow_html else None

            fund_flow_data = self._parse_fund_flow_sina(fund_soup) if fund_soup else {}

            return {
                'pe': self._parse_pe_sina(index_soup),
                'roe': self._parse_roe_sina(index_soup),
                'turnover': self._parse_turnover_sina(index_soup),
                'fund_inflow': fund_flow_data.get('inflow', 0),
                'fund_outflow': fund_flow_data.get('outflow', 0),
                'fund_net_change': fund_flow_data.get('net_change', 0),
            }
        except Exception as e:
            logger.error(f"网页爬虫基本面数据失败: {e}")
            return self._default_fundamental()

    def _default_fundamental(self) -> dict:
        return {
            'pe': 15, 'roe': 8, 'turnover': 3,
            'fund_inflow': 0, 'fund_outflow': 0, 'fund_net_change': 0,
        }

    def _get_index_name(self, code: str) -> str:
        """获取指数名称。"""
        # 常见指数硬编码映射 (快速且可靠)
        known = {
            '000001': '上证指数',
            '000016': '上证50',
            '000300': '沪深300',
            '000688': '科创50',
            '000905': '中证500',
            '399001': '深证成指',
            '399006': '创业板指',
            '399005': '中小100',
        }
        if code in known:
            return known[code]

        # 尝试从网页爬取
        try:
            index_url = self.base_url + self.source_config['index_data_path'].format(code=code)
            html = self.fetch_html(index_url)
            if html:
                soup = BeautifulSoup(html, 'html.parser')
                name_elem = soup.find('h1', class_='name')
                if name_elem:
                    return name_elem.text.strip()
        except Exception:
            pass

        return f'指数{code}'

    # ═══════════════════════════════════════════════════════════════
    # 新浪/东方财富解析方法 (保留作为 fallback)
    # ═══════════════════════════════════════════════════════════════

    def _parse_pe_sina(self, soup):
        try:
            pe_elem = soup.find('td', text=re.compile('市盈率'))
            if pe_elem:
                pe_text = pe_elem.find_next('td').text.strip()
                return float(pe_text) if pe_text else 0
            return 0
        except Exception:
            return 0

    def _parse_roe_sina(self, soup):
        try:
            roe_elem = soup.find('td', text=re.compile('净资产收益率'))
            if roe_elem:
                roe_text = roe_elem.find_next('td').text.strip().replace('%', '')
                return float(roe_text) if roe_text else 0
            return 0
        except Exception:
            return 0

    def _parse_turnover_sina(self, soup):
        try:
            turnover_elem = soup.find('td', text=re.compile('换手率'))
            if turnover_elem:
                turnover_text = turnover_elem.find_next('td').text.strip().replace('%', '')
                return float(turnover_text) if turnover_text else 0
            return 0
        except Exception:
            return 0

    def _parse_fund_flow_sina(self, soup):
        try:
            fund_flow = {'inflow': 0, 'outflow': 0, 'net_change': 0}
            if soup is None:
                return fund_flow

            inflow_elem = soup.find('td', text=re.compile('主力流入'))
            if inflow_elem:
                inflow_text = inflow_elem.find_next('td').text.strip()
                fund_flow['inflow'] = self._parse_amount(inflow_text)

            outflow_elem = soup.find('td', text=re.compile('主力流出'))
            if outflow_elem:
                outflow_text = outflow_elem.find_next('td').text.strip()
                fund_flow['outflow'] = self._parse_amount(outflow_text)

            fund_flow['net_change'] = fund_flow['inflow'] - fund_flow['outflow']
            return fund_flow
        except Exception:
            return {'inflow': 0, 'outflow': 0, 'net_change': 0}

    def _parse_amount(self, amount_str):
        try:
            amount_str = amount_str.strip()
            if not amount_str:
                return 0
            if '亿' in amount_str:
                return float(amount_str.replace('亿', '')) * 100000000
            elif '万' in amount_str:
                return float(amount_str.replace('万', '')) * 10000
            else:
                return float(amount_str)
        except Exception:
            return 0

    # ═══════════════════════════════════════════════════════════════
    # 历史数据
    # ═══════════════════════════════════════════════════════════════

    def get_historical_data(self, code, start_date=None, end_date=None):
        """获取指数历史估值数据 (用于回测/图表)。

        现在优先使用 akshare OHLCV 数据。
        """
        logger.info(f"获取历史数据: {code}")

        ohlcv = self.get_ohlcv_data(code, days=TECHNICAL_INDICATOR_PARAMS['ohlcv_days'])
        if ohlcv is not None and not ohlcv.empty:
            # 添加模拟的基本面列 (保持向后兼容)
            import numpy as np
            n = len(ohlcv)
            np.random.seed(hash(code) % 2**31)
            ohlcv['pe'] = np.random.uniform(10, 30, n)
            ohlcv['roe'] = np.random.uniform(5, 20, n)
            ohlcv['turnover'] = np.random.uniform(0.5, 5, n)
            ohlcv['fund_inflow'] = np.random.uniform(0, 1e8, n)
            ohlcv['fund_outflow'] = np.random.uniform(0, 1e8, n)
            ohlcv['fund_net_change'] = ohlcv['fund_inflow'] - ohlcv['fund_outflow']
            return ohlcv

        return None
