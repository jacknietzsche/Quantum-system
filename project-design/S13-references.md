# S13 — 参考项目与文献

## 13.1 开源项目参考

| 项目 | Stars | 核心贡献 | 我们借鉴 |
|------|-------|----------|----------|
| TradingAgents (TauricResearch) | — | 多Agent LLM交易框架 | 核心架构 |
| TradingAgents-AShare (KylinMountain) | 570 | A股15Agent系统 | A股Agent设计 |
| AI Hedge Fund (virattt) | — | 17位投资大师Agent | 大师视角层 |
| DeerFlow 2.0 (ByteDance) | — | 超级Agent框架 | 上下文工程+记忆 |
| Microsoft Qlib | 14,500+ | AI量化平台 | 数据管理+因子研究+Point-in-Time数据库(可选集成) |
| Microsoft RD-Agent | 3,500+ | LLM自动因子挖掘 | 自动alpha(可选) |
| FinRL (AI4Finance) | 15,404 | 金融强化学习 | DRL环境设计参考 |
| FinGPT (AI4Finance) | 20,479 | 开源金融LLM | 微调方法论参考 |
| FinRobot (AI4Finance) | 7,251 | LLM多Agent金融分析 | 控制器模式 |
| CrewAI | 30,000+ | 角色化多Agent编排 | 设计模式验证 |
| MetaGPT | 47,000+ | SOP驱动多Agent | 结构化输出 |
| Backtrader | 14,500 | 事件驱动回测 | A股broker模拟 |
| AgentOps | 4,000+ | Agent可观测性 | 成本追踪+审计 |
| AlphaForge (SJTU-Quant) | ~1,000 | LLM自动Alpha因子 | 因子生成范式 |
| je-suis-tm/quant-trading | 10,076 | 40+量化策略 | 策略模板库 |
| AKShare | 10,000+ | A股免费数据源 | 主数据源 |
| BaoStock | 2,000+ | 无限制A股历史数据 | 回测数据源 |
| vnpy (VeighNa) | 22,000+ | 量化交易系统框架 | 数据管理+因子库+ML模块 |
| RakshaQuant | 33 | LangGraph多Agent+反馈循环 | 反馈循环设计 |
| TradingGoose | 70 | 多Agent LLM交易 | 组合管理参考 |
| LangMem (LangChain) | — | Agent记忆管理工具 | 记忆提取+搜索+自动整合 |
| OpenViking (字节跳动) | 25,600+ | Agent上下文数据库 | 文件系统范式管理记忆/资源/Skill |
| AlphaAnalyst (kbhujbal) | 42 | 自主股权研究Agent | "LLM是写手不是知识库"+引用验证+纯Python估值+Devil's Advocate |

## 13.2 学术论文

| 论文 | 来源 | 贡献 |
|------|------|------|
| TradingAgents: Multi-Agents LLM Financial Trading Framework | arXiv:2412.20138 | 多Agent交易框架理论基础 |
| Trading-R1 | arXiv:2509.11420 | 推理增强交易模型 |
| R&D-Agent-Quant | arXiv:2505.15155 | LLM因子+模型联合优化，NeurIPS 2025 |
| FinRL | arXiv:2011.09607 | 金融强化学习框架 |
| FinRL-X | arXiv:2603.21330 | 下一代AI原生交易基础设施 |

## 13.3 本地已有资源

| 资源 | 路径 | 可复用内容 |
|------|------|-----------|
| TradingAgents核心 | quant-agents/TradingAgents/ | Agent定义、LangGraph工作流 |
| TradingAgents-AShare | quant-agents/TradingAgents-AShare/ | A股Agent、辩论机制 |
| AI Hedge Fund | quant-agents/ai-hedge-fund/ | 大师Agent实现 |
| Buffett Skills | quant-agents/buffett-skills/ | 巴菲特投资框架 |
| Munger Skill | quant-agents/munger-skill/ | 芒格思维模型 |
| Taleb Skill | quant-agents/taleb-skill/ | 塔勒布反脆弱框架 |
| China Stock Research | quant-agents/china-stock-research-skills/ | A股研究工作流 |
| A-Share Skills | quant-agents/a-share-skill/ | A股数据工具+技术指标 |
| 现有数据层 | a-share-investment-system/providers/ | 数据提供商实现 |
| 现有Skill引擎 | a-share-investment-system/services/skill_engine.py | Skill发现机制 |

---

**依赖**: 全部模块
**被依赖**: 全部模块
