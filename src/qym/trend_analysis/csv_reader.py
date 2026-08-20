# -*- coding: utf-8 -*-
"""
CSV 文件读取工具类

用于读取 stock_limitup.csv 等股票数据文件
"""

from dataclasses import dataclass
from typing import Optional, List, Dict
import csv
import os
import logging
import io

logger = logging.getLogger(__name__)

try:
    from src.qym.trend_analysis.csv_reader import StockLimitupCSVReader
    from src.gitee_client  import GiteeClient
except ImportError:
    import sys
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from src.gitee_client  import GiteeClient


def get_project_root() -> str:
    """获取项目根目录的绝对路径"""
    current_file = os.path.abspath(__file__)
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(current_file)))))


def resolve_csv_path(csv_path: Optional[str] = None) -> str:
    """
    解析 CSV 文件路径
    
    Args:
        csv_path: CSV 文件路径，可以是绝对路径或相对路径
                  如果为 None，使用默认路径
                  如果是相对路径，会基于项目根目录解析
        
    Returns:
        绝对路径
    """
    default_relative_path = os.path.join('sources', 'stock_limitup.csv')
    
    if csv_path is None:
        csv_path = default_relative_path
    
    if os.path.isabs(csv_path):
        return csv_path
    
    project_root = get_project_root()
    return os.path.join(project_root, csv_path)


@dataclass
class StockInfo:
    """股票信息"""
    code: str
    name: str
    limitup_count: int = 0
    sector: str = ""
    
    def to_dict(self) -> Dict:
        return {
            'code': self.code,
            'name': self.name,
            'limitup_count': self.limitup_count,
            'sector': self.sector
        }


class StockLimitupCSVReader:
    """涨停股票 CSV 文件读取器
    
    用于读取 stock_limitup.csv 格式的文件，支持多种分隔符
    支持从本地文件或 Gitee 仓库读取
    """
    
    DEFAULT_LOCAL_PATH = 'sources/stock_limitup.csv'
    DEFAULT_GITEE_PATH = 'input/stock_limitup.csv'
    
    def __init__(self, csv_path: Optional[str] = None, use_gitee: bool = True,
                 gitee_repo: Optional[str] = None, gitee_token: Optional[str] = None):
        """
        初始化 CSV 读取器
        
        Args:
            csv_path: CSV 文件路径
                - 本地模式: 相对路径（基于项目根目录）或绝对路径
                - Gitee 模式: 远程文件路径（相对于仓库根目录）
            use_gitee: 是否从 Gitee 仓库读取，默认 False
            gitee_repo: Gitee 仓库名称，格式为 "username/repo"，默认 "qymmdj/stockdb"
            gitee_token: Gitee 访问令牌，默认从环境变量 GITEE_TOKEN 获取
        """
        self._csv_path_input = csv_path
        self._use_gitee = use_gitee
        self._gitee_repo = gitee_repo or "qymmdj/stockdb"
        self._gitee_token = gitee_token
        self._resolved_path: Optional[str] = None
        self._stock_list: List[StockInfo] = []
        self._stock_dict: Dict[str, StockInfo] = {}
        self._gitee_client: Optional[GiteeClient] = None
    
    @property
    def csv_path(self) -> str:
        """获取解析后的 CSV 文件路径"""
        if self._resolved_path is None:
            if self._use_gitee:
                self._resolved_path = self._csv_path_input or self.DEFAULT_GITEE_PATH
            else:
                self._resolved_path = resolve_csv_path(self._csv_path_input)
        return self._resolved_path
    
    @property
    def gitee_client(self) -> GiteeClient:
        """获取 Gitee 客户端实例"""
        if self._gitee_client is None:
            self._gitee_client = GiteeClient(token=self._gitee_token, repo=self._gitee_repo)
        return self._gitee_client
    
    def _detect_delimiter(self, sample: str) -> str:
        """检测 CSV 文件的分隔符"""
        lines = sample.split('\n')
        if len(lines) > 1:
            first_data_line = lines[1]
            if '\t' in first_data_line:
                return '\t'
            elif ',' in first_data_line:
                return ','
            elif ' ' in first_data_line:
                return ' '
        return '\t'
    
    def _read_from_gitee(self) -> List[StockInfo]:
        """从 Gitee 仓库读取 CSV 文件"""
        try:
            logger.info(f"从 Gitee 仓库读取文件: {self._gitee_repo}/{self.csv_path}")
            
            content = self.gitee_client.get_file_content(self.csv_path)
            if content is None:
                logger.error(f"从 Gitee 读取文件失败: {self.csv_path}")
                return []
            
            return self._parse_csv_content(content, source=f"Gitee:{self._gitee_repo}/{self.csv_path}")
            
        except Exception as e:
            logger.error(f"从 Gitee 读取 CSV 文件失败: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _read_from_local(self) -> List[StockInfo]:
        """从本地文件读取 CSV"""
        try:
            with open(self.csv_path, 'r', encoding='utf-8', newline='') as f:
                content = f.read()
            
            return self._parse_csv_content(content, source=self.csv_path)
            
        except FileNotFoundError:
            logger.error(f"CSV 文件不存在: {self.csv_path}")
            return []
        except Exception as e:
            logger.error(f"读取本地 CSV 文件失败: {e}")
            return []
    
    def _parse_csv_content(self, content: str, source: str = "unknown") -> List[StockInfo]:
        """
        解析 CSV 内容
        
        Args:
            content: CSV 文本内容
            source: 数据来源描述（用于日志）
        
        Returns:
            股票信息列表
        """
        self._stock_list = []
        self._stock_dict = {}
        
        try:
            sample = content[:4096] if len(content) > 4096 else content
            delimiter = self._detect_delimiter(sample)
            
            reader = csv.reader(io.StringIO(content), delimiter=delimiter)
            rows = list(reader)
            
            if not rows:
                logger.warning(f"CSV 内容为空: {source}")
                return []
            
            header_line = rows[0]
            if isinstance(header_line, list) and len(header_line) == 1:
                columns = header_line[0].split()
            elif isinstance(header_line, list):
                columns = header_line
            else:
                columns = header_line.split()
            
            for row in rows[1:]:
                if not row or len(row) < 3:
                    continue
                
                try:
                    stock_info = self._parse_row(row, columns)
                    if stock_info:
                        self._stock_list.append(stock_info)
                        self._stock_dict[stock_info.code] = stock_info
                except Exception as e:
                    logger.debug(f"解析行失败: {row}, 错误: {e}")
                    continue
            
            logger.info(f"成功从 {source} 加载 {len(self._stock_list)} 只股票")
            return self._stock_list
            
        except Exception as e:
            logger.error(f"解析 CSV 内容失败: {e}")
            return []
    
    def read(self) -> List[StockInfo]:
        """
        读取 CSV 文件
        
        Returns:
            股票信息列表
        """
        self._stock_list = []
        self._stock_dict = {}
        
        if self._use_gitee:
            return self._read_from_gitee()
        else:
            return self._read_from_local()
    
    def _parse_row(self, row: List[str], columns: List[str]) -> Optional[StockInfo]:
        """
        解析 CSV 行数据
        
        支持两种格式:
        1. 涨停次数\t股票代码\t股票名称\t关联板块名称
        2. 股票代码\t股票名称\t...
        """
        row = [cell.strip() for cell in row]

        code_idx = -1
        name_idx = -1
        limitup_idx = -1
        sector_idx = -1

        for i, col in enumerate(columns):
            col_lower = col.lower().strip()
            if '代码' in col or 'code' in col_lower:
                code_idx = i
            elif '涨停' in col or 'limitup' in col_lower:
                limitup_idx = i
            elif '中文名称' in col or '股票名称' in col:
                name_idx = i
            elif '板块' in col or 'sector' in col_lower:
                sector_idx = i

        # 如果通过列名没找到代码列，通过内容特征找
        if code_idx == -1:
            for i, cell in enumerate(row):
                if cell and (cell.endswith('.SS') or cell.endswith('.SZ')):
                    code_idx = i
                    break

        # 如果没找到带后缀的，再找数字开头的（6开头上海，0/3开头深圳）
        if code_idx == -1:
            for i, cell in enumerate(row):
                if cell and len(cell) == 6 and cell.isdigit():
                    if cell.startswith('6'):
                        code_idx = i
                        row[i] = cell + '.SS'
                        break
                    elif cell.startswith('0') or cell.startswith('3'):
                        code_idx = i
                        row[i] = cell + '.SZ'
                        break

        if code_idx == -1 or code_idx >= len(row):
            return None

        stock_code = row[code_idx]
        
        stock_name = row[name_idx] if name_idx != -1 and name_idx < len(row) else ""
        
        limitup_count = 0
        if limitup_idx != -1 and limitup_idx < len(row):
            try:
                limitup_count = int(row[limitup_idx])
            except ValueError:
                limitup_count = 0
        
        sector = row[sector_idx] if sector_idx != -1 and sector_idx < len(row) else ""
        
        return StockInfo(
            code=stock_code,
            name=stock_name,
            limitup_count=limitup_count,
            sector=sector
        )
    
    def get_stock_list(self) -> List[StockInfo]:
        """获取股票列表"""
        if not self._stock_list:
            self.read()
        return self._stock_list
    
    def get_stock_dict(self) -> Dict[str, StockInfo]:
        """获取股票字典 (股票代码 -> StockInfo)"""
        if not self._stock_dict:
            self.read()
        return self._stock_dict
    
    def get_stock_by_code(self, code: str) -> Optional[StockInfo]:
        """根据股票代码获取股票信息"""
        if not self._stock_dict:
            self.read()
        return self._stock_dict.get(code)
    
    def get_stock_codes(self) -> List[str]:
        """获取所有股票代码列表"""
        if not self._stock_list:
            self.read()
        return [s.code for s in self._stock_list]
    
    def to_dict_list(self) -> List[Dict]:
        """转换为字典列表"""
        return [s.to_dict() for s in self.get_stock_list()]


def load_stock_limitup_csv(csv_path: Optional[str] = None, use_gitee: bool = False,
                          gitee_repo: Optional[str] = None, gitee_token: Optional[str] = None) -> List[Dict]:
    """
    便捷函数：读取涨停股票 CSV 文件并返回字典列表
    
    Args:
        csv_path: CSV 文件路径
            - 本地模式: None 使用默认路径 sources/stock_limitup.csv（基于项目根目录）
            - 本地模式: 相对路径 基于项目根目录解析
            - 本地模式: 绝对路径 直接使用
            - Gitee 模式: 远程文件路径（相对于仓库根目录）
        use_gitee: 是否从 Gitee 仓库读取，默认 False
        gitee_repo: Gitee 仓库名称，格式为 "username/repo"，默认 "qymmdj/stockdb"
        gitee_token: Gitee 访问令牌，默认从环境变量 GITEE_TOKEN 获取
        
    Returns:
        股票信息字典列表
    """
    reader = StockLimitupCSVReader(csv_path, use_gitee=use_gitee, 
                                 gitee_repo=gitee_repo, gitee_token=gitee_token)
    return reader.to_dict_list()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 60)
    print("测试 1: 从本地文件读取")
    print("=" * 60)
    reader = StockLimitupCSVReader()
    stocks = reader.get_stock_list()
    
    print(f"共加载 {len(stocks)} 只股票")
    for stock in stocks[:5]:
        print(f"  {stock.code} - {stock.name} - 涨停{stock.limitup_count}次 - {stock.sector}")
    
    print("\n" + "=" * 60)
    print("测试 2: 从 Gitee 仓库读取")
    print("=" * 60)
    gitee_reader = StockLimitupCSVReader(use_gitee=True)
    gitee_stocks = gitee_reader.get_stock_list()
    
    print(f"共加载 {len(gitee_stocks)} 只股票")
    for stock in gitee_stocks[:5]:
        print(f"  {stock.code} - {stock.name} - 涨停{stock.limitup_count}次 - {stock.sector}")
