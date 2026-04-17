import pytest

from athena.worker.classifier import VALID_CLASSIFICATIONS, classify


@pytest.mark.parametrize(
    "severity,important,expected",
    [
        ("critical", True, "notify_critical"),
        ("critical", False, "notify_warn"),
        ("warn", True, "notify_warn"),
        ("warn", False, "notify_warn"),
        ("info", True, "log_only"),
        ("info", False, "log_only"),
        ("unknown", True, "log_only"),
    ],
)
def test_classify(severity, important, expected):
    assert classify(severity, important) == expected


def test_valid_classifications_constant():
    assert VALID_CLASSIFICATIONS == frozenset(
        {"notify_critical", "notify_warn", "log_only"}
    )
