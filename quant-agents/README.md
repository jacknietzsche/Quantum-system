# Quant Agents - A股量化交易智能体工作区

## 项目结构

| 项目 | 说明 | 来源 |
|------|------|------|
| a-share-investment-system | A股投资决策系统（核心项目） | 本地原创 |
| a-share-skill | A股数据/模拟盘/策略技能集 | GitHub |
| TradingAgents-CN | 交易智能体（中文版） | GitHub |
| TradingAgents-AShare | 交易智能体（A股版） | GitHub |
| TradingAgents | 交易智能体（原版） | GitHub |
| FinRobot | 金融AI机器人框架 | GitHub |
| QuantLLM | 量化LLM工具 | GitHub |
| RD-Agent | 微软研究智能体 | GitHub |
| ai-hedge-fund | AI对冲基金 | GitHub |
| daily_stock_analysis | 每日股票分析系统 | GitHub |
| buffett-skills | 巴菲特投资技能 | GitHub |
| munger-skill | 芒格投资思维技能 | GitHub |
| taleb-skill | 塔勒布投资哲学技能 | GitHub |
| china-stock-research-skills | 中国股票研究技能 | GitHub |
| qingfeng-skills | 清风技能集（可转债分析） | GitHub |
| report-reader | 研报阅读器技能 | GitHub |

## 版本控制说明

- 父仓库使用 **平铺式管理**，所有子项目代码纳入统一版本控制
- 各子项目保留独立 `.git` 仓库（可单独拉取上游更新）
- `.gitignore` 排除了缓存、日志、数据文件等无需版本控制的内容

## 常用命令

```bash
# 查看全局变更历史
git log --oneline

# 查看某个子项目的变更
git log --oneline -- a-share-investment-system/

# 查看某个文件的历史
git log --follow --oneline -- a-share-investment-system/config.json

# 提交新变更
git add -A && git commit -m "描述变更内容"

# 回滚某个文件到上一版本
git checkout HEAD~1 -- path/to/file

# 创建版本标签
git tag -a v1.0.0 -m "版本说明"
```
