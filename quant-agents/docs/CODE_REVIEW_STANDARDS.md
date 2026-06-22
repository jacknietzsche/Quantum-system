# Quant Agents — 代码审查标准

> 本文档定义本仓库所有项目的代码审查标准。各子项目在此基础之上可追加项目特定的规则。

---

## 📖 目录

1. [审查总则](#1-审查总则)
2. [Python 编码标准](#2-python-编码标准)
3. [TypeScript / Vue 编码标准](#3-typescript--vue-编码标准)
4. [安全标准](#4-安全标准)
5. [性能标准](#5-性能标准)
6. [测试标准](#6-测试标准)
7. [数据与量化专属标准](#7-数据与量化专属标准)
8. [文档标准](#8-文档标准)

---

## 1. 审查总则

### 1.1 严重等级

| 标记 | 含义 | 处理要求 | 示例 |
|------|------|----------|------|
| 🔴 **Blocker** | 必须修复后才能合并 | 阻塞合并 | SQL注入、硬编码密钥、数据损坏风险 |
| 🟡 **Suggestion** | 应该修复，有合理理由可豁免 | 需说明理由 | 缺少类型注解、未抽离的重复代码 |
| 💭 **Nit** | 锦上添花，可改可不改 | 作者自行决定 | 变量命名微调、注释措辞优化 |

### 1.2 审查原则

1. **对事不对人** — 评论代码而非评论人
2. **说明为什么** — 不要只说"改成 X"，要说"改成 X 因为 Y"
3. **建议而非命令** — 用"建议""考虑"而非"必须"（除非是 Blocker）
4. **赞赏好代码** — 看到好的设计模式、巧妙的实现，指出来
5. **关注核心问题** — 安全 > 正确性 > 可维护性 > 性能 > 风格

### 1.3 审查时机

- **必须审查**：所有进入 `main` / `master` 的 PR
- **建议审查**：重构超过 200 行的变更、策略逻辑变更、核心模块变更
- **可跳过**：纯文档修正（typo）、配置值微调（无逻辑变更）

---

## 2. Python 编码标准

### 2.1 类型注解

**要求：公开 API 函数必须有完整类型注解，内部辅助函数渐进式补充。**

```python
# ✅ 好的：完整类型注解
def get_stock_quote(stock_code: str) -> Optional[Dict[str, Any]]:
    """获取单只股票实时行情。"""
    ...

# ✅ 可接受：内部辅助函数，参数简单
def _parse_row(row) -> float:
    """内部解析工具 — 类型从上下文可知。"""
    return float(row.get("price", 0))

# ❌ 避免：公开 API 无类型注解
def get_stock_quote(stock_code):
    ...
```

**量化数据专用注解规范**：

```python
from typing import Dict, List, Optional, TypedDict


class StockQuote(TypedDict, total=False):
    """股票行情结构体。"""
    stock_code: str
    stock_name: str
    price: float
    change_pct: float
    volume: float
    amount: float
    turnover_rate: float
    pe_ratio: float
    pb_ratio: float
    market_cap: float


class BacktestResult(TypedDict):
    """回测结果结构体。"""
    summary: Dict[str, float]
    metrics: Dict[str, float]
    trades: List[Dict[str, Any]]
```

### 2.2 异常处理

```python
# ❌ 绝对禁止：裸 except
try:
    data = fetch_data()
except:  # 吞掉所有异常，包括 KeyboardInterrupt！
    pass

# ✅ 正确：指定异常类型
try:
    data = fetch_data()
except (ConnectionError, TimeoutError) as e:
    logger.warning(f"数据获取失败: {e}")
    data = self._get_fallback_data()

# ✅ 量化专用：多数据源降级模式
for source in [self._primary_source, self._secondary_source, self._fallback_source]:
    try:
        return source.fetch(code)
    except Exception as e:
        logger.debug(f"{source.name} 失败: {e}")
        continue
raise DataUnavailableError(f"所有数据源均失败: {code}")
```

### 2.3 日志规范

```python
import logging

logger = logging.getLogger(__name__)

# 使用级别指南
logger.debug("详细的调试信息")      # 仅在调试时启用
logger.info("数据加载完成: 5124条")  # 正常运行时的重要事件
logger.warning("数据源 ak 不可用，切换到 efinance")  # 异常但可恢复
logger.error("数据库连接失败")       # 需要人工关注的错误

# ❌ 禁止：用 print 替代日志
print("数据加载完成")  # 无法控制级别、无法重定向

# ✅ 例外：CLI 入口文件（main.py）可以用 print 输出用户可见信息
```

### 2.4 命名规范

| 类型 | 规范 | 示例 |
|------|------|------|
| 模块/文件 | `snake_case` | `data_fetcher.py` |
| 类 | `PascalCase` | `MarketDataFetcher` |
| 函数/方法 | `snake_case` | `get_stock_quote()` |
| 常量 | `UPPER_SNAKE` | `MAX_RETRY_COUNT = 3` |
| 私有方法 | `_leading_underscore` | `_parse_row()` |
| 变量 | `snake_case` | `stock_price`, `df_spot` |

**量化命名约定**：

```python
# DataFrame 变量以 df_ 开头
df_spot: pd.DataFrame    # 全市场行情
df_history: pd.DataFrame  # 历史K线
df_signal: pd.DataFrame   # 交易信号

# 配置/参数变量以 cfg_ / param_ 开头
cfg_risk: Dict[str, float]
param_buy_threshold: float

# 回调/处理器以 handler_ / on_ 开头
on_price_change(callback)
handler_signal_tick(event)
```

### 2.5 Docstring

**要求：每个公开模块、类、函数都有 docstring。**

```python
"""
模块级 docstring：说明模块职责和依赖。

数据获取层 — 封装对 AKShare / efinance / 腾讯财经的多源访问。
只支持日频数据，不获取分钟级或 tick 数据。
"""


class MarketDataFetcher:
    """A股市场数据获取器。

    特性：
    - 多数据源降级：AKShare → DataBus → 腾讯 → efinance
    - 内存缓存：5分钟有效期（非交易时段使用最近缓存）
    - 仅日频数据

    Usage:
        fetcher = MarketDataFetcher()
        quote = fetcher.get_stock_quote("600519")
    """

    def get_stock_quote(self, stock_code: str) -> Optional[Dict[str, Any]]:
        """获取单只股票实时行情。

        Args:
            stock_code: 6位股票代码，如 "600519"

        Returns:
            包含行情字段的字典，若取不到数据则返回 None

        Raises:
            DataUnavailableError: 所有数据源都失败时
        """
```

### 2.6 代码组织

```python
# 导入顺序：标准库 → 第三方 → 本地模块
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd
import yaml

from data_bus import DataBus
from models import StockQuote
```

---

## 3. TypeScript / Vue 编码标准

### 3.1 组件结构

```vue
<!-- ✅ 推荐的 Vue 3 SFC 结构 -->
<script setup lang="ts">
// 1. 导入
import { ref, computed, onMounted } from 'vue';
import type { StockQuote } from '@/types/stock';

// 2. Props & Emits
const props = defineProps<{
  stockCode: string;
  showChart?: boolean;
}>();

const emit = defineEmits<{
  (e: 'select', code: string): void;
  (e: 'refresh'): void;
}>();

// 3. 状态
const quote = ref<StockQuote | null>(null);
const loading = ref(false);
const error = ref<string | null>(null);

// 4. 计算属性
const priceColor = computed(() =>
  (quote.value?.change_pct ?? 0) >= 0 ? '#ef4444' : '#22c55e'
);

// 5. 方法
async function fetchQuote() {
  loading.value = true;
  error.value = null;
  try {
    quote.value = await api.getStockQuote(props.stockCode);
  } catch (e) {
    error.value = e instanceof Error ? e.message : '获取失败';
  } finally {
    loading.value = false;
  }
}

// 6. 生命周期
onMounted(fetchQuote);
</script>
```

### 3.2 类型安全

```typescript
// ✅ 推荐：使用 interface / type 定义数据结构
interface StockQuote {
  stock_code: string;
  stock_name: string;
  price: number;
  change_pct: number;
  volume: number;
}

// ❌ 避免：any 类型的广泛使用
const data: any = await api.fetch();

// ✅ 使用类型守卫
function isStockQuote(data: unknown): data is StockQuote {
  return (
    typeof data === 'object' &&
    data !== null &&
    'stock_code' in data &&
    'price' in data
  );
}
```

### 3.3 API 调用规范

```typescript
// ✅ 推荐：统一封装 API 调用，含错误处理和超时
import { apiClient } from '@/utils/api';

export async function getStockQuote(code: string): Promise<StockQuote> {
  return apiClient.get<StockQuote>(`/api/quote/${code}`, {
    timeout: 5000,
    errorMessage: `获取 ${code} 行情失败`,
  });
}

// ❌ 避免：直接裸调 fetch/axios
const res = await fetch(`/api/quote/${code}`);
```

### 3.4 响应式与性能

```typescript
// ✅ 大列表使用虚拟滚动（避免一次性渲染 5000+ 条）
// ✅ 计算属性替代方法调用（自动缓存）
const filteredStocks = computed(() =>
  stocks.value.filter(s =>
    s.name.includes(searchText.value)
  )
);

// ❌ 避免：在模板中调用方法做复杂计算
<span>{{ getAllFilteredStocks() }}</span>  // 每次渲染都重新计算
```

---

## 4. 安全标准

### 4.1 密钥管理 🔴

```python
# ❌ 绝对禁止：硬编码密钥
API_KEY = "sk-abc123..."
PASSWORD = "mypassword123"

# ✅ 正确：环境变量 + 配置管理
import os

api_key = os.environ.get("OPENAI_API_KEY")
if not api_key:
    raise RuntimeError("OPENAI_API_KEY 未设置，请检查 .env 文件")

# ✅ 使用 ConfigManager 统一管理
from config_manager import get_config
email_config = get_config().get_email_config()  # 自动优先读环境变量
```

### 4.2 输入验证 🔴

```python
# ✅ 股票代码验证
import re

STOCK_CODE_PATTERN = re.compile(r"^(0[0-9]{5}|3[0-9]{5}|6[0-9]{5})$")

def validate_stock_code(code: str) -> bool:
    """验证是否为合法的A股代码。"""
    return bool(STOCK_CODE_PATTERN.match(code))

# ✅ 日期范围验证
def validate_date_range(start: str, end: str) -> None:
    start_dt = datetime.strptime(start, "%Y-%m-%d")
    end_dt = datetime.strptime(end, "%Y-%m-%d")
    if start_dt > end_dt:
        raise ValueError(f"开始日期 {start} 不能晚于结束日期 {end}")
    if (end_dt - start_dt).days > 365:
        raise ValueError("回测区间不能超过365天")
```

### 4.3 SQL 注入防护 🔴

```python
# ❌ 危险：字符串拼接
query = f"SELECT * FROM portfolio WHERE code = '{stock_code}'"

# ✅ 安全：参数化查询（SQLAlchemy）
from sqlalchemy import text

result = session.execute(
    text("SELECT * FROM portfolio WHERE stock_code = :code"),
    {"code": stock_code}
)

# ✅ 安全：ORM 查询
holding = session.query(Portfolio).filter_by(stock_code=stock_code).first()
```

### 4.4 依赖安全

```bash
# 定期扫描依赖漏洞
pip-audit                     # Python 依赖
npm audit                     # Node.js 依赖

# CI 中集成
bandit -c pyproject.toml -r .  # Python SAST
```

---

## 5. 性能标准

### 5.1 数据库查询

```python
# ❌ N+1 查询
for holding in portfolio:
    quote = db.query(Quote).filter_by(code=holding.code).first()  # 每只股票一次查询
    ...

# ✅ 批量查询
codes = [h.code for h in portfolio]
quotes = {q.code: q for q in db.query(Quote).filter(Quote.code.in_(codes)).all()}
```

### 5.2 缓存策略

```python
from functools import lru_cache
from datetime import datetime, timedelta


class MarketDataFetcher:
    """行情获取器 — 带内存缓存。"""

    def _get_spot_data(self) -> pd.DataFrame:
        now = datetime.now()
        # 5分钟缓存（非交易时段延长）
        if self._spot_cache is not None and self._cache_time:
            if (now - self._cache_time).seconds < 300:
                return self._spot_cache

        # 缓存过期，重新获取
        self._spot_cache = self._fetch_from_source()
        self._cache_time = now
        return self._spot_cache
```

### 5.3 API 调用

```python
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ✅ 推荐的 HTTP Session：连接复用 + 重试 + 超时
session = requests.Session()
retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=20)
session.mount("https://", adapter)

# 必须设置超时
response = session.get(url, timeout=(5, 30))  # (连接超时, 读取超时)
```

### 5.4 Pandas 优化

```python
# ✅ 链式操作而非中间变量
result = (
    df
    .query('涨跌幅 > 0')
    .sort_values('成交额', ascending=False)
    .head(20)
)

# ✅ 向量化操作替代逐行循环
df['市值分组'] = pd.cut(df['总市值'], bins=[0, 50, 200, 500, float('inf')], labels=['小盘','中盘','大盘','超大盘'])

# ❌ 逐行遍历
for idx, row in df.iterrows():
    if row['涨跌幅'] > 0:
        ...
```

---

## 6. 测试标准

### 6.1 测试分类

| 类型 | 范围 | 覆盖率目标 | 运行频率 |
|------|------|-----------|----------|
| 单元测试 | 单个函数/方法 | ≥ 70% | 每次提交 |
| 集成测试 | 模块间协作 | 关键路径 100% | 每次PR |
| 回测验证 | 策略逻辑 | 全量 | 策略变更时 |
| 端到端测试 | 完整工作流 | 核心流程 | 每日构建 |

### 6.2 测试结构

```
a-share-investment-system/
├── tests/
│   ├── __init__.py
│   ├── conftest.py              # 共享 fixtures
│   ├── unit/                    # 单元测试
│   │   ├── test_data_fetcher.py
│   │   ├── test_config_manager.py
│   │   └── test_signal_extractor.py
│   ├── integration/             # 集成测试
│   │   ├── test_data_bus.py
│   │   └── test_orchestrator.py
│   └── backtest/                # 回测验证
│       └── test_backtest_engine.py
```

### 6.3 测试编写规范

```python
"""测试数据获取器。"""

import pytest
import pandas as pd
from unittest.mock import Mock, patch

from data_fetcher import MarketDataFetcher


class TestMarketDataFetcher:
    """MarketDataFetcher 单元测试。"""

    @pytest.fixture
    def fetcher(self) -> MarketDataFetcher:
        """创建被测对象。"""
        return MarketDataFetcher()

    @pytest.fixture
    def mock_spot_data(self) -> pd.DataFrame:
        """构造模拟的全市场行情数据。"""
        return pd.DataFrame({
            "代码": ["600519", "000858"],
            "名称": ["贵州茅台", "五粮液"],
            "最新价": [1800.0, 150.0],
            "涨跌幅": [2.5, -1.0],
        })

    def test_get_stock_quote_returns_correct_fields(
        self, fetcher, mock_spot_data
    ):
        """获取单只股票行情时，应返回所有标准字段。"""
        with patch.object(fetcher, "_get_spot_data", return_value=mock_spot_data):
            result = fetcher.get_stock_quote("600519")

        assert result is not None
        assert result["stock_code"] == "600519"
        assert result["stock_name"] == "贵州茅台"
        assert result["price"] == 1800.0
        assert result["change_pct"] == 2.5

    def test_get_stock_quote_unknown_code_returns_none(self, fetcher):
        """查询不存在的股票代码时，应返回 None。"""
        empty_df = pd.DataFrame({"代码": [], "名称": []})
        with patch.object(fetcher, "_get_spot_data", return_value=empty_df):
            result = fetcher.get_stock_quote("999999")

        assert result is None

    def test_get_stock_quote_fallback_on_primary_failure(self, fetcher):
        """主数据源失败时，应自动降级到备用数据源。"""
        ...


# ── 参数化测试 ──────────────────────────────────────────

@pytest.mark.parametrize("code,expected", [
    ("600519", True),   # 沪市主板
    ("000001", True),   # 深市主板
    ("300750", True),   # 创业板
    ("688981", True),   # 科创板
    ("12345", False),   # 非6位
    ("abc123", False),  # 含字母
])
def test_validate_stock_code(code, expected):
    """验证各类股票代码的合法性判断。"""
    from utils import validate_stock_code
    assert validate_stock_code(code) == expected
```

### 6.4 Mock 策略

```python
# ✅ 正确的 Mock：mock 外部依赖，不 mock 被测函数本身

# Mock 外部 API
with patch("data_fetcher.akshare.stock_zh_a_hist") as mock_hist:
    mock_hist.return_value = pd.DataFrame({...})
    result = fetcher.get_stock_history("600519")

# Mock 数据库
with patch("models.get_session") as mock_session:
    mock_session.return_value.query.return_value.filter_by.return_value.all.return_value = [...]
    result = service.get_portfolio()

# ❌ 避免：Mock 被测对象自己的方法
with patch.object(fetcher, "get_stock_quote"):  # 在测试 fetcher 时 mock 自身方法
    ...
```

---

## 7. 数据与量化专属标准

### 7.1 前视偏差 (Look-Ahead Bias) 🔴

```python
# ❌ 严重错误：用当日收盘价决定当日买入（前视偏差）
def should_buy_today(code: str, date: str) -> bool:
    close_today = get_price(code, date)           # ← 收盘后才有的价格
    close_yesterday = get_price(code, shift_date(date, -1))
    return close_today > close_yesterday * 1.05   # 用未来信息做决策

# ✅ 正确：用上一日收盘价决定当日信号
def should_buy_today(code: str, date: str) -> bool:
    close_yesterday = get_price(code, shift_date(date, -1))
    close_2days_ago = get_price(code, shift_date(date, -2))
    return close_yesterday > close_2days_ago * 1.05  # 只用已知信息
```

**检查规则**：
- 回测循环中的 `today` 只能访问 `<= today` 的数据
- 禁止在信号计算中使用 `shift(0)` 或 `iloc[-1]`
- 财务数据必须使用发布日期（`pubDate`）过滤，而非报告期

### 7.2 数据源降级链

```python
# ✅ 标准降级模式
DATA_SOURCE_CHAIN = [
    ("akshare", AKShareSource()),
    ("tencent", TencentSource()),
    ("sina", SinaSource()),
    ("efinance", EFinanceSource()),
]

def fetch_with_fallback(code: str, field: str) -> Any:
    """多数据源降级获取数据。

    按优先级依次尝试，记录每次失败原因，全部失败后抛出异常。
    """
    errors: List[str] = []
    for name, source in DATA_SOURCE_CHAIN:
        try:
            result = source.fetch(code, field)
            if result is not None:
                if errors:
                    logger.warning(
                        f"数据源降级: {' → '.join(e.split()[0] for e in errors)} → {name}"
                    )
                return result
        except Exception as e:
            errors.append(f"{name}: {e}")

    raise DataUnavailableError(
        f"所有数据源均失败 [{code}/{field}]: {'; '.join(errors)}"
    )
```

### 7.3 回测与实盘对齐

```python
# ✅ 回测引擎必须与实盘逻辑共享核心信号提取函数
from signal_extractor import extract_buy_signal  # 同一份代码

class BacktestEngine:
    def step(self, date, data):
        signal = extract_buy_signal(data, self.params)  # ← 与实盘一致
        if signal.should_buy:
            self.execute_buy(...)
```

### 7.4 风控检查清单

每次策略变更必须验证：

- [ ] 最大回撤 ≤ 配置阈值
- [ ] 单只股票持仓比例 ≤ 配置上限
- [ ] 总仓位 ≥ 现金底线比例
- [ ] 止损逻辑正确触发
- [ ] 涨跌停限制正确处理（A股 ±10%/±20% 不同）

### 7.5 精度与舍入

```python
# ✅ 金融计算使用 Decimal（避免浮点精度问题）
from decimal import Decimal, ROUND_HALF_UP

price = Decimal("1800.50")
quantity = Decimal("100")
total = (price * quantity).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

# ✅ A股价格：两位小数（ETF/LOF 三位小数）
def format_price(price: float) -> str:
    return f"{price:.2f}"

# ✅ 成交额、市值：取整
def format_amount(amount: float) -> str:
    if amount >= 1e8:
        return f"{amount/1e8:.2f}亿"
    return f"{amount/1e4:.0f}万"
```

---

## 8. 文档标准

### 8.1 模块文档

每个 Python 模块必须在文件头部有模块级 docstring：

```python
"""
模块名 — 一句话描述。

详细说明模块职责、依赖、关键设计决策。

特性：
- 特性点 1
- 特性点 2

注意事项:
    使用前需注意的前置条件或限制
"""
```

### 8.2 架构决策记录 (ADR)

重大技术决策需要在 `docs/adr/` 下记录：

```markdown
# ADR-001: 选择 AKShare 作为主数据源

## 状态
已采纳 (2026-05-06)

## 背景
需要在 TuShare / AKShare / Baostock 之间选择主数据源。

## 决策
选择 AKShare，理由：
1. 免费无需注册
2. 14.8k GitHub stars，社区活跃
3. 覆盖面广（A股/港股/期货/宏观）

## 后果
- 优点：开箱即用，零成本
- 缺点：无官方 SLA，偶尔限流；通过多源降级缓解
```

### 8.3 CHANGELOG

每个子项目维护自己的 `CHANGELOG.md`：

```markdown
## [1.2.0] - 2026-05-06

### Added
- 新增北向资金流向监控模块

### Changed
- DataBus 降级链增加腾讯财经数据源

### Fixed
- 修复回测引擎在非交易日崩溃的问题 (#123)
```

---

## 附录 A：快速参考卡

### Python 一行检查

```bash
ruff check . && ruff format --check . && mypy . && pytest
```

### 前端一行检查

```bash
npx prettier --check . && npx eslint . && npx vitest run
```

### Pre-commit 全量检查

```bash
pre-commit run --all-files
```

---

*最后修订: 2026-05-06 | 版本: 1.0.0*
