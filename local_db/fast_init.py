# -*- coding: utf-8 -*-
"""
快速初始化数据库 - 使用多进程并发下载
"""
import os
import sqlite3
import time
import multiprocessing as mp
from datetime import datetime, timedelta
from functools import partial

# 配置
DB_PATH = "a_stock.db"
LOG_FILE = "fast_init.log"
HISTORY_YEARS = 5
WORKERS = 8  # 并发数
REQUEST_DELAY = 0.02  # 请求间隔

# 数据源
DATA_SOURCES = ["akshare", "baostock", "efinance"]

# 日志
from core.logging_config import setup_logging, get_logger
setup_logging()
logger = get_logger(__name__)

NUMERIC_COLS = ["open", "high", "low", "close", "volume", "amount", "turnover", "pct_chg"]


def init_db():
    """创建数据库表"""
    conn = sqlite3.connect(DB_PATH)
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
    
    conn.commit()
    conn.close()
    logger.info(f"数据库初始化完成: {os.path.abspath(DB_PATH)}")


def get_stock_list():
    """获取股票列表"""
    import akshare as ak
    try:
        df = ak.stock_info_a_code_name()
        result = []
        for _, r in df.iterrows():
            code = str(r["code"]).zfill(6)
            name = str(r["name"])
            if "ST" in name or "退" in name:
                continue
            ex = "sh" if code.startswith(("6", "5")) else "sz"
            result.append((code, name, ex, None, None))
        
        # 保存股票列表
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM stocks")
        c.executemany(
            "INSERT OR REPLACE INTO stocks (code, name, exchange, list_date, delist_date) VALUES (?,?,?,?,?)",
            result
        )
        conn.commit()
        conn.close()
        
        logger.info(f"股票列表更新完成: {len(result)} 只")
        return [r[0] for r in result]
    except Exception as e:
        logger.error(f"获取股票列表失败: {e}")
        return []


def fetch_single_stock(code, start_date, end_date):
    """获取单只股票数据"""
    df = None
    
    for source in DATA_SOURCES:
        try:
            if source == "akshare":
                df = _fetch_akshare(code, start_date, end_date)
            elif source == "baostock":
                df = _fetch_baostock(code, start_date, end_date)
            elif source == "efinance":
                df = _fetch_efinance(code, start_date, end_date)
            
            if df is not None and len(df) > 0:
                break
        except Exception as e:
            logger.debug("data source fetch failed: %s", e)

    if df is None or len(df) == 0:
        return None
    
    # 标准化列名
    rename_map = {
        "日期": "trade_date", "股票代码": "code",
        "开盘": "open", "收盘": "close",
        "最高": "high", "最低": "low",
        "成交量": "volume", "成交额": "amount",
        "涨跌幅": "pct_chg", "换手率": "turnover",
    }
    df = df.rename(columns=rename_map)
    df["code"] = code
    
    # 检查必填列
    required = ["trade_date", "open", "high", "low", "close", "volume"]
    for col in required:
        if col not in df.columns:
            return None
    
    # 裁剪日期
    if "trade_date" in df.columns:
        import pandas as pd
        df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.strftime("%Y-%m-%d")
        df = df[(df["trade_date"] >= start_date) & (df["trade_date"] <= end_date)]
    
    if len(df) == 0:
        return None
    
    # 补算缺失字段
    import pandas as pd
    if "pct_chg" not in df.columns:
        df["pct_chg"] = df["close"].pct_change(fill_method=None) * 100
        df["pct_chg"] = df["pct_chg"].fillna(0.0)
    
    if "turnover" not in df.columns:
        df["turnover"] = df["amount"] / (df["close"] * 1e8) * 100
        df["turnover"] = df["turnover"].fillna(1.0).clip(0.01, 50.0)
    
    # 数据类型转换
    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    
    # 选择列
    cols = ["code", "trade_date", "open", "high", "low", "close", "volume", "amount", "turnover", "pct_chg"]
    df = df[[c for c in cols if c in df.columns]]
    
    # 去重
    df = df.drop_duplicates(subset=["code", "trade_date"], keep="last")
    
    return df


def _fetch_akshare(code, start_date, end_date):
    import akshare as ak
    symbol = f"sh{code}" if code.startswith(("6", "5")) else f"sz{code}"
    df = ak.stock_zh_a_hist(
        symbol=symbol,
        start_date=start_date.replace("-", ""),
        end_date=end_date.replace("-", ""),
        adjust="qfq",
    )
    return df


def _fetch_baostock(code, start_date, end_date):
    import baostock as bs
    prefix = "sh." if code.startswith(("6", "5")) else "sz."
    bs_code = prefix + code
    
    lg = bs.login()
    if lg.error_code != "0":
        return None
    
    rs = bs.query_history_k_data_plus(
        bs_code,
        "date,open,high,low,close,volume,amount,turn,pctChg",
        start_date=start_date,
        end_date=end_date,
        frequency="d",
        adjustflag="2",
    )
    
    rows = []
    while rs.next():
        row = rs.get_row_data()
        if row[0]:
            rows.append(row)
    
    bs.logout()
    
    if not rows:
        return None
    
    import pandas as pd
    return pd.DataFrame(rows, columns=[
        "trade_date", "open", "high", "low", "close",
        "volume", "amount", "turnover", "pct_chg"
    ])


def _fetch_efinance(code, start_date, end_date):
    import efinance as ef
    df = ef.stock.get_quote_history(code)
    return df


def worker(args):
    """工作进程"""
    code, start_date, end_date = args
    
    try:
        df = fetch_single_stock(code, start_date, end_date)
        if df is not None and len(df) > 0:
            # 保存到数据库
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            
            records = [
                (
                    row["code"], row["trade_date"],
                    float(row["open"]) if row["open"] is not None else None,
                    float(row["high"]) if row["high"] is not None else None,
                    float(row["low"]) if row["low"] is not None else None,
                    float(row["close"]) if row["close"] is not None else None,
                    float(row["volume"]) if row["volume"] is not None else None,
                    float(row["amount"]) if row["amount"] is not None else None,
                    float(row["turnover"]) if row.get("turnover") is not None else None,
                    float(row["pct_chg"]) if row.get("pct_chg") is not None else None,
                )
                for row in df.to_dict("records")
            ]
            
            c.executemany("""
                INSERT OR REPLACE INTO daily_price
                    (code, trade_date, open, high, low, close, volume, amount, turnover, pct_chg)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, records)
            conn.commit()
            conn.close()
            
            time.sleep(REQUEST_DELAY)
            return code, len(df)
    except Exception as e:
        pass
    
    return code, 0


def main():
    logger.info("=" * 50)
    logger.info("快速初始化数据库 - 5年历史数据")
    logger.info("=" * 50)
    
    # 初始化数据库
    init_db()
    
    # 获取股票列表
    codes = get_stock_list()
    if not codes:
        logger.error("无法获取股票列表")
        return
    
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=HISTORY_YEARS * 366)).strftime("%Y-%m-%d")
    
    logger.info(f"数据范围: {start_date} ~ {end_date}")
    logger.info(f"股票数量: {len(codes)}")
    logger.info(f"并发数: {WORKERS}")
    
    # 检查已存在的股票
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT code FROM daily_price GROUP BY code")
    existing = set(r[0] for r in c.fetchall())
    conn.close()
    
    # 过滤已存在的股票
    todo_codes = [c for c in codes if c not in existing]
    logger.info(f"需要下载: {len(todo_codes)} 只")
    
    if not todo_codes:
        logger.info("所有数据已存在!")
        return
    
    # 准备任务
    tasks = [(code, start_date, end_date) for code in todo_codes]
    
    # 并发下载
    start_time = time.time()
    success = 0
    fail = 0
    
    with mp.Pool(WORKERS) as pool:
        results = pool.map(worker, tasks)
        
        for code, count in results:
            if count > 0:
                success += 1
            else:
                fail += 1
            
            total = success + fail
            if total % 100 == 0 or total == len(tasks):
                elapsed = time.time() - start_time
                rate = total / elapsed * 60 if elapsed > 0 else 0
                logger.info(f"进度: {total}/{len(tasks)} (成功{success} 失败{fail}) - {rate:.0f}只/分钟")
    
    # 统计
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    stats = {
        "股票总数": c.execute("SELECT COUNT(*) FROM stocks").fetchone()[0],
        "行情记录": c.execute("SELECT COUNT(*) FROM daily_price").fetchone()[0],
        "有数据股票": c.execute("SELECT COUNT(DISTINCT code) FROM daily_price").fetchone()[0],
    }
    conn.close()
    
    logger.info("=" * 50)
    logger.info("初始化完成!")
    for k, v in stats.items():
        logger.info(f"  {k}: {v}")
    logger.info(f"总耗时: {time.time() - start_time:.1f}秒")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()