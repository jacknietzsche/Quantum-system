# -*- coding: utf-8 -*-
"""
笨数据库 - A股本地量化数据库
极简设计：单文件SQLite + 线性逻辑 + 零黑盒

修复记录:
  - 修复重复写入：INSERT OR REPLACE 替代 to_sql(append)
  - 修复数据类型：SQLite 读取后强制 numeric 转换
  - 修复 akshare 日期过滤：下载后按 start/end 裁剪
  - 修复 baostock 会话复用：统一 login 一次批量查询
  - 2026-04-05: 扩展至7层数据源 fallback (akshare/baostock/efinance/sina_http/tencent_http/tushare_pro/eastmoney_api)
  - 2026-04-05: 添加快速失败切换机制，连接断开立即切换数据源
"""
import sqlite3
import os
import shutil
import time
from datetime import datetime, timedelta
from typing import Optional, List, Tuple
import pandas as pd

# ================================================================
# 配置区 - 改这里就行，别的别动
# ================================================================
DB_PATH = "a_stock_quant.db"              # 数据库文件路径（单文件，拷走就能用）
LOG_FILE = "a_stock_db.log"               # 日志文件
BACKUP_DIR = "backup"                     # 备份目录
HISTORY_YEARS = 5                         # 历史数据年数
REQUEST_DELAY = 0.05                      # 每只股票请求间隔（秒），防封（优化后更短）
REQUEST_DELAY_LIST = 1.0                  # 列表接口请求间隔（秒）
RETRY_COUNT = 3                           # 单只股票失败重试次数
RETRY_INTERVALS = [2, 4, 6]               # 重试间隔（秒）

# 可替代的免费数据API资源
ALTERNATIVE_APIS = [
    {
        "name": "网易财经",
        "url": "http://quotes.money.163.com/service/chddata.html",
        "params": {
            "code": "{code}",
            "start": "{start}",
            "end": "{end}"
        }
    },
    {
        "name": "雪球API",
        "url": "https://xueqiu.com/stock/forchartk/stocklist.json",
        "params": {
            "symbol": "{symbol}",
            "period": "1d",
            "type": "before",
            "count": "{count}"
        }
    }
]

# 数据源优先级：akshare > baostock > efinance > 新浪HTTP > 腾讯HTTP
# 周末/非交易日 akshare 经常返回空数据，自动切换为 baostock 优先
_IS_WEEKEND = datetime.now().weekday() >= 5  # 周六=5, 周日=6
if _IS_WEEKEND:
    DATA_SOURCES = ["baostock", "akshare", "efinance", "sina_http", "tushare_pro", "eastmoney_api"]
else:
    DATA_SOURCES = ["akshare", "baostock", "efinance", "sina_http", "tushare_pro", "eastmoney_api"]

# 连续失败后切换数据源的阈值
CONSECUTIVE_FAILURE_THRESHOLD = 2  # 连续2次失败就切换

# ================================================================
# 日志配置
# ================================================================
from core.logging_config import setup_logging, get_logger
setup_logging()
logger = get_logger(__name__)

# 需要转为 float 的列
NUMERIC_COLS = ["open", "high", "low", "close", "volume", "amount", "turnover", "pct_chg"]


# ================================================================
# 核心类：笨数据库
# ================================================================
class 笨数据库:
    """
    极简A股数据库
    --------
    设计原则：
    1. 单文件 SQLite，拷走就能用
    2. 线性逻辑，没有异步/多线程/ORM
    3. 所有操作可打断，重启从断点继续
    4. 与现有回测系统 100% 兼容（字段名、代码格式、日期格式）
    """

    def __init__(self, db_path: str = DB_PATH):
        """
        初始化数据库
        db_path: 数据库文件路径，默认 "a_stock.db"
        """
        self.db_path = db_path
        self._bs_session = None  # baostock 会话复用
        self._bs_last_used = 0   # baostock 上次使用时间
        self._init_db()

    # ============================================================
    # 第1步：创建表
    # ============================================================
    def _init_db(self):
        """创建3张表，如果已存在则跳过"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute("""
            CREATE TABLE IF NOT EXISTS stocks (
                code TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                exchange TEXT,
                list_date TEXT,
                delist_date TEXT
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS daily_price (
                code TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume REAL,
                amount REAL,
                turnover REAL,
                pct_chg REAL,
                PRIMARY KEY (code, trade_date)
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS adj_factor (
                code TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                adj_factor REAL NOT NULL,
                PRIMARY KEY (code, trade_date)
            )
        """)

        conn.commit()
        conn.close()
        logger.info(f"数据库就绪: {os.path.abspath(self.db_path)}")

    # ============================================================
    # 第2步：备份
    # ============================================================
    def _backup(self):
        """更新前自动备份，每次一个文件"""
        if not os.path.exists(self.db_path):
            return

        os.makedirs(BACKUP_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(BACKUP_DIR, f"a_stock_{ts}.db")
        shutil.copy2(self.db_path, path)
        logger.info(f"已备份: {path}")

    def get_backup_list(self) -> List[str]:
        """列出所有备份文件"""
        if not os.path.exists(BACKUP_DIR):
            return []
        files = sorted(os.listdir(BACKUP_DIR))
        return [os.path.join(BACKUP_DIR, f) for f in files if f.endswith(".db")]

    def restore_backup(self, backup_path: str):
        """从备份恢复"""
        if not os.path.exists(backup_path):
            logger.error(f"备份文件不存在: {backup_path}")
            return False
        self._close_bs()
        shutil.copy2(backup_path, self.db_path)
        logger.info(f"已从备份恢复: {backup_path}")
        return True

    # ============================================================
    # 第3步：股票基础信息
    # ============================================================
    def 更新股票列表(self, force: bool = False):
        """
        获取全市场A股列表（代码+名称+交易所）
        force=True 强制全量更新，否则已有数据时跳过
        """
        if not force:
            count = self._query_one("SELECT COUNT(*) FROM stocks")
            if count > 0:
                logger.info(f"股票列表已有 {count} 只，跳过（加 force=True 强制更新）")
                return

        logger.info("正在获取股票列表...")

        rows = None
        for source in DATA_SOURCES:
            try:
                if source == "akshare":
                    rows = self._fetch_akshare_stocks()
                elif source == "baostock":
                    rows = self._fetch_baostock_stocks()
                elif source == "efinance":
                    rows = self._fetch_efinance_stocks()

                if rows and len(rows) > 500:
                    logger.info(f"  {source} 获取成功: {len(rows)} 只")
                    break
            except Exception as e:
                logger.warning(f"  {source} 失败: {e}")

        if not rows or len(rows) < 500:
            logger.error("所有数据源均失败，无法获取股票列表")
            return

        self._backup()

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("DELETE FROM stocks")
        c.executemany(
            "INSERT OR REPLACE INTO stocks (code, name, exchange, list_date, delist_date) VALUES (?,?,?,?,?)",
            rows
        )
        conn.commit()
        conn.close()
        logger.info(f"股票列表更新完成: {len(rows)} 只")

    def _fetch_akshare_stocks(self) -> Optional[List[Tuple]]:
        """akshare 获取股票列表"""
        try:
            import akshare as ak
            df = ak.stock_info_a_code_name()
            if df is None or len(df) == 0:
                return None

            result = []
            for _, r in df.iterrows():
                code = str(r["code"]).zfill(6)
                name = str(r["name"])
                # 过滤ST、退市
                if "ST" in name or "退" in name:
                    continue
                ex = "sh" if code.startswith(("6", "5")) else "sz"
                result.append((code, name, ex, None, None))
            return result
        except Exception as e:
            logger.warning(f"akshare 股票列表失败: {e}")
            return None

    def _fetch_baostock_stocks(self) -> Optional[List[Tuple]]:
        """baostock 获取股票列表"""
        try:
            import baostock as bs
            lg = bs.login()
            if lg.error_code != "0":
                logger.warning(f"baostock 登录失败: {lg.error_msg}")
                return None

            rs = bs.query_all_stock()
            result = []
            while rs.next():
                row = rs.get_row_data()
                if not row[0]:
                    continue
                parts = row[0].split(".")
                if len(parts) != 2:
                    continue
                ex, code = parts[0], parts[1]
                name = row[1] or ""
                list_d = row[2] if row[2] else None
                delist_d = row[3] if row[3] else None
                if "ST" in name or "退" in name:
                    continue
                result.append((code, name, ex, list_d, delist_d))

            bs.logout()
            return result
        except Exception as e:
            logger.warning(f"baostock 股票列表失败: {e}")
            return None

    def _fetch_efinance_stocks(self) -> Optional[List[Tuple]]:
        """efinance 获取股票列表"""
        try:
            import efinance as ef
            df = ef.stock.get_belong_plate_all()
            if df is None or len(df) == 0:
                return None

            df = df.drop_duplicates(subset=["代码"], keep="first")
            result = []
            for _, r in df.iterrows():
                code = str(r["代码"]).zfill(6)
                # 根据列名取名称（efinance 不同版本列名不同）
                name = str(r.get("名称", r.get("股票名称", "")))
                if "ST" in name or "退" in name:
                    continue
                ex = "sh" if code.startswith(("6", "5")) else "sz"
                result.append((code, name, ex, None, None))
            return result
        except Exception as e:
            logger.warning(f"efinance 股票列表失败: {e}")
            return None

    # ============================================================
    # 第4步：下载日线行情
    # ============================================================
    def 初始化历史数据(self, years: int = HISTORY_YEARS):
        """
        首次运行：下载过去N年全市场数据
        中途可随时 Ctrl+C 打断，下次运行自动从断点继续
        """
        self.更新股票列表()

        end = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=years * 366)).strftime("%Y-%m-%d")

        codes = self.get_all_codes()
        total_codes = len(codes)
        logger.info(f"开始处理近{years}年历史数据: {start} ~ {end}, 共 {total_codes} 只股票")

        # 优化：只处理缺失数据的股票（断点续传加速）
        codes_with_data = set()
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT DISTINCT code FROM daily_price")
        for row in c.fetchall():
            codes_with_data.add(row[0])
        conn.close()

        codes_to_download = [code for code in codes if code not in codes_with_data]
        if codes_to_download:
            logger.info(f"断点续传: 跳过 {len(codes_with_data)} 只有数据的股票，还需下载 {len(codes_to_download)} 只")
            codes = codes_to_download
        else:
            logger.info(f"所有 {total_codes} 只股票已有数据，无需下载")
            return

        logger.info(f"开始下载历史数据: {start} ~ {end}, 共 {len(codes)} 只股票")

        self._backup()

        success, fail, skip = 0, 0, 0
        api_error_count = 0
        alternative_api_used = 0
        
        start_time = time.time()
        for i, code in enumerate(codes):
            # 检查这只股票是否已有数据（断点续传）
            latest = self.get_latest_date(code)
            if latest and latest >= end:
                skip += 1
                continue

            actual_start = latest if latest and latest > start else start

            try:
                self._更新单只股票数据(code, actual_start, end)
                success += 1
            except Exception as e:
                fail += 1
                api_error_count += 1
                logger.warning(f"  失败 {code}: {e}")

            # 进度日志
            if (i + 1) % 200 == 0 or (i + 1) == len(codes):
                elapsed = time.time() - start_time
                remaining = (elapsed / (i + 1)) * (len(codes) - i - 1)
                logger.info(
                    f"  进度 {i+1}/{len(codes)} "
                    f"(成功{success} 跳过{skip} 失败{fail}) "
                    f"耗时: {elapsed:.1f}s 预计剩余: {remaining:.1f}s"
                )

            time.sleep(REQUEST_DELAY)

        self._close_bs()
        total_time = time.time() - start_time
        logger.info(f"历史数据初始化完成: 成功{success} 跳过{skip} 失败{fail}")
        logger.info(f"总耗时: {total_time:.1f}秒, 平均每只: {total_time / max(1, len(codes)):.3f}秒")
        logger.info(f"API错误次数: {api_error_count}, 替代API使用次数: {alternative_api_used}")

    def 每日增量更新(self):
        """
        每日收盘后运行：只下载缺失的交易日数据
        """
        logger.info("开始每日增量更新...")

        codes = self.get_all_codes()
        today = datetime.now().strftime("%Y-%m-%d")
        total_codes = len(codes)

        # 查询每只股票的最新日期
        latest_map = {}
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT code, MAX(trade_date) FROM daily_price GROUP BY code")
        for row in c.fetchall():
            latest_map[row[0]] = row[1]
        conn.close()

        success, fail, skip = 0, 0, 0
        api_error_count = 0
        alternative_api_used = 0
        
        start_time = time.time()
        for i, code in enumerate(codes):
            latest = latest_map.get(code)
            if latest is None:
                actual_start = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
            else:
                actual_start = latest

            if actual_start >= today:
                skip += 1
                continue

            try:
                self._更新单只股票数据(code, actual_start, today)
                success += 1
            except Exception as e:
                fail += 1
                api_error_count += 1
                logger.warning(f"  失败 {code}: {e}")

            if (i + 1) % 200 == 0 or (i + 1) == len(codes):
                elapsed = time.time() - start_time
                remaining = (elapsed / (i + 1)) * (len(codes) - i - 1)
                logger.info(
                    f"  进度 {i+1}/{len(codes)} "
                    f"(成功{success} 跳过{skip} 失败{fail}) "
                    f"耗时: {elapsed:.1f}s 预计剩余: {remaining:.1f}s"
                )

            time.sleep(REQUEST_DELAY)

        self._close_bs()
        total_time = time.time() - start_time
        logger.info(f"增量更新完成: 成功{success} 跳过{skip} 失败{fail}")
        logger.info(f"总耗时: {total_time:.1f}秒, 平均每只: {total_time / max(1, len(codes)):.3f}秒")
        logger.info(f"API错误次数: {api_error_count}, 替代API使用次数: {alternative_api_used}")

    def _更新单只股票数据(self, code: str, start_date: str, end_date: str):
        """
        更新单只股票：多源降级 + INSERT OR REPLACE 去重
        快速失败切换：连续失败2次立即切换数据源
        实现指数退避重试、API端点切换和替代API搜索
        """
        df = None
        consecutive_failures = 0
        api_errors = []

        # 主数据源尝试
        for source in DATA_SOURCES:
            for retry in range(RETRY_COUNT):
                try:
                    logger.debug(f"  {code}: 尝试 {source} (第{retry+1}/{RETRY_COUNT}次)")
                    
                    if source == "akshare":
                        df = self._fetch_akshare_daily(code, start_date, end_date)
                    elif source == "baostock":
                        df = self._fetch_baostock_daily(code, start_date, end_date)
                    elif source == "efinance":
                        df = self._fetch_efinance_daily(code, start_date, end_date)
                    elif source == "sina_http":
                        df = self._fetch_sina_http(code, start_date, end_date)
                    elif source == "tencent_http":
                        df = self._fetch_tencent_http(code, start_date, end_date)
                    elif source == "tushare_pro":
                        df = self._fetch_tushare_pro(code, start_date, end_date)
                    elif source == "eastmoney_api":
                        df = self._fetch_eastmoney_api(code, start_date, end_date)

                    if df is not None and len(df) > 0:
                        logger.debug(f"  {code}: {source} 获取 {len(df)} 条")
                        consecutive_failures = 0  # 成功后重置计数
                        return self._save_stock_data(df, code)
                    else:
                        logger.debug(f"  {code}: {source} 返回空数据")
                        api_errors.append(f"{source}: 返回空数据")
                        consecutive_failures += 1
                        if consecutive_failures >= CONSECUTIVE_FAILURE_THRESHOLD:
                            logger.debug(f"  {code} 连续失败{consecutive_failures}次，快速切换数据源")
                            break
                except Exception as e:
                    err_str = str(e).lower()
                    error_msg = f"{source}: {str(e)[:80]}"
                    api_errors.append(error_msg)
                    logger.debug(f"  {code} {source} 异常: {str(e)[:80]}")
                    
                    # 连接断开错误立即切换
                    if 'remote' in err_str or 'disconnected' in err_str or 'connection' in err_str:
                        logger.debug(f"  {code} {source} 连接断开，立即切换")
                        consecutive_failures = CONSECUTIVE_FAILURE_THRESHOLD  # 强制切换
                        break
                    
                    # 指数退避重试
                    if retry < RETRY_COUNT - 1:
                        wait_time = RETRY_INTERVALS[min(retry, len(RETRY_INTERVALS) - 1)]
                        logger.debug(f"  {code} {source} 失败，{wait_time}秒后重试")
                        time.sleep(wait_time)

        # 尝试替代API
        logger.debug(f"  {code} 所有主数据源失败，尝试替代API")
        df = self._try_alternative_apis(code, start_date, end_date)
        if df is not None and len(df) > 0:
            logger.info(f"  {code}: 替代API获取成功 {len(df)} 条")
            return self._save_stock_data(df, code)

        # 所有数据源都失败
        logger.warning(f"  {code}: 所有数据源失败，记录错误: {'; '.join(api_errors[:3])}")
        return

    def _save_stock_data(self, df: pd.DataFrame, code: str):
        """
        保存股票数据到数据库
        """
        # ---- 标准化列名（兼容中文/英文列名）----
        rename_map = {
            "日期": "trade_date", "股票代码": "code",
            "开盘": "open", "收盘": "close",
            "最高": "high", "最低": "low",
            "成交量": "volume", "成交额": "amount",
            "涨跌幅": "pct_chg", "换手率": "turnover",
            "振幅": "amplitude", "涨跌额": "change",
        }
        df = df.rename(columns=rename_map)

        # 确保代码列
        df["code"] = code

        # 检查必填列
        required = ["trade_date", "open", "high", "low", "close", "volume"]
        for col in required:
            if col not in df.columns:
                logger.debug(f"  {code}: 缺少必填字段 {col}")
                return

        # ---- 按日期裁剪（防止 akshare/efinance 返回多余数据）----
        if "trade_date" in df.columns:
            df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.strftime("%Y-%m-%d")

        if len(df) == 0:
            logger.debug(f"  {code}: 数据为空，跳过")
            return

        # ---- 补算缺失字段 ----
        # pct_chg: 涨跌幅(%)
        if "pct_chg" not in df.columns:
            df["pct_chg"] = df["close"].pct_change(fill_method=None) * 100
            df["pct_chg"] = df["pct_chg"].fillna(0.0)

        # turnover: 换手率(%)，用 amount/(close*流通市值) 估算
        if "turnover" not in df.columns:
            df["turnover"] = df["amount"] / (df["close"] * 1e8) * 100
            df["turnover"] = df["turnover"].fillna(1.0).clip(0.01, 50.0)

        # ---- 数据类型转换 ----
        for col in NUMERIC_COLS:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # ---- 选择需要的列并去重 ----
        cols = ["code", "trade_date", "open", "high", "low", "close",
                "volume", "amount", "turnover", "pct_chg"]
        df = df[[c for c in cols if c in df.columns]]

        # 按 code+trade_date 去重（保留最后一条）
        df = df.drop_duplicates(subset=["code", "trade_date"], keep="last")

        # ---- 写入数据库（executemany 批量插入，幂等安全）----
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        # 批量准备数据
        records = [
            (
                row["code"], row["trade_date"],
                float(row["open"]) if pd.notna(row.get("open")) else None,
                float(row["high"]) if pd.notna(row.get("high")) else None,
                float(row["low"]) if pd.notna(row.get("low")) else None,
                float(row["close"]) if pd.notna(row.get("close")) else None,
                float(row["volume"]) if pd.notna(row.get("volume")) else None,
                float(row["amount"]) if pd.notna(row.get("amount")) else None,
                float(row["turnover"]) if pd.notna(row.get("turnover")) else None,
                float(row["pct_chg"]) if pd.notna(row.get("pct_chg")) else None,
            )
            for _, row in df.iterrows()
        ]
        c.executemany("""
            INSERT OR REPLACE INTO daily_price
                (code, trade_date, open, high, low, close, volume, amount, turnover, pct_chg)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, records)
        conn.commit()
        conn.close()
        logger.debug(f"  {code}: 保存 {len(records)} 条数据")

    def _try_alternative_apis(self, code: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        """
        尝试使用替代的免费数据API
        """
        import requests
        import json
        
        # 计算需要的天数
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        days = (end_dt - start_dt).days + 30
        
        # 网易财经API
        try:
            logger.debug(f"  {code}: 尝试网易财经API")
            market = '0' if code.startswith('6') else '1'
            symbol = f"{market}{code}"
            start_str = start_date.replace('-', '')
            end_str = end_date.replace('-', '')
            
            url = f"http://quotes.money.163.com/service/chddata.html?code={symbol}&start={start_str}&end={end_str}&fields=TCLOSE;HIGH;LOW;TOPEN;LCLOSE;CHG;PCHG;TURNOVER;VOTURNOVER;VATURNOVER"
            
            resp = requests.get(url, timeout=15, headers={
                'User-Agent': 'Mozilla/5.0',
                'Referer': 'http://quotes.money.163.com/',
            })
            resp.raise_for_status()
            
            # 解析CSV数据
            import io
            df = pd.read_csv(io.StringIO(resp.text), encoding='gbk')
            if len(df) > 0:
                # 重命名列
                rename_map = {
                    '日期': 'trade_date',
                    '开盘价': 'open',
                    '最高价': 'high',
                    '最低价': 'low',
                    '收盘价': 'close',
                    '成交量': 'volume',
                    '成交金额': 'amount',
                    '涨跌幅': 'pct_chg',
                    '换手率': 'turnover',
                }
                df = df.rename(columns=rename_map)
                logger.debug(f"  {code}: 网易财经API获取 {len(df)} 条")
                return df
        except Exception as e:
            logger.debug(f"  {code}: 网易财经API失败: {str(e)[:50]}")
        
        # 雪球API
        try:
            logger.debug(f"  {code}: 尝试雪球API")
            market = 'SH' if code.startswith('6') else 'SZ'
            symbol = f"{market}{code}"
            
            url = f"https://xueqiu.com/stock/forchartk/stocklist.json?symbol={symbol}&period=1d&type=before&count={min(days, 1000)}"
            
            resp = requests.get(url, timeout=15, headers={
                'User-Agent': 'Mozilla/5.0',
                'Referer': 'https://xueqiu.com/',
            })
            resp.raise_for_status()
            
            data = json.loads(resp.text)
            item = data.get('item', [])
            if item:
                klines = item[0].get('klines', [])
                records = []
                for kline in klines:
                    parts = kline.split(',')
                    if len(parts) >= 6:
                        records.append({
                            'trade_date': parts[0],
                            'open': float(parts[1]),
                            'high': float(parts[2]),
                            'low': float(parts[3]),
                            'close': float(parts[4]),
                            'volume': float(parts[5]),
                        })
                if records:
                    df = pd.DataFrame(records)
                    logger.debug(f"  {code}: 雪球API获取 {len(df)} 条")
                    return df
        except Exception as e:
            logger.debug(f"  {code}: 雪球API失败: {str(e)[:50]}")
        
        return None

    # ============================================================
    # 数据源：AkShare
    # ============================================================
    def _fetch_akshare_daily(self, code: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        """akshare 获取日线（前复权）"""
        import akshare as ak
        # akshare 格式: sh600519
        symbol = f"sh{code}" if code.startswith(("6", "5")) else f"sz{code}"

        df = ak.stock_zh_a_hist(
            symbol=symbol,
            start_date=start_date.replace("-", ""),
            end_date=end_date.replace("-", ""),
            adjust="qfq",
        )

        if df is None or len(df) == 0:
            return None

        # akshare 列名是中文，外层会 rename
        return df

    # ============================================================
    # 数据源：BaoStock（会话复用）
    # ============================================================
    def _get_bs_session(self):
        """获取/复用 baostock 会话（30分钟内复用）"""
        import baostock as bs

        now = time.time()
        if self._bs_session is not None and (now - self._bs_last_used) < 1800:
            self._bs_last_used = now
            return self._bs_session

        # 新建会话
        if self._bs_session is not None:
            try:
                bs.logout()
            except Exception as e:
                logger.debug("session logout ignored: %s", e)

        lg = bs.login()
        if lg.error_code != "0":
            logger.warning(f"baostock 登录失败: {lg.error_msg}")
            return None

        self._bs_session = bs
        self._bs_last_used = now
        return self._bs_session

    def _close_bs(self):
        """关闭 baostock 会话"""
        if self._bs_session is not None:
            try:
                self._bs_session.logout()
            except Exception as e:
                logger.debug("session close ignored: %s", e)
            self._bs_session = None

    def _fetch_baostock_daily(self, code: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        """baostock 获取日线（前复权）"""
        bs = self._get_bs_session()
        if bs is None:
            return None

        prefix = "sh." if code.startswith(("6", "5")) else "sz."
        bs_code = prefix + code

        rs = bs.query_history_k_data_plus(
            bs_code,
            "date,open,high,low,close,volume,amount,turn,pctChg",
            start_date=start_date,
            end_date=end_date,
            frequency="d",
            adjustflag="2",  # 前复权
        )

        rows = []
        while rs.next():
            row = rs.get_row_data()
            if row[0]:  # date 非空
                rows.append(row)

        if not rows:
            return None

        df = pd.DataFrame(rows, columns=[
            "trade_date", "open", "high", "low", "close",
            "volume", "amount", "turnover", "pct_chg"
        ])
        # baostock 返回的列名已经是英文，和外层标准一致
        return df

    # ============================================================
    # 数据源：efinance
    # ============================================================
    def _fetch_efinance_daily(self, code: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        """efinance 获取日线"""
        import efinance as ef

        df = ef.stock.get_quote_history(code)

        if df is None or len(df) == 0:
            return None

        # efinance 列名是中文，外层会 rename
        return df

    # ============================================================
    # 数据源：新浪HTTP
    # ============================================================
    def _fetch_sina_http(self, code: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        """新浪HTTP获取日线"""
        import requests
        import json
        
        # 计算需要的天数
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        days = (end_dt - start_dt).days + 30
        
        market = 'sh' if code.startswith('6') else 'sz'
        symbol = f"{market}{code}"
        
        url = f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={symbol}&scale=240&ma=no&datalen={days}"
        
        try:
            resp = requests.get(url, timeout=10, headers={
                'User-Agent': 'Mozilla/5.0',
                'Referer': 'https://finance.sina.com.cn',
                'Connection': 'close',
            })
            resp.raise_for_status()
            
            text = resp.text.strip()
            if not text or text == 'null':
                return None
            
            data = json.loads(text)
            if not data:
                return None
            
            # 转换为DataFrame
            records = []
            for item in data:
                records.append({
                    'trade_date': item.get('day', ''),
                    'open': float(item.get('open', 0)),
                    'high': float(item.get('high', 0)),
                    'low': float(item.get('low', 0)),
                    'close': float(item.get('close', 0)),
                    'volume': float(item.get('volume', 0)),
                    'amount': float(item.get('amount', 0)),
                })
            
            if not records:
                return None
            
            df = pd.DataFrame(records)
            return df
            
        except Exception as e:
            logger.debug(f"新浪HTTP失败 {code}: {str(e)[:50]}")
            return None

    # ============================================================
    # 数据源：腾讯HTTP
    # ============================================================
    def _fetch_tencent_http(self, code: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        """腾讯HTTP获取日线（添加更快的失败检测和切换）"""
        import requests
        import json
        
        # 跳过指数基金（腾讯API限制）
        if code.startswith('9') and len(code) == 6:
            return None
        
        # 计算需要的天数
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        days = min((end_dt - start_dt).days + 30, 500)
        
        market = 'sh' if code.startswith('6') else 'sz'
        symbol = f"{market}{code}"
        
        url = (f"https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get"
               f"?param={symbol},day,,,{days},qfq")
        
        # 更短的超时，更快的失败切换
        for retry in range(2):  # 最多重试2次
            try:
                resp = requests.get(url, timeout=8, headers={
                    'User-Agent': 'Mozilla/5.0',
                    'Referer': 'https://gu.qq.com/',
                    'Connection': 'close',
                })
                resp.raise_for_status()
                
                text = resp.text.strip()
                if not text:
                    if retry < 1:
                        time.sleep(1)  # 短暂等待后重试
                        continue
                    return None
                
                data = json.loads(text)
                if data.get('code') != 0:
                    return None
                
                stock_data = data.get('data', {}).get(symbol, {})
                klines = stock_data.get('day', [])
                
                if not klines:
                    return None
                
                records = []
                for kline in klines:
                    if isinstance(kline, list) and len(kline) >= 6:
                        records.append({
                            'trade_date': kline[0],
                            'open': float(kline[1]) if kline[1] else 0,
                            'high': float(kline[2]) if kline[2] else 0,
                            'low': float(kline[3]) if kline[3] else 0,
                            'close': float(kline[4]) if kline[4] else 0,
                            'volume': float(kline[5]) if kline[5] else 0,
                            'amount': float(kline[6]) if len(kline) > 6 and kline[6] else 0,
                        })
                
                if not records:
                    return None
                
                df = pd.DataFrame(records)
                return df
                
            except Exception as e:
                err_str = str(e).lower()
                # 如果是连接断开错误，快速切换
                if 'remote' in err_str or 'disconnected' in err_str or 'connection' in err_str:
                    logger.debug(f"腾讯HTTP连接断开 {code}, 快速切换数据源")
                    return None  # 快速返回，让外层切换数据源
                if retry < 1:
                    time.sleep(0.5)
                    continue
                logger.debug(f"腾讯HTTP失败 {code}: {str(e)[:50]}")
                return None
        
        return None

    # ============================================================
    # 数据源：Tushare Pro（需要token，可选）
    # ============================================================
    def _fetch_tushare_pro(self, code: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        """Tushare Pro获取日线"""
        try:
            import tushare as ts
            # 检查是否配置了token
            if not hasattr(ts, 'pro') or not hasattr(ts.pro, 'api'):
                return None
            
            ts_code = f"{code}.SH" if code.startswith('6') else f"{code}.SZ"
            
            pro = ts.pro_api()
            df = pro.daily(
                ts_code=ts_code,
                start_date=start_date.replace('-', ''),
                end_date=end_date.replace('-', '')
            )
            
            if df is None or len(df) == 0:
                return None
            
            # Tushare列名转换
            rename_map = {
                'trade_date': 'trade_date',
                'open': 'open', 'high': 'high', 
                'low': 'low', 'close': 'close',
                'vol': 'volume', 'amount': 'amount',
                'pct_chg': 'pct_chg'
            }
            
            records = []
            for _, row in df.iterrows():
                records.append({
                    'trade_date': str(row.get('trade_date', '')),
                    'open': float(row.get('open', 0)) if pd.notna(row.get('open')) else None,
                    'high': float(row.get('high', 0)) if pd.notna(row.get('high')) else None,
                    'low': float(row.get('low', 0)) if pd.notna(row.get('low')) else None,
                    'close': float(row.get('close', 0)) if pd.notna(row.get('close')) else None,
                    'volume': float(row.get('vol', 0)) if pd.notna(row.get('vol')) else None,
                    'amount': float(row.get('amount', 0)) * 1000 / 1e4 if pd.notna(row.get('amount')) else None,  # 转换为万元
                })
            
            if not records:
                return None
            
            result_df = pd.DataFrame(records)
            logger.debug(f"Tushare Pro获取 {code}: {len(result_df)} 条")
            return result_df
            
        except ImportError:
            logger.debug("Tushare未安装，跳过")
            return None
        except Exception as e:
            logger.debug(f"Tushare Pro失败 {code}: {str(e)[:50]}")
            return None

    # ============================================================
    # 数据源：东方财富API（免费）
    # ============================================================
    def _fetch_eastmoney_api(self, code: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        """东方财富API获取日线（免费接口）- 禁用自动重试，快速失败切换"""
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        import json
        
        market = '1' if code.startswith('6') else '0'
        
        url = "https://push2.eastmoney.com/api/qt/stock/kline/get"
        params = {
            'fields1': 'f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13',
            'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61',
            'beg': start_date.replace('-', ''),
            'end': end_date.replace('-', ''),
            'rtntype': '6',
            'secid': f"{market}.{code}",
            'klt': '101',  # 日K
            'fqt': '1',   # 前复权
        }
        
        # 创建禁用重试的Session
        session = requests.Session()
        adapter = HTTPAdapter(max_retries=Retry(total=0, connect=0, read=0, redirect=0))  # 禁用所有重试
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        
        try:
            for retry in range(1):  # 只尝试1次，失败就切换
                try:
                    resp = session.get(url, params=params, timeout=8, headers={
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                        'Referer': 'https://quote.eastmoney.com/',
                        'Connection': 'close',
                        'Accept': '*/*',
                    })
                    
                    text = resp.text.strip()
                    if not text:
                        continue
                    
                    data = json.loads(text)
                    klines = data.get('data', {}).get('klines', [])
                    
                    if not klines:
                        continue
                    
                    records = []
                    for line in klines:
                        parts = line.split(',')
                        if len(parts) >= 11:
                            records.append({
                                'trade_date': parts[0],
                                'open': float(parts[1]),
                                'close': float(parts[2]),
                                'high': float(parts[3]),
                                'low': float(parts[4]),
                                'volume': float(parts[5]),       # 成交量
                                'amount': float(parts[6]) / 10000 if parts[6] else 0,  # 成交额转万元
                            })
                    
                    if not records:
                        continue
                    
                    result_df = pd.DataFrame(records)
                    logger.debug(f"东方财富API获取 {code}: {len(result_df)} 条")
                    return result_df
                    
                except Exception as e:
                    err_str = str(e).lower()
                    # 连接断开或超时就立即返回，让外层切换数据源
                    if any(x in err_str for x in ['remote', 'disconnected', 'connection', 'timeout', 'timed out']):
                        return None
                    # 其他错误也直接返回
                    return None
                    
        except Exception as e:
            logger.debug(f"东方财富API失败 {code}: {str(e)[:50]}")
            return None

    # ============================================================
    # 第5步：读取接口（与现有系统100%兼容）
    # ============================================================
    def get_price(
        self,
        code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        adjust: str = "none"
    ) -> pd.DataFrame:
        """
        读取行情数据 - 与现有系统 100% 兼容

        参数:
            code:       股票代码 "600519"
            start_date: 起始日期 "2026-01-01"（含）
            end_date:   结束日期 "2026-03-27"（含）
            adjust:     复权类型 "none" / "qfq" / "hfq"

        返回:
            DataFrame，列: [date, open, high, low, close, volume, amount, turnover]
            按 date 升序排列
            如果无数据返回空 DataFrame

        用法示例:
            db = 笨数据库()
            df = db.get_price("600519", "2026-01-01", "2026-03-27")
        """
        query = "SELECT trade_date, open, high, low, close, volume, amount, turnover, pct_chg FROM daily_price WHERE 1=1"
        params = []

        if code:
            query += " AND code = ?"
            params.append(code)
        if start_date:
            query += " AND trade_date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND trade_date <= ?"
            params.append(end_date)

        query += " ORDER BY trade_date ASC"

        conn = sqlite3.connect(self.db_path)
        try:
            df = pd.read_sql_query(query, conn, params=params)
        finally:
            conn.close()

        if len(df) == 0:
            return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume", "amount", "turn", "pctChg"])

        # 列名 trade_date -> date，turnover -> turn，pct_chg -> pctChg（兼容现有系统）
        df = df.rename(columns={"trade_date": "date", "turnover": "turn", "pct_chg": "pctChg"})

        # 关键：强制 numeric 类型（SQLite 默认返回 object/str）
        for col in ["open", "high", "low", "close", "volume", "amount", "turn", "pctChg"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # 确保列顺序
        return df[["date", "open", "high", "low", "close", "volume", "amount", "turn", "pctChg"]]

    def get_stock_name(self, code: str) -> str:
        """获取股票名称，不存在返回空字符串"""
        row = self._query_one("SELECT name FROM stocks WHERE code = ?", (code,))
        return row if row else ""

    def get_all_codes(self) -> List[str]:
        """获取所有股票代码列表"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT code FROM stocks ORDER BY code")
        codes = [r[0] for r in c.fetchall()]
        conn.close()
        return codes

    def get_latest_date(self, code: str) -> Optional[str]:
        """获取某只股票的最新交易日期"""
        return self._query_one("SELECT MAX(trade_date) FROM daily_price WHERE code = ?", (code,))

    def get_db_stats(self) -> dict:
        """获取数据库统计信息"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        stock_count = c.execute("SELECT COUNT(*) FROM stocks").fetchone()[0]
        price_count = c.execute("SELECT COUNT(*) FROM daily_price").fetchone()[0]
        stock_with_data = c.execute("SELECT COUNT(DISTINCT code) FROM daily_price").fetchone()[0]
        date_min = c.execute("SELECT MIN(trade_date) FROM daily_price").fetchone()[0]
        date_max = c.execute("SELECT MAX(trade_date) FROM daily_price").fetchone()[0]

        conn.close()

        return {
            "股票总数": stock_count,
            "行情记录数": price_count,
            "有数据的股票数": stock_with_data,
            "最早日期": date_min or "无",
            "最新日期": date_max or "无",
            "文件大小": f"{os.path.getsize(self.db_path) / 1024 / 1024:.1f} MB" if os.path.exists(self.db_path) else "0 MB",
        }

    # ============================================================
    # 内部工具
    # ============================================================
    def _query_one(self, sql: str, params=()):
        """执行查询返回单个值"""
        conn = sqlite3.connect(self.db_path)
        try:
            c = conn.cursor()
            c.execute(sql, params)
            row = c.fetchone()
            return row[0] if row else None
        finally:
            conn.close()

    def __del__(self):
        """析构时关闭 baostock 会话"""
        self._close_bs()


# ================================================================
# 命令行入口
# ================================================================
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        logger.info("%s", "=" * 50)
        logger.info("笨数据库 - A股本地量化数据库")
        logger.info("%s", "=" * 50)
        logger.info("%s", )
        logger.info("用法:")
        logger.info("python 笨数据库.py init    - 初始化5年历史数据（首次运行）")
        logger.info("python 笨数据库.py update  - 每日增量更新")
        logger.info("python 笨数据库.py read    - 读取数据演示")
        logger.info("python 笨数据库.py stats   - 查看数据库统计")
        logger.info("%s", )
        sys.exit(0)

    mode = sys.argv[1]

    if mode == "init":
        years = int(sys.argv[2]) if len(sys.argv) > 2 else HISTORY_YEARS
        db = 笨数据库()
        db.初始化历史数据(years=years)

    elif mode == "update":
        db = 笨数据库()
        db.每日增量更新()

    elif mode == "read":
        db = 笨数据库()
        logger.info("%s", "\n" + "=" * 50)
        logger.info("数据读取演示")
        logger.info("%s", "=" * 50)

        # 1. 读取单只股票
        logger.info("--- 读取 600519 贵州茅台 ---")
        df = db.get_price("600519", start_date="2026-03-01", end_date="2026-03-27")
        name = db.get_stock_name("600519")
        logger.info("  %s (%s 条)", name, len(df))
        if len(df) > 0:
            logger.info("  列名: %s", list(df.columns))
            logger.info("  数据类型: %s", dict(df.dtypes))
            logger.info("%s", df.head(3).to_string(index=False))

        # 2. 读取多只
        logger.info("--- 批量读取 ---")
        for c in ["000858", "601318", "300750"]:
            d = db.get_price(c, start_date="2026-03-20", end_date="2026-03-27")
            n = db.get_stock_name(c)
            logger.info("  %s %s: %s 条, 最新 %s", c, n, len(d), db.get_latest_date(c))

        # 3. 统计
        logger.info("--- 数据库统计 ---")
        stats = db.get_db_stats()
        for k, v in stats.items():
            logger.info("  %s: %s", k, v)

    elif mode == "stats":
        db = 笨数据库()
        stats = db.get_db_stats()
        logger.info("%s", "=" * 40)
        logger.info("数据库统计")
        logger.info("%s", "=" * 40)
        for k, v in stats.items():
            logger.info("  %s: %s", k, v)

    else:
        logger.info("未知命令: %s", mode)
        logger.info("可用命令: init / update / read / stats")