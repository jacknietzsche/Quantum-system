# 选股模块五项核心改进 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) to implement this plan task-by-task.

**Goal:** Upgrade stock screening module with multi-provider LLM routing, two-level analysis cache, config validation, tool calling enhancement, and comprehensive tests.

**Architecture:** Reuse existing infrastructure (CacheManager, CircuitBreaker, Config, DataBus, MasterAgentRegistry) to add five independent but synergistic improvements. Each is backward-compatible and independently testable.

**Tech Stack:** Python 3.11+, FastAPI, ThreadPoolExecutor, numpy (cosine similarity), existing CircuitBreaker/CacheManager.

---

## File Structure

### New Files
- `services/llm_router.py` — Multi-provider LLM router with health scoring, circuit breaker, cost-based task routing
- `services/stock_cache.py` — Two-level stock analysis cache (Level 1 exact + Level 2 semantic)

### Modified Files
- `services/hard_filter.py` — Config validation, dynamic regime-based thresholds, circuit breaker
- `services/agents/tool_registry.py` — Add get_financials / get_technical / get_sentiment tools
- `services/agents/stock_agent.py` — Enhanced ReAct agent using new data tools
- `config/config.yaml` — Add regime_overrides to hard_filters, add LLM tiers
- `services/trading_orchestrator.py` — Integrate LLM Router and cache

### Test Files
- `tests/unit/test_llm_router.py`
- `tests/unit/test_stock_cache.py`
- `tests/unit/test_hard_filter_config.py`
- `tests/unit/test_tool_registry.py`

---

## Implementation Tasks

### Task 1: LLM Router — Multi-Provider Intelligent Routing

**Files:**
- Create: `services/llm_router.py`
- Modify: `services/trading_orchestrator.py` (integrate router)
- Test: `tests/unit/test_llm_router.py`

### Task 2: Stock Analysis Cache — Two-Level Cache

**Files:**
- Create: `services/stock_cache.py`
- Test: `tests/unit/test_stock_cache.py`

### Task 3: HardFilter Config Validation + Dynamic Thresholds

**Files:**
- Modify: `services/hard_filter.py`
- Modify: `config/config.yaml` (add regime_overrides)
- Test: `tests/unit/test_hard_filter_config.py`

### Task 4: Tool Calling Enhancement — Data Tools for StockAgent

**Files:**
- Modify: `services/agents/tool_registry.py`
- Modify: `services/agents/stock_agent.py`

### Task 5: Comprehensive Tests

**Files:**
- Create: `tests/unit/test_llm_router.py`
- Create: `tests/unit/test_stock_cache.py`
- Create: `tests/unit/test_hard_filter_config.py`
- Create: `tests/unit/test_tool_registry.py`
