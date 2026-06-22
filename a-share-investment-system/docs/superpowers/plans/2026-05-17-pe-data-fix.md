# PE数据修复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复PE数据获取链路，使数据库在数据填充时能正确获取并保存PE（市盈率）字段，覆盖率从当前 0.01% 提升至 >50%

**Architecture:** 通过调整适配器优先级 + 修改 SinaFinancialAdapter.fetch_basic 返回值逻辑，确保 TencentAdapter（唯一可靠的PE来源）能够优先被调用，不再被 SinaFinancialAdapter 短路

**Tech Stack:** Python, SQLite, AKShare, Tencent/新浪/东方财富 API

---

## 问题根因

| 数据源 | PE获取率 | 现状 |
|--------|---------|------|
| Tencent | 58% | ✅ 唯一可靠PE来源（part39=PE） |
| SinaFinancial | 0% | ✅ 返回财报不含PE，但优先级12短路了Tencent(17) |
| Sina | 0% | ✅ 无PE字段 |
| Baostock | 0% | ❌ 非交易日WinError 10057 |
| EastMoney | N/A | ❌ IP阻断（push2.eastmoney.com） |
| AKShare/EFinance | N/A | ❌ 断路器已断开 |

**核心问题**: `SinaFinancialAdapter` 优先级12高于 `TencentAdapter` 优先级17，`fetch_basic` 返回包含资产负债表数据的字典（无PE），被 `_try_one` 判定为"成功"并触发短路，导致后续所有适配器被跳过。

**备用机制也失效**: `_populate_one` 第641-653行有 fallback 逻辑（baostock/tushare），但 baostock 非交易日不可用，tushare 的 `fetch_basic` 不返回 PE。

---

## 实施步骤

### Task 1: 修改适配器优先级 — Tencent 优先

**Files:**
- Modify: `providers/sources/__init__.py:43-64`

- [ ] **Step 1: 读取当前注册顺序**

查看 `register_default_adapters` 函数中适配器注册顺序及优先级设置。

- [ ] **Step 2: 调整 TencentAdapter 优先级**

修改 `providers/sources/tencent.py` 第22行：
```python
# 旧
priority = 17
# 新
priority = 10
```

- [ ] **Step 3: 调整 SinaFinancialAdapter 优先级**

修改 `providers/sources/sina_financial.py` 第16行：
```python
# 旧
priority = 12  # After EastMoney(10), before Baostock(15)
# 新
priority = 30  # 降级，在Tencent(10)之后，只用于补充财报数据
```

调整后优先级顺序：
```
[10] Tencent (PE=20.18, 价格) ← 优先
[12] EastMoney (被阻断)
[15] Baostock (非交易日不可用)
[17] Tushare (无PE)
[25] Sina (无PE)
[30] SinaFinancial (财报, 无PE) ← 降级
[35] BoardRank
[45] ZTPool, LHB
[50] AKShare (断路器断开)
[60] EFinance (断路器断开)
```

- [ ] **Step 4: 验证注册顺序**

运行 `python -c "from providers.market_data import MarketDataProvider; p = MarketDataProvider(); print([a.name for a in p._adapters])"` 确认优先级已更新。

---

### Task 2: 修改 SinaFinancialAdapter.fetch_basic 返回值逻辑

**Files:**
- Modify: `providers/sources/sina_financial.py:98-125`

- [ ] **Step 1: 读取当前 fetch_basic 方法**

查看 `SinaFinancialAdapter.fetch_basic` 方法完整代码（大约第98-125行）。

- [ ] **Step 2: 修改返回值判断**

在 `fetch_basic()` 末尾添加判断：当返回的 dict 不含 `pe_ratio` 且不含 `latest_price` 时，返回 `None`（让链路继续尝试下一个适配器）。

```python
# 在 fetch_basic 末尾（约第124行），在 return result 之前添加：
# 只有当结果包含有意义的数据（PE或价格）时才返回
# 否则返回 None 让 MarketDataProvider 继续尝试其他适配器
has_pe = bool(result.get("pe_ratio") or result.get("peTTM"))
has_price = bool(result.get("latest_price") or result.get("price"))
has_name = bool(result.get("stock_name"))

if not (has_pe or has_price):
    # 没有PE也没有价格 → 只有财报数据 → 返回None让后续适配器处理
    # 因为当前 MarketDataProvider._try_sources 会在第一个非None返回值时短路
    return None

return result
```

**注意**：此修改会导致 SinaFinancial 的财报数据（current_assets, net_income 等）更难获取，作为 trade-off 可接受——PE 比财报更重要，且后续可通过其他方式补充财报数据。

---

### Task 3: 验证修复效果

**Files:**
- Test: `C:\Users\21471\AppData\Local\Temp\opencode\test_pe_comprehensive.py` (临时测试脚本)
- Create: `tests/unit/test_pe_population.py` (新测试文件)

- [ ] **Step 1: 运行临时测试验证**

执行之前的测试脚本确认 Tencent 被优先调用：
```bash
cd "C:\Users\21471\WorkBuddy\Trading agent and skill\a-share-investment-system"
python "C:\Users\21471\AppData\Local\Temp\opencode\test_pe_debug2.py"
```

预期结果：`Tencent 600519: pe=20.18` 出现在 `_try_sources` 的第一个成功位置（而不是被跳过）。

- [ ] **Step 2: 运行完整适配器测试**

执行：
```bash
python "C:\Users\21471\AppData\Local\Temp\opencode\test_pe_comprehensive.py"
```

预期结果：
- `MarketDataProvider._try_sources` 的 PE 获取率从 0% 提升至 >50%
- Tencent 在适配器列表中排第一

- [ ] **Step 3: 创建单元测试**

创建 `tests/unit/test_pe_population.py`：

```python
"""PE数据获取单元测试"""
import pytest
from unittest.mock import patch, MagicMock

class TestPEAdapterPriority:
    """测试适配器优先级确保 Tencent 优先"""

    def test_tencent_priority_before_sina_financial(self):
        from providers.market_data import MarketDataProvider
        p = MarketDataProvider()
        adapters = p._adapters
        tencent_idx = None
        sina_fin_idx = None
        for i, a in enumerate(adapters):
            if a.name == "tencent":
                tencent_idx = i
            if a.name == "sina_financial":
                sina_fin_idx = i
        assert tencent_idx is not None
        assert sina_fin_idx is not None
        assert tencent_idx < sina_fin_idx, f"Tencent({tencent_idx})应在SinaFinancial({sina_fin_idx})之前"

    def test_tencent_fetch_basic_returns_pe(self):
        from providers.sources.tencent import TencentAdapter
        ta = TencentAdapter()
        result = ta.fetch_basic("600519")
        assert result is not None
        assert result.get("pe_ratio") is not None
        assert result.get("pe_ratio") > 0

    def test_sina_financial_returns_none_without_pe(self):
        from providers.sources.sina_financial import SinaFinancialAdapter
        adapter = SinaFinancialAdapter()
        result = adapter.fetch_basic("600519")
        # 修复后应该返回None（无PE）让链路继续
        # 或者返回包含PE的数据
        if result is not None:
            has_pe = bool(result.get("pe_ratio") or result.get("peTTM"))
            has_price = bool(result.get("latest_price") or result.get("price"))
            assert has_pe or has_price, "SinaFinancial应在有PE/价格时返回，否则返回None"


class TestPEDataPopulation:
    """测试PE数据填充流程"""

    def test_save_stock_info_saves_pe(self):
        from services.data_initializer import DataInitializer
        di = DataInitializer()
        test_data = {
            "stock_code": "TEST001",
            "stock_name": "测试股票",
            "latest_price": 100.0,
            "pe_ratio": 25.5,
            "pb_ratio": 3.0,
        }
        di._save_stock_info("TEST001", test_data)
        # 验证已保存
        from shared.models import StockInfo, get_session
        session = get_session()
        info = session.query(StockInfo).filter_by(stock_code="TEST001").first()
        session.close()
        assert info is not None
        assert info.pe_ratio == 25.5

    def test_supplement_pe_only_when_zero(self):
        from services.data_initializer import DataInitializer
        di = DataInitializer()
        # 模拟已有PE值
        test_data = {"pe_ratio": 25.5, "industry": "白酒"}
        di._supplement_pe_industry("600519", test_data)
        # 验证原有PE未被覆盖（因为已经是25.5）
        from shared.models import StockInfo, get_session
        session = get_session()
        info = session.query(StockInfo).filter_by(stock_code="600519").first()
        session.close()
        if info and info.pe_ratio > 0:
            assert info.pe_ratio > 0, "原有PE不应被覆盖"
```

- [ ] **Step 4: 运行新增测试**

```bash
cd "C:\Users\21471\WorkBuddy\Trading agent and skill\a-share-investment-system"
pytest tests/unit/test_pe_population.py -v
```

预期结果：所有测试通过。

---

### Task 4: 运行数据库填充验证

**Files:**
- Modify: `data/investment.db` (数据库文件，不改代码)

- [ ] **Step 1: 检查当前数据库状态**

```python
import sqlite3
conn = sqlite3.connect('data/investment.db')
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM stock_info WHERE pe_ratio > 0')
print(f"PE>0: {cur.fetchone()[0]}/7857")
conn.close()
```

- [ ] **Step 2: 选择5只股票进行手动填充测试**

```python
from services.data_initializer import DataInitializer
di = DataInitializer()
# 测试 _populate_one 对几只股票的行为
for code in ['600519', '000001', '002594', '600036', '300750']:
    result = di._populate_one(code)
    print(f"{code}: has_data={result}")
```

- [ ] **Step 3: 验证数据库中PE被正确保存**

```python
import sqlite3
conn = sqlite3.connect('data/investment.db')
cur = conn.cursor()
for code in ['600519', '000001', '002594', '600036', '300750']:
    cur.execute('SELECT stock_code, stock_name, pe_ratio, latest_price FROM stock_info WHERE stock_code=?', (code,))
    r = cur.fetchone()
    print(f"{r[0]} {r[1]}: price={r[3]}, pe={r[2]}")
conn.close()
```

预期结果：这5只股票中大部分应有 PE > 0。

---

### Task 5: Lint 和类型检查

**Files:**
- Modify: 仅涉及修改的文件

- [ ] **Step 1: 运行 ruff 检查**

```bash
cd "C:\Users\21471\WorkBuddy\Trading agent and skill\a-share-investment-system"
ruff check providers/sources/__init__.py providers/sources/tencent.py providers/sources/sina_financial.py services/data_initializer.py
```

- [ ] **Step 2: 如有错误，运行自动修复**

```bash
ruff check providers/sources/__init__.py providers/sources/tencent.py providers/sources/sina_financial.py services/data_initializer.py --fix
```

---

## 修复后预期效果

| 指标 | 修复前 | 修复后 |
|------|--------|--------|
| 数据库 PE 覆盖率 | 0.01% (1/7857) | >50% |
| MarketDataProvider.get_stock_basic PE获取率 | 0% | >50% |
| TencentAdapter 调用优先级 | 第5（被短路） | 第1 |
| SinaFinancialAdapter 调用优先级 | 第2 | 第6（降级） |

---

## 备选方案（如优先级调整不足以解决问题）

**方案B**: 在 `providers/market_data.py` 的 `_try_one` 方法中增加"有意义数据"判断。当返回的 dict 不含 `pe_ratio` 且不含 `latest_price` 且不含 `stock_name` 时，视为"数据不足"继续尝试下一个适配器。

修改位置：`providers/market_data.py` 第203-230行 `_try_one` 方法。

```python
# 在 if result is not None: 之后添加判断
if result is not None:
    has_meaningful_data = (
        result.get("pe_ratio") or
        result.get("peTTM") or
        result.get("latest_price") or
        result.get("price") or
        result.get("stock_name")
    )
    if has_meaningful_data:
        adapter.cb.record_success()
        return result
    # 无有意义数据 → 不记录成功，继续尝试下一个适配器
```

---

## 执行顺序

1. Task 1（优先级调整）→ 验证 → Task 2（SinaFinancial修改）→ 验证 → Task 3（测试）→ Task 4（DB填充）→ Task 5（Lint）

**Plan complete and saved to `docs/superpowers/plans/2026-05-17-pe-data-fix.md`.**