#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试数据加载功能
"""

import sys
import os
from datetime import datetime

# 添加项目根目录到系统路径
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from backtest.backtest_comprehensive_local import load_local_data

if __name__ == '__main__':
    try:
        print("开始测试数据加载...")
        start_date = '20210324'
        end_date = '20260408'
        
        data_dict, benchmark = load_local_data(start_date, end_date)
        
        print(f"数据加载完成")
        print(f"股票数量: {len(data_dict)}")
        print(f"基准指数: {'沪深300' if benchmark is not None else '无'}")
        
        if data_dict:
            # 打印前5只股票的数据信息
            print("\n前5只股票数据信息:")
            for i, (code, df) in enumerate(list(data_dict.items())[:5]):
                print(f"股票 {code}:")
                print(f"  数据长度: {len(df)}")
                print(f"  列名: {list(df.columns)}")
                if not df.empty:
                    print(f"  最早日期: {df['date'].min()}")
                    print(f"  最晚日期: {df['date'].max()}")
                print()
        else:
            print("没有加载到任何股票数据")
            
    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()
