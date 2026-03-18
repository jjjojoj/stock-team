"""
数据源适配器基类
借鉴 ValueCell 的设计模式
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional


class DataSource(Enum):
    """数据源枚举"""
    AKSHARE = "akshare"
    BAOSTOCK = "baostock"
    EASTMONEY = "eastmoney"
    TENCENT = "tencent"
    TUSHARE = "tushare"


class AssetType(Enum):
    """资产类型"""
    STOCK = "stock"
    INDEX = "index"
    FUND = "fund"
    BOND = "bond"


class Exchange(Enum):
    """交易所"""
    SSE = "SSE"      # 上交所
    SZSE = "SZSE"    # 深交所
    BSE = "BSE"      # 北交所


@dataclass
class AdapterCapability:
    """适配器能力描述"""
    asset_type: AssetType
    exchanges: set
    supports_realtime: bool = False
    supports_history: bool = False
    supports_search: bool = False
    supports_info: bool = False
    notes: str = ""


@dataclass
class AssetPrice:
    """资产价格数据"""
    ticker: str
    price: Decimal
    currency: str
    timestamp: datetime
    source: DataSource
    open_price: Optional[Decimal] = None
    high_price: Optional[Decimal] = None
    low_price: Optional[Decimal] = None
    close_price: Optional[Decimal] = None
    volume: Optional[Decimal] = None
    change: Optional[Decimal] = None
    change_percent: Optional[Decimal] = None


@dataclass
class Asset:
    """资产信息"""
    ticker: str
    name: str
    asset_type: AssetType
    exchange: Exchange
    currency: str = "CNY"
    sector: Optional[str] = None
    industry: Optional[str] = None
    market_cap: Optional[float] = None  # 亿
    pe: Optional[float] = None
    pb: Optional[float] = None
    roe: Optional[float] = None
    dividend_yield: Optional[float] = None
    extra: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.extra is None:
            self.extra = {}


@dataclass
class TechnicalIndicators:
    """技术指标"""
    ticker: str
    timestamp: datetime
    ema_12: Optional[float] = None
    ema_26: Optional[float] = None
    ema_50: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_histogram: Optional[float] = None
    rsi_14: Optional[float] = None
    bb_upper: Optional[float] = None
    bb_middle: Optional[float] = None
    bb_lower: Optional[float] = None
    ma5: Optional[float] = None
    ma10: Optional[float] = None
    ma20: Optional[float] = None
    ma60: Optional[float] = None


class BaseDataAdapter(ABC):
    """数据源适配器基类"""
    
    def __init__(self, source: DataSource, **kwargs):
        self.source = source
        self.config = kwargs
        self._initialize()
    
    def _initialize(self) -> None:
        """初始化适配器（子类实现）"""
        pass
    
    @abstractmethod
    def get_realtime_price(self, ticker: str) -> Optional[AssetPrice]:
        """获取实时价格"""
        pass
    
    @abstractmethod
    def get_historical_prices(
        self,
        ticker: str,
        start_date: datetime,
        end_date: datetime,
        interval: str = "1d"
    ) -> List[AssetPrice]:
        """获取历史价格"""
        pass
    
    @abstractmethod
    def get_asset_info(self, ticker: str) -> Optional[Asset]:
        """获取资产信息"""
        pass
    
    @abstractmethod
    def get_capabilities(self) -> List[AdapterCapability]:
        """获取适配器能力"""
        pass
    
    def get_technical_indicators(
        self,
        ticker: str,
        lookback_days: int = 100
    ) -> Optional[TechnicalIndicators]:
        """计算技术指标（默认实现）"""
        import numpy as np
        import pandas as pd
        from datetime import timedelta
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=lookback_days)
        
        prices = self.get_historical_prices(ticker, start_date, end_date)
        if not prices or len(prices) < 20:
            return None
        
        # 构建 DataFrame
        df = pd.DataFrame([{
            'close': float(p.close_price or p.price),
            'high': float(p.high_price) if p.high_price else None,
            'low': float(p.low_price) if p.low_price else None,
            'volume': float(p.volume) if p.volume else None,
        } for p in prices])
        
        # 计算 EMA
        df['ema_12'] = df['close'].ewm(span=12, adjust=False).mean()
        df['ema_26'] = df['close'].ewm(span=26, adjust=False).mean()
        df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
        
        # 计算 MACD
        df['macd'] = df['ema_12'] - df['ema_26']
        df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
        df['macd_histogram'] = df['macd'] - df['macd_signal']
        
        # 计算 RSI
        delta = df['close'].diff()
        gain = delta.clip(lower=0).rolling(window=14).mean()
        loss = (-delta).clip(lower=0).rolling(window=14).mean()
        rs = gain / loss.replace(0, np.inf)
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # 计算布林带
        df['bb_middle'] = df['close'].rolling(window=20).mean()
        bb_std = df['close'].rolling(window=20).std()
        df['bb_upper'] = df['bb_middle'] + (bb_std * 2)
        df['bb_lower'] = df['bb_middle'] - (bb_std * 2)
        
        # 计算均线
        df['ma5'] = df['close'].rolling(window=5).mean()
        df['ma10'] = df['close'].rolling(window=10).mean()
        df['ma20'] = df['close'].rolling(window=20).mean()
        df['ma60'] = df['close'].rolling(window=60).mean()
        
        # 获取最后一行
        last = df.iloc[-1]
        
        return TechnicalIndicators(
            ticker=ticker,
            timestamp=datetime.now(),
            ema_12=float(last['ema_12']) if pd.notna(last['ema_12']) else None,
            ema_26=float(last['ema_26']) if pd.notna(last['ema_26']) else None,
            ema_50=float(last['ema_50']) if pd.notna(last['ema_50']) else None,
            macd=float(last['macd']) if pd.notna(last['macd']) else None,
            macd_signal=float(last['macd_signal']) if pd.notna(last['macd_signal']) else None,
            macd_histogram=float(last['macd_histogram']) if pd.notna(last['macd_histogram']) else None,
            rsi_14=float(last['rsi']) if pd.notna(last['rsi']) else None,
            bb_upper=float(last['bb_upper']) if pd.notna(last['bb_upper']) else None,
            bb_middle=float(last['bb_middle']) if pd.notna(last['bb_middle']) else None,
            bb_lower=float(last['bb_lower']) if pd.notna(last['bb_lower']) else None,
            ma5=float(last['ma5']) if pd.notna(last['ma5']) else None,
            ma10=float(last['ma10']) if pd.notna(last['ma10']) else None,
            ma20=float(last['ma20']) if pd.notna(last['ma20']) else None,
            ma60=float(last['ma60']) if pd.notna(last['ma60']) else None,
        )
    
    def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        try:
            # 尝试获取一个已知的股票价格
            price = self.get_realtime_price("sh.600519")  # 贵州茅台
            return {
                "status": "ok" if price else "error",
                "source": self.source.value,
                "message": "连接正常" if price else "无法获取数据",
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            return {
                "status": "error",
                "source": self.source.value,
                "message": str(e),
                "timestamp": datetime.now().isoformat()
            }
