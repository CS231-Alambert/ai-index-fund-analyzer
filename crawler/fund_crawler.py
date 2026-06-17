"""
基金数据爬虫 — 获取基金基本信息、持仓明细、类型识别

数据来源: akshare (东方财富)
支持: ETF, 场外指数基金, 主动基金, QDII
"""

from __future__ import annotations

from utils.logger import logger


class FundCrawler:
    """基金数据爬虫"""

    # 基金类型映射
    TYPE_KEYWORDS = {
        'etf': ['ETF', '交易型开放式'],
        'qdii': ['QDII', 'QDII-'],
        'index': ['指数型', '指数', 'ETF联接'],
        'active': ['混合型', '股票型', '灵活配置', '偏股', '普通股票'],
        'bond': ['债券型', '货币型', '理财'],
    }

    @staticmethod
    def classify_fund(fund_type_str: str) -> str:
        """根据 akshare 返回的基金类型字符串分类。

        Returns:
            'etf' | 'otc_index' | 'otc_active' | 'qdii' | 'other'
        """
        ft = str(fund_type_str)

        # QDII 优先 (可能同时包含"指数"关键词)
        if any(kw in ft for kw in FundCrawler.TYPE_KEYWORDS['qdii']):
            return 'qdii'

        # ETF
        if any(kw in ft for kw in FundCrawler.TYPE_KEYWORDS['etf']):
            return 'etf'

        # 指数型（场外）
        if any(kw in ft for kw in FundCrawler.TYPE_KEYWORDS['index']):
            return 'otc_index'

        # 主动型
        if any(kw in ft for kw in FundCrawler.TYPE_KEYWORDS['active']):
            return 'otc_active'

        return 'other'

    @staticmethod
    def is_index_fund(fund_type_str: str) -> bool:
        """判断是否为指数型（被动）基金。"""
        ft = str(fund_type_str)
        return any(kw in ft for kw in FundCrawler.TYPE_KEYWORDS['index'])

    @staticmethod
    def is_etf(fund_type_str: str) -> bool:
        """判断是否为 ETF。"""
        return any(kw in str(fund_type_str) for kw in FundCrawler.TYPE_KEYWORDS['etf'])

    def get_fund_info(self, code: str) -> dict | None:
        """获取基金基本信息。

        Args:
            code: 基金代码 (5-6位)

        Returns:
            {code, name, type, category} 或 None
        """
        try:
            import akshare as ak

            df = ak.fund_name_em()
            if df is None or df.empty:
                logger.warning("fund_name_em 返回空数据")
                return None

            # 精确匹配
            matched = df[df['基金代码'].astype(str).str.strip() == str(code).strip()]
            if matched.empty:
                # 模糊匹配
                matched = df[df['基金代码'].astype(str).str.contains(str(code))]

            if matched.empty:
                logger.warning(f"未找到基金代码: {code}")
                return None

            row = matched.iloc[0]
            fund_type = row.get('基金类型', '')
            category = self.classify_fund(fund_type)

            return {
                'code': str(code).strip(),
                'name': row.get('基金简称', f'基金{code}'),
                'type': fund_type,
                'category': category,
            }

        except ImportError:
            logger.error("akshare 未安装")
            return None
        except Exception as e:
            logger.error(f"获取基金信息失败: {code}, {e}")
            return None

    def get_holdings(self, code: str) -> list[dict]:
        """获取基金持仓明细。

        Args:
            code: 基金代码

        Returns:
            [{stock_code, stock_name, weight_pct, shares, market_value, quarter}]
            按权重降序排列
        """
        try:
            import akshare as ak

            # 尝试最新季度: 当前年份的1季度
            import datetime
            year = datetime.datetime.now().year
            quarters = [f'{year}', f'{year-1}']  # 先试今年再试去年

            for q in quarters:
                try:
                    df = ak.fund_portfolio_hold_em(date=q, symbol=str(code).strip())
                    if df is not None and not df.empty:
                        break
                except Exception:
                    continue
            else:
                logger.warning(f"未找到基金持仓数据: {code}")
                return []

            holdings = []
            for _, row in df.iterrows():
                holdings.append({
                    'stock_code': str(row.get('股票代码', '')).strip(),
                    'stock_name': str(row.get('股票名称', '')).strip(),
                    'weight_pct': float(row.get('占净值比例', 0) or 0),
                    'shares': float(row.get('持股数', 0) or 0),
                    'market_value': float(row.get('持仓市值', 0) or 0),
                    'quarter': str(row.get('季度', '')),
                })

            # 按权重降序
            holdings.sort(key=lambda x: x['weight_pct'], reverse=True)

            logger.info(f"获取基金持仓成功: {code}, {len(holdings)} 只个股")
            return holdings

        except ImportError:
            logger.error("akshare 未安装")
            return []
        except Exception as e:
            logger.error(f"获取基金持仓失败: {code}, {e}")
            return []

    def get_filtered_holdings(self, code: str, fund_type_str: str,
                              top_n: int = 10) -> tuple[list[dict], dict]:
        """获取持仓，根据基金类型自动过滤。

        主动基金/QDII: 取 Top N 重仓股
        指数基金: 取全部持仓

        Args:
            code: 基金代码
            fund_type_str: 基金类型字符串
            top_n: 主动基金取前 N 只 (默认 10)

        Returns:
            (holdings_list, summary_dict)
            summary = {total_count, used_count, coverage_pct, is_full}
        """
        all_holdings = self.get_holdings(code)

        if not all_holdings:
            return [], {'total_count': 0, 'used_count': 0,
                        'coverage_pct': 0.0, 'is_full': False}

        is_index = self.is_index_fund(fund_type_str)

        if is_index:
            # 指数基金: 全部持仓
            used = all_holdings
            is_full = True
        else:
            # 主动基金/QDII: Top N
            used = all_holdings[:top_n]
            is_full = len(used) >= len(all_holdings)

        total_weight = sum(h['weight_pct'] for h in used)
        total_all_weight = sum(h['weight_pct'] for h in all_holdings)

        summary = {
            'total_count': len(all_holdings),
            'used_count': len(used),
            'coverage_pct': round(total_weight, 2),
            'total_coverage_pct': round(total_all_weight, 2),
            'is_full': is_full,
        }

        logger.info(
            f"持仓过滤: {code}, 类型={fund_type_str}, "
            f"取{len(used)}/{len(all_holdings)}只, 覆盖率={total_weight:.1f}%"
        )
        return used, summary
