"""YAML策略加载器 - 表达式沙箱 + 前视偏差审计 + 版本管理"""

import os
import re
from datetime import datetime
from typing import Any

import yaml

from services.base import BaseService, ServiceResult

# ── 表达式安全沙箱 ──

SAFE_OPERATORS = {
    "+",
    "-",
    "*",
    "/",
    ">",
    "<",
    ">=",
    "<=",
    "==",
    "!=",
    "and",
    "or",
    "not",
    "(",
    ")",
}

FORBIDDEN_PATTERNS = [
    r"shift\s*\(\s*-",  # shift(-N) - 使用未来数据
    r"\.shift\s*\(\s*-\d",  # .shift(-N)
    r"import\s+",  # 禁止导入
    r"__",  # 禁止dunder
    r"exec\s*\(|eval\s*\(",  # 禁止代码执行
    r"open\s*\(|file\s*\(",  # 禁止文件操作
    r"lambda\s+",  # 禁止lambda
    r"def\s+\w+\s*\(",  # 禁止函数定义
    r"class\s+\w+",  # 禁止类定义
    r"\.__\w+__",  # 禁止dunder属性
    r"\[.*for\s+.*in\s+.*\]",  # 禁止列表推导
]

LOOK_AHEAD_PATTERNS = [
    (r"\.shift\s*\(\s*-\d", "shift(-N)使用了未来数据"),
    (r"shift\s*\(\s*-", "shift(-N)使用了未来数据"),
    (r"rolling\(.*center\s*=\s*True", "rolling(center=True)使用了未来信息"),
    (r"\.rolling\([^)]*center\s*=\s*True", "rolling(center=True)使用了未来信息"),
]


class ExpressionValidator:
    """表达式安全验证器"""

    @staticmethod
    def validate(formula: str, available_indicators: list[Any]) -> tuple[bool, str]:
        """验证表达式安全性。返回(通过, 错误信息)"""
        # 1. 检查禁用模式
        for pattern in FORBIDDEN_PATTERNS:
            if re.search(pattern, formula, re.IGNORECASE):
                return False, f"表达式包含禁用模式: {pattern}"

        # 2. 提取所有标识符(变量名)
        tokens = re.findall(r"[a-zA-Z_]\w*", formula)

        # 3. 构建允许的标识符集合
        if not available_indicators:
            indicator_names = set()
        elif isinstance(available_indicators[0], dict):
            indicator_names = {ind["name"] for ind in available_indicators}
        else:
            indicator_names = set(available_indicators)

        # 4. 检查标识符是否在允许列表中
        allowed_names = indicator_names | SAFE_OPERATORS | {"True", "False", "None"}
        for token in tokens:
            if token not in allowed_names and not token.isnumeric():
                return False, f"未定义的标识符: '{token}' (允许的指标: {indicator_names})"

        # 5. 检查括号平衡
        if formula.count("(") != formula.count(")"):
            return False, "括号不平衡"

        return True, "OK"


class StrategyAuditor:
    """5项前视偏差自动审计"""

    @staticmethod
    def audit(strategy: dict) -> list[dict]:
        """执行全部5项审计,返回问题列表"""
        issues = []

        # 审计1: shift(-N)检查
        for scoring in strategy.get("scoring", []):
            formula = scoring.get("formula", "")
            for pattern, desc in LOOK_AHEAD_PATTERNS:
                if re.search(pattern, formula):
                    issues.append(
                        {
                            "audit": "shift_check",
                            "severity": "CRITICAL",
                            "location": f"scoring.{scoring.get('name', '?')}.formula",
                            "detail": f"{desc}: '{formula[:80]}'",
                        }
                    )

        # 审计2: rolling(center=True)检查
        for scoring in strategy.get("scoring", []):
            formula = scoring.get("formula", "")
            if re.search(r"rolling\([^)]*center\s*=\s*True", formula):
                issues.append(
                    {
                        "audit": "rolling_check",
                        "severity": "WARNING",
                        "location": f"scoring.{scoring.get('name', '?')}.formula",
                        "detail": "rolling(center=True)使用了当前点两侧数据,包含未来信息",
                    }
                )

        for scoring in strategy.get("scoring", []):
            formula = scoring.get("formula", "")
            if re.search(r"zscore|standardize|normalize", formula, re.IGNORECASE) and not re.search(
                r"expanding|rolling", formula, re.IGNORECASE
            ):
                issues.append(
                    {
                        "audit": "standardization_check",
                        "severity": "WARNING",
                        "location": f"scoring.{scoring.get('name', '?')}.formula",
                        "detail": "标准化操作未指定expanding/rolling窗口,可能存在全样本信息泄漏",
                    }
                )

        entry = strategy.get("entry_threshold")
        strategy_name = strategy.get("name", "")
        if entry and "open" in strategy_name.lower():
            issues.append(
                {
                    "audit": "signal_alignment_check",
                    "severity": "WARNING",
                    "location": "entry_threshold",
                    "detail": "策略声称开盘买入但计分公式可能使用当日close数据(T+1问题)",
                }
            )

        has_close_ref = False
        has_open_buy = False
        for scoring in strategy.get("scoring", []):
            if "close" in scoring.get("formula", ""):
                has_close_ref = True
        for filt in strategy.get("filters", []):
            if "close" in filt.get("condition", ""):
                has_close_ref = True
        if "open" in strategy.get("description", "").lower() or "开盘" in str(strategy):
            has_open_buy = True
        if has_close_ref and has_open_buy:
            issues.append(
                {
                    "audit": "price_peeking_check",
                    "severity": "CRITICAL",
                    "location": "strategy",
                    "detail": "策略使用当日close价格做出开盘买入决策,属于偷价行为",
                }
            )

        return issues


class StrategyLoader(BaseService):
    """YAML策略加载器 + 表达式验证 + 前视偏差审计"""

    def __init__(self, strategies_dir: str = "strategies"):
        super().__init__()
        self.strategies_dir = strategies_dir
        self.validator = ExpressionValidator()
        self.auditor = StrategyAuditor()
        self._cache: dict[str, dict] = {}

    def load_all(self) -> ServiceResult:
        """加载所有YAML策略"""
        try:
            strategies = []
            errors = []
            if not os.path.isdir(self.strategies_dir):
                return ServiceResult.ok(data={"strategies": [], "count": 0})

            for filename in sorted(os.listdir(self.strategies_dir)):
                if filename.endswith((".yaml", ".yml")):
                    result = self.load_one(os.path.join(self.strategies_dir, filename))
                    if result.status == "ok":
                        strategies.append(result.data)
                    else:
                        errors.extend(result.errors)

            self._cache = {s["name"]: s for s in strategies}
            return ServiceResult.ok(
                data={"strategies": strategies, "count": len(strategies)},
                errors=errors if errors else [],
            )
        except Exception as e:
            return ServiceResult.error(errors=[f"load_all failed: {e}"])

    def load_one(self, filepath: str) -> ServiceResult:
        """加载单个策略文件并进行安全审计"""
        try:
            with open(filepath, encoding="utf-8") as f:
                strategy = yaml.safe_load(f)

            if not isinstance(strategy, dict):
                return ServiceResult.error(errors=[f"Invalid YAML structure in {filepath}"])

            # 必需字段检查
            if "name" not in strategy:
                return ServiceResult.error(errors=[f"Missing required field 'name' in {filepath}"])

            # 版本检查
            strategy.setdefault("version", "0.0.0")
            strategy.setdefault("updated_at", datetime.now().strftime("%Y-%m-%d"))

            # 表达式安全验证
            indicators = strategy.get("required_indicators", [])
            validation_errors = []
            for scoring in strategy.get("scoring", []):
                formula = scoring.get("formula", "")
                if formula:
                    ok, msg = self.validator.validate(formula, indicators)
                    if not ok:
                        validation_errors.append(f"scoring.{scoring.get('name', '?')}: {msg}")

            for filt in strategy.get("filters", []):
                condition = filt.get("condition", "")
                if condition:
                    ok, msg = self.validator.validate(condition, indicators)
                    if not ok:
                        validation_errors.append(f"filter: {msg}")

            if validation_errors:
                return ServiceResult.error(errors=validation_errors)

            # 前视偏差审计
            audit_issues = self.auditor.audit(strategy)
            critical_issues = [i for i in audit_issues if i["severity"] == "CRITICAL"]

            enriched = {
                **strategy,
                "_filepath": filepath,
                "_audit_pass": len(critical_issues) == 0,
                "_audit_issues": audit_issues,
                "_audit_issue_count": len(audit_issues),
                "_critical_issue_count": len(critical_issues),
            }

            return ServiceResult.ok(data=enriched)
        except yaml.YAMLError as e:
            return ServiceResult.error(errors=[f"YAML parse error in {filepath}: {e}"])
        except Exception as e:
            return ServiceResult.error(errors=[f"Failed to load {filepath}: {e}"])

    def get_strategy(self, name: str) -> ServiceResult:
        """获取指定策略"""
        if name in self._cache:
            return ServiceResult.ok(data={"strategy": self._cache[name]})
        # 重新加载
        result = self.load_all()
        if result.status == "ok" and name in self._cache:
            return ServiceResult.ok(data={"strategy": self._cache[name]})
        return ServiceResult.error(errors=[f"Strategy not found: {name}"])

    def validate_expression(self, formula: str, indicators: list[str]) -> ServiceResult:
        """独立验证单个表达式"""
        ok, msg = self.validator.validate(formula, indicators)
        return ServiceResult.ok(data={"valid": ok, "message": msg})

    def audit_strategy(self, strategy: dict) -> ServiceResult:
        """独立审计单个策略"""
        issues = self.auditor.audit(strategy)
        critical = [i for i in issues if i["severity"] == "CRITICAL"]
        return ServiceResult.ok(
            data={
                "pass": len(critical) == 0,
                "issues": issues,
                "total": len(issues),
                "critical": len(critical),
            }
        )
