# 代码审查标准与流程规范 (Code Review Standard)

> 版本: v1.0
> 创建: 2026-04-29
> 适用范围: 量化交易系统 (quant system)

---

## 1. 总则

### 1.1 审查目标

- **保证质量**: 确保代码符合项目规范，降低缺陷率
- **知识共享**: 通过审查促进团队成员间的技术交流
- **一致性**: 统一代码风格和架构模式
- **安全性**: 防止安全漏洞和金融风险

### 1.2 适用范围

| 类型 | 说明 | 强制性 |
|------|------|--------|
| 核心模块 | `core/` 下所有文件 | ✅ 必须 |
| 因子引擎 | `factors/` 下所有因子计算 | ✅ 必须 |
| 回测系统 | `backtest_system/` 关键逻辑 | ✅ 必须 |
| 数据层 | `local_db/`, 数据获取逻辑 | ✅ 必须 |
| 入口脚本 | `run_*.py`, `dashboard*.py` | ⚠️ 建议辅助 |
| 工具脚本 | 检查/清理脚本 | ❌ 可选 |

---

## 2. 量化项目代码规范

### 2.1 命名规范 (强制)

```python
# ✅ 正确示例
class V15Scorer:                    # 大驼峰 - 类名
class UnifiedDataFetcher:           # 大驼峰 - 类名

def calculate_score(self, symbol):   # 小写+下划线 - 函数名
def get_daily_data(self, days):      # 动词+名词 - 函数名
def _fetch_from_baostock(self):      # 下划线前缀 - 内部方法

MAX_POSITION_PCT = 0.10             # 全大写+下划线 - 常量
DEFAULT_CACHE_HOURS = 24            # 全大写+下划线 - 常量

stock_data: Dict[str, DataFrame]    # 小写 - 变量名
price_series: pd.Series            # 描述性命名

# ❌ 错误示例
class scorer:                       # 小写类名
def GetData():                      # 驼峰函数名
def calc(s):                       # 缩写变量
data = []                           # 无意义命名
```

### 2.2 文档字符串规范 (强制)

**每个公开模块、类、函数必须有 docstring**

```python
"""
core.strategy — 策略与因子层
=============================
整合评分体系的所有因子模块。

提供:
  1. V15Scorer — 统一评分器（五层加权 + 防顶 + 因子引擎V2）
  2. StockFilter — 股票过滤器
  ...
"""

class V15Scorer:
    """
    v15 统一评分器 — 五层加权评分 + 防顶过滤 + 因子引擎V2

    评分模型:
        1. 基础因子 (40%): MACD, RSI, 布林带等9因子
        2. 增强因子 (25%): 假突破 + 动量 + K线形态
        ...

    Attributes:
        total_score: 最终评分 (0-1)
        base_score: 基础因子评分
        ...

    Example:
        >>> scorer = V15Scorer(config)
        >>> result = scorer.score("000001", df)
    """

    def score(
        self,
        symbol: str,
        df: pd.DataFrame,
        market_state: Optional[dict] = None,
    ) -> dict:
        """
        对单只股票进行完整评分。

        Args:
            symbol: 股票代码 (6位)
            df: 日频数据 DataFrame
            market_state: 市场环境状态

        Returns:
            评分结果字典 {symbol, total_score, ...}

        Raises:
            ValueError: 当数据不足时
        """
```

### 2.3 异常处理规范 (P0级 - 必须遵守)

```python
# ✅ 正确 - 指定异常类型 + 日志记录
try:
    result = api.fetch_data(code)
except ConnectionError as e:
    logger.error(f"数据获取失败 {code}: {e}")
    return pd.DataFrame()
except ValueError as e:
    logger.warning(f"数据格式错误 {code}: {e}")
    return self._fallback_fetch(code)

# ✅ 正确 - 已知兼容性处理 (需注释说明)
try:
    self._bs_session.logout()
except Exception:
    pass  # baostock logout 偶发失败可忽略 (v15已知问题)

# ❌ 错误 - 裸 except 吞噬所有异常
try:
    result = dangerous_operation()
except:          # ← P0 违规！必须指定类型
    pass          # ← P0 违规！至少要 logger.warning()

# ❌ 错误 - 不记录日志的静默失败
try:
    save_to_database(data)
except Exception as e:
    return       # ← P1 违规：异常被完全忽略
```

### 2.4 日志规范 (P1级 - 强烈建议)

```python
import logging
logger = logging.getLogger(__name__)

# ✅ 正确 - 使用 %s 占位符(懒加载)
logger.info("获取股票数据: %s, 行数: %d", symbol, len(df))
logger.error("连接失败: %s", str(e))

# ⚠️ 可接受但非最优 - f-string
logger.info(f"获取股票数据: {symbol}, 行数: {len(df)}")

# ❌ 错误 - print 替代 logging
print(f"正在处理 {symbol}...")     # ← P2 违规
print("完成")                        # ← P2 违规

# 日志级别使用指南:
# DEBUG    → 开发调试信息 (详细计算过程)
# INFO     → 正常业务流程 (开始/完成/进度)
# WARNING  → 可恢复的问题 (降级/重试/使用备选)
# ERROR    → 操作失败但不致命 (单股票失败)
# CRITICAL → 系统级故障 (数据库崩溃/无法启动)
```

### 2.5 金融数据处理规范 (量化专项 - 强制)

```python
# ✅ 正确 - 边界检查
def calculate_return(price_current: float, price_base: float) -> float:
    """计算收益率, 处理零值和负数边界"""
    if price_base <= 0:
        raise ValueError(f"基准价格无效: {price_base}")
    return (price_current / price_base) - 1.0

# ✅ 正确 - 使用配置中的常量
from core.config import RiskConfig
cfg = RiskConfig()
if drawdown > cfg.stop_loss_pct:  # 配置化阈值
    trigger_stop_loss()

# ❌ 错误 - 硬编码金融参数
if drawdown > 0.08:               # ← P1 违规：魔法数字
    ...

if commission_rate == 0.0003:      # ← P1 违规：应从配置读取
    ...
```

---

## 3. 代码审查清单 (Review Checklist)

### 3.1 功能正确性 (P0)

- [ ] **业务逻辑**: 计算公式是否正确？是否有单元测试验证？
- [ ] **边界条件**: 空DataFrame、零除法、空列表、None输入？
- [ ] **数值精度**: 浮点数比较是否使用近似相等 (`np.isclose()`)?
- [ ] **时区处理**: 日期时间是否统一处理时区？
- [ ] **复权处理**: 是否正确使用前复权/后复权？

### 3.2 代码设计 (P1)

- [ ] **单一职责**: 函数/类是否只做一件事？(建议 <80行)
- [ ] **复杂度控制**: 圈复杂度 < 10? 嵌套层级 < 4?
- [ ] **重复代码**: 是否可以抽取公共方法？
- [ ] **接口一致**: 与现有模块风格是否一致？

### 3.3 安全性与健壮性 (P0/P1)

- [ ] **SQL注入**: 是否使用参数化查询？
- [ ] **敏感信息**: 无硬编码密钥/API Key？
- [ ] **输入校验**: 外部输入是否验证？
- [ ] **异常处理**: 不允许裸 `except:` 或吞异常

### 3.4 性能 (P1/P2)

- [ ] **大数据集**: 是否考虑分批处理/并行化？
- [ ] **I/O操作**: 是否有缓存机制？
- [ ] **内存泄漏**: 大对象是否及时释放？

### 3.5 可维护性 (P2)

- [ ] **文档**: 公开API有docstring？
- [ ] **命名**: 变量/函数名语义清晰？
- [ ] **注释**: 复杂逻辑有行内注释？
- [ ] **日志**: 关键路径有日志记录？

---

## 4. 审查流程

### 4.1 提交前自检 (作者)

```
□ 代码通过 flake8/pylint 基本检查
□ 新功能有对应测试用例
□ docstring 补充完整
□ 无 print 调试语句残留
□ 无 TODO/FIXME/HACK 未处理
□ 日志级别使用正确
□ 配置项已添加到 config.py
□ ARCHITECTURE.md 已更新(如涉及架构变更)
```

### 4.2 Pull Request 流程

```
1. 创建分支: feature/xxx 或 fix/xxx
2. 编写代码 + 自检
3. 提交 PR，填写模板:
   - 变更内容概述
   - 影响范围
   - 测试方案
   - 截图/性能数据(如有)
4. 指定 >=1 名审查者
5. 审查者按清单逐项检查
6. 作者修复反馈问题
7. 审查通过后合并
```

### 4.3 PR 模板

```markdown
## 变更概述
<!-- 一句话描述这个PR做了什么 -->

## 详细变更
- [ ] 新增功能: xxx
- [ ] Bug修复: xxx
- [ ] 重构: xxx
- [ ] 性能优化: xxx

## 影响范围
<!-- 影响哪些模块/功能 -->

## 测试方案
<!-- 如何验证此改动 -->

## 自检清单
- [ ] 代码符合本规范
- [ ] docstring 完整
- [ ] 无裸 except / 吞异常
- [ ] 日志使用规范
- [ ] 配置项已集中管理
```

### 4.4 审查分级响应

| 级别 | 定义 | 处理方式 |
|------|------|----------|
| **P0** | 必须修复 | 阻止合并 |
| **P1** | 应该修复 | 建议修复后再合并 |
| **P2** | 可以改进 | 后续迭代优化 |

---

## 5. 项目特有规则

### 5.1 数据源管理

- 所有数据请求必须通过 `UnifiedDataFetcher`
- 禁止直接调用 baostock/akshare/efinance API
- 缓存 TTL 统一由 `DataSourceConfig.cache_hours` 控制
- 本地数据库优先策略由配置开关控制

### 5.2 因子开发

```python
# 新因子必须实现接口
@runtime_checkable
class BaseFactorEngine(Protocol):
    def calculate(self, df: pd.DataFrame) -> Dict: ...

# 注册到 V15Scorer
scorer.register_factor(MyFactor(), weight=0.05)
```

### 5.3 回测规范

- 使用 `BacktestEngine` 统一接口
- A股交易成本通过 `ChinaStockCommission` 计算
- 报告输出到指定目录，不硬编码路径

### 5.4 禁止事项

1. **禁止** 在核心模块中使用 `print()` 输出
2. **禁止** 裸 `except:` 或 `except Exception: pass`
3. **禁止** 硬编码金融参数 (阈值/费率/权重)
4. **禁止** 直接修改本地数据库文件 (必须通过 DB Manager)
5. **禁止** 在生产代码中包含调试断点/临时代码

---

## 6. 工具支持

### 6.1 推荐工具

| 工具 | 用途 | 安装 |
|------|------|------|
| ruff/flake8 | Linting | `pip install ruff` |
| mypy | 类型检查 | `pip install mypy` |
| pytest | 单元测试 | `pip install pytest` |
| black | 格式化 | `pip install black` |

### 6.2 快速检查命令

```bash
# Lint 检查
ruff check core/ factors/ backtest_system/

# 格式化
black --check core/

# 类型检查 (可选)
mypy core/ --ignore-missing-imports

# 运行测试
pytest tests/ -v
```

---

## 7. 附录

### A. 常见问题速查

| 问题 | 规范引用 | 示例 |
|------|----------|------|
| 函数太长 | §2.3 | 拆分为多个子函数 |
| 异常处理不当 | §2.3 | 指定类型 + 记录日志 |
| 魔法数字 | §2.5 | 移入 config.py |
| 缺少文档 | §2.2 | 添加 docstring |
| print残留 | §2.4 | 改为 logger |

### B. 优先级定义

| 优先级 | 含义 | 响应时间 |
|--------|------|----------|
| P0 | 阻塞性问题，必须立即修复 | 合并前 |
| P1 | 重要问题，应尽快修复 | 本次迭代内 |
| P2 | 改进建议，可延后 | 下个迭代 |

---

*本文档随项目演进持续更新。最后更新: 2026-04-29*
