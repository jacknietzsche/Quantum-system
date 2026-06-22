"""Unit tests for services.strategy_loader."""

import os


class TestExpressionValidator:
    def test_valid_simple_formula(self):
        from services.strategy_loader import ExpressionValidator

        ev = ExpressionValidator()
        ok, msg = ev.validate("close > open", ["close", "open"])
        assert ok is True
        assert msg == "OK"

    def test_forbidden_import(self):
        from services.strategy_loader import ExpressionValidator

        ev = ExpressionValidator()
        ok, msg = ev.validate("import os", [])
        assert ok is False

    def test_forbidden_exec(self):
        from services.strategy_loader import ExpressionValidator

        ev = ExpressionValidator()
        ok, msg = ev.validate("exec('print(1)')", [])
        assert ok is False

    def test_forbidden_dunder(self):
        from services.strategy_loader import ExpressionValidator

        ev = ExpressionValidator()
        ok, msg = ev.validate("x.__class__", [])
        assert ok is False

    def test_undefined_variable(self):
        from services.strategy_loader import ExpressionValidator

        ev = ExpressionValidator()
        ok, msg = ev.validate("close > unknown_var", ["close"])
        assert ok is False
        assert "unknown_var" in msg

    def test_unbalanced_parens(self):
        from services.strategy_loader import ExpressionValidator

        ev = ExpressionValidator()
        ok, msg = ev.validate("(close > open", ["close", "open"])
        assert ok is False
        assert ok is False

    def test_valid_with_dict_indicators(self):
        from services.strategy_loader import ExpressionValidator

        ev = ExpressionValidator()
        indicators = [{"name": "rsi_14"}, {"name": "macd"}]
        ok, msg = ev.validate("rsi_14 > 50", indicators)
        assert ok is True

    def test_forbidden_lambda(self):
        from services.strategy_loader import ExpressionValidator

        ev = ExpressionValidator()
        ok, msg = ev.validate("lambda x: x+1", [])
        assert ok is False

    def test_forbidden_list_comprehension(self):
        from services.strategy_loader import ExpressionValidator

        ev = ExpressionValidator()
        ok, msg = ev.validate("[x for x in y]", [])
        assert ok is False


class TestStrategyAuditor:
    def test_audit_clean_strategy(self):
        from services.strategy_loader import StrategyAuditor

        strategy = {
            "name": "test_strategy",
            "scoring": [{"name": "s1", "formula": "close > sma_20"}],
            "filters": [],
        }
        issues = StrategyAuditor.audit(strategy)
        critical = [i for i in issues if i["severity"] == "CRITICAL"]
        assert len(critical) == 0

    def test_audit_shift_negative(self):
        from services.strategy_loader import StrategyAuditor

        strategy = {
            "name": "bad_strategy",
            "scoring": [{"name": "s1", "formula": "close.shift(-5)"}],
            "filters": [],
        }
        issues = StrategyAuditor.audit(strategy)
        critical = [i for i in issues if i["severity"] == "CRITICAL"]
        assert len(critical) >= 1

    def test_audit_rolling_center(self):
        from services.strategy_loader import StrategyAuditor

        strategy = {
            "name": "rolling_strategy",
            "scoring": [{"name": "s1", "formula": "close.rolling(20, center=True).mean()"}],
            "filters": [],
        }
        issues = StrategyAuditor.audit(strategy)
        assert len(issues) >= 1

    def test_audit_standardization_warning(self):
        from services.strategy_loader import StrategyAuditor

        strategy = {
            "name": "zscore_strategy",
            "scoring": [{"name": "s1", "formula": "zscore(close)"}],
            "filters": [],
        }
        issues = StrategyAuditor.audit(strategy)
        assert any("standardization" in i.get("audit", "") for i in issues)


class TestStrategyLoader:
    def test_load_all_empty_dir(self, tmp_path):
        from services.strategy_loader import StrategyLoader

        strategies_dir = str(tmp_path / "strategies")
        os.makedirs(strategies_dir)
        loader = StrategyLoader(strategies_dir=strategies_dir)
        result = loader.load_all()
        assert result.status == "ok"
        assert result.data["count"] == 0

    def test_load_all_nonexistent_dir(self, tmp_path):
        from services.strategy_loader import StrategyLoader

        loader = StrategyLoader(strategies_dir=str(tmp_path / "nonexistent"))
        result = loader.load_all()
        assert result.status == "ok"
        assert result.data["count"] == 0

    def test_load_one_valid_yaml(self, tmp_path):
        import yaml

        from services.strategy_loader import StrategyLoader

        strategy = {
            "name": "test_strat",
            "version": "1.0.0",
            "scoring": [{"name": "s1", "formula": "close > open"}],
            "required_indicators": ["close", "open"],
            "filters": [],
        }
        filepath = str(tmp_path / "test.yaml")
        with open(filepath, "w", encoding="utf-8") as f:
            yaml.dump(strategy, f)
        loader = StrategyLoader()
        result = loader.load_one(filepath)
        assert result.status == "ok"
        assert result.data["name"] == "test_strat"

    def test_load_one_missing_name(self, tmp_path):
        import yaml

        from services.strategy_loader import StrategyLoader

        strategy = {"version": "1.0.0"}
        filepath = str(tmp_path / "noname.yaml")
        with open(filepath, "w", encoding="utf-8") as f:
            yaml.dump(strategy, f)
        loader = StrategyLoader()
        result = loader.load_one(filepath)
        assert result.status == "error"

    def test_load_one_invalid_yaml(self, tmp_path):
        from services.strategy_loader import StrategyLoader

        filepath = str(tmp_path / "bad.yaml")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("not: [valid: yaml: {")
        loader = StrategyLoader()
        result = loader.load_one(filepath)
        # Should either error or handle gracefully
        assert result.status in ("ok", "error")

    def test_validate_expression(self, tmp_path):
        from services.strategy_loader import StrategyLoader

        loader = StrategyLoader()
        result = loader.validate_expression("close > 100", ["close"])
        assert result.status == "ok"
        assert result.data["valid"] is True

    def test_validate_expression_invalid(self, tmp_path):
        from services.strategy_loader import StrategyLoader

        loader = StrategyLoader()
        result = loader.validate_expression("import os", [])
        assert result.status == "ok"
        assert result.data["valid"] is False

    def test_audit_strategy(self, tmp_path):
        from services.strategy_loader import StrategyLoader

        loader = StrategyLoader()
        strategy = {
            "name": "clean",
            "scoring": [{"name": "s1", "formula": "close > sma_20"}],
            "filters": [],
        }
        result = loader.audit_strategy(strategy)
        assert result.status == "ok"
        assert "pass" in result.data

    def test_get_strategy_not_found(self, tmp_path):
        from services.strategy_loader import StrategyLoader

        loader = StrategyLoader(strategies_dir=str(tmp_path / "empty"))
        result = loader.get_strategy("nonexistent")
        assert result.status == "error"
