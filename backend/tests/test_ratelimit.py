import pytest
from fastapi import HTTPException

from oathbox.ratelimit import RateLimiter


def test_off_by_default():
    lim = RateLimiter()
    for _ in range(1000):
        lim.check("1.2.3.4")


def test_per_visitor_hourly_limit():
    lim = RateLimiter(per_ip_per_hour=2, what="questions")
    lim.check("a")
    lim.check("a")
    with pytest.raises(HTTPException) as e:
        lim.check("a")
    assert e.value.status_code == 429 and "2 questions an hour" in e.value.detail
    lim.check("b")  # other visitors are unaffected


def test_daily_total_limit():
    lim = RateLimiter(per_day=3, what="questions")
    for ip in ("a", "b", "c"):
        lim.check(ip)
    with pytest.raises(HTTPException) as e:
        lim.check("d")
    assert "today's limit of 3" in e.value.detail


def test_refused_request_is_not_counted_against_the_day():
    lim = RateLimiter(per_ip_per_hour=1, per_day=2)
    lim.check("a")
    with pytest.raises(HTTPException):
        lim.check("a")  # over the hourly limit: must not use up the daily total
    lim.check("b")
