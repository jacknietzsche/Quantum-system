# 冗余文件清单

## 1. 备份文件

### 数据库备份文件
- `backtest/backup/a_stock_20260409_222808.db`
- `backtest/backup/a_stock_20260410_132300.db`
- `backtest/backup/a_stock_20260410_132313.db`
- `backtest/backup/a_stock_20260410_132731.db`

## 2. 日志文件

### 根目录日志文件
- `a_stock_db.log`

### logs目录日志文件
- `logs/backtest_comprehensive.log`
- `logs/v15_20260401_201400.log`
- `logs/v15_20260401_202814.log`
- `logs/v15_20260401_210240.log`
- `logs/v15_20260401_211556.log`
- `logs/v15_20260401_211912.log`
- `logs/v15_20260401_215604.log`
- `logs/v15_20260401_222423.log`
- `logs/v15_20260402_201300.log`
- `logs/v15_20260402_203703.log`
- `logs/v15_20260403_212349.log`
- `logs/v15_20260404_105509.log`

### backtest目录日志文件
- `backtest/a_stock_db.log`

## 3. 测试文件

### 根目录测试文件
- `test_large_dataset_performance.py`
- `test_performance_benchmark.py`
- `test_optimization_performance.py`
- `test_simple_performance.py`
- `test_backtest_performance.py`
- `test_performance.py`
- `test_env.py`
- `test_optimization.py`
- `test_strategy.py`
- `test_data_load.py`
- `test_db_connection.py`

### backtest目录测试文件
- `backtest/test_backtest.py`

### scripts目录测试文件
- `scripts/test_factor_engine_debug.py`
- `scripts/test_factor_engine.py`

### local_db目录测试文件
- `local_db/test_data_source.py`

## 4. 空文件夹

- `backtest_system/templates`
- `daily_reports_combined`
- `data_cache`
- `utils`

## 5. 临时文件和辅助脚本

- `find_duplicates.py` (临时脚本，用于识别重复文件)
- `find_empty_folders.py` (临时脚本，用于识别空文件夹)

## 6. 人工确认要求

在执行删除操作前，请确认以下事项：
1. 备份文件是否确实过时且不再需要
2. 日志文件是否包含重要信息
3. 测试文件是否仍在使用中
4. 空文件夹是否可能在未来被使用
5. 临时脚本是否可以安全删除

请在确认后执行删除操作。
