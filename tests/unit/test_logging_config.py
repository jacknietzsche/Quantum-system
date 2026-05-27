"""core.logging_config 单元测试"""
import logging


def test_setup_logging_idempotent():
    from core.logging_config import setup_logging
    root_before = len(logging.getLogger().handlers)
    setup_logging()
    setup_logging()  # 不应重复添加 handler
    root_after = len(logging.getLogger().handlers)
    assert root_after == root_before + 1 or root_after == root_before


def test_get_logger():
    from core.logging_config import get_logger
    logger = get_logger("test_module")
    assert logger.name == "test_module"
    assert isinstance(logger, logging.Logger)
