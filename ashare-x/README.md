# AShare-X

> 多 Agent 协作的 A 股智能投研系统 —— **全新重写版**
>
> 本项目是 `experiments/IMPLEMENTATION_PLAN.md` 描述的全新重写实现，与仓库内 `a-share-investment-system/` **并存且独立**（不 import、不共享数据）。设计依据见 `../project-design/`（S01–S15），实验数据见 `../experiments/`（含 exp14 真实定价）。

## 状态

- **Phase 1: 基础设施** — 进行中（core / db / providers）
- 后续 Phase 见 `../experiments/IMPLEMENTATION_PLAN.md` §二

## 快速开始

```bash
cd ashare-x
python -m venv .venv && .venv\Scripts\activate     # Windows
pip install -e ".[dev]"

cp .env.example .env                                # 填入 DEEPSEEK_API_KEY
pytest tests/unit/ -v                               # 运行单元测试
```

## 成本口径

预算按 **RMB 月成本**（exp14 实测，非旧 token 预算）：10 只/天 ≈ ¥46–74/月，默认预算 ¥100/月。详见 `../experiments/RESULTS.md` 实验14。

## 目录

见 `../experiments/IMPLEMENTATION_PLAN.md` §一。核心分层：
- `core/` — 配置、状态、LLM 客户端、异常、i18n
- `db/` — SQLAlchemy 引擎 + ORM + 迁移
- `providers/` — 数据源适配器（断路器 + 重试 + 连接池）+ 数据库优先数据总线
- `tools/` → `agents/` → `graph/` → `skills/` → `memory/` → `services/` → `api/` → `electron/`（后续 Phase）
