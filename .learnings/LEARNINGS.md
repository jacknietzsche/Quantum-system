## [ERR-20260331-001] run_v15_local.py analyze_stock 方法名大小写错误导致全量0分

**Logged**: 2026-03-31T17:05:00+08:00
**Priority**: high
**Status**: resolved
**Area**: backend

### Summary
`analyze_stock` 调用了 `self.db.get_price_For_factor()` (大写F)，正确方法名为 `get_price_for_factor()` (小写f)。Python 方法名区分大小写，导致全部 5316 只股票触发 AttributeError → 被 bare `except` 吞掉 → 返回 None → 0 只得分。

### Error
```
分析完成: 0只, 耗时0.0秒
```

### Context
- 首次写入文件时 write_to_file 传输过程中出现乱码（大段非代码字符注入），导致方法名被破坏为 `get_price_For_factor`
- bare `except: return None` 吞掉了所有异常，增加了调试难度

### Resolution
- **Resolved**: 2026-03-31T17:05:00+08:00
- **Notes**: 完全重写 run_v15_local.py，修正方法名为 `get_price_for_factor`。同时将 bare `except` 改为 `except Exception`，便于后续调试。

### Metadata
- Source: error
- Related Files: run_v15_local.py, quant_system/data/local_db_adapter.py
- Pattern-Key: harden.method_name_case
- Recurrence-Count: 1
- First-Seen: 2026-03-31
- Last-Seen: 2026-03-31

---

## [LRN-20260331-001] Python方法名大小写错误 + bare except 隐蔽性

**Logged**: 2026-03-31T17:05:00+08:00
**Priority**: high
**Status**: pending
**Area**: backend

### Summary
Python 方法名严格区分大小写。`obj.Method()` 和 `obj.method()` 是两个不同的调用。配合 bare `except: pass` 使用时，错误会被完全吞掉，极难排查。

### Details
- 错误调用: `self.db.get_price_For_factor()` (大写F)
- 正确调用: `self.db.get_price_for_factor()` (小写f)
- bare `except:` 会捕获包括 SystemExit/KeyboardInterrupt 在内的所有异常
- 建议始终用 `except Exception as e:` 并至少 log 一行

### Suggested Action
1. 代码中禁止 bare `except:`，统一使用 `except Exception as e:`
2. IDE 开启 pyflakes/flake8 的 `bare-except` 检查
3. 调试阶段可临时在 except 块中 `logger.debug(e)`

### Metadata
- Source: error
- Related Files: run_v15_local.py
- Tags: python, debugging, best_practice
- Pattern-Key: harden.bare_except

---

## [LRN-20260331-002] write_to_file 长文件传输可能出现乱码注入

**Logged**: 2026-03-31T17:05:00+08:00
**Priority**: medium
**Status**: pending
**Area**: infra

### Summary
通过 write_to_file 工具写入较长的 Python 文件时（含大量 HTML 模板字符串），传输过程中偶尔出现大段乱码字符注入到文件内容中，导致 SyntaxError 或方法名被破坏。

### Details
- 现象: 文件中出现大段非代码字符（如 `parameter`、`834nl533534` 等）
- 影响: SyntaxError、方法名被破坏、逻辑错误
- 发生场景: 长文件（>200行）+ 含 HTML/CSS 模板字符串

### Suggested Action
1. 对含大量 HTML 模板的 Python 文件，优先将模板放到单独文件中
2. 长文件写入后务必执行 `python -c "import ast; ast.parse(open('file.py').read())"` 语法检查
3. 写入后立即运行测试，不要延迟验证

### Metadata
- Source: error
- Related Files: run_v15_local.py
- Tags: tooling, file-writing, debugging
- Pattern-Key: harden.long_file_write

---

## [LRN-20260331-003] 专业量化选股报告的七大核心要素

**Logged**: 2026-03-31T17:05:00+08:00
**Priority**: low
**Status**: pending
**Area**: docs

### Summary
用户要求专业量化选股报告包含：策略逻辑、数据处理、因子体系、筛选条件、市场环境分析、结果展示、风险提示七大核心要素。推荐股票需包含购买理由和推荐仓位，最多5只。

### Details
已实现完整的七大板块 HTML 报告模板，包含：
1. 策略逻辑 - 四因子加权选股思路
2. 数据处理 - SQLite 本地数据库统计
3. 因子体系 - 动量/成交量/价格强度/波动率四因子
4. 筛选条件 - ST/科创板/次新/高价股过滤
5. 市场环境 - 股票总数/分析样本/符合条件/总仓位
6. 推荐列表 - Top5 股票含购买理由和仓位
7. 风险提示 - 五条专业风险声明

### Metadata
- Source: user_feedback
- Related Files: run_v15_local.py (generate_report方法)
- Tags: report, quant, best_practice

---

## [LRN-20260407-001] QuantStats生成专业量化回测报告

**Logged**: 2026-04-07T12:50:00+08:00
**Priority**: medium
**Status**: pending
**Area**: docs

### Summary
用户要求专业回测报告必须使用QuantStats库生成。QuantStats是专业的量化投资组合分析库，可生成包含完整风险指标、收益分析、Drawdown分析等专业内容的HTML报告。

### Details
QuantStats主要功能：
- 收益指标：总收益率、年化收益率、夏普比率、卡尔玛比率
- 风险指标：最大回撤、波动率、VaR/CVaR、索提诺比率
- 盈利统计：胜率、平均盈利/亏损、盈亏比
- 分布分析：偏度、峰度、直方图
- 月度收益表、最佳/最差月份

使用方式：
```python
import quantstats as qs
qs.reports.html(returns=returns, benchmark=None, output='report.html')
```

### Metadata
- Source: user_feedback
- Related Files: backtest_quantstats_large_cap.py, backtest_quantstats_full_factor.py
- Tags: quantstats, backtest, report
- Pattern-Key: best_practice.quantstats_report
