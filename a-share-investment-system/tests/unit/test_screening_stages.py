"""测试覆盖: Stage4辩论 / SSE端点 / _apply_portfolio_context / _save_style_signals / abort"""

import inspect
from unittest.mock import patch

import api.routes.screening as sc
from api.routes.screening import (
    LIVE_STATUS_RUN_ID,
    _read_live_status,
    _write_live_status,
    run_screening_stream,
)
from services.stage4_debate import Stage4Debate
from services.stock_screener import StockScreener
from shared.logging import emit_log
from shared.models import ScreenResult, StyleSignal, get_session

# ── Stage4 辩论 ──


class TestStage4Debate:
    def test_select_debate_candidates_uses_divergence(self):
        debate = Stage4Debate({"enabled": True, "top_n": 3})
        candidates = [
            {"stock_code": "000001", "master_score": 80, "score": 70},
            {"stock_code": "000002", "master_score": 50, "score": 75},
            {"stock_code": "000003", "master_score": 60, "score": 55},
            {"stock_code": "000004", "master_score": 90, "score": 88},
        ]
        result = debate._select_debate_candidates(candidates)
        in_debate = [c for c in result if c.get("_in_debate")]
        assert len(in_debate) <= 3
        for c in result:
            assert "_divergence" in c

    def test_run_returns_analyzed_flag_when_enabled(self):
        debate = Stage4Debate({"enabled": True, "top_n": 2})
        candidates = [{"stock_code": "000001", "master_score": 80, "score": 70}]
        result = debate.run(candidates)
        for c in result:
            assert "stage4_analyzed" in c

    def test_run_returns_without_analyzed_when_disabled(self):
        debate = Stage4Debate({"enabled": False})
        candidates = [{"stock_code": "000001"}]
        result = debate.run(candidates)
        for c in result:
            assert c.get("stage4_analyzed") is False


# ── _apply_portfolio_context ──


class TestApplyPortfolioContext:
    def test_adds_portfolio_flags(self):
        s = StockScreener(style="hybrid")
        recs = [
            {"stock_code": "000001", "score": 80, "signal": "买入"},
            {"stock_code": "000002", "score": 30, "signal": "观望"},
        ]
        holdings = {"000001": {"quantity": 100, "profit_loss_pct": -5}}
        result = s._apply_portfolio_context(recs, holdings)
        r1 = next(r for r in result if r["stock_code"] == "000001")
        assert r1.get("in_portfolio") is True
        assert r1.get("holding_qty") == 100

    def test_stop_loss_overrides_signal_when_below_threshold(self):
        s = StockScreener(style="hybrid")
        recs = [{"stock_code": "000001", "score": 50, "signal": "买入"}]
        holdings = {"000001": {"quantity": 100, "profit_loss_pct": -12}}
        result = s._apply_portfolio_context(recs, holdings)
        r = result[0]
        assert r.get("signal") == "卖出"

    def test_high_score_prevents_stop_loss_override(self):
        s = StockScreener(style="hybrid")
        recs = [{"stock_code": "000001", "score": 75, "signal": "买入"}]
        holdings = {"000001": {"quantity": 100, "profit_loss_pct": -12}}
        result = s._apply_portfolio_context(recs, holdings)
        r = result[0]
        assert r.get("signal") != "卖出"


# ── _save_style_signals ──


class TestSaveStyleSignals:
    def test_empty_list_does_not_crash(self):
        s = StockScreener(style="hybrid")
        s._save_style_signals([])

    def test_upserts_recommendations(self):
        session = get_session()
        session.query(StyleSignal).filter_by(stock_code="000001", style="hybrid").delete()
        session.commit()
        session.close()
        s = StockScreener(style="hybrid")
        recs = [{"stock_code": "000001", "score": 80, "signal": "买入", "rank": 1}]
        s._save_style_signals(recs)
        session = get_session()
        row = session.query(StyleSignal).filter_by(stock_code="000001", style="hybrid").first()
        session.close()
        assert row is not None
        assert row.score == 80


# ── Abort 事件 ──


class TestAbortEvent:
    def test_abort_event_clears_running(self):
        with patch("api.routes.screening.emit_log", emit_log):
            sc._screening_abort.clear()
            result = sc.abort_screening()
            assert result["status"] == "aborted"
            assert sc._screening_abort.is_set()

    def test_in_process_running_respected(self):
        with (
            patch("api.routes.screening.emit_log", emit_log),
            patch.object(sc, "_screening_status", {"running": True, "style": "hybrid"}),
        ):
            resp = sc.run_screening(style="limit_up")
            assert resp["status"] == "already_running"


# ── SSE 端点 ──


class TestSSEEndpoint:
    def test_sse_returns_streaming_response(self):
        with patch("api.routes.screening.emit_log", emit_log):
            assert inspect.iscoroutinefunction(run_screening_stream)


# ── 全局状态 DB 回退 ──


class TestLiveStatus:
    def test_write_and_read_live_status(self):
        with patch("api.routes.screening.emit_log", emit_log):
            pass
        session = get_session()
        session.query(ScreenResult).filter_by(run_id=LIVE_STATUS_RUN_ID).delete()
        session.commit()
        session.close()

        _write_live_status(
            style="hybrid", status="running", recommendations_json='{"progress": 50}'
        )
        status = _read_live_status()
        assert status is not None
        assert status.get("progress") == 50
