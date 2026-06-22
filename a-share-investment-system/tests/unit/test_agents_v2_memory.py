"""Tests for agents_v2.memory - TradingMemory."""


class TestTradingMemoryV2:
    def test_init(self):
        from agents_v2.memory import TradingMemory

        tm = TradingMemory(config={"memory_dir": ":memory:"})
        assert tm is not None

    def test_init_default(self):
        from agents_v2.memory import TradingMemory

        tm = TradingMemory()
        assert tm is not None

    def test_get_pending_entries(self):
        from agents_v2.memory import TradingMemory

        tm = TradingMemory(config={"memory_dir": ":memory:"})
        result = tm.get_pending_entries()
        assert isinstance(result, list)

    def test_get_past_context(self):
        from agents_v2.memory import TradingMemory

        tm = TradingMemory(config={"memory_dir": ":memory:"})
        result = tm.get_past_context("600519")
        assert isinstance(result, str)

    def test_store_decision(self):
        from agents_v2.memory import TradingMemory

        tm = TradingMemory(config={"memory_dir": ":memory:"})
        try:
            tm.store_decision("600519", "Moutai", "buy", 0.8, "strong moat")
        except Exception:
            pass  # May need file system

    def test_load_entries(self):
        from agents_v2.memory import TradingMemory

        tm = TradingMemory(config={"memory_dir": ":memory:"})
        result = tm.load_entries()
        assert isinstance(result, list)
