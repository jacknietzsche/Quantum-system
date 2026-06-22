"""Unit tests for agents_v2.utils.stock_validator."""


class TestValidationResult:
    def test_to_dict(self):
        from agents_v2.utils.stock_validator import ValidationResult

        vr = ValidationResult(
            is_valid=True,
            stock_code="600519",
            market_type="china_a",
            stock_name="Moutai",
        )
        d = vr.to_dict()
        assert d["is_valid"] is True
        assert d["stock_code"] == "600519"
        assert d["market_type"] == "china_a"

    def test_to_dict_defaults(self):
        from agents_v2.utils.stock_validator import ValidationResult

        vr = ValidationResult(is_valid=False, stock_code="999999", error_message="not found")
        d = vr.to_dict()
        assert d["is_valid"] is False
        assert d["error_message"] == "not found"
        assert d["has_historical_data"] is False


class TestStockValidator:
    def test_init_defaults(self):
        from agents_v2.utils.stock_validator import StockValidator

        sv = StockValidator()
        assert sv.default_period_days == 30
        assert sv.timeout_seconds == 15

    def test_init_custom(self):
        from agents_v2.utils.stock_validator import StockValidator

        sv = StockValidator(default_period_days=60)
        assert sv.default_period_days == 60

    def test_validate_empty_code(self):
        from agents_v2.utils.stock_validator import StockValidator

        sv = StockValidator()
        result = sv.validate("")
        assert isinstance(result, object)
        assert hasattr(result, "is_valid")
