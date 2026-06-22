"""Unit tests for services.memory_bank."""

import os


class TestMemoryBank:
    def _make_bank(self, tmp_path):
        from services.memory_bank import MemoryBank

        mem_dir = str(tmp_path / "test_memory")
        return MemoryBank(memory_dir=mem_dir)

    def test_init_creates_dir(self, tmp_path):
        bank = self._make_bank(tmp_path)
        assert os.path.exists(str(tmp_path / "test_memory"))

    def test_init_empty_state(self, tmp_path):
        bank = self._make_bank(tmp_path)
        assert bank.bull_docs == []
        assert bank.bear_docs == []

    def test_encode_situation(self, tmp_path):
        bank = self._make_bank(tmp_path)
        situation = {
            "stock_code": "600519",
            "stock_name": "Moutai",
            "regime": "BULL",
            "pe": 35.5,
            "roe": 25.3,
            "industry": "liquor",
            "pl_pct": 5.0,
        }
        result = bank._encode_situation(situation)
        assert "600519" in result
        assert "Moutai" in result

    def test_encode_situation_empty(self, tmp_path):
        bank = self._make_bank(tmp_path)
        result = bank._encode_situation({})
        assert isinstance(result, str)

    def test_store_bull(self, tmp_path):
        bank = self._make_bank(tmp_path)
        situation = {"stock_code": "600519", "stock_name": "Moutai", "regime": "BULL"}
        decision = {"verdict": "买入", "confidence": 0.8}
        outcome = {"return_pct": 5.0, "correct": True}
        result = bank.store(situation, decision, outcome)
        assert result.status == "ok"
        assert len(bank.bull_docs) == 1

    def test_store_bear(self, tmp_path):
        bank = self._make_bank(tmp_path)
        situation = {"stock_code": "000858", "stock_name": "Wuliangye"}
        decision = {"verdict": "卖出", "confidence": 0.7}
        outcome = {"return_pct": -3.0, "correct": False}
        result = bank.store(situation, decision, outcome)
        assert result.status == "ok"
        assert len(bank.bear_docs) == 1

    def test_store_hold(self, tmp_path):
        bank = self._make_bank(tmp_path)
        situation = {"stock_code": "600036"}
        decision = {"verdict": "持有", "confidence": 0.5}
        outcome = {"return_pct": 0.0}
        result = bank.store(situation, decision, outcome)
        assert result.status == "ok"
        # hold doesn't go to bull or bear
        assert len(bank.bull_docs) == 0
        assert len(bank.bear_docs) == 0

    def test_search_empty(self, tmp_path):
        bank = self._make_bank(tmp_path)
        result = bank._search(None, [], ["query"], 5)
        assert result == []

    def test_persistence(self, tmp_path):
        bank = self._make_bank(tmp_path)
        bank.store(
            {"stock_code": "600519"},
            {"verdict": "买入", "confidence": 0.8},
            {"return_pct": 5.0, "correct": True},
        )
        # Reload
        from services.memory_bank import MemoryBank

        bank2 = MemoryBank(memory_dir=bank.memory_dir)
        assert len(bank2.bull_docs) == 1
