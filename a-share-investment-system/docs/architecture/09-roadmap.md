# 9. 开发路线图与任务拆分

> **注意**: 本文档已更新为实际状态。原始 5 Phase 计划大部分已跳过或部分完成。

**最后更新**: 2026-06-12

---

## 已完成

| 任务 | 状态 | 说明 |
|------|------|------|
| 数据源适配 | ✅ 完成 | 5 个稳定源（腾讯/东方财富/新浪/Baostock/AKShare） |
| 选股 Pipeline | ✅ 完成 | 4 阶段漏斗（hard_filter → master_analyze → deep_analyze → agent_workflow） |
| 17 位大师分析器 | ✅ 完成 | services/master_agents.py |
| AI 深度分析 | ✅ 完成 | 3 Agent（StockAgent/PortfolioAgent/DecisionAgent） |
| 风控引擎 | ✅ 完成 | VaR + 预警 + 集中度检查 |
| 交易计划生成 | ✅ 完成 | services/trading_plan.py |
| 前端 15 个页面 | ✅ 完成 | Dashboard/Screening/Portfolio/Analysis/Reports 等 |
| 22 个 API 端点 | ✅ 完成 | api/routes/ 下 22 个路由文件 |
| 17 个投资技能 | ✅ 完成 | skills/ 目录下 Prompt Skill |

---

## 待完善

| 任务 | 优先级 | 说明 |
|------|--------|------|
| 修复测试 import 错误 | P0 | 2 个测试文件 import 断裂 |
| 数据源 fallback 加固 | P1 | 主源超时自动切换备用源 |
| 风控引擎端到端验证 | P1 | 构造测试组合验证 VaR 计算 |
| 回测闭环验证 | P2 | 用历史数据验证选股有效性 |
| 数据缓存优化 | P2 | 同一天数据拉一次后缓存 |

---

## 未来演进方向（M7 认知架构）

> 以下任务将系统从"多因子打分器"升级为"具备持续学习能力的分析主体"。
> 详见 `docs/architecture/designs/M7-cognitive-architecture.md`。

### P0 — 核心认知能力（必须先做）

| 任务 | 说明 | 工时 |
|------|------|------|
| 反事实推理引擎 | 对每只候选股回答 3 个反事实问题，生成预警清单 | 3-5 天 |
| 概率化输出 | 从 strong_buy/buy/hold 改为概率分布 + 不对称比 | 5-7 天 |
| 决策-结果反馈数据库 | 记录每笔 AI 建议，5/10/20 日后自动验证 | 2-3 天 |

### P1 — 自我进化能力

| 任务 | 说明 | 工时 |
|------|------|------|
| 元 AI（Meta-Agent） | 每周分析决策日志，识别系统性失败模式 | 5-7 天 |
| 叙事引擎 | 持久化市场叙事 + 跨日演化 + 策略权重推导 | 7-10 天 |
| 动态大师调度 | 根据叙事选择性激活 3-5 位大师，而非 17 位全量 | 3-5 天 |

### P2 — 信息与风控增强

| 任务 | 说明 | 工时 |
|------|------|------|
| 主动信息检索 | AI 每日生成查询问题，检索新闻/互动易 | 3-5 天 |
| 微观结构信号 | 大小单资金流、融资融券、北向边际变化 | 5-7 天 |
| 动态仓位计算 | Kelly 公式 + 叙事调整 + 集中度调整 + 流动性调整 | 3-5 天 |
| 情景压力测试 | 流动性危机/风格反转/黑天鹅三种情景 | 3-5 天 |

---

## 不做（个人使用不需要）

| 任务 | 原因 |
|------|------|
| LangGraph Agent 编排 | 现有 workflows/nodes/ 够用 |
| Master-Specialist 5 Agent | 现有 3 Agent 够用 |
| Skill 执行引擎 | 现有 services/screening/ 够用 |
| models_v2 新表 | 现有 models.py 够用 |
| 多用户支持 | 个人使用 |
| 国际化 | 个人使用 |
| 移动端适配 | 个人使用 |
| 实盘交易对接 | 先把分析做准 |
| Electron 桌面版 | Web 版够用 |

---

## 原始 Phase 计划（仅供参考）

> 以下原始计划大部分已跳过，保留供参考。

### Phase 1: 基础框架（已跳过）

| 任务 | 状态 | 说明 |
|------|------|------|
| T1.1 搭建重构项目骨架 | ⏭️ 跳过 | 实际没做 backend/shared/ 重构 |
| T1.2 迁移数据源适配层 | ✅ 完成 | providers/ 利旧 |
| T1.3 精简 ORM 模型 | ⏭️ 跳过 | 保持现有 models.py |
| T1.4 Skill 执行引擎 | ⏭️ 跳过 | 无 SkillExecutor |
| T1.5 Skill 注册中心 | ⏭️ 跳过 | 无 SkillRegistry |

### Phase 2: 核心 Skill（部分完成）

| 任务 | 状态 | 说明 |
|------|------|------|
| T2.1 Data Skills | ✅ 完成 | providers/ 直接复用 |
| T2.2 P0-1 因子标准化 | ⏭️ 跳过 | 个人使用不需要 |
| T2.3 P0-2 因子定义标准化 | ⚠️ 部分 | factor_farm.py 有基础实现 |
| T2.4 P0-3 流动性过滤 | ✅ 完成 | hard_filter.py 已实现 |
| T2.5 P1-4 ICIR 加权 | ⏭️ 跳过 | 个人使用等权足够 |
| T2.6 P1-5 分风格推荐 | ✅ 完成 | 4 种风格已支持 |
| T2.7 Report Skills | ✅ 完成 | 报告生成已实现 |
| T2.8 Communication Skills | ✅ 完成 | 邮件发送已实现 |
| T2.9 Memory Skills | ⏭️ 跳过 | 无独立 Memory Skill |

### Phase 3: Agent 与工作流（部分完成）

| 任务 | 状态 | 说明 |
|------|------|------|
| T3.1 Master Agent | ⏭️ 跳过 | 无 Master Agent |
| T3.2 Market Agent | ⚠️ 部分 | market_perception.py 实现 |
| T3.3 Analyst Agent | ✅ 完成 | StockAgent 实现 |
| T3.4 Portfolio Agent | ✅ 完成 | PortfolioAgent 实现 |
| T3.5 Reflection Agent | ⏭️ 跳过 | 无 Reflection Agent |
| T3.6 Daily Workflow | ⚠️ 部分 | workflows/nodes/ 实现 |
| T3.7 Stock Deep Dive | ✅ 完成 | StockAgent 实现 |
| T3.8 Report+Email | ✅ 完成 | 报告+邮件已实现 |

### Phase 4: API + 前端（基本完成）

| 任务 | 状态 | 说明 |
|------|------|------|
| T4.1 FastAPI 路由 | ✅ 完成 | 22 个端点 |
| T4.2 SSE 流式推送 | ✅ 完成 | SSE 已实现 |
| T4.3 Vue 3 项目初始化 | ✅ 完成 | 前端已搭建 |
| T4.4 Chat 面板 | ✅ 完成 | 对话 UI 已实现 |
| T4.5 Dashboard 页面 | ✅ 完成 | Dashboard 已实现 |
| T4.6 Report 页面 | ✅ 完成 | 报告页面已实现 |
| T4.7 K 线图组件 | ✅ 完成 | ECharts 已集成 |
| T4.8 选股漏斗可视化 | ✅ 完成 | Screening 页面已实现 |
| T4.9 Portfolio 页面 | ✅ 完成 | 持仓页面已实现 |
| T4.10 Settings 页面 | ✅ 完成 | 设置页面已实现 |

### Phase 5: 测试与发布（未完成）

| 任务 | 状态 | 说明 |
|------|------|------|
| T5.1 单元测试 | ⚠️ 部分 | 1193 个测试，2 个文件有 import 错误 |
| T5.2 集成测试 | ⏭️ 跳过 | 未实现 |
| T5.3 前端冒烟测试 | ⏭️ 跳过 | 未实现 |
| T5.4 文档编写 | ⚠️ 部分 | 部分文档已写 |
| T5.5 快速回放验证 | ⏭️ 跳过 | 未实现 |
| T5.6 MVP 发布 | ⚠️ 部分 | 可运行但不完善 |

---

## 统计

| 类别 | 数量 |
|------|------|
| 已完成 | 15 |
| 部分完成 | 7 |
| 跳过 | 13 |
| 待完善 | 5 |

---

**返回**: [README.md](README.md)
