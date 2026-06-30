"""
core.data_validator — 数据完整性校验模块
==================================
负责验证从网络接口获取并写入数据库的数据的完整性和准确性。

设计原则:
  - 全面的数据完整性检查
  - 合理的数据合理性验证
  - 数据连续性检查
  - 提供详细的校验报告
"""

import os
import time
import threading
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from pathlib import Path

import pandas as pd
import numpy as np

from core.record_manager import record_error, record_result

logger = __import__('logging').getLogger(__name__)

__all__ = [
    "DataValidator",
    "get_data_validator",
    "validate_stock_data",
    "validate_batch_stock_data",
    "generate_quality_report",
]


class DataValidator:
    """
    数据完整性校验器
    
    负责验证数据的完整性、合理性和连续性
    """
    
    def __init__(self):
        self._lock = threading.RLock()
        logger.info("DataValidator 初始化完成")
    
    def validate_stock_data(self, df: pd.DataFrame, symbol: str) -> Dict[str, Any]:
        """
        验证股票数据的完整性
        
        Args:
            df: 股票数据 DataFrame
            symbol: 股票代码
            
        Returns:
            校验结果
        """
        result = {
            'symbol': symbol,
            'valid': True,
            'errors': [],
            'warnings': [],
            'stats': {}
        }
        
        # 检查数据是否为空
        if df.empty:
            result['valid'] = False
            result['errors'].append('数据为空')
            return result
        
        # 检查必要字段
        required_columns = ['open', 'high', 'low', 'close', 'volume']
        for col in required_columns:
            if col not in df.columns:
                result['valid'] = False
                result['errors'].append(f'缺少必要字段: {col}')
        
        # 检查数据类型
        numeric_columns = ['open', 'high', 'low', 'close', 'volume', 'amount', 'pct_change']
        for col in numeric_columns:
            if col in df.columns:
                if not pd.api.types.is_numeric_dtype(df[col]):
                    try:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                        result['warnings'].append(f'字段 {col} 类型转换为数值')
                    except Exception as e:
                        result['valid'] = False
                        result['errors'].append(f'字段 {col} 类型转换失败: {e}')
        
        # 检查数据质量
        if 'close' in df.columns:
            # 检查收盘价是否为负数
            if (df['close'] < 0).any():
                result['valid'] = False
                result['errors'].append('收盘价存在负数')
            
            # 检查收盘价是否为 NaN
            if df['close'].isna().any():
                result['valid'] = False
                result['errors'].append('收盘价存在 NaN 值')
        
        if 'volume' in df.columns:
            # 检查成交量是否为负数
            if (df['volume'] < 0).any():
                result['valid'] = False
                result['errors'].append('成交量存在负数')
            
            # 检查成交量是否为 0（可能是停牌）
            zero_volume_count = (df['volume'] == 0).sum()
            if zero_volume_count > 0:
                result['warnings'].append(f'存在 {zero_volume_count} 条成交量为 0 的记录（可能是停牌）')
        
        # 检查价格合理性
        if all(col in df.columns for col in ['open', 'high', 'low', 'close']):
            # 检查最高价是否大于等于最低价
            if (df['high'] < df['low']).any():
                result['valid'] = False
                result['errors'].append('最高价小于最低价')
            
            # 检查开盘价和收盘价是否在最高价和最低价之间
            if ((df['open'] < df['low']) | (df['open'] > df['high'])).any():
                result['valid'] = False
                result['errors'].append('开盘价超出最高价或最低价范围')
            
            if ((df['close'] < df['low']) | (df['close'] > df['high'])).any():
                result['valid'] = False
                result['errors'].append('收盘价超出最高价或最低价范围')
        
        # 检查数据连续性
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date')
            
            # 检查日期连续性
            date_diff = df['date'].diff().dropna()
            max_gap = date_diff.max()
            if max_gap > pd.Timedelta(days=7):
                result['warnings'].append(f'数据存在较大时间间隔: {max_gap}')
        elif isinstance(df.index, pd.DatetimeIndex):
            df = df.sort_index()
            
            # 检查日期连续性
            date_diff = df.index.to_series().diff().dropna()
            max_gap = date_diff.max()
            if max_gap > pd.Timedelta(days=7):
                result['warnings'].append(f'数据存在较大时间间隔: {max_gap}')
        
        # 检查数据长度
        data_length = len(df)
        result['stats']['data_length'] = data_length
        if data_length < 30:
            result['warnings'].append(f'数据长度不足: {data_length} 条')
        
        # 检查涨跌幅合理性
        if 'pct_change' in df.columns:
            max_pct = df['pct_change'].abs().max()
            if max_pct > 20:
                result['warnings'].append(f'涨跌幅异常: {max_pct:.2f}%')
        
        # 生成统计信息
        if 'close' in df.columns:
            result['stats']['close_mean'] = df['close'].mean()
            result['stats']['close_std'] = df['close'].std()
        
        if 'volume' in df.columns:
            result['stats']['volume_mean'] = df['volume'].mean()
            result['stats']['volume_std'] = df['volume'].std()
        
        # 记录校验结果
        if not result['valid']:
            error_msg = f"股票 {symbol} 数据校验失败: {', '.join(result['errors'][:3])}"
            logger.warning(error_msg)
            record_error("data_validation", error_msg, {
                "symbol": symbol,
                "errors": result['errors'],
                "warnings": result['warnings']
            })
        elif result['warnings']:
            warning_msg = f"股票 {symbol} 数据校验存在警告: {', '.join(result['warnings'][:3])}"
            logger.debug(warning_msg)
            record_result("data_validation", {
                "symbol": symbol,
                "status": "warning",
                "warnings": result['warnings'],
                "stats": result['stats']
            })
        else:
            logger.debug("股票 %s 数据校验通过", symbol)
            record_result("data_validation", {
                "symbol": symbol,
                "status": "success",
                "stats": result['stats']
            })
        
        return result
    
    def validate_batch_stock_data(self, data: Dict[str, pd.DataFrame]) -> Dict[str, Dict[str, Any]]:
        """
        批量验证股票数据
        
        Args:
            data: {symbol: DataFrame} 格式的数据
            
        Returns:
            批量校验结果
        """
        results = {}
        valid_count = 0
        warning_count = 0
        error_count = 0
        
        logger.info(f"开始批量验证 {len(data)} 只股票数据...")
        
        for symbol, df in data.items():
            result = self.validate_stock_data(df, symbol)
            results[symbol] = result
            
            if result['valid']:
                if result['warnings']:
                    warning_count += 1
                else:
                    valid_count += 1
            else:
                error_count += 1
        
        # 生成批量校验报告
        report = {
            'total': len(data),
            'valid': valid_count,
            'warning': warning_count,
            'error': error_count,
            'timestamp': datetime.now().isoformat()
        }
        
        logger.info("批量验证完成: 有效 %s, 警告 %s, 错误 %s", valid_count, warning_count, error_count)
        
        record_result("batch_data_validation", report)
        
        return results
    
    def validate_stock_list(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        验证股票列表数据
        
        Args:
            df: 股票列表 DataFrame
            
        Returns:
            校验结果
        """
        result = {
            'valid': True,
            'errors': [],
            'warnings': [],
            'stats': {}
        }
        
        # 检查数据是否为空
        if df.empty:
            result['valid'] = False
            result['errors'].append('股票列表为空')
            return result
        
        # 检查必要字段
        required_columns = ['code', 'name']
        for col in required_columns:
            if col not in df.columns:
                result['valid'] = False
                result['errors'].append(f'缺少必要字段: {col}')
        
        # 检查股票代码格式
        if 'code' in df.columns:
            df['code'] = df['code'].astype(str)
            # 检查代码长度
            invalid_codes = df[df['code'].str.len() != 6]['code'].tolist()
            if invalid_codes:
                result['valid'] = False
                result['errors'].append(f'股票代码格式错误: {invalid_codes[:5]}')
            
            # 检查代码是否重复
            duplicate_codes = df[df['code'].duplicated()]['code'].tolist()
            if duplicate_codes:
                result['valid'] = False
                result['errors'].append(f'股票代码重复: {duplicate_codes[:5]}')
        
        # 检查股票名称
        if 'name' in df.columns:
            # 检查名称是否为空
            empty_names = df[df['name'].isna() | (df['name'] == '')]['code'].tolist()
            if empty_names:
                result['warnings'].append(f'股票名称为空: {empty_names[:5]}')
        
        # 生成统计信息
        result['stats']['stock_count'] = len(df)
        
        # 记录校验结果
        if not result['valid']:
            error_msg = f"股票列表校验失败: {', '.join(result['errors'][:3])}"
            logger.warning(error_msg)
            record_error("stock_list_validation", error_msg, {
                "errors": result['errors'],
                "warnings": result['warnings']
            })
        elif result['warnings']:
            warning_msg = f"股票列表校验存在警告: {', '.join(result['warnings'][:3])}"
            logger.debug(warning_msg)
            record_result("stock_list_validation", {
                "status": "warning",
                "warnings": result['warnings'],
                "stats": result['stats']
            })
        else:
            logger.debug("股票列表校验通过")
            record_result("stock_list_validation", {
                "status": "success",
                "stats": result['stats']
            })
        
        return result
    
    def generate_quality_report(self, data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        """
        生成数据质量报告
        
        Args:
            data: {symbol: DataFrame} 格式的数据
            
        Returns:
            数据质量报告 DataFrame
        """
        report_data = []
        
        for symbol, df in data.items():
            validation_result = self.validate_stock_data(df, symbol)
            
            report_entry = {
                'symbol': symbol,
                'valid': validation_result['valid'],
                'error_count': len(validation_result['errors']),
                'warning_count': len(validation_result['warnings']),
                'data_length': validation_result['stats'].get('data_length', 0),
                'close_mean': validation_result['stats'].get('close_mean', 0),
                'close_std': validation_result['stats'].get('close_std', 0),
                'volume_mean': validation_result['stats'].get('volume_mean', 0),
                'volume_std': validation_result['stats'].get('volume_std', 0),
                'errors': ', '.join(validation_result['errors']),
                'warnings': ', '.join(validation_result['warnings'])
            }
            
            report_data.append(report_entry)
        
        report_df = pd.DataFrame(report_data)
        
        # 保存报告
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = Path(r"c:\Users\21471\WorkBuddy\quant system\.workbuddy") / f"data_quality_report_{timestamp}.csv"
        report_df.to_csv(report_path, index=False, encoding='utf-8-sig')
        
        logger.info("数据质量报告已生成: %s", report_path)
        record_result("data_quality_report", {
            "path": str(report_path.relative_to(Path(r"c:\Users\21471\WorkBuddy\quant system"))),
            "timestamp": datetime.now().isoformat(),
            "stock_count": len(data)
        })
        
        return report_df


# 全局数据校验器实例
_data_validator = None
_data_validator_lock = threading.RLock()


def get_data_validator() -> DataValidator:
    """
    获取数据校验器实例
    
    Returns:
        数据校验器实例
    """
    global _data_validator
    with _data_validator_lock:
        if _data_validator is None:
            _data_validator = DataValidator()
        return _data_validator


def validate_stock_data(df: pd.DataFrame, symbol: str) -> Dict[str, Any]:
    """
    验证股票数据的完整性
    
    Args:
        df: 股票数据 DataFrame
        symbol: 股票代码
        
    Returns:
        校验结果
    """
    validator = get_data_validator()
    return validator.validate_stock_data(df, symbol)


def validate_batch_stock_data(data: Dict[str, pd.DataFrame]) -> Dict[str, Dict[str, Any]]:
    """
    批量验证股票数据
    
    Args:
        data: {symbol: DataFrame} 格式的数据
        
    Returns:
        批量校验结果
    """
    validator = get_data_validator()
    return validator.validate_batch_stock_data(data)


def generate_quality_report(data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    生成数据质量报告
    
    Args:
        data: {symbol: DataFrame} 格式的数据
        
    Returns:
        数据质量报告 DataFrame
    """
    validator = get_data_validator()
    return validator.generate_quality_report(data)
