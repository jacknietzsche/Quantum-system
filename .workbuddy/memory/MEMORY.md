# 量化系统项目 - 长期记忆

> 完整架构详情见 ARCHITECTURE.md

## 项目概况
- **位置**: c:\Users\21471\WorkBuddy\quant system
- **架构**: v15 统一架构（core/ 包）
- **数据源**: baostock + akshare/efinance/新浪HTTP/腾讯HTTP（五层fallback）+ 本地SQLite
- **入口**: run_v15_full.py | run_v15_local.py | run_portfolio_v2.py | dashboard_v15.py
- **核心模块**: core/ (config/data/strategy/risk/report/engine)

## 评分体系 (V15Scorer)
- 基础因子(40%): MACD, RSI, 布林带等9因子
- 增强因子(25%): 假突破+动量+K线+VWAP+学术因子(IC +5.8%)
- 市场环境(10%): 北向资金+融资融券+资金流+板块强度
- 因子引擎V2(25%): 51个日频因子(动量/量价/资金流/波动率/情绪/微观结构/反转)
- 防顶过滤: 10因子见顶风险评估
- **行为金融学+经典多因子(21%)**: CGO/VNSP/CDE/ΔDE + 动量/反转 + 质量/低波 (新增8因子)

## 数据系统
- 五层fallback + 会话崩溃重建 + 指数退避重试 + 24h缓存
- **指数基金过滤**: 排除sz.9xxxxx格式的指数基金代码（腾讯API限制）
- 本地SQLite: 53K股票, 564万行情, 2GB (local_db/)
- 分析范围: ~4300只（排除ST/科创/高价/次新/指数基金）

## 代码质量状态 (2026-04-29)

### Phase 1 ✅ 完成
- **裸except修复**: 22处全部修复为 `except Exception`
- 核心模块异常吞噬处理完成

### Phase 2 ✅ 完成
- **logger f-string优化**: 234处已转换 (core/ 119处 + factors/ 25处 + backtest/ 90处)
- 剩余45处为复杂表达式（字典访问/函数调用/百分比格式化），保留f-string是合理用法

### Phase 3 ⚠️ 部分完成
- **语法检查**: core/ + factors/ 全部通过 ✅
- **docstring检查**: core/ + factors/ 模块docstring齐全 ✅
- **超长函数拆分**: 发现20个>80行函数，但属于核心业务逻辑，高风险重构需谨慎
- **重复代码**: V15Scorer.score与V16Scorer.score是正常的OOP子类重写，非重复

## 关键配置
- 默认workers=8, request_delay=0.08s, cache_hours=24
- 每日自动化: 21:00运行选股+调仓+整合报告
- 报告: daily_reports_v15_*/ | daily_reports_combined/

## 待办/提醒
- 技能安装目录: C:\Users\21471\.workbuddy\skills

## 变更记录
- **2026-04-29**: Phase 1-2代码审查完成 - 22处裸except修复，234处logger f-string优化，语法检查全通过，综合评分3.7/5.0
- **2026-04-29**: Phase 1代码修复完成 - 22处裸except全部修复(.gitignore/factors/__init__.py已创建)，Code Review标准文档已建立(CODE_REVIEW_STANDARD.md)，综合评分从3.1→3.5
- **2026-04-07**: 行为金融学+经典多因子集成完成 - 创建behavioral_classic_factors.py模块(CGO/VNSP/CDE/ΔDE/动量/反转/质量/低波)，修复factor_engine_v2.py中的导入缩进错误，更新权重配置(behavioral_classic占21%)，创建全因子回测脚本backtest_quantstats_all_factors.py
- **2026-04-06**: 文件整理 - 删除42个过时文件(7个quantstats_*.py + 7个run_*.py + 7个backtest_*.py + 5个test_*.py + 7个其他脚本 + 5个HTML报告 + daily_reports_v14目录 + 3个README)，保留v15最新系统
- **2026-04-05**: v15本地数据回测完成 - 本地SQLite(53K股/564万行情)+V15Scorer+Backtrader，30只等权重，2025-01~2026-03，总收益21.42%，年化16.93%，夏普1.16，回撤14.64%
- **2026-04-01**: 架构整理 - 创建 ARCHITECTURE.md, 删除 ~30个冗余文件, 迁移 local_db_adapter 到 core/, 删除 quant_system/pg_stock_db/笨数据库 目录, 更新 CLAUDE.md
- **2026-03-31**: 本地数据库量化系统 + 代码审查
- **2026-03-30**: 性能优化（workers 3→8, 批量并行化, 缓存优化）
- **2026-03-27**: 持仓管理修复5个Bug + Streamlit仪表盘 + 系统检查
- **2026-03-26**: 因子引擎V2 + 防顶因子 + 处置效应因子
- **2026-03-25**: 学术因子集成 + pct_change修复
