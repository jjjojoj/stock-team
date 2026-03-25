"""
Baostock 数据源适配器
你现有的主要数据源，保持兼容
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional

# 添加与当前解释器版本匹配的虚拟环境路径，避免跨版本二进制包污染
PROJECT_ROOT = Path(__file__).resolve().parent.parent
VENV_PATH = PROJECT_ROOT / "venv" / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"
if VENV_PATH.is_dir():
    sys.path.insert(0, str(VENV_PATH))

try:
    import baostock as bs
    import pandas as pd
except ImportError:
    print("请安装依赖: pip install baostock pandas")
    raise

from .base import (
    BaseDataAdapter,
    DataSource,
    AssetType,
    Exchange,
    AssetPrice,
    Asset,
    AdapterCapability,
)


class BaostockAdapter(BaseDataAdapter):
    """Baostock 数据源适配器"""
    
    def __init__(self, **kwargs):
        self._logged_in = False
        super().__init__(DataSource.BAOSTOCK, **kwargs)
    
    def _initialize(self) -> None:
        """初始化 Baostock 登录"""
        self.timeout = self.config.get("timeout", 10)
        self._login()
    
    def _login(self) -> bool:
        """登录 Baostock"""
        if self._logged_in:
            return True
        
        try:
            lg = bs.login()
            if lg.error_code != "0":
                print(f"Baostock 登录失败: {lg.error_msg}")
                return False
            self._logged_in = True
            return True
        except Exception as e:
            print(f"Baostock 登录异常: {e}")
            return False
    
    def _logout(self):
        """登出 Baostock"""
        if self._logged_in:
            try:
                bs.logout()
            except:
                pass
            self._logged_in = False
    
    def _normalize_ticker(self, ticker: str) -> tuple:
        """
        标准化股票代码
        输入: sh.600519 或 600519
        输出: (exchange_code, symbol) 如 ("sh", "600519")
        """
        ticker = ticker.lower().strip()
        
        if "." in ticker:
            prefix, symbol = ticker.split(".", 1)
            return prefix, symbol
        
        # 纯数字格式
        if ticker.startswith(("600", "601", "603", "688")):
            return "sh", ticker
        elif ticker.startswith(("000", "002", "300")):
            return "sz", ticker
        elif ticker.startswith(("430", "830", "870")):
            return "bj", ticker
        
        return "sh", ticker
    
    def get_realtime_price(self, ticker: str) -> Optional[AssetPrice]:
        """获取实时价格（通过最新日线数据模拟）"""
        try:
            if not self._login():
                return None
            
            exchange, symbol = self._normalize_ticker(ticker)
            
            # 获取最近几天的数据
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
            
            rs = bs.query_history_k_data_plus(
                f"{exchange}.{symbol}",
                "date,code,open,high,low,close,volume,amount,pctChg",
                start_date=start_date,
                end_date=end_date,
                frequency="d",
                adjustflag="2",  # 前复权
            )
            
            if rs.error_code != "0":
                return None
            
            data_list = []
            while rs.next():
                data_list.append(rs.get_row_data())
            
            if not data_list:
                return None
            
            # 获取最后一条
            last = data_list[-1]
            
            return AssetPrice(
                ticker=ticker,
                price=Decimal(last[5]) if last[5] else Decimal("0"),
                currency="CNY",
                timestamp=datetime.strptime(last[0], "%Y-%m-%d"),
                source=DataSource.BAOSTOCK,
                open_price=Decimal(last[2]) if last[2] else None,
                high_price=Decimal(last[3]) if last[3] else None,
                low_price=Decimal(last[4]) if last[4] else None,
                close_price=Decimal(last[5]) if last[5] else None,
                volume=Decimal(last[6]) if last[6] else None,
                change_percent=Decimal(last[8]) if last[8] else None,
            )
            
        except Exception as e:
            print(f"Baostock 获取实时价格失败 [{ticker}]: {e}")
            return None
    
    def get_historical_prices(
        self,
        ticker: str,
        start_date: datetime,
        end_date: datetime,
        interval: str = "1d"
    ) -> List[AssetPrice]:
        """获取历史价格"""
        try:
            if not self._login():
                return []
            
            exchange, symbol = self._normalize_ticker(ticker)
            
            # 格式化日期
            start_str = start_date.strftime("%Y-%m-%d")
            end_str = end_date.strftime("%Y-%m-%d")
            
            # 映射周期
            frequency_map = {
                "1d": "d",
                "1w": "w",
                "1m": "m",
            }
            frequency = frequency_map.get(interval, "d")
            
            rs = bs.query_history_k_data_plus(
                f"{exchange}.{symbol}",
                "date,code,open,high,low,close,volume,amount,pctChg,peTTM,pbMRQ",
                start_date=start_str,
                end_date=end_str,
                frequency=frequency,
                adjustflag="2",  # 前复权
            )
            
            if rs.error_code != "0":
                return []
            
            prices = []
            while rs.next():
                row = rs.get_row_data()
                try:
                    prices.append(AssetPrice(
                        ticker=ticker,
                        price=Decimal(row[5]) if row[5] else Decimal("0"),
                        currency="CNY",
                        timestamp=datetime.strptime(row[0], "%Y-%m-%d"),
                        source=DataSource.BAOSTOCK,
                        open_price=Decimal(row[2]) if row[2] else None,
                        high_price=Decimal(row[3]) if row[3] else None,
                        low_price=Decimal(row[4]) if row[4] else None,
                        close_price=Decimal(row[5]) if row[5] else None,
                        volume=Decimal(row[6]) if row[6] else None,
                        change_percent=Decimal(row[8]) if row[8] else None,
                    ))
                except:
                    continue
            
            return prices
            
        except Exception as e:
            print(f"Baostock 获取历史价格失败 [{ticker}]: {e}")
            return []
    
    def get_asset_info(self, ticker: str) -> Optional[Asset]:
        """获取资产信息"""
        try:
            exchange, symbol = self._normalize_ticker(ticker)
            
            # 获取最近数据来提取信息
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            
            rs = bs.query_history_k_data_plus(
                f"{exchange}.{symbol}",
                "date,code,open,high,low,close,volume,amount,pctChg,peTTM,pbMRQ",
                start_date=start_date,
                end_date=end_date,
                frequency="d",
                adjustflag="2",
            )
            
            if rs.error_code != "0" or not rs.next():
                return None
            
            # 获取最后一条
            row = rs.get_row_data()
            
            # 确定交易所
            if exchange == "sh":
                exc = Exchange.SSE
            elif exchange == "sz":
                exc = Exchange.SZSE
            else:
                exc = Exchange.BSE
            
            return Asset(
                ticker=ticker,
                name=symbol,
                asset_type=AssetType.STOCK,
                exchange=exc,
                currency="CNY",
                pe=float(row[9]) if row[9] and row[9] != "" else None,
                pb=float(row[10]) if row[10] and row[10] != "" else None,
            )
            
        except Exception as e:
            print(f"Baostock 获取资产信息失败 [{ticker}]: {e}")
            return None
    
    def get_capabilities(self) -> List[AdapterCapability]:
        """获取适配器能力"""
        return [
            AdapterCapability(
                asset_type=AssetType.STOCK,
                exchanges={Exchange.SSE, Exchange.SZSE, Exchange.BSE},
                supports_realtime=True,
                supports_history=True,
                supports_search=False,
                supports_info=True,
                notes="稳定可靠的 A 股数据源，支持前复权",
            ),
        ]
    
    def __del__(self):
        """析构时登出"""
        self._logout()
