"""
数据源管理器
自动选择最优数据源，支持故障切换
"""

import sys
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

# 添加项目路径
sys.path.insert(0, os.path.dirname(__file__))

from .base import (
    BaseDataAdapter,
    DataSource,
    AssetType,
    Exchange,
    AssetPrice,
    Asset,
    TechnicalIndicators,
    AdapterCapability,
)
from .akshare_adapter import AKShareAdapter
from .baostock_adapter import BaostockAdapter


import logging

logger = logging.getLogger(__name__)


class DataSourceManager:
    """
    数据源管理器
    - 自动选择最优数据源
    - 支持故障切换
    - 健康检查
    - 统一 API
    """
    
    def __init__(self, primary: DataSource = DataSource.BAOSTOCK):
        """
        初始化数据源管理器
        
        Args:
            primary: 首选数据源
        """
        self.primary = primary
        self.adapters: Dict[DataSource, BaseDataAdapter] = {}
        self.health_status: Dict[DataSource, Dict] = {}
        self.last_health_check: Optional[datetime] = None
        
        # 初始化所有适配器
        self._init_adapters()
    
    def _init_adapters(self):
        """初始化所有数据源适配器"""
        # Baostock（主力数据源）
        try:
            self.adapters[DataSource.BAOSTOCK] = BaostockAdapter()
            logger.info("✅ Baostock 适配器已初始化")
        except Exception as e:
            logger.error(f"❌ Baostock 适配器初始化失败: {e}")
        
        # AKShare（备用数据源）
        try:
            self.adapters[DataSource.AKSHARE] = AKShareAdapter()
            logger.info("✅ AKShare 适配器已初始化")
        except Exception as e:
            logger.error(f"❌ AKShare 适配器初始化失败: {e}")
    
    def get_adapter(self, source: Optional[DataSource] = None) -> Optional[BaseDataAdapter]:
        """获取数据源适配器"""
        if source:
            return self.adapters.get(source)
        
        # 使用首选数据源
        if self.primary in self.adapters:
            return self.adapters[self.primary]
        
        # 降级到任意可用数据源
        for adapter in self.adapters.values():
            return adapter
        
        return None
    
    def get_realtime_price(
        self,
        ticker: str,
        prefer_source: Optional[DataSource] = None
    ) -> Optional[AssetPrice]:
        """
        获取实时价格（支持故障切换）
        
        Args:
            ticker: 股票代码
            prefer_source: 首选数据源
        
        Returns:
            价格数据
        """
        # 尝试顺序
        sources_to_try = []
        
        if prefer_source:
            sources_to_try.append(prefer_source)
        if self.primary != prefer_source:
            sources_to_try.append(self.primary)
        
        # 添加其他数据源作为备用
        for ds in self.adapters.keys():
            if ds not in sources_to_try:
                sources_to_try.append(ds)
        
        for source in sources_to_try:
            adapter = self.adapters.get(source)
            if not adapter:
                continue
            
            try:
                price = adapter.get_realtime_price(ticker)
                if price:
                    return price
            except Exception as e:
                logger.warning(f"⚠️ {source.value} 获取价格失败: {e}")
                continue
        
        return None
    
    def get_historical_prices(
        self,
        ticker: str,
        start_date: datetime,
        end_date: datetime,
        interval: str = "1d",
        prefer_source: Optional[DataSource] = None
    ) -> List[AssetPrice]:
        """获取历史价格（支持故障切换）"""
        sources_to_try = []
        
        if prefer_source:
            sources_to_try.append(prefer_source)
        if self.primary != prefer_source:
            sources_to_try.append(self.primary)
        
        for ds in self.adapters.keys():
            if ds not in sources_to_try:
                sources_to_try.append(ds)
        
        for source in sources_to_try:
            adapter = self.adapters.get(source)
            if not adapter:
                continue
            
            try:
                prices = adapter.get_historical_prices(ticker, start_date, end_date, interval)
                if prices:
                    return prices
            except Exception as e:
                logger.warning(f"⚠️ {source.value} 获取历史价格失败: {e}")
                continue
        
        return []
    
    def get_asset_info(self, ticker: str) -> Optional[Asset]:
        """获取资产信息"""
        adapter = self.get_adapter()
        if adapter:
            return adapter.get_asset_info(ticker)
        return None
    
    def get_technical_indicators(
        self,
        ticker: str,
        lookback_days: int = 100
    ) -> Optional[TechnicalIndicators]:
        """计算技术指标"""
        adapter = self.get_adapter()
        if adapter:
            return adapter.get_technical_indicators(ticker, lookback_days)
        return None
    
    def health_check(self) -> Dict[str, Any]:
        """
        健康检查所有数据源
        
        Returns:
            健康状态报告
        """
        results = {}
        
        for source, adapter in self.adapters.items():
            try:
                results[source.value] = adapter.health_check()
            except Exception as e:
                results[source.value] = {
                    "status": "error",
                    "message": str(e),
                    "timestamp": datetime.now().isoformat()
                }
        
        self.health_status = results
        self.last_health_check = datetime.now()
        
        return {
            "check_time": datetime.now().isoformat(),
            "primary_source": self.primary.value,
            "sources": results,
        }
    
    def switch_primary(self, new_primary: DataSource) -> bool:
        """
        切换首选数据源
        
        Args:
            new_primary: 新的首选数据源
        
        Returns:
            是否切换成功
        """
        if new_primary not in self.adapters:
            logger.error(f"数据源 {new_primary.value} 不可用")
            return False
        
        self.primary = new_primary
        logger.info(f"✅ 已切换首选数据源为: {new_primary.value}")
        return True
    
    def get_available_sources(self) -> List[str]:
        """获取可用数据源列表"""
        return [s.value for s in self.adapters.keys()]


# 全局单例
_manager_instance: Optional[DataSourceManager] = None


def get_data_manager() -> DataSourceManager:
    """获取全局数据源管理器单例"""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = DataSourceManager()
    return _manager_instance
