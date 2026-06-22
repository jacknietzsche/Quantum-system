# AShare-X — 项目设计文档

> **文档版本**: v2.3  
> **日期**: 2026-06-13  
> **定位**: 个人使用的AI专业投资系统，专注于A股市场  
> **核心目标**: AI像极其专业的投资人一样工作，用户直接使用交易计划进行真实投资  
> **约束**: 纯API调用（不本地部署LLM），仅使用免费数据源，零额外成本运行

## 项目概述

AShare-X 是一个多Agent协作的A股智能投研系统。12个专业Agent（分析师→研究员→交易员→风险团队→组合经理）模拟真实投资机构的决策流程，通过多空辩论和三方风险辩论，最终输出可直接执行的交易计划（入场价/止损/止盈/仓位）。

## 技术栈

| 层级 | 组件 | 选择 |
|------|------|------|
| 后端 | Python 3.10+ / FastAPI | 异步框架 |
| 工作流 | LangGraph | 状态机编排 |
| LLM | DeepSeek API | deepseek-chat免费500万token/天 |
| 数据库 | SQLite + SQLAlchemy 2.0 | 零配置 |
| 前端 | React 18 + TypeScript + Vite + Tailwind | 现代前端 |
| 可视化 | ReactFlow + Recharts + lightweight-charts | Agent流程图+K线 |
| 桌面 | Electron | 桌面应用壳（与前端同栈 Node.js，渲染一致性最佳） |
| 数据源 | AKShare / BaoStock / 腾讯 / 新浪 / 东方财富 | 全部免费 |

## 快速入门

1. **阅读顺序**: S1(问题) → S2(理念) → S3(架构) → S4(Agent) → S5(数据) → S6(工作流)
2. **核心模块**: S4(Agent体系) + S5(数据层) + S10(前端) + S14(API) + S15(LLM层)
3. **参考项目**: S13 列出了19个开源项目和5篇论文

## 模块索引

| 模块 | 文件 | 内容摘要 |
|------|------|----------|
| S1 | [S01-problem-definition.md](./S01-problem-definition.md) | 现有系统6个核心缺陷 + 19个参考项目对比 |
| S2 | [S02-design-philosophy.md](./S02-design-philosophy.md) | 8条设计哲学 + 6条硬性约束 |
| S3 | [S03-system-architecture.md](./S03-system-architecture.md) | 6层架构 + 目录结构 + 配置Schema + 环境变量覆盖 + CLI工具 + 输出语言 + 测试 + 日志 + 部署 |
| S4 | [S04-agent-system.md](./S04-agent-system.md) | 12个核心Agent + 7个可选大师 + 24个设计模式 + 数据契约 + 错误分层 |
| S5 | [S05-data-layer.md](./S05-data-layer.md) | 断路器/重试/连接池 + 15张SQLite表 + 10个适配器 + ~2500行可复用代码 |
| S6 | [S06-workflow-engine.md](./S06-workflow-engine.md) | LangGraph工作流 + 并行执行 + 条件路由 + 检查点 + 超时 + 进度推送 + 快速模式 + Graph可视化 + 多Ticker批处理 |
| S7 | [S07-skill-system.md](./S07-skill-system.md) | SKILL.md格式规范 + SkillEngine发现/加载/注入 + Agent绑定关系 |
| S8 | [S08-risk-management.md](./S08-risk-management.md) | 三层风险体系 + 交易计划schema + A股Broker模拟 + 回测引擎 |
| S9 | [S09-memory-learning.md](./S09-memory-learning.md) | 决策日志 + 反思引擎 + 长期记忆注入 + 记忆轮转 |
| S10 | [S10-frontend.md](./S10-frontend.md) | ReactFlow Agent可视化 + SSE实时推送 + 辩论抽屉 + 14个组件 + 暗色模式 |
| S11 | [S11-tech-stack.md](./S11-tech-stack.md) | 免费技术栈 + DeepSeek/Qwen/GLM API方案 + 零成本估算 |
| S12 | [S12-roadmap.md](./S12-roadmap.md) | 5阶段9周实施计划 + 5个里程碑 |
| S13 | [S13-references.md](./S13-references.md) | 19个开源项目 + 5篇论文 + 9个本地可复用资源 |
| S14 | [S14-api-design.md](./S14-api-design.md) | REST端点清单 + 请求/响应Schema + SSE事件类型 + 错误码体系 |
| S15 | [S15-llm-layer.md](./S15-llm-layer.md) | LLMClient + Provider分组(OpenAI兼容) + 懒加载 + Agent级模型路由 + 结构化输出 + Token计数 + 自动默认值 |

## 模块依赖关系

```
S1(问题定义) → S2(设计理念) → S3(系统架构)
                                │
                    ┌───────────┼───────────┐
                    │           │           │
                    ▼           ▼           ▼
              S4(Agent体系)  S5(数据层)  S10(前端)
              ↑   ↑  │         │   ↑        ↑
              │   │  │         │   │        │
           S7(Skill) │      S8(风险)   S14(API)
              │      │         │         ↑
              │      ▼         │         │
              │   S15(LLM层)   │    S6(工作流)
              │      │         │     ↑   ↑   ↑
              │      └────┬────┘     │   │   │
              │           │          │   │   │
              │      S9(记忆学习)────┘   │   │
              │                          │   │
              └──────────────────────────┘   │
                                             │
                    S11(技术栈) ←── 全部模块
                    S12(路线图) ←── 全部模块
                    S13(参考) ──→ 全部模块
```

**关键依赖说明**:
- S15(LLM层) → S4(Agent): 所有Agent通过LLMClient调用LLM
- S4(Agent) → S6(工作流): Agent定义被工作流编排
- S5(数据) → S6(工作流): 数据层为工作流提供工具
- S7(Skill) → S4(Agent): Skill注入到Agent的prompt中
- S8(风险) → S5(数据): 风险计算依赖数据层
- S9(记忆) → S6(工作流): 记忆在工作流执行前后读写
- S10(前端) → S14(API): 前端通过API端点获取数据
- S14(API) → S6(工作流): API层调用工作流执行分析
- S6(工作流) → S15(LLM层): 工作流节点通过LLMClient调用LLM

---

*本文档随设计迭代同步更新。修改任意模块文件后，需同步更新本索引的模块摘要。*
