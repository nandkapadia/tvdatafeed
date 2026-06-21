"""Tests for live-feed primitives and the auth-retry flow in get_hist."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pandas as pd

from tvDatafeed import Interval, Seis, TvDatafeed, TvDatafeedLive

SAT = TvDatafeedLive._SeisesAndTrigger


def series_with_completed() -> str:
    """A minimal raw payload that parses to one bar and is 'completed'."""
    return (
        '{"m":"timescale_update","p":["cs",{"s1":{"s":'
        '[{"i":0,"v":[1609459200.0,150.0,151.5,149.5,151.0,1000000.0]}],'
        '"ns":{}}}]}\n'
        '{"m":"series_completed","p":["cs"]}'
    )


# --------------------------------------------------------------------------- #
# Seis
# --------------------------------------------------------------------------- #


class TestSeis:
    def test_equality_by_identity_fields(self):
        a = Seis("AAPL", "NASDAQ", Interval.in_1_hour)
        b = Seis("AAPL", "NASDAQ", Interval.in_1_hour)
        c = Seis("MSFT", "NASDAQ", Interval.in_1_hour)
        assert a == b
        assert a != c

    def test_is_new_data_detects_change(self):
        seis = Seis("AAPL", "NASDAQ", Interval.in_daily)
        idx1 = pd.DatetimeIndex([datetime(2025, 1, 1, tzinfo=timezone.utc)])
        idx2 = pd.DatetimeIndex([datetime(2025, 1, 2, tzinfo=timezone.utc)])
        df1 = pd.DataFrame({"close": [1.0]}, index=idx1)
        df2 = pd.DataFrame({"close": [2.0]}, index=idx2)

        assert seis.is_new_data(df1) is True  # first time
        assert seis.is_new_data(df1) is False  # same timestamp
        assert seis.is_new_data(df2) is True  # new timestamp


# --------------------------------------------------------------------------- #
# _SeisesAndTrigger  (exercises the tz-aware datetime fix)
# --------------------------------------------------------------------------- #


class TestSeisesAndTrigger:
    def test_append_contains_and_get_seis(self):
        sat = SAT()
        seis = Seis("AAPL", "NASDAQ", Interval.in_1_minute)
        sat.append(seis, datetime.now(timezone.utc))
        assert seis in sat
        assert sat.get_seis("AAPL", "NASDAQ", Interval.in_1_minute) is seis
        assert sat.get_seis("NOPE", "NASDAQ", Interval.in_1_minute) is None

    def test_get_expired_with_tz_aware_datetimes(self):
        # A past update_dt means the next bar is already due -> expired.
        # This also asserts no naive/aware TypeError is raised.
        sat = SAT()
        seis = Seis("AAPL", "NASDAQ", Interval.in_1_minute)
        past = datetime.now(timezone.utc) - timedelta(minutes=2)
        sat.append(seis, past)
        assert "1" in sat.get_expired()

    def test_not_expired_in_future(self):
        sat = SAT()
        seis = Seis("AAPL", "NASDAQ", Interval.in_1_minute)
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        sat.append(seis, future)
        assert sat.get_expired() == []

    def test_discard_removes_interval_group(self):
        sat = SAT()
        seis = Seis("AAPL", "NASDAQ", Interval.in_1_minute)
        sat.append(seis, datetime.now(timezone.utc))
        sat.discard(seis)
        assert seis not in sat
        assert "1" not in sat.intervals()


# --------------------------------------------------------------------------- #
# get_hist auth-failure -> refresh -> retry
# --------------------------------------------------------------------------- #


class TestGetHistAuthRetry:
    def test_refreshes_and_retries_on_auth_error(self, tmp_path):
        tv = TvDatafeed(token_cache_file=tmp_path / ".tv_token.json")
        tv.token = "STALE"
        outcomes = [("", True), (series_with_completed(), False)]

        with (
            patch.object(tv, "_fetch_series", side_effect=outcomes) as fetch,
            patch.object(tv, "_try_refresh_token", return_value=True) as refresh,
        ):
            df = tv.get_hist("AAPL", "NASDAQ")

        assert refresh.call_count == 1
        assert fetch.call_count == 2
        assert df is not None
        assert len(df) == 1

    def test_no_infinite_retry_when_refresh_fails(self, tmp_path):
        tv = TvDatafeed(token_cache_file=tmp_path / ".tv_token.json")
        tv.token = "STALE"

        with (
            patch.object(tv, "_fetch_series", return_value=("", True)) as fetch,
            patch.object(tv, "_try_refresh_token", return_value=False),
        ):
            df = tv.get_hist("AAPL", "NASDAQ")

        assert df is None
        assert fetch.call_count == 1  # gave up, did not loop


# --------------------------------------------------------------------------- #
# async get_hist auth-failure -> refresh -> retry
# --------------------------------------------------------------------------- #


class TestAsyncAuthRetry:
    async def test_async_refreshes_and_retries(self, tmp_path):
        tv = TvDatafeed(token_cache_file=tmp_path / ".tv_token.json")
        tv.token = "STALE"
        fetch = AsyncMock(side_effect=[("", True), (series_with_completed(), False)])

        with (
            patch.object(tv, "_async_fetch_series", fetch),
            patch.object(tv, "_try_refresh_token", return_value=True),
        ):
            df = await tv._do_fetch_symbol_data(
                "AAPL", "NASDAQ", Interval.in_daily, 2, None, False, True
            )

        assert fetch.await_count == 2
        assert df is not None
        assert len(df) == 1


# --------------------------------------------------------------------------- #
# Regression: quote_add_symbols must not carry the force_permission flag
# --------------------------------------------------------------------------- #


class TestQuoteAddSymbolsFlag:
    """Earlier 2.2.x sent ``quote_add_symbols`` as
    ``[session, symbol, {"flags": ["force_permission"]}]``. TradingView rejects
    the extra parameter with ``critical_error: invalid_parameters``; get_hist
    treats that as a (false) auth failure and aborts before the historical
    ``series_completed`` payload arrives, so every fetch returned ``None``. The
    quote channel only carries live prices, never the bars, so the flag must
    not be present.
    """

    def test_quote_add_symbols_omits_force_permission(
        self, mock_create_connection, mock_websocket, tmp_path
    ):
        tv = TvDatafeed(token_cache_file=tmp_path / ".tv_token.json")
        mock_websocket.recv.return_value = series_with_completed()
        tv.get_hist("AAPL", "NASDAQ", n_bars=5)

        sent = [c.args[0] for c in mock_websocket.send.call_args_list]
        quote_add = [m for m in sent if "quote_add_symbols" in m]
        assert quote_add, "expected a quote_add_symbols message to be sent"
        assert all("force_permission" not in m for m in quote_add), (
            "quote_add_symbols must not carry the force_permission flag — "
            "TradingView rejects it as invalid_parameters and the fetch aborts"
        )


# --------------------------------------------------------------------------- #
# Regression: series_completed without a data block must not crash get_hist
# --------------------------------------------------------------------------- #


class TestGetHistNoData:
    def test_returns_none_when_series_completed_without_data(
        self, mock_create_connection, mock_websocket, tmp_path
    ):
        # An invalid/empty symbol completes the series with no "s":[...] block.
        # get_hist must return None, not raise AttributeError.
        tv = TvDatafeed(token_cache_file=tmp_path / ".tv_token.json")
        mock_websocket.recv.return_value = '{"m":"series_completed","p":["cs"]}'
        assert tv.get_hist("BADSYM", "NASDAQ", n_bars=5) is None
