import pytest

from app.bot.utils import parse_time


@pytest.mark.parametrize("value", ["nan", "inf", "-inf", "1:nan", "-1"])
def test_non_finite_or_negative_times_are_rejected(value):
    with pytest.raises(ValueError):
        parse_time(value)


def test_time_with_minutes_and_seconds():
    assert parse_time("1:02.5") == 62.5
