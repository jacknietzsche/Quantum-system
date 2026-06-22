"""
实验3: AKShare数据获取验证
目标: 验证AKShare获取A股数据的可行性（财务数据/龙虎榜/北向资金）
"""
import pandas as pd
from datetime import datetime, timedelta

print("=" * 60)
print("实验3: AKShare数据获取验证")
print("=" * 60)

# ========== 实验3.1: 财务数据 ==========
print("\n" + "=" * 60)
print("实验3.1: AKShare财务数据获取")
print("=" * 60)

try:
    import akshare as ak

    # 获取贵州茅台财务数据
    df = ak.stock_financial_abstract_ths(symbol="600519", indicator="按报告期")
    print(f"财务数据: {len(df)} 条")
    print(f"列名: {list(df.columns)}")
    print(f"前3行:\n{df.head(3)}")
    print("✅ AKShare财务数据获取成功\n")
except Exception as e:
    print(f"❌ AKShare财务数据失败: {e}\n")

# ========== 实验3.2: 龙虎榜 ==========
print("=" * 60)
print("实验3.2: AKShare龙虎榜获取")
print("=" * 60)

try:
    import akshare as ak

    # 获取最近龙虎榜
    df = ak.stock_lhb_detail_em()
    print(f"龙虎榜数据: {len(df)} 条")
    print(f"列名: {list(df.columns)}")
    print(f"前3行:\n{df.head(3)}")
    print("✅ AKShare龙虎榜获取成功\n")
except Exception as e:
    print(f"❌ AKShare龙虎榜失败: {e}\n")

# ========== 实验3.3: 北向资金 ==========
print("=" * 60)
print("实验3.3: AKShare北向资金获取")
print("=" * 60)

try:
    import akshare as ak

    # 获取北向资金历史数据
    df = ak.stock_hsgt_north_net_flow_in_em(symbol="北向资金")
    print(f"北向资金数据: {len(df)} 条")
    print(f"列名: {list(df.columns)}")
    print(f"最近5天:\n{df.tail(5)}")
    print("✅ AKShare北向资金获取成功\n")
except Exception as e:
    print(f"❌ AKShare北向资金失败: {e}\n")

# ========== 实验3.4: 融资融券 ==========
print("=" * 60)
print("实验3.4: AKShare融资融券获取")
print("=" * 60)

try:
    import akshare as ak

    # 获取个股融资融券数据
    df = ak.stock_margin_detail_szse(date=datetime.now().strftime("%Y%m%d"))
    print(f"融资融券数据: {len(df)} 条")
    print(f"列名: {list(df.columns)}")
    print(f"前3行:\n{df.head(3)}")
    print("✅ AKShare融资融券获取成功\n")
except Exception as e:
    print(f"❌ AKShare融资融券失败: {e}\n")

# ========== 实验3.5: 指数数据 ==========
print("=" * 60)
print("实验3.5: AKShare指数数据获取")
print("=" * 60)

try:
    import akshare as ak

    # 获取上证指数日K线
    df = ak.stock_zh_index_daily(symbol="sh000001")
    print(f"上证指数数据: {len(df)} 条")
    print(f"列名: {list(df.columns)}")
    print(f"最近5天:\n{df.tail(5)}")
    print("✅ AKShare指数数据获取成功\n")
except Exception as e:
    print(f"❌ AKShare指数数据失败: {e}\n")

print("=" * 60)
print("实验3完成")
print("=" * 60)
