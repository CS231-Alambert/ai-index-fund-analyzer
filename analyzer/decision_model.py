from config import DECISION_MODEL_CONFIG
from utils.logger import logger


class DecisionModel:
    """决策分析模型"""
    
    def __init__(self):
        """初始化决策模型"""
        self.config = DECISION_MODEL_CONFIG
        self.indicators_config = self.config['indicators']
        self.score_levels = self.config['score_levels']
        logger.info("决策模型初始化完成")
    
    def analyze(self, index_data):
        """分析指数数据，生成决策建议
        
        Args:
            index_data: 包含指数数据的字典
            
        Returns:
            包含决策结果的字典
        """
        logger.info(f"开始分析指数数据: {index_data.get('code')} {index_data.get('name')}")
        
        # 计算各指标得分
        indicators_scores = self._calculate_indicators_scores(index_data)
        
        # 计算综合得分
        total_score = self._calculate_total_score(indicators_scores)
        
        # 确定建议等级
        suggestion = self._determine_suggestion(total_score)
        
        # 生成决策结果
        decision_result = {
            'code': index_data.get('code'),
            'name': index_data.get('name'),
            'total_score': total_score,
            'suggestion': suggestion,
            'indicators_scores': indicators_scores,
            'decision_basis': self._generate_decision_basis(indicators_scores, total_score, suggestion),
            'indicator_weights': {k: v['weight'] for k, v in self.indicators_config.items()}
        }
        
        logger.info(f"决策分析完成: {index_data.get('code')}, 综合得分: {total_score}, 建议: {suggestion}")
        return decision_result
    
    def _calculate_indicators_scores(self, index_data):
        """计算各指标得分
        
        Args:
            index_data: 包含指数数据的字典
            
        Returns:
            包含各指标得分的字典
        """
        scores = {}
        
        for indicator, config in self.indicators_config.items():
            value = index_data.get(indicator, 0)
            weight = config['weight']
            thresholds = config['thresholds']
            
            # 根据指标类型选择不同的评分逻辑
            if indicator == 'pe':
                # PE越低，得分越高
                score = self._score_pe(value, thresholds)
            elif indicator == 'roe':
                # ROE越高，得分越高
                score = self._score_roe(value, thresholds)
            elif indicator == 'turnover':
                # 换手率适中，得分越高
                score = self._score_turnover(value, thresholds)
            elif indicator == 'fund_flow':
                # 资金净流入越多，得分越高
                score = self._score_fund_flow(index_data.get('fund_net_change', 0), thresholds)
            else:
                logger.warning(f"未实现的指标评分逻辑: {indicator}")
                score = 50
            
            scores[indicator] = {
                'value': value,
                'score': score,
                'weight': weight,
                'weighted_score': score * weight
            }
        
        return scores
    
    def _score_pe(self, pe, thresholds):
        """PE评分逻辑
        PE越低，得分越高
        """
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
        """ROE评分逻辑
        ROE越高，得分越高
        """
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
        """换手率评分逻辑
        换手率适中，得分越高
        """
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
        """资金流评分逻辑
        资金净流入越多，得分越高
        """
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
    
    def _calculate_total_score(self, indicators_scores):
        """计算综合得分
        
        Args:
            indicators_scores: 包含各指标得分的字典
            
        Returns:
            综合得分（0-100）
        """
        total_weighted_score = sum(score_info['weighted_score'] for score_info in indicators_scores.values())
        # 权重总和应该是1.0，这里再次确认
        total_weight = sum(score_info['weight'] for score_info in indicators_scores.values())
        
        if total_weight != 1.0:
            logger.warning(f"指标权重总和不等于1.0，实际值: {total_weight}，将进行归一化处理")
            total_score = total_weighted_score / total_weight
        else:
            total_score = total_weighted_score
        
        # 确保得分在0-100之间
        total_score = max(0, min(100, total_score))
        return round(total_score, 2)
    
    def _determine_suggestion(self, total_score):
        """根据综合得分确定建议等级
        
        Args:
            total_score: 综合得分
            
        Returns:
            建议等级（strong_buy, buy, hold, sell, strong_sell）
        """
        for suggestion, (min_score, max_score) in self.score_levels.items():
            if min_score <= total_score <= max_score:
                return suggestion
        
        # 默认返回持有
        logger.warning(f"无法确定建议等级，综合得分: {total_score}")
        return 'hold'
    
    def _generate_decision_basis(self, indicators_scores, total_score, suggestion):
        """生成决策依据
        
        Args:
            indicators_scores: 包含各指标得分的字典
            total_score: 综合得分
            suggestion: 建议等级
            
        Returns:
            决策依据字符串
        """
        basis = []
        
        # 添加综合得分信息
        basis.append(f"综合得分: {total_score}，建议: {self._get_suggestion_text(suggestion)}")
        
        # 添加各指标详细信息
        for indicator, score_info in indicators_scores.items():
            indicator_name = self._get_indicator_name(indicator)
            value = score_info['value']
            score = score_info['score']
            weight = score_info['weight'] * 100
            
            basis.append(f"{indicator_name}: 值={value:.2f}，得分={score:.2f}，权重={weight:.1f}%")
        
        return '\n'.join(basis)
    
    def _get_indicator_name(self, indicator):
        """获取指标中文名称
        
        Args:
            indicator: 指标英文名称
            
        Returns:
            指标中文名称
        """
        indicator_names = {
            'pe': '市盈率(PE)',
            'roe': '净资产收益率(ROE)',
            'turnover': '换手率',
            'fund_flow': '主力资金净流入'
        }
        return indicator_names.get(indicator, indicator)
    
    def _get_suggestion_text(self, suggestion):
        """获取建议中文描述
        
        Args:
            suggestion: 建议英文名称
            
        Returns:
            建议中文描述
        """
        suggestion_texts = {
            'strong_buy': '强烈买入',
            'buy': '买入',
            'hold': '持有',
            'sell': '卖出',
            'strong_sell': '强烈卖出'
        }
        return suggestion_texts.get(suggestion, suggestion)
    
    def get_suggestion_text(self, suggestion):
        """获取建议中文描述（对外接口）
        
        Args:
            suggestion: 建议英文名称
            
        Returns:
            建议中文描述
        """
        return self._get_suggestion_text(suggestion)
    
    def get_indicator_name(self, indicator):
        """获取指标中文名称（对外接口）
        
        Args:
            indicator: 指标英文名称
            
        Returns:
            指标中文名称
        """
        return self._get_indicator_name(indicator)
