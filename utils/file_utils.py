import os
import datetime
from pathlib import Path


def ensure_dir(directory):
    """确保目录存在，如果不存在则创建"""
    Path(directory).mkdir(parents=True, exist_ok=True)


def file_exists(file_path):
    """检查文件是否存在"""
    return os.path.exists(file_path)


def generate_filename(pattern, code, name):
    """根据模板生成文件名"""
    today = datetime.datetime.now().strftime('%Y%m%d')
    return pattern.format(code=code, name=name, date=today)


def get_file_size(file_path):
    """获取文件大小（字节）"""
    if not file_exists(file_path):
        return 0
    return os.path.getsize(file_path)


def list_files(directory, extension=None):
    """列出目录下的文件，可选择按扩展名过滤"""
    if not os.path.isdir(directory):
        return []
    
    files = os.listdir(directory)
    if extension:
        files = [f for f in files if f.endswith(extension)]
    
    return files


def get_absolute_path(relative_path):
    """获取相对路径的绝对路径"""
    return os.path.abspath(relative_path)
