import requests
from utils.logger import logger
from crawler.robots_checker import robots_checker
from config import CACHE_CONFIG


class BaseCrawler:
    """基础爬虫类"""
    
    def __init__(self, base_url, user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'):
        """初始化基础爬虫"""
        self.base_url = base_url
        self.user_agent = user_agent
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9'
        })
    
    def fetch(self, url, method='GET', params=None, data=None, headers=None, **kwargs):
        """发送请求获取数据
        
        Args:
            url: 请求URL
            method: 请求方法（GET或POST）
            params: URL参数
            data: 请求体数据
            headers: 额外的请求头
            **kwargs: 其他请求参数
            
        Returns:
            请求响应对象，如果请求失败则返回None
        """
        # 检查是否可以爬取
        if not robots_checker.can_crawl(url, self.user_agent):
            logger.warning(f"根据robots.txt规则，禁止爬取: {url}")
            return None
        
        # 合并请求头
        if headers:
            self.session.headers.update(headers)
        
        # 重试机制
        for retry in range(CACHE_CONFIG['max_retries']):
            try:
                logger.debug(f"发送请求: {method} {url}, 重试次数: {retry+1}")
                
                if method.upper() == 'GET':
                    response = self.session.get(url, params=params, timeout=10, **kwargs)
                elif method.upper() == 'POST':
                    response = self.session.post(url, params=params, data=data, timeout=10, **kwargs)
                else:
                    logger.error(f"不支持的请求方法: {method}")
                    return None
                
                response.raise_for_status()
                logger.debug(f"请求成功: {url}")
                return response
            except requests.RequestException as e:
                logger.warning(f"请求失败: {url}, 错误: {str(e)}, 重试次数: {retry+1}")
                
                if retry == CACHE_CONFIG['max_retries'] - 1:
                    logger.error(f"请求多次失败，放弃: {url}")
                    return None
                
                # 等待一段时间后重试
                import time
                time.sleep(CACHE_CONFIG['retry_delay'])
        
        return None
    
    def fetch_html(self, url, **kwargs):
        """获取HTML内容
        
        Args:
            url: 请求URL
            **kwargs: 其他请求参数
            
        Returns:
            HTML字符串，如果请求失败则返回None
        """
        response = self.fetch(url, **kwargs)
        if response:
            return response.text
        return None
    
    def fetch_json(self, url, **kwargs):
        """获取JSON数据
        
        Args:
            url: 请求URL
            **kwargs: 其他请求参数
            
        Returns:
            JSON数据（字典或列表），如果请求失败则返回None
        """
        response = self.fetch(url, **kwargs)
        if response:
            try:
                return response.json()
            except ValueError as e:
                logger.error(f"解析JSON失败: {url}, 错误: {str(e)}")
                return None
        return None
    
    def close(self):
        """关闭会话"""
        self.session.close()
