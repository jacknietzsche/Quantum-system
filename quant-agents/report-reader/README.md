# Report Reader（报告解读）

> 30 分钟带着 AI 读完一份财报——非财务背景投资者的实操手册，封装成可复用的 AI Skill。

## 它是什么

Report Reader 是一个 AI Skill，输入公司名称或年报 PDF，自动完成四轮递进式财报解读，输出结构化 Markdown 报告和可视化信息图 PNG。

**核心能力：**

- 🔍 **业务画像**：搞懂公司靠什么赚钱——产品结构、渠道分布、毛利率分析
- 📊 **财务三表拆解**：利润表、资产负债表、现金流量表的关键信号提取
- 🗣️ **管理层信号**：从 MD&A 措辞变化中读出管理层没说出口的话
- 📈 **研报交叉验证**（可选）：对比券商研报与年报数据，发现选择性偏差
- 🎨 **可视化信息图**：自动生成专业级财报速查卡 PNG

## 适用场景

- 非财务背景投资者快速了解一家公司
- 投资前的尽调初筛
- 跟踪持仓公司的季度/年度变化
- 验证券商研报结论的可靠性

## 目录结构

```
report-reader/
├── SKILL.md                          # Skill 主文件（角色 + 规则 + 工作流程）
├── README.md                         # 本文件
├── package.json                      # Node.js 依赖（Playwright）
├── config.yaml                       # 可配置参数
├── assets/
│   ├── capture.js                    # HTML → PNG 截图脚本
│   ├── infograph_template.html       # 信息图 HTML 模板
│   └── logo.png                      # Footer logo
└── references/
    ├── round-prompts.md              # 四轮递进式 prompt 模板
    ├── infograph-guide.md            # 信息图设计规范
    └── data-checklist.md             # 数据核对清单 + 防幻觉指南
```

## 工作流程

```
输入：公司名称 / 年报 PDF
  │
  ├─ Step 0：准备（下载年报 PDF / 安装依赖）
  │
  ├─ Step 1：业务理解（5 分钟）
  │   → 公司靠什么赚钱？各业务线收入、占比、增速、毛利率
  │
  ├─ Step 2：财务三表拆解（15 分钟）
  │   → 利润表：赚钱效率变化
  │   → 资产负债表：有没有雷
  │   → 现金流量表：利润真假
  │
  ├─ Step 3：管理层话语分析（5 分钟）
  │   → MD&A 措辞变化、经营目标、风险信号
  │
  ├─ Step 4：研报交叉验证（可选，5 分钟）
  │   → 研报结论 vs 年报数据
  │
  ├─ Step 5：生成可视化信息图
  │   → HTML 模板 + Playwright 截图 → PNG
  │
  └─ Step 6：输出交付
      → {公司名}_财报解读.md + {公司名}_财报解读.png
```

## 安装

### 1. 克隆到 Skill 目录

```bash
git clone https://github.com/{your-username}/report-reader.git
```

将 `report-reader/` 目录放入你的 AI 工具的 skill 目录中（如 Claude Code 的 `~/.claude/skills/`）。

### 2. 安装依赖

```bash
cd report-reader
npm install
npx playwright install chromium
```

## 使用方式

### 方式一：上传年报 PDF

直接上传年报 PDF 文件，然后触发 skill：

> 帮我解读这份财报

### 方式二：只提供公司名称

> 解读贵州茅台的财报

Skill 会自动通过联网搜索下载最新年报 PDF。

### 触发词

`解读财报`、`分析年报`、`读财报`、`年报解读`、`报告解读`

## 输出示例

以贵州茅台 2024 年报为例，输出包含：

**Markdown 报告**（约 3000 字）：
- 业务画像：茅台酒收入 1,459 亿（占比 85.5%），毛利率 94.06%
- 财务健康度：营收 +15.71%，净利润 +15.38%，现金流/净利润 107.2%
- 管理层信号：2025 年目标降至 9%，「三期叠加」措辞新增
- 关键预警：合同负债 -32%，销售费用增速超收入增速

**信息图 PNG**（1080×auto）：
- 4 个核心指标卡片（营收、净利润、毛利率、ROE）
- 业务结构可视化（产品占比条形图 + 渠道对比）
- 5 条关键信号（绿色=正面，红色=预警）
- 2025 年目标深色卡片

## 设计原则

1. **数据溯源**：每个关键数字标注年报页码，30 秒可回原文核对
2. **逐轮推进**：四轮有严格先后依赖，不跳步，不一次性扔所有问题
3. **术语人话**：财务术语用一句大白话解释，面向非专业投资者
4. **区分事实与判断**：数字是事实，趋势判断是分析，明确标注
5. **信息图是摘要**：只放最关键发现，不是报告全文的可视化

## 技术栈

| 组件 | 技术 |
|------|------|
| 信息图模板 | HTML + 内联 CSS + SVG 滤镜 |
| 截图引擎 | Playwright (Chromium headless) |
| 字体 | Google Fonts (DM Serif Display + DM Sans) |
| 输出格式 | Markdown (.md) + PNG |

## 配置

编辑 `config.yaml` 可调整：

```yaml
# 输出目录
output_dir: "~/Downloads/"

# 信息图默认色调（沉思/锐利/温暖/技术/科研/创意/商业/默认）
default_tone: "商业"

# 信息图默认密度（稀/中/密）
default_density: "中"

# 信息图宽度（px）
infograph_width: 1080
```

## 致谢

- 可视化机制参照 [ljg-card](https://github.com/lijigang/ljg-card) 的 HTML 模板 + Playwright 截图方案
- 财报解读方法论参考「30 分钟带着 AI 读完一份财报」实操手册

## License

MIT
