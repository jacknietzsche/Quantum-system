# 量化系统代码审查指南 v1.1

> 本指南提供实用的代码审查检查清单和常见问题解决方案。
> **版本**: v1.1 | **更新日期**: 2026-04-05

## 📋 2026-03-28 更新：新增规范

### 🔴 变量命名规范（必须遵守）
**禁止使用 Python 内置模块名作为变量名：**
- ❌ `warnings`, `list`, `dict`, `str`, `int`, `float`, `bool`, `type`
- ✅ `stock_warnings`, `portfolio_warnings`, `my_list`, `data_dict`

**原因**：变量名覆盖内置模块会导致运行时错误或难以调试的问题。

**修复示例**：
```python
# ❌ 错误
warnings = []
for item in items:
    warnings.append(item)

# ✅ 正确
item_warnings = []
for item in items:
    item_warnings.append(item)

# 或使用别名导入
import warnings as warnings_builtin
```

### 🔴 依赖注入规范（核心模块）
**core/ 模块应遵循依赖倒置原则：**

```python
# ❌ 错误：直接导入具体实现
from a_stock_selector_v12_optimized import HuanfangStockSelectorV12

class V15Scorer:
    def __init__(self):
        self.selector = HuanfangStockSelectorV12()  # 硬耦合

# ✅ 正确：依赖注入 + 延迟加载
from typing import Optional, Any
from abc import ABC, abstractmethod

class V15Scorer:
    def __init__(
        self,
        config=None,
        selector: Optional[Any] = None,  # 可注入
        enhanced_calc: Optional[Any] = None,
    ):
        self.cfg = config
        if selector:
            self._components = {"selector": selector}  # 优先使用注入
        else:
            self._lazy_loader = LazyComponentLoader()  # 延迟加载
```

### 🟡 类型注解规范
**所有公开方法必须添加类型注解：**

```python
# ❌ 错误
def check_stock(symbol, df):
    warnings = []
    return {"passed": False, "warnings": warnings}

# ✅ 正确
from typing import Dict, List, Optional
import pandas as pd

def check_stock(self, symbol: str, df: pd.DataFrame) -> Dict:
    stock_warnings: List[str] = []
    return {"passed": False, "warnings": stock_warnings}
```

---

## 📋 审查流程

### 阶段 1: 自动化审查（必做）

```bash
# 运行自动化审查工具
python code_review_tool.py

# 修复所有 [阻塞] 和 [警告] 级别问题
```

### 阶段 2: 手动审查清单

#### 🔴 阻塞级问题（必须修复）
- [ ] 数组/列表切片是否有长度检查？
  ```python
  # ❌ 错误示例
  data[20:-5]
  
  # ✅ 正确示例
  if len(data) >= 25:
      data[20:-5]
  ```

- [ ] 除法操作是否有除零保护？
  ```python
  # ❌ 错误示例
  result = a / b
  
  # ✅ 正确示例
  result = a / b if b != 0 else 0
  ```

- [ ] 随机采样是否检查空数组？
  ```python
  # ❌ 错误示例
  samples = np.random.choice(data, 10)
  
  # ✅ 正确示例
  if len(data) >= 10:
      samples = np.random.choice(data, 10)
  ```

- [ ] 数据源是否有 fallback 机制？
  ```python
  # ❌ 错误示例
  data = baostock.query()
  
  # ✅ 正确示例
  data = baostock.query()
  if not data:
      data = akshare.query()
  if not data:
      data = efinance.query()
  ```

#### 🟡 警告级问题（建议修复）
- [ ] DataFrame 操作前是否检查空值？
  ```python
  # ✅ 正确示例
  if not df.empty:
      df.pct_change()
  ```

- [ ] 时间序列是否有最小长度要求？
  ```python
  # ✅ 正确示例
  if len(df) >= 20:  # 20日均线需要至少20天数据
      df['ma20'] = df['close'].rolling(20).mean()
  ```

- [ ] 文件操作是否有异常处理？
  ```python
  # ✅ 正确示例
  try:
      df.to_hdf('file.h5', key='data')
  except Exception as e:
      logger.error(f"保存失败: {e}")
  ```

#### 💭 建议级问题（最佳实践）
- [ ] 变量命名是否清晰？
- [ ] 函数是否单一职责？
- [ ] 是否有足够的注释？
- [ ] 是否添加了日志记录？

### 阶段 3: 性能审查

```python
# 检查是否有低效循环
# ❌ 避免：在循环中重复查询数据库
for stock in stocks:
    df = fetch_data(stock)  # 重复网络请求

# ✅ 推荐：批量查询
all_data = fetch_batch_data(stocks)

# 检查是否有向量化优化空间
# ❌ 避免：逐行计算
for i in range(len(df)):
    df.loc[i, 'sma'] = df['close'][:i].mean()

# ✅ 推荐：向量化计算
df['sma'] = df['close'].rolling(window).mean()
```

## 🎯 量化系统专用审查要点

### 数据层
1. **数据完整性**
   - 检查空值、NaN、inf
   - 验证日期连续性
   - 检查价格异常值（如 <= 0）

2. **数据源容错**
   - 主数据源失败是否有备用方案
   - 网络超时是否有重试机制
   - 缓存机制是否合理

### 计算层
1. **数值稳定性**
   - 对数计算检查 <= 0
   - 指数计算检查溢出
   - 滑动窗口检查最小长度

2. **边界条件**
   - 数组切片检查长度
   - 除法检查分母为零
   - 百分比计算检查基数为零

### 策略层
1. **交易逻辑**
   - 仓位计算限制在 0-100%
   - 买卖信号考虑持仓状态
   - 交易成本计算合理

2. **风险控制**
   - 止损价格是否合理
   - 最大回撤计算正确
   - 风险敞口监控

### 回测层
1. **数据完整性**
   - 回测日期范围是否足够
   - 避免未来函数
   - 停牌股票处理

2. **绩效计算**
   - 年化收益率计算正确
   - 夏普比率计算正确
   - 最大回撤计算正确

## 📊 审查结果记录

每次审查后，在 `.workbuddy/memory/` 中记录：

```markdown
## 代码审查记录 - 2026-03-27

### 审查文件
dashboard_v15.py

### 发现的问题
- [x] 🔴 第 151 行: np.random.choice 空数组风险（已修复）
  - 问题：dates[20:-5] 可能为空
  - 修复：添加长度检查，最小 25 天
  
### 修复方案
```python
min_required_days = 25
if len(dates) < min_required_days:
    trade_dates = []
else:
    trade_dates = np.random.choice(dates[20:-5], ...)
```

### 后续行动
- [ ] 添加单元测试
- [ ] 添加集成测试
```

## 🚀 提交前自查清单

- [ ] 运行 `python code_review_tool.py` 无阻塞级问题
- [ ] 手动检查数据边界、空值、除零
- [ ] 测试边界条件（如：数据为空、长度为1、最小要求）
- [ ] 运行示例代码验证功能正常
- [ ] 更新相关文档
- [ ] 记录审查结果到 memory

## 📚 常见陷阱与解决方案

### 陷阱 1: 日期切片导致空数组
```python
# 问题
dates = pd.date_range(..., freq='B')
trade_dates = np.random.choice(dates[20:-5], 10)  # 如果 len(dates) < 25 就崩溃

# 解决方案
if len(dates) >= 25:
    trade_dates = np.random.choice(dates[20:-5], 10)
else:
    logger.warning("日期范围太短")
    trade_dates = []
```

### 陷阱 2: 收益率计算除零
```python
# 问题
returns = (current - cost) / cost  # cost 可能为 0

# 解决方案
returns = (current - cost) / cost if cost > 0 else 0
```

### 陷阱 3: 空 DataFrame 操作
```python
# 问题
df['return'] = df['close'].pct_change()  # df 可能为空
mean_return = df['return'].mean()  # 结果为 NaN

# 解决方案
if not df.empty:
    df['return'] = df['close'].pct_change()
    mean_return = df['return'].mean() if not df['return'].isna().all() else 0
```

### 陷阱 4: 文件不存在
```python
# 问题
df = pd.read_hdf('data.h5', 'stock_data')  # 文件可能不存在

# 解决方案
if os.path.exists('data.h5'):
    df = pd.read_hdf('data.h5', 'stock_data')
else:
    df = pd.DataFrame()  # 返回空 DataFrame
```

## 🔧 工具使用

### 运行自动化审查
```bash
# 审查整个系统
python code_review_tool.py

# 审查单个文件
python code_review_tool.py dashboard_v15.py
```

### 集成到开发流程
```bash
# 在 git pre-commit 中添加
pre-commit:
    python code_review_tool.py
    if [ $? -ne 0 ]; then
        echo "代码审查未通过，请修复问题后再提交"
        exit 1
    fi
```

---

## 📋 快速检查表（5分钟版）

### 1分钟：运行工具
```bash
python code_review_tool.py --all
```

### 2分钟：检查关键项
- [ ] 数据获取是否有 fallback？
- [ ] 除法操作有除零保护？
- [ ] 数组切片有边界检查？
- [ ] 异常处理是否完善？

### 3分钟：量化系统专项
- [ ] DataFrame 操作前检查空值？
- [ ] 时间序列有最小长度要求？
- [ ] 浮点数比较使用 tolerance？
- [ ] 缓存失效有日志？

## 🎯 常见模式检查

### 模式1：DataFrame 空值检查
```python
# ❌ 错误
df['return'] = df['close'].pct_change()

# ✅ 正确
if not df.empty and len(df) > 1:
    df['return'] = df['close'].pct_change()
```

### 模式2：滑动窗口边界
```python
# ❌ 错误
df['ma20'] = df['close'].rolling(20).mean()

# ✅ 正确
MIN_DAYS = 20
if len(df) >= MIN_DAYS:
    df['ma20'] = df['close'].rolling(MIN_DAYS).mean()
else:
    df['ma20'] = np.nan
```

### 模式3：数值比较 tolerance
```python
# ❌ 错误
if a == b:

# ✅ 正确
import numpy as np
TOLERANCE = 1e-6
if np.abs(a - b) < TOLERANCE:
    pass
```

### 模式4：批量请求
```python
# ❌ 错误
for stock in stocks:
    data = fetch(stock)

# ✅ 正确
data = fetch_batch(stocks)
```

### 模式5：缓存键生成
```python
# ❌ 错误
cache_key = f"{symbol}_{date}"

# ✅ 正确
import hashlib
cache_key = hashlib.md5(f"{symbol}_{date}".encode()).hexdigest()
```

### 模式6：日志脱敏
```python
# ❌ 错误
logger.info(f"API Key: {api_key}")

# ✅ 正确
logger.info(f"API Key: {api_key[:4]}****")
```

## 🔧 工具输出解读

### 评分等级
| 分数 | 等级 | 行动 |
|------|------|------|
| 90-100 | 🟢 优秀 | 可直接合并 |
| 75-89 | 🟡 良好 | 建议小修后合并 |
| 60-74 | 🟠 需改进 | 必须修复部分问题 |
| <60 | 🔴 不通过 | 存在严重问题 |

### 问题数量参考
- P0 > 0: 必须修复后才能合并
- P1 > 10: 建议修复后再合并
- P2 > 20: 可以合并但建议改进

---

**记住：好的代码审查不是为了挑刺，而是为了建造更健壮的系统！**
