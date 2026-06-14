import requests
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
from utils.logger import logger


class RobotsChecker:
    """Robots协议检查器"""
    
    def __init__(self):
        """初始化Robots检查器"""
        self.cache = {}
    
    def _fetch_robots(self, base_url):
        """获取网站的robots.txt内容"""
        robots_url = urljoin(base_url, '/robots.txt')
        
        try:
            response = requests.get(robots_url, timeout=5)
            response.raise_for_status()
            logger.debug(f"获取robots.txt成功: {robots_url}")
            return response.text
        except requests.RequestException as e:
            logger.warning(f"获取robots.txt失败: {robots_url}, 错误: {str(e)}")
            return ""
    
    def _parse_robots(self, robots_content):
        """解析robots.txt内容"""
        rules = {}
        current_user_agent = '*'
        
        for line in robots_content.split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            parts = line.split(':', 1)
            if len(parts) != 2:
                continue
            
            key, value = parts[0].strip().lower(), parts[1].strip()
            
            if key == 'user-agent':
                current_user_agent = value
                rules[current_user_agent] = {
                    'allow': [],
                    'disallow': []
                }
            elif key in ['allow', 'disallow']:
                if current_user_agent not in rules:
                    rules[current_user_agent] = {
                        'allow': [],
                        'disallow': []
                    }
                rules[current_user_agent][key].append(value)
        
        return rules
    
    def can_crawl(self, url, user_agent='*'):
        """检查是否可以爬取指定URL"""
        parsed_url = urlparse(url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        path = parsed_url.path or "/"
        
        # 检查缓存
        cache_key = f"{base_url}:{user_agent}"
        if cache_key not in self.cache:
            robots_content = self._fetch_robots(base_url)
            rules = self._parse_robots(robots_content)
            self.cache[cache_key] = rules
        
        rules = self.cache[cache_key]
        
        # 获取适用的规则
        applicable_rules = rules.get(user_agent, {})
        # 如果没有特定的user-agent规则，使用通用规则
        if not applicable_rules and '*' in rules:
            applicable_rules = rules['*']
        
        # 默认允许爬取
        can_crawl = True
        
        # 检查disallow规则
        for disallow_path in applicable_rules.get('disallow', []):
            if disallow_path == '' or path.startswith(disallow_path):
                can_crawl = False
                break
        
        # 检查allow规则（优先级高于disallow）
        if not can_crawl:
            for allow_path in applicable_rules.get('allow', []):
                if path.startswith(allow_path):
                    can_crawl = True
                    break
        
        logger.debug(f"URL爬取检查结果: {url} - {'允许' if can_crawl else '禁止'}")
        return can_crawl
    
    def clear_cache(self):
        """清除缓存"""
        self.cache.clear()
        logger.debug("Robots检查器缓存已清除")


# 创建默认实例
robots_checker = RobotsChecker()
