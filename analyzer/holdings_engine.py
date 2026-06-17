"""
持仓加权引擎 — 从个股数据到基金层面指标的核心桥梁

流程:
  1. 接收基金持仓列表 [{stock_code, weight_pct, ...}]
  2. 对每只持仓个股获取 OHLCV + 基本面 + 资金流
  3. 逐日加权合成基金的虚拟 OHLCV
  4. 加权计算基金的 PE, ROE, PB, turnover, fund_flow
  5. 归一化权重到 100%

所有计算均为纯 Python + pandas + numpy。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import TECHNICAL_INDICATOR_PARAMS
from crawler.stock_crawler import StockCrawler
from utils.logger import logger
from utils.market_utils import is_a_market_open, trading_day_fraction


class HoldingsEngine:
    """持仓加权引擎"""

    def __init__(self, max_workers: int = 5):
        self.stock_crawler = StockCrawler()
        self.ohlcv_days = TECHNICAL_INDICATOR_PARAMS['ohlcv_days']
        self.max_workers = max_workers

    def build_synthetic_data(self, code: str, holdings: list[dict]
                             ) -> dict | None:
        """从持仓个股数据合成基金级别的分析数据。"""
        if not holdings:
            logger.warning(f"持仓列表为空: {code}")
            return None

        # 归一化权重
        total_w = sum(h['weight_pct'] for h in holdings)
        if total_w <= 0:
            logger.error(f"持仓权重总和为 0: {code}")
            return None

        for h in holdings:
            h['weight_norm'] = h['weight_pct'] / total_w

        # 预取全市场行情 (收盘后跳过 — API 收盘后关)
        market_open = is_a_market_open()
        if market_open:
            spot_df = self._fetch_spot_snapshot()
            logger.info("盘中模式, 尝试获取实时 PE/PB 快照")
        else:
            spot_df = {}
            logger.info("收盘后模式, 跳过实时快照, 使用日线收盘价")

        # 并行获取个股 OHLCV, 从 spot_df 补充基本面
        stock_data_list = self._fetch_all_stocks(holdings, spot_df)

        if not stock_data_list:
            logger.error(f"所有个股数据获取失败: {code}")
            return None

        # 合成 OHLCV
        synth_ohlcv = self._synthesize_ohlcv(stock_data_list)

        # 加权基本面
        fundamentals = self._weighted_fundamentals(stock_data_list)

        # 计算资金流
        fund_flow = sum(
            sd.get('fund_flow', 0) * sd['weight_norm']
            for sd in stock_data_list
        )

        result = {
            'code': code,
            'ohlcv': synth_ohlcv,
            'pe': fundamentals['pe'],
            'pb': fundamentals['pb'],
            'roe': fundamentals['roe'],
            'turnover': fundamentals['turnover'],
            'fund_flow': fund_flow,
            'fund_inflow': max(0, fund_flow),
            'fund_outflow': abs(min(0, fund_flow)),
            'fund_net_change': fund_flow,
            'coverage_pct': round(total_w, 2),
            'holdings_detail': stock_data_list,
        }

        logger.info(
            f"合成数据完成: {code}, "
            f"合成OHLCV: {len(synth_ohlcv)}条, "
            f"加权PE: {fundamentals['pe']:.1f}, "
            f"覆盖率: {total_w:.1f}%"
        )
        return result

    # ── 全市场行情快照 ────────────────────────────────────────

    def _fetch_spot_snapshot(self) -> dict[str, dict]:
        """一次性获取全市场个股 PE/PB/换手率。

        Returns:
            {stock_code: {pe, pb, turnover}} 或空 dict
        """
        try:
            import akshare as ak
            df = ak.stock_zh_a_spot_em()
            if df is None or df.empty:
                logger.warning("全市场行情返回空")
                return {}

            # 检测代码列
            code_col = None
            for col in ['代码', 'code']:
                if col in df.columns:
                    code_col = col
                    break
            if code_col is None:
                return {}

            # 构建查找表
            spot = {}
            for _, row in df.iterrows():
                stock_code = str(row[code_col]).strip()
                pe = 0.0
                for col in ['市盈率-动态', '动态市盈率']:
                    if col in df.columns:
                        v = row.get(col)
                        if v and float(v) > 0:
                            pe = float(v)
                            break

                pb = 0.0
                for col in ['市净率']:
                    if col in df.columns:
                        v = row.get(col)
                        if v and float(v) > 0:
                            pb = float(v)
                            break

                turnover = 0.0
                for col in ['换手率']:
                    if col in df.columns:
                        v = row.get(col)
                        if v and float(v) > 0:
                            turnover = float(v)
                            break

                if pe > 0 or pb > 0:
                    spot[stock_code] = {'pe': pe, 'pb': pb, 'turnover': turnover}

            logger.info(f"全市场行情快照: {len(spot)} 只个股有PE/PB数据")
            return spot

        except ImportError:
            logger.debug("akshare 不可用")
            return {}
        except Exception as e:
            logger.warning(f"获取全市场行情快照失败: {e}")
            return {}

    # ── 并行获取 ──────────────────────────────────────────────

    def _fetch_all_stocks(self, holdings: list[dict],
                          spot: dict[str, dict] | None = None) -> list[dict]:
        """并行获取所有持仓个股 OHLCV, 从 spot 快照补充基本面。"""
        results = []
        spot = spot or {}

        def fetch_one(h: dict) -> dict | None:
            stock_code = h['stock_code']
            try:
                ohlcv = self.stock_crawler.get_ohlcv(stock_code, self.ohlcv_days)
                fund_flow = self.stock_crawler.get_fund_flow(stock_code, ohlcv=ohlcv)

                # 从 spot 快照取 PE/PB (一次 API 调用已获取)
                spot_data = spot.get(stock_code, {})
                pe = spot_data.get('pe', 15.0) or 15.0
                pb = spot_data.get('pb', 2.0) or 2.0
                turnover = spot_data.get('turnover', 2.0) or 2.0

                return {
                    **h,
                    'ohlcv': ohlcv,
                    'pe': pe, 'pb': pb, 'roe': 10.0,  # ROE 无实时源, 默认值
                    'turnover': turnover, 'fund_flow': fund_flow,
                }
            except Exception as e:
                logger.warning(f"获取个股数据失败: {stock_code}, {e}")
                return None

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(fetch_one, h): h for h in holdings}
            for future in as_completed(futures):
                result = future.result()
                if result is not None and result.get('ohlcv') is not None:
                    results.append(result)

        logger.info(f"个股数据获取: {len(results)}/{len(holdings)} 成功")
        return results

    # ── OHLCV 合成 ────────────────────────────────────────────

    def _synthesize_ohlcv(self, stock_data_list: list[dict]) -> pd.DataFrame:
        """逐日加权合成基金 OHLCV。

        算法:
          synth_col[t] = Σ(个股col[t] × weight_norm) / Σ(weight_norm)

        由于权重已归一化 (Σ weight_norm = 1), 等价于:
          synth_col[t] = Σ(个股col[t] × weight_norm)
        """
        # 找到公共日期交集
        all_dates = None
        for sd in stock_data_list:
            df = sd['ohlcv']
            if df is not None and not df.empty:
                dates = set(df['date'].values)
                if all_dates is None:
                    all_dates = dates
                else:
                    all_dates &= dates

        if not all_dates:
            # 退回：使用第一个有效股票的日期
            for sd in stock_data_list:
                if sd['ohlcv'] is not None and not sd['ohlcv'].empty:
                    all_dates = set(sd['ohlcv']['date'].values)
                    break

        if not all_dates:
            return self._empty_ohlcv()

        dates_sorted = sorted(all_dates)

        # 逐日加权
        synth_rows = []
        for date in dates_sorted:
            row = {'date': date}
            total_w_day = 0.0

            for field in ['open', 'high', 'low', 'close', 'volume']:
                weighted_sum = 0.0
                weight_sum = 0.0

                for sd in stock_data_list:
                    df = sd['ohlcv']
                    if df is None or df.empty:
                        continue

                    match = df[df['date'] == date]
                    if match.empty:
                        continue

                    val = match.iloc[0][field]
                    w = sd['weight_norm']
                    weighted_sum += val * w
                    weight_sum += w

                if weight_sum > 0:
                    row[field] = weighted_sum / weight_sum
                    if field == 'close':
                        total_w_day = weight_sum
                else:
                    row[field] = 0.0

            row['_day_coverage'] = total_w_day
            synth_rows.append(row)

        df = pd.DataFrame(synth_rows)

        # 填补缺失值: forward fill
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].replace(0.0, np.nan).ffill().fillna(0)

        # 盘中 volume 外推: 当日成交量仅为部分, 按时间比例外推到全天
        if is_a_market_open() and len(df) > 0:
            from datetime import date as date_type
            last_date = df['date'].iloc[-1]
            if isinstance(last_date, pd.Timestamp):
                last_date = last_date.date()
            today = date_type.today()
            if last_date == today:
                frac = trading_day_fraction()
                if frac > 0.1 and frac < 1.0:
                    last_vol = df['volume'].iloc[-1]
                    df.at[df.index[-1], 'volume'] = last_vol / frac
                    df.at[df.index[-1], '_volume_adjusted'] = True
                    logger.debug(f"盘中 volume 外推: day_fraction={frac:.2f}, "
                                 f"raw={last_vol:.0f} → projected={last_vol/frac:.0f}")

        return df

    def _empty_ohlcv(self) -> pd.DataFrame:
        """返回空的 OHLCV DataFrame (带标准列)。"""
        return pd.DataFrame(columns=['date', 'open', 'high', 'low', 'close', 'volume'])

    # ── 基本面加权 ────────────────────────────────────────────

    def _weighted_fundamentals(self, stock_data_list: list[dict]) -> dict:
        """加权计算基金的基本面指标。

        PE, PB, turnover: 按 weight_norm 加权平均
        ROE: 同样加权平均
        """
        pe = self._weighted_mean(stock_data_list, 'pe')
        pb = self._weighted_mean(stock_data_list, 'pb')
        roe = self._weighted_mean(stock_data_list, 'roe')
        turnover = self._weighted_mean(stock_data_list, 'turnover')

        return {
            'pe': round(pe, 2),
            'pb': round(pb, 2),
            'roe': round(roe, 2),
            'turnover': round(turnover, 2),
        }

    def _weighted_mean(self, data_list: list[dict], field: str) -> float:
        """计算加权平均值。"""
        total = 0.0
        weight_sum = 0.0
        for d in data_list:
            val = d.get(field, 0)
            w = d.get('weight_norm', 0)
            if val and val > 0:
                total += val * w
                weight_sum += w

        return total / weight_sum if weight_sum > 0 else 0.0
