"""core.config 单元测试"""
from core.config import QuantConfig, PROJECT_ROOT, A_SHARE_LOT_SIZE


def test_quant_config_defaults():
    cfg = QuantConfig()
    assert cfg.portfolio.initial_cash == 1_000_000.0
    assert cfg.trade.commission_rate == 0.0003
    assert cfg.risk.risk_free_rate == 0.025


def test_config_dir_creation():
    cfg = QuantConfig()
    cfg.ensure_dirs()


def test_project_root_exists():
    assert PROJECT_ROOT.exists()
    assert PROJECT_ROOT.is_dir()


def test_a_share_lot_size():
    assert A_SHARE_LOT_SIZE == 100
