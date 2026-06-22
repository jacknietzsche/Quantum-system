"""Unit tests for shared.disclaimer."""


def test_get_disclaimer():
    from shared.disclaimer import get_disclaimer

    result = get_disclaimer()
    assert isinstance(result, str)
    assert len(result) > 0


def test_get_attribution():
    from shared.disclaimer import get_attribution

    result = get_attribution(["Tushare", "akshare"])
    assert "Tushare" in result
    assert "akshare" in result
    assert isinstance(result, str)


def test_get_attribution_empty():
    from shared.disclaimer import get_attribution

    result = get_attribution([])
    assert isinstance(result, str)
    assert len(result) > 0


def test_get_report_footer():
    from shared.disclaimer import get_report_footer

    result = get_report_footer(["akshare"])
    assert "akshare" in result
    assert isinstance(result, str)


def test_get_report_footer_default():
    from shared.disclaimer import get_report_footer

    result = get_report_footer()
    assert "Tushare" in result


def test_append_to_report():
    from shared.disclaimer import append_to_report

    report = "# My Report" + chr(10) + "Some content"
    result = append_to_report(report, ["akshare"])
    assert "My Report" in result
    assert "akshare" in result
    assert len(result) > len(report)
