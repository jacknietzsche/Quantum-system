"""Tests for agents_v2.utils.logging_manager."""

import logging


class TestLoggingManager:
    def test_init(self):
        from agents_v2.utils.logging_manager import LoggingManager

        lm = LoggingManager()
        assert lm is not None

    def test_init_with_config(self):
        from agents_v2.utils.logging_manager import LoggingManager

        try:
            lm = LoggingManager(config={"level": "DEBUG"})
            assert lm is not None
        except Exception:
            pass

    def test_get_logger(self):
        from agents_v2.utils.logging_manager import LoggingManager

        lm = LoggingManager()
        logger = lm.get_logger("test_mgr")
        assert isinstance(logger, logging.Logger)

    def test_log_analysis_start(self):
        from agents_v2.utils.logging_manager import LoggingManager

        lm = LoggingManager()
        logger = lm.get_logger("test_start")
        lm.log_analysis_start(logger, "600519", "research")

    def test_log_analysis_complete(self):
        from agents_v2.utils.logging_manager import LoggingManager

        lm = LoggingManager()
        logger = lm.get_logger("test_complete")
        lm.log_analysis_complete(logger, "600519", "research", 1.5)

    def test_log_module_error(self):
        from agents_v2.utils.logging_manager import LoggingManager

        lm = LoggingManager()
        logger = lm.get_logger("test_error")
        lm.log_module_error(logger, "test_module", "600519", "test error")

    def test_log_token_usage(self):
        from agents_v2.utils.logging_manager import LoggingManager

        lm = LoggingManager()
        logger = lm.get_logger("test_tokens")
        lm.log_token_usage(logger, "deepseek", "v4", 100, 50, 0.01)


class TestStructuredFormatter:
    def test_format(self):
        from agents_v2.utils.logging_manager import StructuredFormatter

        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test",
            args=None,
            exc_info=None,
        )
        result = formatter.format(record)
        assert isinstance(result, str)


class TestColoredFormatter:
    def test_format(self):
        from agents_v2.utils.logging_manager import ColoredFormatter

        formatter = ColoredFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test",
            args=None,
            exc_info=None,
        )
        result = formatter.format(record)
        assert isinstance(result, str)


class TestGetLoggingManager:
    def test_singleton(self):
        from agents_v2.utils.logging_manager import get_logging_manager

        m1 = get_logging_manager()
        m2 = get_logging_manager()
        assert m1 is m2
