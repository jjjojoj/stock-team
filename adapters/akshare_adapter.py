"""
AKShare 数据源适配器
借鉴 ValueCell 的设计，提供 A 股、港股、美股数据
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Dict, Any

# 添加与当前解释器版本匹配的虚拟环境路径，避免跨版本二进制包污染
PROJECT_ROOT = Path(__file__).resolve().parent.parent
VENV_PATH = PROJECT_ROOT / "venv" / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"
if VENV_PATH.is_dir():
    sys.path.insert(0, str(VENV_PATH))

from .base import (
    BaseDataAdapter,
    DataSource,
    AssetType,
    Exchange,
    AssetPrice,
    Asset,
    AdapterCapability,
)


class AKShareAdapter(BaseDataAdapter):
    """
    AKShare 数据源适配器
    支持A股、港股、美股的实时行情和历史数据
    """
    
    def __init__(self, **kwargs):
        self.ak = None
        super().__init__(DataSource.AKSHARE, **kwargs)
    
    def _initialize(self) -> None:
        """初始化 AKShare"""
        try:
            import akshare as ak
            self.ak = ak
            print("✅ AKShare 初始化成功")
        except ImportError:
            print("⚠️ AKShare 未安装，请运行: pip install akshare")
            self.ak = None
    
    def _normalize_code(self, ticker: str) -> str:
        """
        标准化股票代码
        
        输入格式: sh.600519 或 sz.000001
        输出格式: 600519 或 000001
        """
        if "." in ticker:
            return ticker.split(".")[1]
        return ticker
    
    def _get_exchange(self, ticker: str) -> str:
        """获取交易所代码"""
        if ticker.startswith("sh.") or ticker.startswith("6"):
            return "sh"
        elif ticker.startswith("sz.") or ticker.startswith(("0", "3")):
            return "sz"
        elif ticker.startswith("bj.") or ticker.startswith(("4", "8")):
            return "bj"
        return "sh"
    
    def get_realtime_price(self, ticker: str) -> Optional[AssetPrice]:
        """获取实时价格"""
        if not self.ak:
            return None
        
        try:
            code = self._normalize_code(ticker)
            
            # 使用东方财富实时行情接口
            df = self.ak.stock_zh_a_spot_em()
            
            # 查找对应股票
            mask = df["代码"] == code
            if not mask.any():
                return None
            
            row = df[mask].iloc[0]
            
            return AssetPrice(
                ticker=ticker,
                price=Decimal(str(row.get("最新价", 0))),
                currency="CNY",
                timestamp=datetime.now(),
                source=DataSource.AKSHARE,
                open_price=Decimal(str(row.get("今开", 0))) if row.get("今开") else None,
                high_price=Decimal(str(row.get("最高", 0))) if row.get("最高") else None,
                low_price=Decimal(str(row.get("最低", 0))) if row.get("最低") else None,
                close_price=Decimal(str(row.get("最新价", 0))),
                volume=Decimal(str(row.get("成交量", 0))) if row.get("成交量") else None,
                change=Decimal(str(row.get("涨跌额", 0))) if row.get("涨跌额") else None,
                change_percent=Decimal(str(row.get("涨跌幅", 0).replace("%", ""))) if row.get("涨跌幅") else None,
            )
        except Exception as e:
            print(f"AKShare 获取实时价格失败: {e}")
            return None
    
    def get_historical_prices(
        self,
        ticker: str,
        start_date: datetime,
        end_date: datetime,
        interval: str = "1d"
    ) -> List[AssetPrice]:
        """获取历史价格"""
        if not self.ak:
            return []
        
        try:
            code = self._normalize_code(ticker)
            
            # 映射周期
            period_map = {
                "1d": "daily",
                "1w": "weekly",
                "1m": "monthly",
            }
            period = period_map.get(interval, "daily")
            
            # 获取历史数据
            df = self.ak.stock_zh_a_hist(
                symbol=code,
                period=period,
                start_date=start_date.strftime("%Y%m%d"),
                end_date=end_date.strftime("%Y%m%d"),
                adjust="qfq"  # 前复权
            )
            
            if df.empty:
                return []
            
            prices = []
            for _, row in df.iterrows():
                price = AssetPrice(
                    ticker=ticker,
                    price=Decimal(str(row.get("收盘", 0))),
                    currency="CNY",
                    timestamp=datetime.strptime(str(row.get("日期", "")), "%Y-%m-%d"),
                    source=DataSource.AKSHARE,
                    open_price=Decimal(str(row.get("开盘", 0))) if row.get("开盘") else None,
                    high_price=Decimal(str(row.get("最高", 0))) if row.get("最高") else None,
                    low_price=Decimal(str(row.get("最低", 0))) if row.get("最低") else None,
                    close_price=Decimal(str(row.get("收盘", 0))),
                    volume=Decimal(str(row.get("成交量", 0))) if row.get("成交量") else None,
                )
                prices.append(price)
            
            return prices
        except Exception as e:
            print(f"AKShare 获取历史价格失败: {e}")
            return []
    
    def get_asset_info(self, ticker: str) -> Optional[Asset]:
        """获取资产信息"""
        if not self.ak:
            return None
        
        try:
            code = self._normalize_code(ticker)
            
            # 使用实时行情获取基本信息
            df = self.ak.stock_zh_a_spot_em()
            mask = df["代码"] == code
            if not mask.any():
                return None
            
            row = df[mask].iloc[0]
            
            # 尝试获取更多财务数据
            try:
                info_df = self.ak.stock_individual_info_em(symbol=code)
                info_dict = dict(zip(info_df["item"], info_df["value"]))
            except:
                info_dict = {}
            
            return Asset(
                ticker=ticker,
                name=row.get("名称", ""),
                asset_type=AssetType.STOCK,
                exchange=Exchange.SSE if ticker.startswith("6") else Exchange.SZSE,
                currency="CNY",
                market_cap=float(row.get("总市值", 0)) / 1e8 if row.get("总市值") else None,  # 转换为亿
                pe=info_dict.get("市盈率"),
                pb=info_dict.get("市净率"),
                roe=info_dict.get("ROE"),
                extra={
                    "industry": info_dict.get("行业"),
                    "sector": info_dict.get("板块"),
                }
            )
        except Exception as e:
            print(f"AKShare 获取资产信息失败: {e}")
            return None
    
    def search_stocks(self, query: str, limit: int = 10) -> List[Asset]:
        """搜索股票"""
        if not self.ak:
            return []
        
        try:
            df = self.ak.stock_zh_a_spot_em()
            
            # 按名称或代码搜索
            mask = df["名称"].str.contains(query, na=False) | df["代码"].str.contains(query, na=False)
            results = df[mask].head(limit)
            
            assets = []
            for _, row in results.iterrows():
                code = row.get("代码", "")
                exchange = Exchange.SSE if code.startswith("6") else Exchange.SZSE
                
                asset = Asset(
                    ticker=f"{'sh' if exchange == Exchange.SSE else 'sz'}.{code}",
                    name=row.get("名称", ""),
                    asset_type=AssetType.STOCK,
                    exchange=exchange,
                    currency="CNY",
                    market_cap=float(row.get("总市值", 0)) / 1e8 if row.get("总市值") else None,
                )
                assets.append(asset)
            
            return assets
        except Exception as e:
            print(f"AKShare 搜索股票失败: {e}")
            return []
    
    def get_capabilities(self) -> List[AdapterCapability]:
        """获取适配器能力"""
        return [
            AdapterCapability(
                asset_type=AssetType.STOCK,
                exchanges={Exchange.SSE, Exchange.SZSE, Exchange.BSE},
                supports_realtime=True,
                supports_history=True,
                supports_search=True,
                supports_info=True,
                notes="AKShare 支持 A 股实时行情、历史数据、基本信息搜索",
            ),
        ]
