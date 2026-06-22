# AShare-X 优化计划

## 一、已完成的优化

### 1.1 数据源修复
- ✅ 移除 baostock 从 `_KNOWN_DEAD_SOURCES`（已恢复正常）
- ✅ TickFlow API key 已配置（需启动 Hiddify 代理）

### 1.2 风险引擎增强 (risk_engine.py)
- ✅ `assess_stock_risk()` - 个股风险评估（波动率/估值/流动性/财务）
- ✅ `calculate_var()` - VaR 计算（历史模拟法 + 参数法）
- ✅ `risk_alerts()` - 风险预警列表（止损/止盈/集中度/行业）
- ✅ `portfolio_var()` - 组合 VaR 计算

### 1.3 交易计划生成器 (trading_plan.py)
- ✅ 从 88 行数据模型 → 完整的 `TradingPlanGenerator` 类
- ✅ 即时订单生成（买入/卖出/加仓/减仓/持有）
- ✅ 条件订单生成（止损/止盈/突破买入）
- ✅ 仓位分配（Kelly 公式 + 等权混合）
- ✅ 监控信号生成
- ✅ 风控规则生成

### 1.4 组合优化器增强 (portfolio_optimizer.py)
- ✅ `kelly_position_sizing()` - Kelly 公式仓位计算
- ✅ `risk_budget_allocation()` - 风险平价分配

### 1.5 数据库修复
- ✅ 800 只股票名称修复（标记为 分级_/北交所_/LOF_ 等）

### 1.6 API 路由增强
- ✅ `risk.py` - 新增 5 个端点：/alerts, /assess-stock, /portfolio-var, /stress-test
- ✅ `screening.py` - 新增 2 个端点：/generate-plan, /daily-summary

### 1.7 日频分析流程增强
- ✅ `main.py daily` 命令增加交易计划生成
- ✅ 生成买入/卖出计划表格

### 1.8 前端增强
- ✅ Screening 页面增加交易计划板块
- ✅ 显示买入/卖出/条件单/监控信号
- ✅ Kelly 公式仓位建议表格
- ✅ 风控规则展示
- ✅ Dashboard 每日摘要卡片

### 1.9 选股器优化
- ✅ 优化数据过滤条件（PE > 0 且 PE < 200）
- ✅ 改进默认值计算（EPS/BVPS/GPM）

---

## 二、日频策略工作流

### 每日收盘后操作流程

```
1. python main.py daily
   ├── Kline 数据刷新
   ├── 市场感知（判断牛熊）
   ├── 全市场选股（Top 50）
   ├── 持仓分析（止损/止盈信号）
   ├── 交易计划生成（买入/卖出/仓位）
   └── 保存报告到 reports/daily_YYYYMMDD.json

2. 查看报告
   - 前端: http://localhost:8765 → Screening → Generate Plan
   - CLI: 查看 reports/ 目录下的 JSON 文件

3. 次日实操
   - 根据交易计划执行买入/卖出
   - 设置条件单（止损/止盈）
   - 记录交易到 Portfolio 页面
```

### 前端操作流程

```
1. 打开 http://localhost:8765
2. 进入 Dashboard 查看每日摘要和 Top Picks
3. 进入 Screening 页面
4. 点击 "RUN SCREEN" 运行选股
5. 选股完成后点击 "Generate Plan" 生成交易计划
6. 查看买入/卖出计划
7. 进入 Portfolio 页面记录实际交易
8. 每日查看 Dashboard 了解风险状态
```

---

## 三、用户行动计划（需要你完成）

### 3.1 知识库建设（增强 AI 分析深度）

**目标**: 让 AI 分析更专业，接近投资人水平

**需要做的**:
1. 收集高质量研报
   - 券商研报（中金/中信/国泰君安等）
   - 行业深度报告
   - 公司调研报告

2. 收集投资框架
   - 巴菲特价值投资框架
   - 格雷厄姆安全边际
   - 林奇成长投资
   - 塔勒布反脆弱

3. 创建知识库文件
   - 在 `skills/` 目录下创建知识文件
   - 格式: Markdown，包含投资原则和案例

### 3.2 Skill 蒸馏（增强 AI 技能）

**目标**: 创建专业分析技能

**需要做的**:
1. 基本面分析技能
   - 财务报表分析
   - 估值模型（DCF/PE/PB）
   - 行业分析框架

2. 技术面分析技能
   - K 线形态识别
   - 技术指标解读
   - 趋势判断

3. 情绪面分析技能
   - 市场情绪指标
   - 资金流向分析
   - 新闻情绪分析

4. 资金面分析技能
   - 北向资金
   - 主力资金
   - 融资融券

### 3.3 数据源增强

**目标**: 获取更多高质量数据

**需要做的**:
1. 新闻情绪数据
   - 接入财经新闻 API
   - 添加情绪分析

2. 资金流向数据
   - 接入北向资金数据
   - 接入主力资金数据

3. 机构数据
   - 接入机构持仓数据
   - 接入研报数据

### 3.4 代理配置（使 TickFlow 可用）

**目标**: 启用 TickFlow 数据源

**需要做的**:
1. 启动 Hiddify 代理（端口 12334）
2. 验证代理可用: `curl -x http://127.0.0.1:12334 https://api.tickflow.com/v1/market/spot?market=cn`

### 3.5 实盘交易（可选）

**目标**: 连接券商 API 进行实盘交易

**需要做的**:
1. 选择支持 API 的券商
2. 获取 API 密钥
3. 配置到 config/.env
4. 修改 trade_executor.py 对接券商 API

---

## 四、参考资源

### GitHub 项目
1. **FinRL** - 深度强化学习量化交易
2. **Qlib** - 微软量化投资平台
3. **Zipline/Backtrader** - 回测框架
4. **vnpy** - Python 量化交易框架
5. **ai-hedge-fund** - AI 对冲基金参考

### 前沿论文
1. **巴菲特投资策略**: 价值投资框架
2. **格雷厄姆安全边际**: 估值方法
3. **林奇成长投资**: 成长股选择
4. **塔勒布反脆弱**: 风险管理
5. **Kelly 公式**: 仓位管理

### 投行参考
1. **摩根士丹利**: 风险管理框架
2. **高盛**: 量化分析方法
3. **桥水**: 全天候策略

---

## 五、系统状态

### 当前数据
- 股票: 7,867 只
- K 线: 532,010 条（2023-09-15 ~ 2026-05-29）
- 因子: 35+ 个

### 可用数据源
- ✅ 腾讯 (0.2s)
- ✅ 东方财富 (0.5s)
- ✅ 新浪 (0.2s)
- ✅ Baostock (0.5s)
- ✅ akshare (~10s)
- ❌ TickFlow（需启动代理）

### LLM 提供商
- ✅ DeepSeek
- ✅ SiliconFlow
- ✅ ChatAnywhere
- ✅ Juguang
- ✅ Cherryin
- ✅ OpenRouter

---

## 六、系统功能清单

### 后端 (38 个服务模块)
- 7 位投资大师分析 (Buffett/Graham/Lynch/Taleb/Munger/Pabrai)
- 35+ 量化因子
- 4 阶段选股管线
- 7 方法风险引擎 (含 VaR/风险预警)
- Kelly 公式仓位管理
- 交易计划生成器
- 模拟交易 + Kill Switch

### 前端 (18 个页面)
- Dashboard: 市场概览 + 每日摘要 + Top Picks
- Screening: 分类选股 + 交易计划生成
- Portfolio: 持仓管理 + NAV 图表
- Analysis: 单股/批量分析
- Reports: 报告管理

### API (75+ 端点)
- `/api/screening/generate-plan` - 交易计划生成
- `/api/screening/daily-summary` - 每日摘要
- `/api/risk/alerts` - 风险预警
- `/api/risk/assess-stock` - 个股风险评估
- `/api/risk/portfolio-var` - 组合 VaR
