from config import DECISION_MODEL_CONFIG
from analyzer.technical_indicators import TechnicalIndicators
from utils.logger import logger


class DecisionModel:
    """AI 决策分析模型 — 技术指标(70%) + 基本面指标(30%)"""

    def __init__(self):
        """初始化决策模型"""
        self.config = DECISION_MODEL_CONFIG
        self.indicators_config = self.config['indicators']
        self.score_levels = self.config['score_levels']
        self.tech_indicators = TechnicalIndicators()
        logger.info("决策模型初始化完成 (技术指标引擎已加载)")

    def analyze(self, index_data):
        """分析指数数据，生成决策建议

        Args:
            index_data: 包含指数数据和 ohlcv DataFrame 的字典
                必需字段: code, name
                OHLCV 数据: index_data['ohlcv'] (pd.DataFrame)
                基本面数据: pe, roe, turnover, fund_flow, fund_net_change 等

        Returns:
            包含决策结果的字典
        """
        logger.info(f"开始分析指数数据: {index_data.get('code')} {index_data.get('name')}")

        # 计算技术指标评分 (如果 OHLCV 数据可用)
        ohlcv_df = index_data.get('ohlcv')
        if ohlcv_df is not None and not ohlcv_df.empty:
            tech_scores = self.tech_indicators.compute_all(ohlcv_df)
        else:
            logger.warning("无 OHLCV 数据，技术指标设为默认 50 分")
            tech_scores = {
                'price_action': 50.0, 'fibonacci': 50.0,
                'volume': 50.0, 'vwap': 50.0,
                'ema': 50.0, 'ma': 50.0,
            }

        # 合并技术指标得分到 index_data（使评分逻辑统一）
        enriched_data = {**index_data}
        for key, score in tech_scores.items():
            enriched_data[key] = score

        # 计算各指标加权得分
        indicators_scores = self._calculate_indicators_scores(enriched_data)

        # 计算综合得分 (含覆盖率折扣)
        total_score = self._calculate_total_score(
            indicators_scores, holdings_summary=index_data.get('holdings_summary')
        )

        # 按类别计算得分
        tech_total = sum(
            info['weighted_score'] for key, info in indicators_scores.items()
            if self.indicators_config[key]['category'] == 'technical'
        )
        tech_weight = sum(
            info['weight'] for key, info in indicators_scores.items()
            if self.indicators_config[key]['category'] == 'technical'
        )
        fund_total = sum(
            info['weighted_score'] for key, info in indicators_scores.items()
            if self.indicators_config[key]['category'] == 'fundamental'
        )
        fund_weight = sum(
            info['weight'] for key, info in indicators_scores.items()
            if self.indicators_config[key]['category'] == 'fundamental'
        )

        tech_normalized = tech_total / tech_weight if tech_weight > 0 else 50
        fund_normalized = fund_total / fund_weight if fund_weight > 0 else 50

        # 确定建议等级
        suggestion = self._determine_suggestion(total_score)

        # 持仓覆盖信息
        holdings_summary = index_data.get('holdings_summary', {})
        holdings_detail = index_data.get('holdings_detail', [])

        # 生成决策结果
        decision_result = {
            'code': index_data.get('code'),
            'name': index_data.get('name'),
            'fund_type': index_data.get('fund_type', 'unknown'),
            'fund_category': index_data.get('fund_category', ''),
            'total_score': total_score,
            'technical_score': round(tech_normalized, 2),
            'fundamental_score': round(fund_normalized, 2),
            'suggestion': suggestion,
            'indicators_scores': indicators_scores,
            'decision_basis': self._generate_decision_basis(
                indicators_scores, total_score, suggestion, holdings_summary
            ),
            'indicator_weights': {k: v['weight'] for k, v in self.indicators_config.items()},
            'indicator_categories': {k: v['category'] for k, v in self.indicators_config.items()},
            'holdings_summary': holdings_summary,
            'holdings_detail': holdings_detail,
            'coverage_confidence': min(1.0, holdings_summary.get('coverage_pct', 100) / 100.0) if holdings_summary else 1.0,
        }

        logger.info(
            f"决策分析完成: {index_data.get('code')}, "
            f"综合: {total_score}, 技术: {tech_normalized:.1f}, 基本面: {fund_normalized:.1f}, "
            f"建议: {suggestion}"
        )
        return decision_result

    def _calculate_indicators_scores(self, index_data):
        """计算各指标得分

        Args:
            index_data: 包含指数数据的字典 (已合并技术指标评分)

        Returns:
            包含各指标得分的字典
        """
        scores = {}

        for indicator, config in self.indicators_config.items():
            value = index_data.get(indicator, 0)
            weight = config['weight']
            thresholds = config['thresholds']
            category = config['category']

            if category == 'technical':
                # 技术指标: value 已经是 TechnicalIndicators 算出的 0-100 评分
                score = value
            elif indicator == 'pe':
                score = self._score_pe(value, thresholds)
            elif indicator == 'roe':
                score = self._score_roe(value, thresholds)
            elif indicator == 'turnover':
                score = self._score_turnover(value, thresholds)
            elif indicator == 'fund_flow':
                score = self._score_fund_flow(
                    index_data.get('fund_net_change', 0), thresholds
                )
            else:
                logger.warning(f"未实现的指标评分逻辑: {indicator}")
                score = 50

            scores[indicator] = {
                'value': value,
                'score': score,
                'weight': weight,
                'category': category,
                'weighted_score': score * weight,
            }

        return scores

    # ── 基本面指标评分 (保持不变) ──────────────────────────────

    def _score_pe(self, pe, thresholds):
        """PE评分逻辑 — PE越低得分越高"""
        if pe <= thresholds['strong_buy']:
            return 100
        elif pe <= thresholds['buy']:
            return 80
        elif pe <= thresholds['hold']:
            return 60
        elif pe <= thresholds['sell']:
            return 40
        else:
            return 20

    def _score_roe(self, roe, thresholds):
        """ROE评分逻辑 — ROE越高得分越高"""
        if roe >= thresholds['strong_buy']:
            return 100
        elif roe >= thresholds['buy']:
            return 80
        elif roe >= thresholds['hold']:
            return 60
        elif roe >= thresholds['sell']:
            return 40
        else:
            return 20

    def _score_turnover(self, turnover, thresholds):
        """换手率评分逻辑 — 适中得分最高"""
        if turnover <= thresholds['strong_buy']:
            return 80
        elif turnover <= thresholds['buy']:
            return 100
        elif turnover <= thresholds['hold']:
            return 60
        elif turnover <= thresholds['sell']:
            return 40
        else:
            return 20

    def _score_fund_flow(self, fund_flow, thresholds):
        """资金流评分逻辑 — 净流入越多得分越高"""
        if fund_flow >= thresholds['strong_buy']:
            return 100
        elif fund_flow >= thresholds['buy']:
            return 80
        elif fund_flow >= thresholds['hold']:
            return 60
        elif fund_flow >= thresholds['sell']:
            return 40
        else:
            return 20

    # ── 综合得分类别判定 ────────────────────────────────────

    def _calculate_total_score(self, indicators_scores, holdings_summary=None):
        """计算综合得分 (0-100), 低覆盖率时回归中性。"""
        total_weighted_score = sum(
            info['weighted_score'] for info in indicators_scores.values()
        )
        total_weight = sum(
            info['weight'] for info in indicators_scores.values()
        )

        if total_weight != 1.0:
            logger.warning(
                f"指标权重总和不等于1.0，实际值: {total_weight}，将进行归一化处理"
            )
            raw = total_weighted_score / total_weight if total_weight > 0 else 50
        else:
            raw = total_weighted_score

        raw = max(0, min(100, raw))

        # 覆盖率置信度折扣: 低覆盖 → 回归中性 (50)
        if holdings_summary:
            coverage = holdings_summary.get('coverage_pct', 100) / 100.0
            confidence = min(1.0, coverage)
            adjusted = 50 + (raw - 50) * confidence
            if confidence < 0.95:
                logger.info(
                    f"覆盖率折扣: raw={raw:.1f}, coverage={coverage:.1%}, "
                    f"adjusted={adjusted:.1f}"
                )
            return round(adjusted, 2)

        return round(raw, 2)

    def _determine_suggestion(self, total_score):
        """根据综合得分确定建议等级"""
        for suggestion, (min_score, max_score) in self.score_levels.items():
            if min_score <= total_score <= max_score:
                return suggestion

        logger.warning(f"无法确定建议等级，综合得分: {total_score}")
        return 'hold'

    def _generate_decision_basis(self, indicators_scores, total_score, suggestion,
                                 holdings_summary=None):
        """生成决策依据文本"""
        basis = []

        basis.append(f"综合得分: {total_score}，建议: {self._get_suggestion_text(suggestion)}")

        # 持仓覆盖信息
        if holdings_summary and holdings_summary.get('used_count', 0) > 0:
            cov = holdings_summary
            if cov.get('is_full'):
                basis.append(f"持仓覆盖: 全部 {cov['used_count']} 只个股, 权重覆盖率 {cov.get('coverage_pct', 0):.1f}%")
            else:
                basis.append(
                    f"持仓覆盖: 前 {cov['used_count']}/{cov['total_count']} 只重仓股, "
                    f"权重覆盖率 {cov.get('coverage_pct', 0):.1f}%"
                )
        basis.append("")

        # 按类别分组输出
        tech_indicators = []
        fund_indicators = []

        for indicator, score_info in indicators_scores.items():
            config = self.indicators_config.get(indicator, {})
            category = config.get('category', 'unknown')
            name = self._get_indicator_name(indicator)
            value = score_info['value']
            score = score_info['score']
            weight = score_info['weight'] * 100

            line = f"  {name}: 得分={score:.1f}，权重={weight:.1f}%"

            if category == 'technical':
                tech_indicators.append(line)
            else:
                fund_indicators.append(f"{line}，值={value:.2f}" if isinstance(value, (int, float)) else line)

        basis.append("── 技术指标 (70%) ──")
        basis.extend(tech_indicators)
        basis.append("")
        basis.append("── 基本面指标 (30%) ──")
        basis.extend(fund_indicators)

        return '\n'.join(basis)

    # ── 名称映射 ─────────────────────────────────────────────

    def _get_indicator_name(self, indicator):
        """获取指标中文名称"""
        indicator_names = {
            # 技术指标
            'price_action': '价格行为(PRICE ACTION)',
            'fibonacci': '斐波那契(FIBONACCI)',
            'volume': '成交量(VOLUME)',
            'vwap': '均价(VWAP)',
            'ema': '指数均线(EMA)',
            'ma': '移动均线(MA)',
            # 基本面指标
            'pe': '市盈率(PE)',
            'roe': '净资产收益率(ROE)',
            'turnover': '换手率',
            'fund_flow': '主力资金净流入',
        }
        return indicator_names.get(indicator, indicator)

    def _get_suggestion_text(self, suggestion):
        """获取建议中文描述"""
        suggestion_texts = {
            'strong_buy': '📈 强烈买入',
            'buy': '👍 买入',
            'hold': '🤝 持有',
            'sell': '👎 卖出',
            'strong_sell': '📉 强烈卖出',
        }
        return suggestion_texts.get(suggestion, suggestion)

    # ── 公共接口 ────────────────────────────────────────────

    def get_suggestion_text(self, suggestion):
        return self._get_suggestion_text(suggestion)

    def get_indicator_name(self, indicator):
        return self._get_indicator_name(indicator)
