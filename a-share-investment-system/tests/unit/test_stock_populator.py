"""Unit tests for StockPopulator."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from services.stock_populator import StockPopulator


class TestStockPopulatorInit:
    """Test StockPopulator initialization."""

    def test_class_exists(self):
        assert StockPopulator is not None

    def test_init_with_provider(self):
        mock_provider = MagicMock()
        sp = StockPopulator(mock_provider)
        assert sp.provider is mock_provider

    def test_inherits_base_service(self):
        from services.base import BaseService

        assert issubclass(StockPopulator, BaseService)


class TestPopulateStockList:
    """Test populate_stock_list method."""

    @pytest.fixture()
    def sp(self):
        mock_provider = MagicMock()
        return StockPopulator(mock_provider)

    def test_calls_populate_batch(self, sp):
        with patch.object(sp, "_populate_batch") as mock:
            mock.return_value = {"status": "ok", "data": {"total": 1, "success": 1, "failed": 0}}
            result = sp.populate_stock_list(["600519"])
            mock.assert_called_once()

    def test_uses_get_pool_fn_when_codes_none(self, sp):
        mock_pool = MagicMock(return_value=["600519", "000858"])
        with patch.object(sp, "_populate_batch") as mock:
            mock.return_value = {"status": "ok", "data": {"total": 2, "success": 2, "failed": 0}}
            sp.populate_stock_list(None, mock_pool)
            mock.assert_called_once()

    def test_empty_codes_returns_ok(self, sp):
        with patch.object(sp, "_populate_batch") as mock:
            mock.return_value = {"status": "ok", "data": {"total": 0, "success": 0, "failed": 0}}
            result = sp.populate_stock_list([])
            assert result["status"] == "ok"


class TestPopulateOne:
    """Test _populate_one method."""

    @pytest.fixture()
    def sp(self):
        mock_provider = MagicMock()
        return StockPopulator(mock_provider)

    def test_returns_true_when_data_exists(self, sp):
        mock_session = MagicMock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = MagicMock(
            latest_price=1800.0, updated_at=datetime.now()
        )
        mock_session.query.return_value.filter_by.return_value.count.return_value = 50

        with patch("shared.models.get_session", return_value=mock_session):
            result = sp._populate_one("600519")
            assert result is True

    def test_calls_ensure_stock_row(self, sp):
        with patch.object(sp, "_ensure_stock_row") as mock_ensure:
            with patch.object(sp.provider, "get_stock_basic", return_value=None):
                sp._populate_one("600519")
                mock_ensure.assert_called_once_with("600519")


class TestSaveStockInfo:
    """Test _save_stock_info method."""

    @pytest.fixture()
    def sp(self):
        mock_provider = MagicMock()
        return StockPopulator(mock_provider)

    def test_saves_basic_fields(self, sp):
        mock_session = MagicMock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = None

        data = {
            "stock_name": "贵州茅台",
            "industry": "白酒",
            "latest_price": 1800.0,
            "change_pct": 2.5,
            "pe_ratio": 35.0,
        }

        with patch("shared.models.get_session", return_value=mock_session):
            sp._save_stock_info("600519", data)
            mock_session.add.assert_called_once()
            mock_session.commit.assert_called_once()


class TestSaveKlines:
    """Test _save_klines method."""

    @pytest.fixture()
    def sp(self):
        mock_provider = MagicMock()
        return StockPopulator(mock_provider)

    def test_saves_kline_data(self, sp):
        import pandas as pd

        mock_session = MagicMock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = None

        df = pd.DataFrame(
            {
                "date": ["2025-01-15"],
                "open": [1800.0],
                "high": [1810.0],
                "low": [1790.0],
                "close": [1805.0],
                "volume": [1000000],
                "amount": [1800000000],
            }
        )

        with patch("shared.models.get_session", return_value=mock_session):
            sp._save_klines("600519", df)
            mock_session.add.assert_called_once()
            mock_session.commit.assert_called_once()


class TestEnsureStockRow:
    """Test _ensure_stock_row method."""

    @pytest.fixture()
    def sp(self):
        mock_provider = MagicMock()
        return StockPopulator(mock_provider)

    def test_creates_row_if_not_exists(self, sp):
        mock_session = MagicMock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = None

        with patch("shared.models.get_session", return_value=mock_session):
            sp._ensure_stock_row("600519")
            mock_session.add.assert_called_once()
            mock_session.commit.assert_called_once()

    def test_no_add_if_exists(self, sp):
        mock_session = MagicMock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = MagicMock()

        with patch("shared.models.get_session", return_value=mock_session):
            sp._ensure_stock_row("600519")
            mock_session.add.assert_not_called()
