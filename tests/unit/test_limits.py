import asyncio

import pytest

from cloud_crawler_lab.errors import ApiError
from cloud_crawler_lab.security.limits import READ_DEADLINE_SECONDS, check_declared_length, read_body


class FakeRequest:
    def __init__(self, chunks, headers=None, delay=0.0):
        self.headers = headers or {}
        self._chunks, self._delay = chunks, delay

    async def stream(self):
        for chunk in self._chunks:
            if self._delay:
                await asyncio.sleep(self._delay)
            yield chunk


def test_the_declared_length_is_checked_before_anything_is_read():
    check_declared_length(FakeRequest([], {"content-length": "10"}), 10)
    check_declared_length(FakeRequest([], {}), 10)
    check_declared_length(FakeRequest([], {"content-length": "not a number"}), 10)
    check_declared_length(FakeRequest([], {"content-length": "²"}), 10)  # a superscript two: `isdigit`, but not int()
    with pytest.raises(ApiError) as caught:
        check_declared_length(FakeRequest([], {"content-length": "11"}), 10)
    assert caught.value.status == 413 and caught.value.details == {"maxUploadBytes": 10}


@pytest.mark.anyio
async def test_a_body_that_trickles_in_is_cut_off_at_the_deadline():
    slow = FakeRequest([b"a"] * 50, delay=0.05)
    with pytest.raises(ApiError) as caught:
        await read_body(slow, 1000, deadline_seconds=0.1)
    assert (caught.value.status, caught.value.code) == (408, "request_timeout")


@pytest.mark.anyio
async def test_a_body_inside_the_deadline_and_the_limit_is_returned_whole():
    assert await read_body(FakeRequest([b"ab", b"cd"]), 10, deadline_seconds=5) == b"abcd"
    assert await read_body(FakeRequest([b"ab", b"cd"]), 10) == b"abcd", "no deadline given: none applied"


@pytest.mark.anyio
async def test_the_size_limit_still_applies_inside_the_deadline():
    with pytest.raises(ApiError) as caught:
        await read_body(FakeRequest([b"x" * 6, b"y" * 6]), 10, deadline_seconds=5)
    assert caught.value.status == 413


def test_the_deadline_is_long_enough_for_a_slow_link_and_short_enough_to_matter():
    assert 10 <= READ_DEADLINE_SECONDS <= 120
