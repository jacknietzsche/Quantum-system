"""
core.data_updater — 数据更新服务
==================================
负责从网络数据源获取数据并更新到本地数据库，为回测和分析提供数据支持。

设计原则:
  - 网络数据接口仅用于数据库更新操作
  - 回测和分析功能必须通过数据库获取数据
  - 实现增量更新，减少网络请求
  - 支持多数据源 fallback
  - 实现错误处理和重试机制
"""

import os
import sys
import time
import logging
import threading
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from pathlib import Path

import pandas as pd
import numpy as np

from core.config import DataSourceConfig, QuantConfig
from core.local_db_fetcher import LocalDBFetcher
from core.data import normalize_code, code_to_baostock
from core.data_validator import validate_stock_data

logger = logging.getLogger(__name__)


class DataUpdater:
    """
    数据更新服务
    
    负责从网络数据源获取数据并更新到本地数据库
    """
    
    def __init__(self, config: Optional[DataSourceConfig] = None):
        self.cfg = config or DataSourceConfig()
        self.db_fetcher = LocalDBFetcher(self.cfg.local_db_path)
        self._lock = threading.Lock()
        
        # 数据源状态
        self._datasource_status = {
            'baostock': True,
            'akshare': True,
            'efinance': True,
            'sina': True,
            'tencent': True
        }
        
        # 检测数据源依赖
        self._check_deps()
        
        logger.info("DataUpdater 初始化完成")
    
    def _check_deps(self):
        """检查数据源依赖"""
        try:
            import baostock
            logger.info(f"  baostock {baostock.__version__}")
        except ImportError:
            self._datasource_status['baostock'] = False
            logger.warning("baostock 未安装")
        
        try:
            import akshare
            self._akshare_ok = True
        except ImportError:
            self._akshare_ok = False
            self._datasource_status['akshare'] = False
            logger.warning("akshare 未安装")
        
        try:
            import efinance
            self._efinance_ok = True
        except ImportError:
            self._efinance_ok = False
            self._datasource_status['efinance'] = False
            logger.warning("efinance 未安装")
    
    def update_stock_list(self) -> bool:
        """更新股票列表到数据库"""
        logger.info("开始更新股票列表...")
        
        try:
            # 尝试从 akshare 获取股票列表
            if self._akshare_ok:
                import akshare as ak
                df = ak.stock_info_a_code_name()
                if not df.empty:
                    # 转换为标准格式
                    stock_list = []
                    for _, row in df.iterrows():
                        code = str(row.iloc[0]).zfill(6)
                        name = str(row.iloc[1]).strip()
                        market = 'SH' if code.startswith('6') else 'SZ'
                        stock_list.append({
                            'code': code,
                            'name': name,
                            'exchange': market
                        })
                    
                    # 更新到数据库
                    self._update_stock_list_to_db(stock_list)
                    logger.info(f"成功更新股票列表: {len(stock_list)} 只")
                    return True
            
            # fallback: 从 baostock 获取
            if self._datasource_status['baostock']:
                import baostock as bs
                lg = bs.login()
                if lg.error_code == '0':
                    today = datetime.now().strftime('%Y-%m-%d')
                    rs = bs.query_all_stock(today)
                    df_raw = rs.get_data()
                    if not df_raw.empty and 'code' in df_raw.columns:
                        stock_list = []
                        for _, row in df_raw.iterrows():
                            code = row['code'].split('.')[-1] if '.' in row['code'] else row['code']
                            code = code.zfill(6)
                            if len(code) == 6 and code.isdigit():
                                name = str(row['code_name']).strip()
                                market = 'SH' if code.startswith('6') else 'SZ'
                                stock_list.append({
                                    'code': code,
                                    'name': name,
                                    'exchange': market
                                })
                        
                        self._update_stock_list_to_db(stock_list)
                        logger.info(f"成功更新股票列表: {len(stock_list)} 只")
                        bs.logout()
                        return True
                    bs.logout()
        except Exception as e:
            logger.error("更新股票列表失败: %s", e)
        
        logger.warning("无法更新股票列表，使用现有数据")
        return False
    
    def _update_stock_list_to_db(self, stock_list: List[Dict[str, str]]):
        """将股票列表更新到数据库"""
        # 这里需要实现具体的数据库更新逻辑
        # 由于 LocalDBFetcher 没有提供更新股票列表的方法
        # 我们需要直接操作数据库
        import sqlite3
        
        db_path = self.db_fetcher.db_path
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        try:
            # 清空现有股票列表
            cursor.execute("DELETE FROM stocks")
            
            # 插入新股票列表
            for stock in stock_list:
                cursor.execute(
                    "INSERT INTO stocks (code, name, exchange) VALUES (?, ?, ?)",
                    (stock['code'], stock['name'], stock['exchange'])
                )
            
            conn.commit()
            logger.info(f"股票列表已更新到数据库: {len(stock_list)} 只")
        except Exception as e:
            logger.error("更新股票列表到数据库失败: %s", e)
            conn.rollback()
        finally:
            conn.close()
    
    def update_stock_data(self, symbols: List[str], days: int = 180) -> Dict[str, bool]:
        """
        更新指定股票的数据
        
        Args:
            symbols: 股票代码列表
            days: 更新天数
            
        Returns:
            {symbol: success}
        """
        result = {}
        total = len(symbols)
        success_count = 0
        
        logger.info("开始更新 %s 只股票数据...", total)
        
        for i, symbol in enumerate(symbols, 1):
            try:
                logger.info("[%s/%s] 更新 %s...", i, total, symbol)
                success = self._update_single_stock(symbol, days)
                result[symbol] = success
                if success:
                    success_count += 1
                
                # 控制请求频率
                time.sleep(self.cfg.request_delay)
            except Exception as e:
                logger.error("更新 %s 失败: %s", symbol, e)
                result[symbol] = False
        
        logger.info("更新完成: %s/%s 只成功", success_count, total)
        return result
    
    def _update_single_stock(self, symbol: str, days: int) -> bool:
        """更新单只股票的数据"""
        symbol = normalize_code(symbol)
        bs_code = code_to_baostock(symbol)
        
        # 计算日期范围
        end = datetime.now()
        start = end - timedelta(days=days)
        start_str = start.strftime('%Y-%m-%d')
        end_str = end.strftime('%Y-%m-%d')
        
        # 尝试从多个数据源获取数据
        data_sources = ['baostock', 'akshare', 'efinance', 'sina', 'tencent']
        
        for source in data_sources:
            if not self._datasource_status[source]:
                continue
            
            try:
                df = self._fetch_from_source(source, bs_code, symbol, days, start_str, end_str)
                if not df.empty:
                    # 数据完整性校验
                    validation_result = validate_stock_data(df, symbol)
                    if validation_result['valid']:
                        # 更新到数据库
                        if self._update_to_db(symbol, df):
                            logger.debug("从 %s 获取并更新 %s 成功", source, symbol)
                            return True
                    else:
                        logger.warning("数据校验失败 %s: {', '.join(validation_result['errors'][:3])}", symbol)
            except Exception as e:
                logger.debug("从 %s 获取 %s 失败: %s", source, symbol, e)
        
        return False
    
    def _fetch_from_source(self, source: str, bs_code: str, symbol: str, days: int, start_str: str, end_str: str) -> pd.DataFrame:
        """从指定数据源获取数据"""
        if source == 'baostock':
            return self._fetch_baostock(bs_code, start_str, end_str)
        elif source == 'akshare':
            return self._fetch_akshare(symbol, start_str, end_str)
        elif source == 'efinance':
            return self._fetch_efinance(symbol, days)
        elif source == 'sina':
            return self._fetch_sina(symbol, days)
        elif source == 'tencent':
            return self._fetch_tencent(symbol, days)
        return pd.DataFrame()
    
    def _fetch_baostock(self, bs_code: str, start_str: str, end_str: str) -> pd.DataFrame:
        """从 baostock 获取数据"""
        import baostock as bs
        lg = bs.login()
        if lg.error_code != '0':
            logger.warning(f"baostock 登录失败: {lg.error_msg}")
            return pd.DataFrame()
        
        try:
            rs = bs.query_history_k_data_plus(
                code=bs_code,
                fields="date,open,high,low,close,volume,amount,pctChg,turn",
                start_date=start_str, end_date=end_str,
                frequency="d", adjustflag="2"
            )
            rows = []
            while rs.next():
                rows.append(rs.get_row_data())
            
            if not rows:
                return pd.DataFrame()
            
            df = pd.DataFrame(rows, columns=rs.fields)
            df['date'] = pd.to_datetime(df['date'])
            for col in ['open', 'high', 'low', 'close', 'volume', 'amount', 'pctChg', 'turn']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            df = df.rename(columns={'pctChg': 'pct_change'})
            df = df.dropna(subset=['close']).sort_values('date')
            df = df.set_index('date')
            return df
        finally:
            bs.logout()
    
    def _fetch_akshare(self, symbol: str, start_str: str, end_str: str) -> pd.DataFrame:
        """从 akshare 获取数据"""
        if not self._akshare_ok:
            return pd.DataFrame()
        
        try:
            import akshare as ak
            ak_start = start_str.replace('-', '')
            ak_end = end_str.replace('-', '')
            df = ak.stock_zh_a_hist(
                symbol=symbol, period="daily",
                start_date=ak_start, end_date=ak_end,
                adjust="qfq", timeout=15.0
            )
            
            if df is None or df.empty:
                return pd.DataFrame()
            
            field_map = {'日期':'date','开盘':'open','收盘':'close','最高':'high',
                         '最低':'low','成交量':'volume','成交额':'amount','涨跌幅':'pct_change'}
            df = df.rename(columns=field_map)
            required = ['date','open','high','low','close','volume','amount','pct_change']
            for c in required:
                if c not in df.columns:
                    return pd.DataFrame()
            df = df[required].copy()
            df['date'] = pd.to_datetime(df['date'])
            for c in required[1:]:
                df[c] = pd.to_numeric(df[c], errors='coerce')
            if df['pct_change'].isna().all() and len(df) > 1:
                df['pct_change'] = df['close'].pct_change() * 100
            df = df.dropna(subset=['close']).sort_values('date')
            df = df.set_index('date')
            return df
        except Exception:
            return pd.DataFrame()
    
    def _fetch_efinance(self, symbol: str, days: int) -> pd.DataFrame:
        """从 efinance 获取数据"""
        if not self._efinance_ok:
            return pd.DataFrame()
        
        try:
            import efinance as ef
            df = ef.stock.get_quote_history(symbol)
            if df.empty:
                return pd.DataFrame()
            
            col_map = {'日期':'date','开盘':'open','收盘':'close','最高':'high',
                       '最低':'low','成交量':'volume','成交额':'amount','涨跌幅':'pct_change'}
            actual = df.columns.tolist()
            mapped = {}
            for cn, en in col_map.items():
                for ac in actual:
                    if cn in ac or ac in cn:
                        mapped[ac] = en
                        break
            df = df.rename(columns=mapped)
            
            required = ['date','open','high','low','close','volume','amount','pct_change']
            missing = [c for c in required if c not in df.columns]
            if missing:
                return pd.DataFrame()
            
            df = df[required].copy()
            df['date'] = pd.to_datetime(df['date'])
            for c in required[1:]:
                df[c] = pd.to_numeric(df[c], errors='coerce')
            if df['pct_change'].isna().all() and len(df) > 1:
                df['pct_change'] = df['close'].pct_change() * 100
            df = df.dropna(subset=['close']).sort_values('date').tail(days)
            df = df.set_index('date')
            return df
        except Exception:
            return pd.DataFrame()
    
    def _fetch_sina(self, symbol: str, days: int) -> pd.DataFrame:
        """从新浪HTTP获取数据"""
        import json
        from urllib.request import urlopen, Request
        
        market = 'sh' if symbol.startswith('6') else 'sz'
        sina_code = f"{market}{symbol}"
        fetch_count = min(days + 30, 800)
        
        try:
            url = (
                f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php"
                f"/CN_MarketData.getKLineData?symbol={sina_code}"
                f"&scale=240&ma=no&datalen={fetch_count}"
            )
            req = Request(url, headers={
                'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.sina.com.cn/',
                'Connection': 'close',
            })
            resp = urlopen(req, timeout=10)
            raw = resp.read().decode('utf-8', errors='ignore').strip()
            if not raw or raw in ('null', '[]'):
                return pd.DataFrame()
            
            data = json.loads(raw)
            if not isinstance(data, list) or not data:
                return pd.DataFrame()
            
            rows = []
            for item in data:
                try:
                    rows.append({
                        'date': item.get('day',''), 
                        'open': float(item.get('open',0)),
                        'close': float(item.get('close',0)), 
                        'high': float(item.get('high',0)),
                        'low': float(item.get('low',0)), 
                        'volume': float(item.get('volume',0)),
                        'amount': 0.0, 
                        'pct_change': 0.0
                    })
                except (ValueError, TypeError):
                    continue
            
            if not rows:
                return pd.DataFrame()
            
            df = pd.DataFrame(rows)
            df = df[df['date'] != '']
            df['date'] = pd.to_datetime(df['date'])
            df = df.dropna(subset=['close']).sort_values('date')
            if len(df) > 1:
                df['pct_change'] = df['close'].pct_change() * 100
                df['pct_change'] = df['pct_change'].fillna(0)
            df['amount'] = df['close'] * df['volume'] * 10
            df = df.tail(days).set_index('date')
            return df
        except Exception:
            return pd.DataFrame()
    
    def _fetch_tencent(self, symbol: str, days: int) -> pd.DataFrame:
        """从腾讯HTTP获取数据"""
        import json
        from urllib.request import urlopen, Request
        
        # 过滤指数基金
        if symbol.startswith('9') and len(symbol) == 6 and symbol[1:].isdigit():
            try:
                code_num = int(symbol)
                if 920000 <= code_num <= 939999:
                    logger.debug("跳过指数基金 %s", symbol)
                    return pd.DataFrame()
            except ValueError:
                pass
        
        market = 'sh' if symbol.startswith('6') else 'sz'
        qcode = f"{market}{symbol}"
        fetch_count = min(days + 30, 800)
        
        try:
            url = (
                f"https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get"
                f"?param={qcode},day,,,{fetch_count},qfq"
            )
            req = Request(url, headers={
                'User-Agent': 'Mozilla/5.0', 'Referer': 'https://gu.qq.com/',
                'Connection': 'close',
            })
            resp = urlopen(req, timeout=10)
            raw = resp.read().decode('utf-8', errors='ignore').strip()
            if not raw:
                return pd.DataFrame()
            
            data = json.loads(raw)
            if data.get('code') != 0:
                return pd.DataFrame()
            
            stock_data = data.get('data', {}).get(qcode, {})
            day_data = stock_data.get('qfqday') or stock_data.get('day', [])
            if not day_data or not isinstance(day_data, list) or len(day_data) < 2:
                return pd.DataFrame()
            
            rows = []
            for item in day_data:
                if not isinstance(item, list) or len(item) < 6:
                    continue
                try:
                    rows.append({
                        'date': str(item[0]), 
                        'open': float(item[1]), 
                        'close': float(item[2]),
                        'high': float(item[3]), 
                        'low': float(item[4]), 
                        'volume': float(item[5]),
                        'pct_change': float(item[7]) if len(item) > 7 and item[7] != '' else 0.0,
                        'amount': float(item[8]) * 10000 if len(item) > 8 and item[8] != '' else 0.0,
                    })
                except (ValueError, TypeError, IndexError):
                    continue
            
            if not rows:
                return pd.DataFrame()
            
            df = pd.DataFrame(rows)
            df['date'] = pd.to_datetime(df['date'])
            df = df.dropna(subset=['close']).sort_values('date')
            if df['amount'].sum() == 0:
                df['amount'] = df['close'] * df['volume'] * 10
            if df['pct_change'].abs().sum() < 0.01 and len(df) > 1:
                df['pct_change'] = df['close'].pct_change() * 100
                df['pct_change'] = df['pct_change'].fillna(0)
            df = df.tail(days).set_index('date')
            return df
        except Exception:
            return pd.DataFrame()
    
    def _validate_data(self, df: pd.DataFrame) -> bool:
        """数据完整性校验"""
        if df.empty:
            return False
        
        # 检查必要列
        required_columns = ['open', 'high', 'low', 'close', 'volume']
        for col in required_columns:
            if col not in df.columns:
                return False
        
        # 检查数据长度
        if len(df) < 30:
            logger.warning(f"数据长度不足: {len(df)} 条")
            return False
        
        # 检查数据质量
        if df['close'].isna().any():
            return False
        
        # 检查数据连续性
        date_diff = df.index.to_series().diff().dropna()
        if (date_diff > pd.Timedelta(days=7)).any():
            logger.warning("数据存在较大时间间隔")
        
        return True
    
    def _update_to_db(self, symbol: str, df: pd.DataFrame) -> bool:
        """将数据更新到数据库"""
        import sqlite3
        
        db_path = self.db_fetcher.db_path
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        try:
            # 删除现有数据
            cursor.execute("DELETE FROM daily_price WHERE code = ?", (symbol,))
            
            # 插入新数据
            for date, row in df.iterrows():
                trade_date = date.strftime('%Y-%m-%d')
                cursor.execute(
                    "INSERT INTO daily_price (code, trade_date, open, high, low, close, volume, amount, turnover, pct_chg) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        symbol,
                        trade_date,
                        row.get('open', 0),
                        row.get('high', 0),
                        row.get('low', 0),
                        row.get('close', 0),
                        row.get('volume', 0),
                        row.get('amount', 0),
                        row.get('turn', 0),
                        row.get('pct_change', 0)
                    )
                )
            
            conn.commit()
            logger.debug("成功更新 %s 数据: {len(df)} 条", symbol)
            return True
        except Exception as e:
            logger.error("更新数据库失败: %s", e)
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def update_all_stocks(self, days: int = 180) -> Dict[str, bool]:
        """更新所有股票数据"""
        try:
            # 获取股票列表
            stock_list = self.db_fetcher.get_stock_list()
            symbols = stock_list['symbol'].tolist()
            
            # 分批更新
            batch_size = 100
            results = {}
            
            for i in range(0, len(symbols), batch_size):
                batch = symbols[i:i+batch_size]
                batch_result = self.update_stock_data(batch, days)
                results.update(batch_result)
                
                # 批次之间休息
                time.sleep(5)
            
            return results
        except Exception as e:
            logger.error("更新所有股票失败: %s", e)
            return {}


def get_data_updater(config: Optional[DataSourceConfig] = None) -> DataUpdater:
    """获取数据更新器实例"""
    return DataUpdater(config)
