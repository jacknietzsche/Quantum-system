# china-cb-analysis

中国可转债 AI 分析工具 - 通过集思录数据获取和 AI 决策分析，为用户提供可转债投资建议。

## 功能特点

- 📊 **实时数据获取**: 从集思录获取可转债实时数据、强赎数据、转股价格调整记录
- 🔍 **智能过滤**: 根据预设条件（价格、溢价率、余额等）自动过滤候选标的
- 🤖 **AI 决策**: 使用 Claude Code 内置的 MCP AI 工具进行深度分析，生成投资建议
- 📝 **报告输出**: 支持 JSON 和 Markdown 格式的分析报告

## 安装

```bash
pip install -r requirements.txt
```

## 配置

复制 `config.yaml` 并填写必要配置：

```yaml
# 集思录 Cookie (必填)
jsl_cookie: "your_cookie_here"

# AI 决策风格提示词 (可选)
# 默认策略：三低优化策略 - 低价、低溢价、低余额
# 其他可选策略：
#   - "稳健防守策略 - 侧重高 AAA 评级、低价格转债"
#   - "激进进攻策略 - 侧重高弹性、小余额转债"
#   - "平衡配置策略 - 兼顾安全性和收益性"
ai_strategy_prompt: ""

# 数据过滤条件 (可选)
filter:
  max_remaining_size: 50  # 最大剩余规模 (亿元)
  max_price: 150          # 最高转债价格 (元)
  max_premium_ratio: 50   # 最高溢价率 (%)
```

**注意：AI 配置已移除** - 使用 Claude Code 内置的 MCP AI 工具自动处理，无需手动配置 API Key。

### 获取集思录 Cookie

1. 登录 [集思录](https://www.jisilu.cn/)
2. 打开浏览器开发者工具 (F12)
3. 刷新页面，找到请求头中的 `Cookie`
4. 复制 Cookie 值填入配置

## 使用方法

### 命令行运行

```bash
# 运行完整分析
python -m skills.china_cb_analysis

# 指定输出文件
python -m skills.china_cb_analysis --output report/cb_analysis.json

# 使用严格过滤条件
python -m skills.china_cb_analysis --filter-strict

# 推荐 5 只标的
python -m skills.china_cb_analysis --top-n 5
```

### 代码调用

```python
from skills.china_cb_analysis import run_analysis

result = run_analysis(
    output_path="report.json",
    filter_strict=False,
    top_n=10
)
```

## 工作流程

```
1. 加载配置 → 2. 获取市场数据 → 3. 条件过滤 → 4. AI 分析 (MCP) → 5. 输出报告
```

### 过滤条件

默认过滤规则：
- 排除已公告强赎的转债
- 剩余规模 ≤ 50 亿
- 转债价格 ≤ 150 元
- 转股溢价率 ≤ 50%
- 排除正股 ST 的转债

严格模式 (`--filter-strict`):
- 剩余规模 ≤ 30 亿
- 转债价格 ≤ 120 元
- 转股溢价率 ≤ 30%

### AI 策略

默认采用 **"三低优化策略"**:
- **低价**: 关注转债价格较低，具有安全边际的标的
- **低溢价**: 关注转股溢价率较低，股性较强的标的
- **低余额**: 关注剩余规模较小，弹性较大的标的

可在配置中自定义策略提示词。

## 输出示例

```
============================================================
AI 分析报告
============================================================
【市场分析】
当前可转债市场整体估值处于...

【推荐标的】
1. 123456 XX 转债
   - 推荐理由：低价 + 低溢价，正股基本面良好
   - 风险提示：正股波动较大
   - 建议操作：逢低分批建仓

2. ...

【配置建议】
建议仓位 60-70%，分散配置 5-8 只标的...

【风险提示】
1. 市场系统性风险
2. 正股基本面变化
...
============================================================
```

## 依赖

- akshare: 金融数据获取
- pandas: 数据处理
- pyyaml: 配置解析

**AI 调用**: 使用 Claude Code 内置的 MCP AI 工具，无需额外配置。

## 风险提示

⚠️ 本工具仅供学习和研究使用，不构成投资建议。

可转债投资有风险，入市需谨慎。请根据自身风险承受能力，
独立判断，自主决策。
