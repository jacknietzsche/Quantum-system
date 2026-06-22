"""Unit tests for shared.logging utilities."""


def test_emit_log():
    from shared.logging import emit_log, get_log_buffer

    initial_len = len(get_log_buffer())
    emit_log("INFO", "test_module", "test message")
    buf = get_log_buffer()
    assert len(buf) >= initial_len
    assert buf[-1]["module"] == "test_module"
    assert buf[-1]["msg"] == "test message"


def test_emit_log_truncates():
    from shared.logging import emit_log, get_log_buffer

    long_msg = "x" * 1000
    emit_log("INFO", "test", long_msg)
    buf = get_log_buffer()
    assert len(buf[-1]["msg"]) <= 500


def test_get_error_logs():
    from shared.logging import emit_log, get_error_logs

    emit_log("ERROR", "test_mod", "error occurred")
    errors = get_error_logs()
    assert any("error occurred" in e["msg"] for e in errors)


def test_get_logs_since():
    from shared.logging import get_logs_since

    # get_logs_since returns (logs, total_len)
    # At index 0, should return all logs
    logs, total_len = get_logs_since(0)
    assert isinstance(logs, list)
    assert isinstance(total_len, int)
    assert total_len >= 0
    # At a very large index, should return empty
    logs2, total_len2 = get_logs_since(999999)
    assert logs2 == []


def test_get_logs_since_no_new():
    from shared.logging import get_log_buffer, get_logs_since

    current_len = len(get_log_buffer())
    logs, new_len = get_logs_since(current_len + 1000)
    assert logs == []


def test_log_exception():
    from shared.logging import get_log_buffer, log_exception

    try:
        raise ValueError("test error")
    except ValueError as e:
        log_exception("test_mod", e, context="unit test")
    buf = get_log_buffer()
    assert any("ValueError" in entry["msg"] for entry in buf)


def test_log_exception_no_context():
    from shared.logging import get_log_buffer, log_exception

    try:
        raise RuntimeError("runtime oops")
    except RuntimeError as e:
        log_exception("test_mod", e)
    buf = get_log_buffer()
    assert any("RuntimeError" in entry["msg"] for entry in buf)


def test_get_logger():
    from shared.logging import get_logger

    logger = get_logger("test_logger_name")
    assert logger.name == "test_logger_name"
