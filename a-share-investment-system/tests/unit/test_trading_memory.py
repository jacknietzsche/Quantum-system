"""Unit tests for services.trading_memory."""


class TestTradingMemory:
    def _make_memory(self, tmp_path):
        from services.trading_memory import TradingMemory

        mem_file = str(tmp_path / "test_memory.json")
        return TradingMemory(memory_file=mem_file)

    def test_init_default(self, tmp_path):
        mem = self._make_memory(tmp_path)
        assert mem.memories["trades"] == []
        assert mem.memories["reflections"] == []
        assert mem.memories["patterns"] == []
        assert mem.memories["lessons"] == []

    def test_record_trade(self, tmp_path):
        mem = self._make_memory(tmp_path)
        mem.record_trade({"stock_code": "600519", "action": "buy", "price": 1800})
        assert len(mem.memories["trades"]) == 1
        assert "timestamp" in mem.memories["trades"][0]

    def test_record_trade_limit(self, tmp_path):
        mem = self._make_memory(tmp_path)
        for i in range(1005):
            mem.record_trade({"stock_code": f"{i:06d}", "action": "buy"})
        assert len(mem.memories["trades"]) == 1000

    def test_record_reflection(self, tmp_path):
        mem = self._make_memory(tmp_path)
        mem.record_reflection({"topic": "test_reflection"})
        assert len(mem.memories["reflections"]) == 1
        assert "timestamp" in mem.memories["reflections"][0]

    def test_record_reflection_limit(self, tmp_path):
        mem = self._make_memory(tmp_path)
        for i in range(105):
            mem.record_reflection({"topic": f"r_{i}"})
        assert len(mem.memories["reflections"]) == 100

    def test_record_pattern(self, tmp_path):
        mem = self._make_memory(tmp_path)
        mem.record_pattern({"name": "head_shoulders"})
        assert len(mem.memories["patterns"]) == 1

    def test_record_lesson(self, tmp_path):
        mem = self._make_memory(tmp_path)
        mem.record_lesson({"lesson": "always use stop loss"})
        assert len(mem.memories["lessons"]) == 1

    def test_get_recent_trades(self, tmp_path):
        mem = self._make_memory(tmp_path)
        for i in range(20):
            mem.record_trade({"stock_code": f"{i:06d}"})
        recent = mem.get_recent_trades(limit=5)
        assert len(recent) == 5

    def test_get_reflections(self, tmp_path):
        mem = self._make_memory(tmp_path)
        for i in range(5):
            mem.record_reflection({"topic": f"r_{i}"})
        assert len(mem.get_reflections(limit=3)) == 3

    def test_get_patterns(self, tmp_path):
        mem = self._make_memory(tmp_path)
        mem.record_pattern({"name": "p1"})
        mem.record_pattern({"name": "p2"})
        assert len(mem.get_patterns()) == 2

    def test_get_lessons(self, tmp_path):
        mem = self._make_memory(tmp_path)
        mem.record_lesson({"lesson": "l1"})
        assert len(mem.get_lessons()) == 1

    def test_analyze_performance_empty(self, tmp_path):
        mem = self._make_memory(tmp_path)
        result = mem.analyze_performance()
        assert result["total_trades"] == 0
        assert result["win_rate"] == 0

    def test_analyze_performance_with_trades(self, tmp_path):
        mem = self._make_memory(tmp_path)
        mem.record_trade({"stock_code": "A", "pnl": 100, "return_pct": 5.0})
        mem.record_trade({"stock_code": "B", "pnl": -50, "return_pct": -2.0})
        mem.record_trade({"stock_code": "C", "pnl": 200, "return_pct": 10.0})
        result = mem.analyze_performance()
        assert result["total_trades"] == 3
        assert result["winning_trades"] == 2
        assert result["losing_trades"] == 1
        assert result["win_rate"] > 60

    def test_persistence(self, tmp_path):
        mem = self._make_memory(tmp_path)
        mem.record_trade({"stock_code": "600519", "action": "buy"})
        mem_file = mem.memory_file
        # Reload
        from services.trading_memory import TradingMemory

        mem2 = TradingMemory(memory_file=mem_file)
        assert len(mem2.memories["trades"]) == 1


class TestTradingReflector:
    def test_reflect_on_trade(self, tmp_path):
        from services.trading_memory import TradingMemory, TradingReflector

        mem = TradingMemory(memory_file=str(tmp_path / "mem.json"))
        ref = TradingReflector(mem)
        trade = {
            "id": "T1",
            "stock_code": "600519",
            "action": "buy",
            "price": 1800,
            "reasoning": "strong moat",
        }
        outcome = {"exit_price": 1900, "pnl": 100, "return_pct": 5.5, "reasoning": "target hit"}
        result = ref.reflect_on_trade(trade, outcome)
        assert result["stock_code"] == "600519"
        assert len(mem.memories["reflections"]) == 1

    def test_extract_lessons_big_win(self, tmp_path):
        from services.trading_memory import TradingMemory, TradingReflector

        mem = TradingMemory(memory_file=str(tmp_path / "mem.json"))
        ref = TradingReflector(mem)
        lessons = ref._extract_lessons({"id": "T1"}, {"pnl": 500, "return_pct": 15.0})
        assert len(lessons) >= 1

    def test_extract_lessons_big_loss(self, tmp_path):
        from services.trading_memory import TradingMemory, TradingReflector

        mem = TradingMemory(memory_file=str(tmp_path / "mem.json"))
        ref = TradingReflector(mem)
        lessons = ref._extract_lessons({"id": "T2"}, {"pnl": -500, "return_pct": -15.0})
        assert len(lessons) >= 1

    def test_get_performance_summary(self, tmp_path):
        from services.trading_memory import TradingMemory, TradingReflector

        mem = TradingMemory(memory_file=str(tmp_path / "mem.json"))
        ref = TradingReflector(mem)
        result = ref.get_performance_summary()
        assert "total_trades" in result

    def test_get_learning_points(self, tmp_path):
        from services.trading_memory import TradingMemory, TradingReflector

        mem = TradingMemory(memory_file=str(tmp_path / "mem.json"))
        ref = TradingReflector(mem)
        mem.record_lesson({"lesson": "test_lesson"})
        points = ref.get_learning_points()
        assert "test_lesson" in points


class TestGlobalInstances:
    def test_get_memory_singleton(self, tmp_path):
        import services.trading_memory as tm

        old_mem = tm._memory
        tm._memory = None
        try:
            m1 = tm.get_memory()
            m2 = tm.get_memory()
            assert m1 is m2
        finally:
            tm._memory = old_mem

    def test_get_reflector_singleton(self, tmp_path):
        import services.trading_memory as tm

        old_ref = tm._reflector
        old_mem = tm._memory
        tm._reflector = None
        tm._memory = None
        try:
            r1 = tm.get_reflector()
            r2 = tm.get_reflector()
            assert r1 is r2
        finally:
            tm._reflector = old_ref
            tm._memory = old_mem
