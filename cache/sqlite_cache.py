import sqlite3
import json
import datetime
import os
from config import CACHE_CONFIG
from utils.logger import logger
from utils.file_utils import ensure_dir


class SQLiteCache:
    """SQLite缓存实现"""
    
    def __init__(self):
        """初始化缓存"""
        # 确保缓存目录存在
        cache_dir = os.path.dirname(CACHE_CONFIG['db_path'])
        ensure_dir(cache_dir)
        
        self.db_path = CACHE_CONFIG['db_path']
        self.default_ttl = CACHE_CONFIG['default_ttl']
        self._init_db()
    
    def _init_db(self):
        """初始化数据库表"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # 创建缓存表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL
                )
            ''')
            # 创建过期索引
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_expires_at ON cache(expires_at)
            ''')
            conn.commit()
    
    def _get_current_timestamp(self):
        """获取当前时间戳（秒）"""
        return int(datetime.datetime.now().timestamp())
    
    def set(self, key, value, ttl=None):
        """存储缓存
        
        Args:
            key: 缓存键
            value: 缓存值（将被序列化为JSON）
            ttl: 过期时间（秒），如果为None则使用默认值
        """
        ttl = ttl or self.default_ttl
        current_ts = self._get_current_timestamp()
        expires_at = current_ts + ttl
        
        try:
            serialized_value = json.dumps(value)
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO cache (key, value, created_at, expires_at)
                    VALUES (?, ?, ?, ?)
                ''', (key, serialized_value, current_ts, expires_at))
                conn.commit()
            logger.debug(f"缓存已存储: {key}")
            return True
        except Exception as e:
            logger.error(f"存储缓存失败: {key}, 错误: {str(e)}")
            return False
    
    def get(self, key):
        """获取缓存
        
        Args:
            key: 缓存键
            
        Returns:
            缓存值，如果不存在或已过期则返回None
        """
        current_ts = self._get_current_timestamp()
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT value, expires_at FROM cache WHERE key = ?
                ''', (key,))
                row = cursor.fetchone()
                
                if not row:
                    logger.debug(f"缓存不存在: {key}")
                    return None
                
                serialized_value, expires_at = row
                
                # 检查是否过期
                if current_ts > expires_at:
                    logger.debug(f"缓存已过期: {key}")
                    self.delete(key)
                    return None
                
                value = json.loads(serialized_value)
                logger.debug(f"缓存已获取: {key}")
                return value
        except Exception as e:
            logger.error(f"获取缓存失败: {key}, 错误: {str(e)}")
            return None
    
    def delete(self, key):
        """删除缓存"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM cache WHERE key = ?', (key,))
                conn.commit()
            logger.debug(f"缓存已删除: {key}")
            return True
        except Exception as e:
            logger.error(f"删除缓存失败: {key}, 错误: {str(e)}")
            return False
    
    def clear_expired(self):
        """清除所有过期缓存"""
        current_ts = self._get_current_timestamp()
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM cache WHERE expires_at < ?', (current_ts,))
                deleted_count = cursor.rowcount
                conn.commit()
            logger.debug(f"已清除过期缓存: {deleted_count} 条")
            return deleted_count
        except Exception as e:
            logger.error(f"清除过期缓存失败: {str(e)}")
            return 0
    
    def clear_all(self):
        """清除所有缓存"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM cache')
                conn.commit()
            logger.debug("所有缓存已清除")
            return True
        except Exception as e:
            logger.error(f"清除所有缓存失败: {str(e)}")
            return False
    
    def get_keys(self):
        """获取所有缓存键"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT key FROM cache')
                keys = [row[0] for row in cursor.fetchall()]
            return keys
        except Exception as e:
            logger.error(f"获取缓存键失败: {str(e)}")
            return []
    
    def get_stats(self):
        """获取缓存统计信息"""
        current_ts = self._get_current_timestamp()
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 总缓存数
                cursor.execute('SELECT COUNT(*) FROM cache')
                total = cursor.fetchone()[0]
                
                # 过期缓存数
                cursor.execute('SELECT COUNT(*) FROM cache WHERE expires_at < ?', (current_ts,))
                expired = cursor.fetchone()[0]
                
                # 有效缓存数
                valid = total - expired
                
            return {
                'total': total,
                'valid': valid,
                'expired': expired
            }
        except Exception as e:
            logger.error(f"获取缓存统计信息失败: {str(e)}")
            return {
                'total': 0,
                'valid': 0,
                'expired': 0
            }


# 创建默认缓存实例
cache = SQLiteCache()
