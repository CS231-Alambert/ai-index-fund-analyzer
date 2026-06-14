from crawler.base_crawler import BaseCrawler
from config import DATA_SOURCES
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
        """获取指数数据
        
        Args:
            code: 6位指数代码
            
        Returns:
            包含指数数据的字典，如果失败则返回None
        """
        logger.info(f"开始爬取指数数据: {code}, 数据源: {self.source}")
        
        # 根据数据源选择不同的爬取逻辑
        if self.source == 'default':
            return self._get_sina_index_data(code)
        elif self.source == 'eastmoney':
            return self._get_eastmoney_index_data(code)
        else:
            logger.error(f"未实现的数据源爬取逻辑: {self.source}")
            return None
    
    def _get_sina_index_data(self, code):
        """从新浪财经获取指数数据"""
        try:
            # 构建URL
            index_url = f"{self.base_url}{self.source_config['index_data_path'].format(code=code)}"
            fund_flow_url = f"{self.base_url}{self.source_config['fund_flow_path'].format(code=code)}"
            
            # 爬取指数基本数据
            index_html = self.fetch_html(index_url)
            if not index_html:
                return None
            
            # 爬取资金流数据
            fund_flow_html = self.fetch_html(fund_flow_url)
            if not fund_flow_html:
                return None
            
            # 解析指数数据
            index_soup = BeautifulSoup(index_html, 'html.parser')
            fund_flow_soup = BeautifulSoup(fund_flow_html, 'html.parser')
            
            # 解析基本指标
            pe = self._parse_pe_sina(index_soup)
            roe = self._parse_roe_sina(index_soup)
            turnover = self._parse_turnover_sina(index_soup)
            
            # 解析资金流数据
            fund_flow_data = self._parse_fund_flow_sina(fund_flow_soup)
            
            # 整合数据
            index_data = {
                'code': code,
                'name': self._parse_name_sina(index_soup),
                'pe': pe,
                'roe': roe,
                'turnover': turnover,
                'fund_inflow': fund_flow_data.get('inflow', 0),
                'fund_outflow': fund_flow_data.get('outflow', 0),
                'fund_net_change': fund_flow_data.get('net_change', 0),
                'source': self.source
            }
            
            logger.info(f"爬取指数数据成功: {code}")
            return index_data
        except Exception as e:
            logger.error(f"爬取新浪指数数据失败: {code}, 错误: {str(e)}")
            return None
    
    def _get_eastmoney_index_data(self, code):
        """从东方财富获取指数数据"""
        try:
            # 确定市场类型（上证/深证）
            market = 'sh' if code.startswith('0') or code.startswith('3') else 'sz'
            
            # 构建URL
            index_url = f"{self.base_url}{self.source_config['index_data_path'].format(market=market, code=code)}"
            
            # 爬取数据
            index_html = self.fetch_html(index_url)
            if not index_html:
                return None
            
            # 解析数据
            index_soup = BeautifulSoup(index_html, 'html.parser')
            
            # 解析基本指标
            pe = self._parse_pe_eastmoney(index_soup)
            roe = self._parse_roe_eastmoney(index_soup)
            turnover = self._parse_turnover_eastmoney(index_soup)
            
            # 整合数据（东方财富的资金流数据可能需要单独爬取）
            index_data = {
                'code': code,
                'name': self._parse_name_eastmoney(index_soup),
                'pe': pe,
                'roe': roe,
                'turnover': turnover,
                'fund_inflow': 0,  # 东方财富资金流数据需要单独实现
                'fund_outflow': 0,
                'fund_net_change': 0,
                'source': self.source
            }
            
            logger.info(f"爬取指数数据成功: {code}")
            return index_data
        except Exception as e:
            logger.error(f"爬取东方财富指数数据失败: {code}, 错误: {str(e)}")
            return None
    
    # 新浪财经解析方法
    def _parse_name_sina(self, soup):
        """解析指数名称"""
        try:
            name_elem = soup.find('h1', class_='name')
            return name_elem.text.strip() if name_elem else ''
        except Exception:
            return ''
    
    def _parse_pe_sina(self, soup):
        """解析PE"""
        try:
            # 这里需要根据新浪财经的实际页面结构调整
            pe_elem = soup.find('td', text=re.compile('市盈率'))
            if pe_elem:
                pe_text = pe_elem.find_next('td').text.strip()
                return float(pe_text) if pe_text else 0
            return 0
        except Exception:
            return 0
    
    def _parse_roe_sina(self, soup):
        """解析ROE"""
        try:
            # 这里需要根据新浪财经的实际页面结构调整
            roe_elem = soup.find('td', text=re.compile('净资产收益率'))
            if roe_elem:
                roe_text = roe_elem.find_next('td').text.strip()
                # 移除百分号并转换为浮点数
                roe_text = roe_text.replace('%', '')
                return float(roe_text) if roe_text else 0
            return 0
        except Exception:
            return 0
    
    def _parse_turnover_sina(self, soup):
        """解析换手率"""
        try:
            # 这里需要根据新浪财经的实际页面结构调整
            turnover_elem = soup.find('td', text=re.compile('换手率'))
            if turnover_elem:
                turnover_text = turnover_elem.find_next('td').text.strip()
                # 移除百分号并转换为浮点数
                turnover_text = turnover_text.replace('%', '')
                return float(turnover_text) if turnover_text else 0
            return 0
        except Exception:
            return 0
    
    def _parse_fund_flow_sina(self, soup):
        """解析资金流数据"""
        try:
            # 这里需要根据新浪财经的实际页面结构调整
            fund_flow = {
                'inflow': 0,
                'outflow': 0,
                'net_change': 0
            }
            
            # 示例解析逻辑，需要根据实际页面调整
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
        except Exception as e:
            logger.error(f"解析资金流数据失败: {str(e)}")
            return {
                'inflow': 0,
                'outflow': 0,
                'net_change': 0
            }
    
    # 东方财富解析方法
    def _parse_name_eastmoney(self, soup):
        """解析指数名称"""
        try:
            name_elem = soup.find('div', class_='name')
            return name_elem.text.strip() if name_elem else ''
        except Exception:
            return ''
    
    def _parse_pe_eastmoney(self, soup):
        """解析PE"""
        try:
            # 这里需要根据东方财富的实际页面结构调整
            pe_elem = soup.find('span', text=re.compile('市盈率'))
            if pe_elem:
                pe_text = pe_elem.find_next('span').text.strip()
                return float(pe_text) if pe_text else 0
            return 0
        except Exception:
            return 0
    
    def _parse_roe_eastmoney(self, soup):
        """解析ROE"""
        try:
            # 这里需要根据东方财富的实际页面结构调整
            roe_elem = soup.find('span', text=re.compile('净资产收益率'))
            if roe_elem:
                roe_text = roe_elem.find_next('span').text.strip()
                # 移除百分号并转换为浮点数
                roe_text = roe_text.replace('%', '')
                return float(roe_text) if roe_text else 0
            return 0
        except Exception:
            return 0
    
    def _parse_turnover_eastmoney(self, soup):
        """解析换手率"""
        try:
            # 这里需要根据东方财富的实际页面结构调整
            turnover_elem = soup.find('span', text=re.compile('换手率'))
            if turnover_elem:
                turnover_text = turnover_elem.find_next('span').text.strip()
                # 移除百分号并转换为浮点数
                turnover_text = turnover_text.replace('%', '')
                return float(turnover_text) if turnover_text else 0
            return 0
        except Exception:
            return 0
    
    def _parse_amount(self, amount_str):
        """解析金额字符串为数字（处理亿、万等单位）"""
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
    
    def get_historical_data(self, code, start_date=None, end_date=None):
        """获取指数历史数据
        
        Args:
            code: 6位指数代码
            start_date: 开始日期（格式：YYYY-MM-DD）
            end_date: 结束日期（格式：YYYY-MM-DD）
            
        Returns:
            包含历史数据的DataFrame，如果失败则返回None
        """
        logger.info(f"获取指数历史数据: {code}, 开始日期: {start_date}, 结束日期: {end_date}")
        
        # 这里可以实现历史数据的爬取逻辑
        # 示例：返回模拟数据
        import pandas as pd
        import numpy as np
        
        # 创建日期范围
        if not start_date:
            start_date = '2020-01-01'
        if not end_date:
            end_date = pd.Timestamp.now().strftime('%Y-%m-%d')
        
        date_range = pd.date_range(start=start_date, end=end_date, freq='D')
        
        # 创建模拟数据
        data = {
            'date': date_range,
            'code': [code] * len(date_range),
            'name': [f'指数{code}'] * len(date_range),
            'pe': np.random.uniform(10, 30, len(date_range)),
            'roe': np.random.uniform(5, 20, len(date_range)),
            'turnover': np.random.uniform(0.5, 5, len(date_range)),
            'fund_inflow': np.random.uniform(0, 100000000, len(date_range)),
            'fund_outflow': np.random.uniform(0, 100000000, len(date_range))
        }
        
        df = pd.DataFrame(data)
        df['fund_net_change'] = df['fund_inflow'] - df['fund_outflow']
        
        logger.info(f"获取指数历史数据成功: {code}, 数据条数: {len(df)}")
        return df
