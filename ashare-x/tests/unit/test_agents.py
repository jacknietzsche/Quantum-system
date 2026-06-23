"""Phase 3 LLM+Agent层测试。"""

from __future__ import annotations

from unittest.mock import MagicMock

from agents.base import (
    _gather_fundamentals_data,
    _gather_news_data,
    _gather_prior_reports,
    _gather_sentiment_data,
    _gather_technical_data,
    create_agent,
)
from agents.masters.selector import select_masters
from core.llm_client import LLMResponse, TokenCounter


class TestTokenCounter:
    def test_record_and_remaining(self):
        counter = TokenCounter(daily_budget=100000)
        counter.record("agent1", "600519", 5000)
        assert counter.remaining() == 95000
        assert counter.per_stock["600519"] == 5000

    def test_fast_mode_threshold(self):
        counter = TokenCounter(daily_budget=100000)
        counter.record("agent1", "600519", 90000)
        assert counter.should_fast_mode() is True

    def test_stock_remaining(self):
        counter = TokenCounter()
        counter.record("agent1", "600519", 10000)
        assert counter.stock_remaining("600519") == 15000
        assert counter.stock_remaining("000001") == 25000


class TestLLMResponse:
    def test_response_fields(self):
        resp = LLMResponse(content="test", tokens=100, latency_ms=50, model="deepseek-chat")
        assert resp.content == "test"
        assert resp.tokens == 100
        assert resp.model == "deepseek-chat"


class TestAgentFactory:
    def test_create_agent_returns_callable(self):
        mock_llm = MagicMock()
        agent = create_agent("test_agent", "Test prompt", mock_llm)
        assert callable(agent)

    def test_agent_node_returns_dict(self):
        mock_llm = MagicMock()
        mock_llm.complete.return_value = LLMResponse(content="test response")
        agent = create_agent("test_agent", "Test prompt", mock_llm)
        result = agent({"ticker": "600519"})
        assert "test_agent_report" in result


class TestMasterSelector:
    def test_select_for_value_stock(self):
        profile = {"pe_ratio": 15, "roe": 25, "volatility": 0.2, "revenue_growth": 0.1}
        masters = select_masters(profile)
        assert len(masters) <= 3
        assert "buffett" in masters or "munger" in masters

    def test_select_for_growth_stock(self):
        profile = {"pe_ratio": 50, "roe": 20, "volatility": 0.4, "revenue_growth": 0.35}
        masters = select_masters(profile)
        assert len(masters) <= 3
        assert "wood" in masters or "fisher" in masters

    def test_select_for_volatile_stock(self):
        profile = {"pe_ratio": 10, "roe": 10, "volatility": 0.5, "revenue_growth": 0.05}
        masters = select_masters(profile)
        assert len(masters) <= 3


class TestDataGatherers:
    def test_gather_technical_data_with_data(self, monkeypatch):
        from tools import stock_data as sd_mod

        fake_data = {
            "kline": [
                {
                    "trade_date": "2026-06-20",
                    "open": 1.0,
                    "high": 2.0,
                    "low": 0.5,
                    "close": 1.5,
                    "volume": 1000,
                }
            ],
            "indicators": {
                "ma5": 1.2,
                "ma20": 1.3,
                "ma60": 1.4,
                "macd": 0.1,
                "dif": 0.2,
                "dea": 0.3,
                "rsi_14": 55.0,
                "boll_upper": 2.0,
                "boll_lower": 1.0,
                "atr_14": 0.5,
            },
        }
        monkeypatch.setattr(sd_mod, "get_stock_data", lambda code, days: fake_data)
        result = _gather_technical_data("600519")
        assert "技术指标数据" in result
        assert "2026-06-20" in result

    def test_gather_technical_data_no_kline(self, monkeypatch):
        from tools import stock_data as sd_mod

        monkeypatch.setattr(sd_mod, "get_stock_data", lambda code, days: {"kline": None})
        result = _gather_technical_data("600519")
        assert "暂无K线数据" in result

    def test_gather_technical_data_exception(self, monkeypatch):
        from tools import stock_data as sd_mod

        def boom(*args, **kwargs):
            raise RuntimeError("network")

        monkeypatch.setattr(sd_mod, "get_stock_data", boom)
        result = _gather_technical_data("600519")
        assert "技术指标数据获取失败" in result

    def test_gather_fundamentals_data(self, monkeypatch):
        from tools import fundamentals as fm_mod

        monkeypatch.setattr(
            fm_mod,
            "get_fundamentals",
            lambda code: {
                "stock_name": "茅台",
                "industry": "白酒",
                "pe_ratio": 30,
                "pb_ratio": 5,
                "latest_price": 1500,
                "change_pct": 1.5,
                "roe": 25,
                "roa": 15,
                "gross_margin": 90,
                "net_margin": 50,
                "revenue_yoy": 10,
                "net_income_yoy": 12,
                "debt_to_equity": 20,
                "revenue": 1000,
                "net_income": 500,
                "report_period": "2026Q1",
            },
        )
        result = _gather_fundamentals_data("600519")
        assert "基本面数据" in result
        assert "茅台" in result

    def test_gather_fundamentals_data_empty(self, monkeypatch):
        from tools import fundamentals as fm_mod

        monkeypatch.setattr(fm_mod, "get_fundamentals", lambda code: None)
        result = _gather_fundamentals_data("600519")
        assert "暂无基本面数据" in result

    def test_gather_news_data(self, monkeypatch):
        from tools import news_search as ns_mod

        monkeypatch.setattr(
            ns_mod,
            "get_news",
            lambda code, days: [{"title": "News1", "date": "2026-06-20", "source": "Sina"}],
        )
        monkeypatch.setattr(
            ns_mod,
            "get_global_news",
            lambda: [{"title": "Macro", "date": "2026-06-20"}],
        )
        result = _gather_news_data("600519")
        assert "新闻数据" in result
        assert "News1" in result
        assert "Macro" in result

    def test_gather_sentiment_data(self, monkeypatch):
        from tools import social_sentiment as ss_mod

        monkeypatch.setattr(
            ss_mod,
            "get_social_sentiment",
            lambda code: {
                "turnover_rate": 1.5,
                "latest_price": 100,
                "change_pct": 2.0,
                "amount": 1000000,
                "dragon_tiger": {
                    "date": "2026-06-20",
                    "reason": "涨幅偏离",
                    "net_buy": 1000,
                    "buy_amount": 2000,
                    "sell_amount": 1000,
                },
                "fund_flow": {
                    "main_net_inflow": 1000,
                    "main_net_pct": 10,
                    "super_large_net": 500,
                    "large_net": 300,
                    "medium_net": 200,
                    "small_net": 100,
                },
                "north_flow": 10000,
            },
        )
        result = _gather_sentiment_data("600519")
        assert "情绪数据" in result
        assert "龙虎榜" in result
        assert "资金流向" in result

    def test_gather_sentiment_data_empty(self, monkeypatch):
        from tools import social_sentiment as ss_mod

        monkeypatch.setattr(ss_mod, "get_social_sentiment", lambda code: {})
        result = _gather_sentiment_data("600519")
        assert "暂无情绪数据" in result


class TestGatherPriorReports:
    def test_gather_prior_reports_before_current(self):
        state = {
            "market_analyst_report": "market report",
            "fundamentals_analyst_report": "fundamentals report",
        }
        result = _gather_prior_reports(state, "news_analyst")
        assert "market_analyst" in result
        assert "fundamentals_analyst" in result

    def test_gather_prior_reports_not_found_current(self):
        state = {"market_analyst_report": "market report"}
        result = _gather_prior_reports(state, "unknown_agent")
        assert result == ""

    def test_gather_prior_reports_empty(self):
        state = {"market_analyst_report": "market report"}
        result = _gather_prior_reports(state, "market_analyst")
        assert result == ""


class TestCreateAgent:
    def test_create_agent_with_analyst_data_provider(self, monkeypatch):
        from tools import stock_data as sd_mod

        fake_data = {
            "kline": [
                {
                    "trade_date": "2026-06-20",
                    "open": 1.0,
                    "high": 2.0,
                    "low": 0.5,
                    "close": 1.5,
                    "volume": 1000,
                }
            ],
            "indicators": {},
        }
        monkeypatch.setattr(sd_mod, "get_stock_data", lambda code, days: fake_data)

        mock_llm = MagicMock()
        mock_llm.complete.return_value = LLMResponse(content="analysis")
        agent = create_agent("market_analyst", "prompt", mock_llm)
        result = agent({"ticker": "600519"})
        assert "market_analyst_report" in result

    def test_create_agent_with_skill_engine(self, monkeypatch):
        from skills import engine as eng_mod

        fake_engine = MagicMock()
        fake_skill = MagicMock()
        fake_skill.metadata.name = "skill1"
        fake_skill.metadata.max_tokens = 100
        fake_skill.prompt = "skill prompt"
        fake_engine.get_for_agent.return_value = [fake_skill]
        fake_engine.registry = {"skill1": fake_skill}

        monkeypatch.setattr(eng_mod, "SkillEngine", lambda: fake_engine)

        mock_llm = MagicMock()
        mock_llm.complete.return_value = LLMResponse(content="result")
        agent = create_agent("test_agent", "prompt", mock_llm)
        result = agent({"ticker": "600519"})
        assert "test_agent_report" in result

    def test_create_agent_llm_error(self):
        mock_llm = MagicMock()
        mock_llm.complete.side_effect = RuntimeError("llm error")
        agent = create_agent("test_agent", "prompt", mock_llm)
        result = agent({"ticker": "600519"})
        assert "test_agent_report" in result
        assert "分析失败" in result["test_agent_report"]

    def test_create_agent_react_mode(self, monkeypatch):
        from agents import react as react_mod

        fake_agent = MagicMock(return_value={"test_agent_report": "react"})
        monkeypatch.setattr(react_mod, "create_react_agent", lambda *args, **kwargs: fake_agent)

        mock_llm = MagicMock()
        agent = create_agent("test_agent", "prompt", mock_llm, mode="react")
        result = agent({"ticker": "600519"})
        assert result == {"test_agent_report": "react"}

    def test_create_agent_with_master_context(self):
        mock_llm = MagicMock()
        mock_llm.complete.return_value = LLMResponse(content="result")
        agent = create_agent("test_agent", "prompt", mock_llm)
        result = agent({"ticker": "600519", "master_prior_context": "summary"})
        assert "test_agent_report" in result
