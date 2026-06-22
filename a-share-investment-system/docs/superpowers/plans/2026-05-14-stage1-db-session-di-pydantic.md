# Stage 1 修复计划: DB Session + DI + Pydantic

> **目标:** 解决3个P0致命缺陷 — DB Session泄漏、api/deps.py未使用、无Pydantic验证
> **策略:** 分5个Task逐文件推进，每Task独立可测试可提交

---

### Task 1: 创建共享 DB Session 上下文管理器

**文件:** 新建 `shared/db_session.py`

- [ ] **Step 1:** 创建 `shared/db_session.py`

```python
"""DB Session 上下文管理器 — 统一会话生命周期管理"""
from contextlib import contextmanager
from typing import Generator

from shared.models import get_session


@contextmanager
def db_session() -> Generator:
    """数据库会话上下文管理器 — 自动提交/回滚/关闭"""
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

- [ ] **Step 2:** 验证语法
```bash
cd "C:\Users\21471\WorkBuddy\Trading agent and skill\a-share-investment-system" && python -c "from shared.db_session import db_session; print('OK')"
```

### Task 2: 迁移 `api/routes/database.py` 使用上下文管理器

**文件:** `api/routes/database.py`

- [ ] **Step 1:** 在所有函数中将 `session = get_session()` / `session.close()` 替换为 `with db_session() as session:`
- [ ] **Step 2:** 将延迟导入 `from shared.models import ...` 全部移到文件顶部
- [ ] **Step 3:** 运行语法检查

### Task 3: 迁移 `api/routes/` 剩余文件

**文件:** `api/routes/analysis.py`, `reports.py`, `tasks.py`, `favorites.py`, `signals.py`, `system.py`

- [ ] **Step 1:** 逐个文件替换 session 模式
- [ ] **Step 2:** 移除多余的 try/except 包装层

### Task 4: 将 `api/deps.py` 注入路由

**文件:** `api/deps.py`, `api/routes/database.py`, `server.py`

- [ ] **Step 1:** 将 `api/deps.py` 的 `get_db()` 改为使用 `db_session` 上下文管理器
- [ ] **Step 2:** 在 `database.py` 路由中通过 `Depends(get_db)` 注入 DB session
- [ ] **Step 3:** 新增 `get_data_initializer()` DI 提供者

### Task 5: 添加 Pydantic 请求/响应模型

**文件:** 新建 `api/schemas/` 包 + 各路由

- [ ] **Step 1:** 创建 `api/schemas/__init__.py`
- [ ] **Step 2:** 创建 `api/schemas/database.py` — StockInfo/Refresh/Stats 模型
- [ ] **Step 3:** 在 `database.py` 路由中应用 `response_model`

---

## 验证清单

- [ ] `python -c "from shared.db_session import db_session; print('OK')"`
- [ ] `python -m pytest tests/unit/ -v --timeout=15 2>&1 | tail -20`
- [ ] Ruff lint: `ruff check api/routes/ shared/`
