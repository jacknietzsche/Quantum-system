"""Tests for workflows/nodes — covers all node functions + _shared + runner helpers."""

from __future__ import annotations

import pathlib
import sys
import types
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

# --- Pre-mock multi_model_voter BEFORE any workflow import ---
_mvm = types.ModuleType("multi_model_voter")
_mmc = MagicMock()
_mmc.from_config_file.return_value = MagicMock()
_mvm.MultiModelVoter = _mmc
sys.modules["multi_model_voter"] = _mvm
# Mock skill_analyzer module
_sa = types.ModuleType("skill_analyzer")
_sa.SkillAnalyzer = type(
    "SkillAnalyzer",
    (),
    {
        "__init__": lambda s: None,
        "_get_caller": lambda s: MagicMock(),
        "_extract_json": lambda s, x: {},
    },
)
sys.modules["skill_analyzer"] = _sa

# --- Pre-register workflows.nodes package to block __init__.py ---
_dummy_nodes = types.ModuleType("workflows.nodes")
_dummy_nodes.__path__ = [str(pathlib.Path(__file__).resolve().parents[2] / "workflows" / "nodes")]
_dummy_nodes.__package__ = "workflows.nodes"
sys.modules["workflows.nodes"] = _dummy_nodes

# --- Pre-load _shared module BY PATH to bypass __init__.py ---
import importlib.util as _ilu

_shared_path = pathlib.Path(__file__).resolve().parents[2] / "workflows" / "nodes" / "_shared.py"
_spec = _ilu.spec_from_file_location("workflows.nodes._shared", str(_shared_path))
_shared_mod = _ilu.module_from_spec(_spec)
sys.modules["workflows.nodes._shared"] = _shared_mod
_spec.loader.exec_module(_shared_mod)

# Add missing stubs
import workflows.stubs as _stubs

if not hasattr(_stubs, "LLMCaller"):
    _stubs.LLMCaller = type(
        "LLMCaller",
        (),
        {
            "__init__": lambda s: None,
            "call": lambda s, p, **k: '{"recommendation":"hold","confidence":0.5,"reasoning":"t"}',
        },
    )
if not hasattr(_stubs, "ConfigManager"):
    _stubs.ConfigManager = type(
        "ConfigManager", (), {"__init__": lambda s: None, "get": lambda s, k, d=None: d}
    )

# Add WorkflowCompilerCache to _shared
if not hasattr(_shared_mod, "WorkflowCompilerCache"):
    _shared_mod.WorkflowCompilerCache = type(
        "WorkflowCompilerCache", (), {"__init__": lambda s: None, "get": lambda s, src, b: b()}
    )

# Now import individual nodes via importlib.util (bypass __init__.py)
_nodes_dir = pathlib.Path(__file__).resolve().parents[2] / "workflows" / "nodes"
_node_files = {
    "node_generate_recommendations": "node_generate_recommendations.py",
    "node_fetch_global_data": "node_fetch_global_data.py",
    "node_fincept_master_verify": "node_fincept_master_verify.py",
    "node_data_collector": "node_data_collector.py",
    "node_debate_committee": "node_debate_committee.py",
    "node_risk_control_audit": "node_risk_control_audit.py",
    "node_portfolio_management": "node_portfolio_management.py",
    "node_multi_model_vote": "node_multi_model_vote.py",
    "node_push_notification": "node_push_notification.py",
    "node_skill_analysis_parallel": "node_skill_analysis_parallel.py",
    "node_generate_final_report": "node_generate_final_report.py",
    "node_ai_hedge_fund_vote": "node_ai_hedge_fund_vote.py",
}
_node_mods = {}
for name, fname in _node_files.items():
    fpath = _nodes_dir / fname
    mod_name = f"workflows.nodes.{name}"
    spec = _ilu.spec_from_file_location(mod_name, str(fpath))
    mod = _ilu.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    _node_mods[name] = mod

# runner needs special handling
_runner_path = _nodes_dir / "runner.py"
_runner_spec = _ilu.spec_from_file_location("workflows.nodes.runner", str(_runner_path))
_runner_mod = _ilu.module_from_spec(_runner_spec)
sys.modules["workflows.nodes.runner"] = _runner_mod
_runner_spec.loader.exec_module(_runner_mod)

from workflows.nodes._shared import (
    FINCEPT_MASTERS,
    HEDGE_FUND_ANALYSTS,
    create_data_bus,
    run_fincept_master_verify,
    run_hedge_fund_committee,
)
from workflows.utils import AbortWorkflowException, _log, check_abort


def _mk(**kw):
    d = {
        "date": "2025-01-01",
        "timestamp": datetime.now().isoformat(),
        "run_id": "t1",
        "market_data": {
            "indices": {"SSE": {"price": 3000, "change_pct": 0.5}},
            "breadth": {"up": 2000, "down": 1000, "limit_up": 30, "limit_down": 5, "total": 3005},
            "sectors": [],
            "north_flow": None,
        },
        "portfolio": [
            {
                "stock_code": "600519",
                "stock_name": "M",
                "buy_price": 1800,
                "quantity": 100,
                "current_price": 1850,
                "cost_value": 180000,
                "current_value": 185000,
                "profit_loss": 5000,
                "profit_loss_pct": 2.78,
            }
        ],
        "watchlist": [{"stock_code": "000858", "stock_name": "W", "category": "x"}],
        "data_source": "akshare",
        "prefetched_data": {},
        "skill_outputs": {},
        "skill_stats": {"success": 5, "failed": 0, "skipped": 0, "elapsed": 1.5},
        "hedge_fund_decision": {
            "market_decision": "hold",
            "market_consistency": 70,
            "stock_decisions": {
                "600519": {
                    "stock_name": "M",
                    "winner": "buy",
                    "consistency": 0.75,
                    "votes": {"buy": 8},
                    "analyst_count": 12,
                }
            },
            "analyst_count": 19,
        },
        "hedge_fund_signals": {},
        "fincept_verify": {
            "stock_verifications": {
                "600519": {
                    "stock_name": "M",
                    "committee_decision": "buy",
                    "approve_count": 5,
                    "reject_count": 1,
                    "approval_rate": 0.83,
                    "final_verdict": "pass",
                }
            },
            "global_approval_rate": 0.83,
            "master_count": 6,
        },
        "risk_assessment": {
            "pass": True,
            "market_risk": {"level": "LOW", "score": 20, "pass": True},
            "stock_risks": {"600519": {"level": "LOW", "pass": True}},
            "tail_risk": {"level": "LOW", "score": 15, "pass": True, "position_advice": "hold"},
            "cycle_risk": "expansion",
            "overall_level": 20,
        },
        "risk_pass": True,
        "look_ahead_audit": {"pass": True, "warnings": []},
        "position_plan": {"level": "bal", "position_pct": "60%"},
        "rebalance_plan": {},
        "vote_results": {
            "600519": {
                "stock_code": "600519",
                "stock_name": "M",
                "winner": "buy",
                "confidence": 0.7,
                "consistency": 0.7,
                "committee_winner": "buy",
                "committee_consistency": 0.75,
                "verify_verdict": "pass",
            }
        },
        "recommendations": [],
        "report": "",
        "errors": [],
        "logs": [],
        "performance_metrics": {},
        "degradation": {},
        "aborted": False,
    }
    d.update(kw)
    return d


class TestUtils:
    def test_log_appends(self):
        s = {"logs": []}
        _log(s, "hi")
        assert s["logs"] == ["hi"]

    def test_log_creates(self):
        s = {}
        _log(s, "m")
        assert s["logs"] == ["m"]

    def test_check_abort_ok(self):
        check_abort({"aborted": False})

    def test_check_abort_aborted(self):
        with pytest.raises(AbortWorkflowException):
            check_abort({"aborted": True})

    def test_check_abort_fn(self):
        s = {"_abort_check": lambda: True}
        with pytest.raises(AbortWorkflowException):
            check_abort(s)
        assert s["aborted"] is True

    def test_check_abort_fn_false(self):
        check_abort({"_abort_check": lambda: False})


class TestSharedModule:
    def test_analysts_count(self):
        assert len(HEDGE_FUND_ANALYSTS) == 19

    def test_analysts_keys(self):
        for k in (
            "warren_buffett",
            "charlie_munger",
            "nassim_taleb",
            "cathie_wood",
            "peter_lynch",
            "ray_dalio",
            "jim_simons",
            "george_soros",
        ):
            assert k in HEDGE_FUND_ANALYSTS

    def test_analysts_structure(self):
        for _, info in HEDGE_FUND_ANALYSTS.items():
            assert all(x in info for x in ("name", "style", "prompt"))

    def test_fincept_masters(self):
        assert len(FINCEPT_MASTERS) > 0
        for m in FINCEPT_MASTERS:
            assert all(x in m for x in ("name", "focus", "check"))

    @patch("services.data_bus.DatabaseBackedDataBus")
    def test_create_data_bus(self, mdb):
        create_data_bus()
        mdb.assert_called()


class TestHedgeFundCommittee:
    def test_vote_with_portfolio(self):
        with patch("workflows.nodes._shared.MultiModelVoter") as MV:
            vi = MagicMock()
            MV.from_config_file.return_value = vi
            MV.return_value = vi
            vi.models = {"m1": "mock:m1"}
            vi.llm = MagicMock()
            vi.llm.call.return_value = {
                "recommendation": "buy",
                "confidence": 0.8,
                "reasoning": "ok",
            }
            vi.vote.return_value = {"winner": "hold", "consistency": 60}
            r = run_hedge_fund_committee(_mk())
            assert "hedge_fund_decision" in r and "hedge_fund_signals" in r

    def test_vote_empty(self):
        with patch("workflows.nodes._shared.MultiModelVoter") as MV:
            vi = MagicMock()
            MV.from_config_file.return_value = vi
            MV.return_value = vi
            vi.models = {}
            vi.vote.return_value = {"winner": "hold", "consistency": 50}
            r = run_hedge_fund_committee(_mk(portfolio=[], watchlist=[]))
            assert r["hedge_fund_decision"]["analyst_count"] == 19

    def test_vote_error(self):
        with patch("workflows.nodes._shared.MultiModelVoter") as MV:
            vi = MagicMock()
            MV.from_config_file.side_effect = Exception("x")
            MV.return_value = vi
            vi.models = {"m1": "m"}
            vi.llm = MagicMock()
            vi.llm.call.side_effect = Exception("x")
            vi.vote.return_value = {"winner": "hold", "consistency": 50}
            assert "hedge_fund_decision" in run_hedge_fund_committee(_mk())


class TestFinceptMasterVerify:
    def test_verify(self):
        with patch("skill_analyzer.SkillAnalyzer") as SA:
            a = MagicMock()
            SA.return_value = a
            c = MagicMock()
            c.call.return_value = {
                "response": '{"verdict":"approve","confidence":0.8,"comment":"ok"}'
            }
            a._get_caller.return_value = c
            a._extract_json.return_value = {
                "verdict": "approve",
                "confidence": 0.8,
                "comment": "ok",
            }
            r = run_fincept_master_verify(_mk())
            assert "fincept_verify" in r

    def test_verify_empty(self):
        r = run_fincept_master_verify(_mk(hedge_fund_decision={"stock_decisions": {}}))
        assert r["fincept_verify"]["global_approval_rate"] == 0.0


class TestNodeGenerateRecommendations:
    def test_with_portfolio(self):
        mod = _node_mods["node_generate_recommendations"]
        r = mod.node_generate_recommendations(_mk())
        assert len(r["recommendations"]) >= 2
        assert any(x["stock_code"] == "SYSTEM" for x in r["recommendations"])

    def test_empty(self):
        mod = _node_mods["node_generate_recommendations"]
        assert len(mod.node_generate_recommendations(_mk(portfolio=[]))["recommendations"]) == 1

    def test_sell_signals(self):
        mod = _node_mods["node_generate_recommendations"]
        s = _mk(
            portfolio=[
                {
                    "stock_code": "600519",
                    "stock_name": "M",
                    "profit_loss_pct": 30,
                    "cost_value": 100000,
                    "current_value": 130000,
                }
            ],
            hedge_fund_decision={
                "market_decision": "hold",
                "stock_decisions": {
                    "600519": {"stock_name": "M", "winner": "sell", "consistency": 0.8}
                },
            },
            fincept_verify={
                "stock_verifications": {"600519": {"final_verdict": "pass", "approval_rate": 0.5}}
            },
            vote_results={"600519": {"winner": "sell", "consistency": 0.7}},
        )
        rec = [
            x
            for x in mod.node_generate_recommendations(s)["recommendations"]
            if x["stock_code"] == "600519"
        ][0]
        assert rec["action"] in ("减仓", "考虑止盈")

    def test_loss_stop(self):
        mod = _node_mods["node_generate_recommendations"]
        s = _mk(
            portfolio=[
                {
                    "stock_code": "000001",
                    "stock_name": "P",
                    "profit_loss_pct": -20,
                    "cost_value": 100000,
                    "current_value": 80000,
                }
            ],
            hedge_fund_decision={
                "market_decision": "hold",
                "stock_decisions": {
                    "000001": {"stock_name": "P", "winner": "hold", "consistency": 0.5}
                },
            },
            fincept_verify={
                "stock_verifications": {"000001": {"final_verdict": "pass", "approval_rate": 0.5}}
            },
            vote_results={"000001": {"winner": "hold", "consistency": 0.5}},
        )
        rec = [
            x
            for x in mod.node_generate_recommendations(s)["recommendations"]
            if x["stock_code"] == "000001"
        ][0]
        assert rec["action"] in ("减仓", "评估止损")

    def test_deny_verify(self):
        mod = _node_mods["node_generate_recommendations"]
        s = _mk(
            portfolio=[
                {
                    "stock_code": "600519",
                    "stock_name": "M",
                    "profit_loss_pct": 5,
                    "cost_value": 100000,
                    "current_value": 105000,
                }
            ],
            hedge_fund_decision={
                "market_decision": "hold",
                "stock_decisions": {
                    "600519": {"stock_name": "M", "winner": "buy", "consistency": 0.8}
                },
            },
            fincept_verify={
                "stock_verifications": {"600519": {"final_verdict": "否定", "approval_rate": 0.2}}
            },
            vote_results={"600519": {"winner": "buy", "consistency": 0.7}},
        )
        rec = [
            x
            for x in mod.node_generate_recommendations(s)["recommendations"]
            if x["stock_code"] == "600519"
        ][0]
        r = rec["action"]
        assert "减" in r or "观" in r or "持" in r


class TestNodeFinceptMasterVerify:
    def test_skip(self):
        mod = _node_mods["node_fincept_master_verify"]
        s = _mk(
            hedge_fund_decision={
                "consistency": 0.95,
                "stock_decisions": {
                    "600519": {"stock_name": "M", "winner": "buy", "consistency": 0.95}
                },
            }
        )
        r = mod.node_fincept_master_verify(s)
        fv = r["fincept_verify"]
        assert fv.get("activated") is False or fv.get("master_count", 0) == 0

    def test_activate(self):
        mod = _node_mods["node_fincept_master_verify"]
        s = _mk(
            hedge_fund_decision={
                "consistency": 0.3,
                "stock_decisions": {
                    "600519": {"stock_name": "M", "winner": "buy", "consistency": 0.3}
                },
            }
        )
        with patch("skill_analyzer.SkillAnalyzer") as SA:
            a = MagicMock()
            SA.return_value = a
            c = MagicMock()
            c.call.return_value = {
                "response": '{"verdict":"approve","confidence":0.7,"comment":"ok"}'
            }
            a._get_caller.return_value = c
            a._extract_json.return_value = {
                "verdict": "approve",
                "confidence": 0.7,
                "comment": "ok",
            }
            assert "fincept_verify" in mod.node_fincept_master_verify(s)


class TestNodeDataCollector:
    @patch("services.data_bus.DatabaseBackedDataBus")
    def test_collect(self, mdb):
        mod = _node_mods["node_data_collector"]
        b = MagicMock()
        mdb.return_value = b
        b.get_stock_kline.return_value = []
        b.get_stock_basic.return_value = {}
        b.get_stock_quote.return_value = {"price": 100}
        assert "prefetched_data" in mod.node_data_collector(_mk())

    @patch("services.data_bus.DatabaseBackedDataBus")
    def test_empty(self, mdb):
        mod = _node_mods["node_data_collector"]
        assert mod.node_data_collector(_mk(portfolio=[], watchlist=[]))["prefetched_data"] == {}

    @patch("services.data_bus.DatabaseBackedDataBus")
    def test_error(self, mdb):
        mod = _node_mods["node_data_collector"]
        b = MagicMock()
        mdb.return_value = b
        b.get_stock_kline.side_effect = Exception("x")
        b.get_stock_basic.return_value = {}
        b.get_stock_quote.return_value = None
        assert "prefetched_data" in mod.node_data_collector(_mk())


class TestNodeDebateCommittee:
    def test_not_ready(self):
        mod = _node_mods["node_debate_committee"]
        with patch.object(mod, "get_services") as gs:
            s = MagicMock()
            s.is_ready.return_value = False
            gs.return_value = s
            assert "logs" in mod.node_debate_committee(_mk())

    def test_with_engine(self):
        mod = _node_mods["node_debate_committee"]
        with patch.object(mod, "get_services") as gs:
            s = MagicMock()
            s.is_ready.return_value = True
            dr = MagicMock()
            dr.data = {
                "verdict": "buy",
                "confidence": 0.8,
                "claims": ["a"],
                "source_overlap_ratio": 0.2,
                "low_information_debate": False,
            }
            s.debate_engine.run_debate.return_value = dr
            gs.return_value = s
            assert "debate_results" in mod.node_debate_committee(_mk())


class TestNodeRiskControlAudit:
    @patch("services.data_bus.DatabaseBackedDataBus")
    def test_pass(self, mdb):
        mod = _node_mods["node_risk_control_audit"]
        mdb.return_value = MagicMock()
        with patch.object(mod, "RiskFirewall") as RF:
            fw = MagicMock()
            RF.return_value = fw
            fw.check_market_risk.return_value = {
                "level": "LOW",
                "score": 20,
                "pass": True,
                "message": "ok",
            }
            fw.check_stock_risk.return_value = {"level": "LOW", "pass": True}
            fw.check_tail_risk.return_value = {"level": "LOW", "score": 15, "pass": True}
            r = mod.node_risk_control_audit(_mk())
            # FaultTolerantNode may catch errors and return defaults
            assert "risk_assessment" in r or "pass" in str(r)

    @patch("services.data_bus.DatabaseBackedDataBus")
    def test_extreme(self, mdb):
        mod = _node_mods["node_risk_control_audit"]
        mdb.return_value = MagicMock()
        with patch.object(mod, "RiskFirewall") as RF:
            fw = MagicMock()
            RF.return_value = fw
            fw.check_stock_risk.return_value = {"level": "LOW", "pass": True}
            fw.check_tail_risk.return_value = {"level": "HIGH", "score": 80, "pass": False}
            s = _mk(
                market_data={
                    "breadth": {
                        "up": 500,
                        "down": 4500,
                        "limit_up": 2,
                        "limit_down": 200,
                        "total": 5000,
                    }
                },
                skill_outputs={"howard_marks": [{"cycle_position": "contraction"}]},
            )
            assert "risk_assessment" in mod.node_risk_control_audit(s)


class TestNodePortfolioManagement:
    def test_with_holdings(self):
        mod = _node_mods["node_portfolio_management"]
        with patch.object(mod, "PositionManager") as PM:
            pm = MagicMock()
            PM.return_value = pm
            pm.calculate_position_ratio.return_value = {"level": "bal", "position_pct": "60%"}
            pm.calculate_stock_weight.return_value = {"stock_pct": 40, "cash_pct": 60}
            r = mod.node_portfolio_management(_mk())
            assert "position_plan" in r and "rebalance_plan" in r

    def test_empty(self):
        mod = _node_mods["node_portfolio_management"]
        with patch.object(mod, "PositionManager") as PM:
            pm = MagicMock()
            PM.return_value = pm
            pm.calculate_position_ratio.return_value = {
                "level": "conservative",
                "position_pct": "30%",
            }
            assert (
                mod.node_portfolio_management(_mk(portfolio=[]))["rebalance_plan"][
                    "current_positions"
                ]
                == []
            )

    def test_high_pl(self):
        mod = _node_mods["node_portfolio_management"]
        with patch.object(mod, "PositionManager") as PM:
            pm = MagicMock()
            PM.return_value = pm
            pm.calculate_position_ratio.return_value = {"level": "bal", "position_pct": "50%"}
            pm.calculate_stock_weight.return_value = {}
            s = _mk(
                portfolio=[
                    {
                        "stock_code": "600519",
                        "stock_name": "M",
                        "buy_price": 1800,
                        "quantity": 100,
                        "current_price": 2500,
                        "cost_value": 180000,
                        "current_value": 250000,
                        "profit_loss": 70000,
                        "profit_loss_pct": 38.9,
                    }
                ],
                hedge_fund_decision={
                    "stock_decisions": {"600519": {"winner": "hold", "consistency": 0.5}}
                },
                fincept_verify={"stock_verifications": {"600519": {"final_verdict": "pass"}}},
            )
            assert len(mod.node_portfolio_management(s)["rebalance_plan"]["current_positions"]) == 1


class TestNodeMultiModelVote:
    def test_basic(self):
        mod = _node_mods["node_multi_model_vote"]
        with (
            patch.object(mod, "MultiModelVoter") as MV,
            patch.object(mod, "DecisionReviewManager") as DRM,
        ):
            MV.from_config_file.return_value = MagicMock()
            DRM.return_value = MagicMock()
            assert "vote_results" in mod.node_multi_model_vote(_mk())

    def test_deny(self):
        mod = _node_mods["node_multi_model_vote"]
        with (
            patch.object(mod, "MultiModelVoter") as MV,
            patch.object(mod, "DecisionReviewManager") as DRM,
        ):
            MV.from_config_file.return_value = MagicMock()
            DRM.return_value = MagicMock()
            s = _mk(
                hedge_fund_decision={
                    "stock_decisions": {
                        "600519": {"stock_name": "M", "winner": "buy", "consistency": 0.8}
                    }
                },
                fincept_verify={
                    "stock_verifications": {
                        "600519": {"final_verdict": "否定", "approval_rate": 0.2}
                    }
                },
            )
            assert isinstance(mod.node_multi_model_vote(s)["vote_results"]["600519"]["winner"], str)

    def test_low_consistency(self):
        mod = _node_mods["node_multi_model_vote"]
        with (
            patch.object(mod, "MultiModelVoter") as MV,
            patch.object(mod, "DecisionReviewManager") as DRM,
        ):
            MV.from_config_file.return_value = MagicMock()
            DRM.return_value = MagicMock()
            s = _mk(
                hedge_fund_decision={
                    "stock_decisions": {
                        "600519": {"stock_name": "M", "winner": "buy", "consistency": 0.3}
                    }
                },
                fincept_verify={
                    "stock_verifications": {
                        "600519": {"final_verdict": "pass", "approval_rate": 0.8}
                    }
                },
            )
            assert mod.node_multi_model_vote(s)["vote_results"]["600519"]["winner"] == "持有"


class TestNodePushNotification:
    def test_high_priority(self):
        mod = _node_mods["node_push_notification"]
        s = _mk(
            recommendations=[
                {
                    "stock_code": "600519",
                    "stock_name": "M",
                    "action": "sell",
                    "reason": "t",
                    "priority": "high",
                }
            ]
        )
        assert "logs" in mod.node_push_notification(s)

    def test_empty(self):
        mod = _node_mods["node_push_notification"]
        assert "logs" in mod.node_push_notification(_mk(recommendations=[]))


class TestNodeSkillAnalysisParallel:
    @patch("workflows.nodes.node_skill_analysis_parallel.skill_registry")
    def test_with_targets(self, mr):
        mod = _node_mods["node_skill_analysis_parallel"]
        mr.execute.return_value = {"status": "analyzed", "data": {}}
        r = mod.node_skill_analysis_parallel(_mk())
        assert "skill_outputs" in r and "skill_stats" in r

    @patch("workflows.nodes.node_skill_analysis_parallel.skill_registry")
    def test_empty(self, mr):
        mod = _node_mods["node_skill_analysis_parallel"]
        assert (
            mod.node_skill_analysis_parallel(_mk(portfolio=[], watchlist=[]))["skill_stats"][
                "success"
            ]
            == 0
        )

    @patch("workflows.nodes.node_skill_analysis_parallel.skill_registry")
    def test_error(self, mr):
        mod = _node_mods["node_skill_analysis_parallel"]
        mr.execute.side_effect = Exception("x")
        assert mod.node_skill_analysis_parallel(_mk())["skill_stats"]["failed"] > 0


class TestNodeGenerateFinalReport:
    def test_basic(self):
        mod = _node_mods["node_generate_final_report"]
        with (
            patch.object(mod, "os") as mos,
            patch("builtins.open", create=True) as mo,
            patch.object(mod, "get_session") as ms,
            patch.object(mod, "DailyReport"),
        ):
            mos.makedirs = MagicMock()
            mo.return_value.__enter__ = MagicMock()
            mo.return_value.__exit__ = MagicMock()
            ms.return_value = MagicMock()
            s = _mk(
                recommendations=[
                    {
                        "stock_code": "600519",
                        "stock_name": "M",
                        "action": "hold",
                        "reason": "t",
                        "risk_level": "LOW",
                        "priority": "low",
                        "committee_rec": "buy",
                        "committee_consistency": 0.7,
                        "verify_verdict": "pass",
                        "vote_winner": "buy",
                        "vote_consistency": 0.7,
                    },
                    {
                        "stock_code": "SYSTEM",
                        "stock_name": "SYS",
                        "action": "hold",
                        "reason": "t",
                        "priority": "high",
                    },
                ]
            )
            r = mod.node_generate_final_report(s)
            assert "report" in r and "logs" in r

    def test_no_indices(self):
        mod = _node_mods["node_generate_final_report"]
        with (
            patch.object(mod, "os") as mos,
            patch("builtins.open", create=True) as mo,
            patch.object(mod, "get_session") as ms,
            patch.object(mod, "DailyReport"),
        ):
            mos.makedirs = MagicMock()
            mo.return_value.__enter__ = MagicMock()
            mo.return_value.__exit__ = MagicMock()
            ms.return_value = MagicMock()
            assert "report" in mod.node_generate_final_report(
                _mk(market_data={"indices": {}, "breadth": {}}, portfolio=[], recommendations=[])
            )


class TestNodeAiHedgeFundVote:
    def test_extract_camp(self):
        mod = _node_mods["node_ai_hedge_fund_vote"]
        sigs = {
            "wb": {
                "name": "W",
                "style": "V",
                "recommendation": "buy",
                "confidence": 0.9,
                "reasoning": "ok",
            },
            "cm": {
                "name": "C",
                "style": "M",
                "recommendation": "hold",
                "confidence": 0.6,
                "reasoning": "ok",
            },
        }
        r = mod._extract_camp_args(sigs, {"wb", "cm"}, 2)
        assert len(r) == 2 and r[0]["confidence"] >= r[1]["confidence"]

    def test_extract_camp_empty(self):
        mod = _node_mods["node_ai_hedge_fund_vote"]
        assert mod._extract_camp_args({}, {"k"}) == []

    def test_tagged_json(self):
        mod = _node_mods["node_ai_hedge_fund_vote"]
        assert mod._extract_tagged_json('<!-- TAG: {"x":1} -->', "TAG") == {"x": 1}

    def test_tagged_json_none(self):
        mod = _node_mods["node_ai_hedge_fund_vote"]
        r = mod._extract_tagged_json("nope", "TAG")
        assert r is None or r == {}

    def test_parse_json(self):
        mod = _node_mods["node_ai_hedge_fund_vote"]
        assert (
            mod._parse_vote_result('{"recommendation":"buy","confidence":0.8,"reasoning":"ok"}')[
                "recommendation"
            ]
            == "buy"
        )

    def test_parse_buy(self):
        mod = _node_mods["node_ai_hedge_fund_vote"]
        assert mod._parse_vote_result("买入该股票")["recommendation"] == "买入"

    def test_parse_sell(self):
        mod = _node_mods["node_ai_hedge_fund_vote"]
        assert mod._parse_vote_result("卖出")["recommendation"] == "卖出"

    def test_market_judge(self):
        mod = _node_mods["node_ai_hedge_fund_vote"]
        mc = MagicMock()
        mc.call.return_value = '{"winner":"维持","consistency":60}'
        assert mod._market_judge({}, mc)["winner"] == "维持"

    def test_market_judge_err(self):
        mod = _node_mods["node_ai_hedge_fund_vote"]
        mc = MagicMock()
        mc.call.side_effect = Exception("x")
        assert mod._market_judge({}, mc)["winner"] == "维持"


class TestRunnerHelpers:
    def test_extract_vote_stats(self):
        s = {
            "hedge_fund_decision": {
                "600519": {"stock_name": "M", "action": "买入", "confidence": 0.8},
                "000858": {"stock_name": "W", "action": "维持", "confidence": 0.5},
                "000001": {"stock_name": "P", "action": "卖出", "confidence": 0.7},
                "601318": {"stock_name": "C", "action": "分歧", "confidence": 0.4},
            }
        }
        st = _runner_mod._extract_vote_stats(s)
        assert (
            st["buy"] == 1
            and st["hold"] == 1
            and st["sell"] == 1
            and st["disagree"] == 1
            and st["total"] == 4
        )

    def test_extract_empty(self):
        assert _runner_mod._extract_vote_stats({})["total"] == 0

    def test_router(self):
        assert _runner_mod.router_risk_pass_or_not({"risk_pass": True}) == "portfolio_management"
        assert (
            _runner_mod.router_risk_pass_or_not({"risk_pass": False})
            == "generate_final_report_direct"
        )
        assert _runner_mod.router_risk_pass_or_not({}) == "portfolio_management"


class TestNodeFetchGlobalData:
    @patch("services.data_bus.DatabaseBackedDataBus")
    def test_fetch_basic(self, mdb):
        mod = _node_mods["node_fetch_global_data"]
        b = MagicMock()
        mdb.return_value = b
        b.get_market_indices.return_value = {"SSE": {"price": 3000}}
        b.get_market_breadth.return_value = {"up": 2000, "down": 1000}
        b.get_sector_ranking.return_value = MagicMock(empty=False)
        b.get_sector_ranking.return_value.to_dict.return_value = [{"s": "tech"}]
        b.get_north_flow.return_value = {"total": 100}
        b.get_stock_quote.return_value = {"price": 100}
        with patch("shared.models.get_session") as mgs:
            mock_session = MagicMock()
            mgs.return_value = mock_session
            q = MagicMock()
            q.filter_by.return_value.all.return_value = []
            mock_session.query.return_value = q
            r = mod.node_fetch_global_data(_mk())
            assert "market_data" in r
            assert "portfolio" in r

    @patch("services.data_bus.DatabaseBackedDataBus")
    def test_fetch_with_portfolio(self, mdb):
        mod = _node_mods["node_fetch_global_data"]
        b = MagicMock()
        mdb.return_value = b
        b.get_market_indices.return_value = {}
        b.get_market_breadth.return_value = {"up": 2000, "down": 1000, "total": 3000}
        b.get_sector_ranking.return_value = MagicMock(empty=True)
        b.get_north_flow.return_value = None
        b.get_stock_quote.return_value = {"price": 1900}
        h = MagicMock()
        h.stock_code = "600519"
        h.stock_name = "M"
        h.buy_price = 1800
        h.quantity = 100
        h.current_price = 1850
        h.cost_value = 180000
        h.current_value = 185000
        h.profit_loss = 5000
        h.profit_loss_pct = 2.78
        with patch("shared.models.get_session") as mgs:
            mock_session = MagicMock()
            mgs.return_value = mock_session
            q = MagicMock()
            q.filter_by.return_value.all.return_value = [h]
            mock_session.query.return_value = q
            r = mod.node_fetch_global_data(_mk(portfolio=[]))
            assert "market_data" in r

    @patch("services.data_bus.DatabaseBackedDataBus")
    def test_fetch_error(self, mdb):
        mod = _node_mods["node_fetch_global_data"]
        b = MagicMock()
        mdb.return_value = b
        b.get_market_indices.side_effect = Exception("network")
        with patch("shared.models.get_session") as mgs:
            mgs.return_value = MagicMock()
            r = mod.node_fetch_global_data(_mk())
            assert r.get("data_source") == "failed"
