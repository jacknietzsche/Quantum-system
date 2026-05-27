#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_backtest.py — 运行量化策略回测
"""

import sys

from backtest.backtest_comprehensive_local import main

if __name__ == '__main__':
    # 手动设置参数
    sys.argv = [
        'run_backtest.py',
        '--start-date', '20210324',
        '--end-date', '20260409',
        '--initial-cash', '1000000'
    ]
    main()
