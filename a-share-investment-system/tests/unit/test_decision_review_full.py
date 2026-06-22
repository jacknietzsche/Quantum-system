"""Tests for decision_review.py — PositionManager + DecisionReviewManager."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestPositionManager:
    def test_calculate_position_ratio(self):
        with patch("decision_review.get_session") as mgs, patch("decision_review.init_db"):
            mgs.return_value = MagicMock()
            from decision_review import PositionManager

            pm = PositionManager()
            result = pm.calculate_position_ratio(50)
            assert "level" in result
            assert "position_pct" in result

    def test_position_ratio_extreme(self):
        with patch("decision_review.get_session") as mgs, patch("decision_review.init_db"):
            mgs.return_value = MagicMock()
            from decision_review import PositionManager

            pm = PositionManager()
            r1 = pm.calculate_position_ratio(90)
            r2 = pm.calculate_position_ratio(10)
            assert "level" in r1 and "level" in r2

    def test_calculate_stock_weight(self):
        with patch("decision_review.get_session") as mgs, patch("decision_review.init_db"):
            mgs.return_value = MagicMock()
            from decision_review import PositionManager

            pm = PositionManager()
            result = pm.calculate_stock_weight(100000, 50, 3)
            assert isinstance(result, dict)


class TestDecisionReviewManager:
    def test_record_decision(self):
        with patch("decision_review.get_session") as mgs, patch("decision_review.init_db"):
            mock_session = MagicMock()
            mgs.return_value = mock_session
            from decision_review import DecisionReviewManager

            drm = DecisionReviewManager()
            result = drm.record_decision("600519", "M", "buy", 0.8, 0.7, "test")
            assert result["status"] == "ok"

    def test_record_vote_result_format1(self):
        with patch("decision_review.get_session") as mgs, patch("decision_review.init_db"):
            mock_session = MagicMock()
            mgs.return_value = mock_session
            from decision_review import DecisionReviewManager

            drm = DecisionReviewManager()
            vr = {
                "stock_code": "600519",
                "stock_name": "M",
                "winner": "buy",
                "confidence": 0.8,
                "consistency": 0.7,
                "reasoning": "good stock",
            }
            result = drm.record_vote_result(vr)
            assert result["status"] == "ok"

    def test_record_vote_result_no_code(self):
        with patch("decision_review.get_session") as mgs, patch("decision_review.init_db"):
            mgs.return_value = MagicMock()
            from decision_review import DecisionReviewManager

            drm = DecisionReviewManager()
            result = drm.record_vote_result({"winner": "hold"})
            assert result["status"] == "skip"

    def test_record_vote_result_with_question(self):
        with patch("decision_review.get_session") as mgs, patch("decision_review.init_db"):
            mock_session = MagicMock()
            mgs.return_value = mock_session
            from decision_review import DecisionReviewManager

            drm = DecisionReviewManager()
            vr = {"winner": "buy", "question": "analyze 600519", "confidence": 0.7}
            result = drm.record_vote_result(vr)
            assert result["status"] == "ok"

    def test_record_vote_result_error(self):
        with patch("decision_review.get_session") as mgs, patch("decision_review.init_db"):
            mgs.side_effect = Exception("db error")
            from decision_review import DecisionReviewManager

            try:
                drm = DecisionReviewManager()
            except Exception:
                pass

    def test_close(self):
        with patch("decision_review.get_session") as mgs, patch("decision_review.init_db"):
            mock_session = MagicMock()
            mgs.return_value = mock_session
            from decision_review import DecisionReviewManager

            drm = DecisionReviewManager()
            drm.close()
