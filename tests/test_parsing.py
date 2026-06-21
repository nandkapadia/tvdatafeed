"""Tests for data parsing, symbol formatting, and symbol search."""

from __future__ import annotations

import json
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from tvDatafeed import Interval, TvDatafeed

# Name-mangled private staticmethods exposed for unit testing.
parse_data = TvDatafeed._TvDatafeed__parse_data
format_symbol = TvDatafeed._TvDatafeed__format_symbol
create_df = TvDatafeed._TvDatafeed__create_df


def series_msg(rows: list[str]) -> str:
    """Build a TradingView-style series payload from raw value lists."""
    bars = ",".join(f'{{"i":{i},"v":[{r}]}}' for i, r in enumerate(rows))
    return f'~m~100~m~{{"m":"timescale_update","p":["cs",{{"s1":{{"s":[{bars}],"ns":{{}}}}}}]}}'


# --------------------------------------------------------------------------- #
# __parse_data
# --------------------------------------------------------------------------- #


class TestParseData:
    def test_parses_two_bars(self):
        raw = series_msg(
            [
                "1609459200.0,150.0,151.5,149.5,151.0,1000000.0",
                "1609545600.0,151.0,152.5,150.5,152.0,1100000.0",
            ]
        )
        rows = parse_data(raw, False)
        assert len(rows) == 2
        assert rows[0] == [1609459200, 150.0, 151.5, 149.5, 151.0, 1000000.0]
        assert rows[1] == [1609545600, 151.0, 152.5, 150.5, 152.0, 1100000.0]

    def test_datetime_output_is_utc_aware(self):
        raw = series_msg(["1609459200.0,150.0,151.5,149.5,151.0,1000000.0"])
        rows = parse_data(raw, True)
        ts = rows[0][0]
        assert ts.tzinfo is not None
        assert ts.utcoffset().total_seconds() == 0

    def test_missing_volume_does_not_leak_to_next_bar(self):
        # Regression: a bar with no volume must not zero out later bars'
        # volume (the old sticky-flag bug did exactly that).
        raw = series_msg(
            [
                "1609459200.0,150.0,151.5,149.5,151.0",  # no volume
                "1609545600.0,151.0,152.5,150.5,152.0,1100000.0",  # has volume
            ]
        )
        rows = parse_data(raw, False)
        assert rows[0][5] == 0.0  # missing volume -> 0
        assert rows[1][5] == 1100000.0  # later bar keeps its real volume

    def test_parses_bars_across_multiple_pages(self):
        # Regression: the request_more_data paging loop accumulates one
        # "s":[...] block per frame. ALL pages must be parsed, not just the
        # first (the old re.search-first-match dropped pages 2..N silently).
        page1 = series_msg(
            [
                "1609459200.0,1.0,2.0,0.5,1.5,100.0",
                "1609459260.0,1.1,2.1,0.6,1.6,110.0",
            ]
        )
        page2 = series_msg(
            [
                "1609459320.0,1.2,2.2,0.7,1.7,120.0",
                "1609459380.0,1.3,2.3,0.8,1.8,130.0",
            ]
        )
        rows = parse_data(page1 + "\n" + page2, False)
        assert [r[0] for r in rows] == [1609459200, 1609459260, 1609459320, 1609459380]

    def test_dedups_overlapping_bars_keeping_latest(self):
        # request_more_data can resend a bar; the newest values must win and the
        # timestamp must appear only once.
        first = series_msg(["1609459200.0,1.0,2.0,0.5,1.5,100.0"])
        updated = series_msg(["1609459200.0,9.0,9.0,9.0,9.0,999.0"])
        rows = parse_data(first + "\n" + updated, False)
        assert len(rows) == 1
        assert rows[0] == [1609459200, 9.0, 9.0, 9.0, 9.0, 999.0]

    def test_no_series_block_returns_empty(self):
        # series_completed with no data block (e.g. invalid symbol) must return
        # [] rather than raising AttributeError.
        assert parse_data('{"m":"series_completed","p":["cs"]}', True) == []


# --------------------------------------------------------------------------- #
# __format_symbol
# --------------------------------------------------------------------------- #


class TestFormatSymbol:
    def test_plain_symbol(self):
        assert format_symbol("AAPL", "NASDAQ") == "NASDAQ:AAPL"

    def test_already_qualified_symbol(self):
        assert format_symbol("NASDAQ:AAPL", "IGNORED") == "NASDAQ:AAPL"

    def test_futures_contract(self):
        assert format_symbol("CRUDEOIL", "MCX", 1) == "MCX:CRUDEOIL1!"

    def test_invalid_contract_raises(self):
        with pytest.raises(ValueError):
            format_symbol("X", "NSE", "not-an-int")


# --------------------------------------------------------------------------- #
# __create_df
# --------------------------------------------------------------------------- #


class TestCreateDf:
    def test_creates_dataframe(self):
        rows = [[1609459200, 1.0, 2.0, 0.5, 1.5, 100.0]]
        df = create_df(rows, "NASDAQ:AAPL")
        assert isinstance(df, pd.DataFrame)
        assert list(df.columns) == ["symbol", "open", "high", "low", "close", "volume"]
        assert df.iloc[0]["symbol"] == "NASDAQ:AAPL"

    def test_invalid_input_returns_none(self):
        assert create_df("garbage", "SYM") is None


# --------------------------------------------------------------------------- #
# search_symbol (uses module-level requests.get)
# --------------------------------------------------------------------------- #


class TestSearchSymbol:
    def test_strips_html_and_parses(self, tmp_path):
        tv = TvDatafeed(token_cache_file=tmp_path / ".tv_token.json")
        payload = [{"symbol": "<em>AAP</em>L", "exchange": "NASDAQ"}]
        resp = Mock()
        resp.raise_for_status.return_value = None
        resp.text = json.dumps(payload)
        with patch("tvDatafeed.main.requests.get", return_value=resp):
            results = tv.search_symbol("AAPL", "NASDAQ")
        assert results == [{"symbol": "AAPL", "exchange": "NASDAQ"}]

    def test_network_error_returns_empty(self, tmp_path):
        import requests

        tv = TvDatafeed(token_cache_file=tmp_path / ".tv_token.json")
        with patch("tvDatafeed.main.requests.get", side_effect=requests.RequestException):
            assert tv.search_symbol("AAPL") == []


# --------------------------------------------------------------------------- #
# get_token / Interval enum
# --------------------------------------------------------------------------- #


class TestMisc:
    def test_get_token(self, tmp_path):
        tv = TvDatafeed(token_cache_file=tmp_path / ".tv_token.json")
        tv.token = "TOK"
        assert tv.get_token() == "TOK"

    def test_interval_values(self):
        assert Interval.in_1_hour.value == "1H"
        assert Interval.in_daily.value == "1D"
