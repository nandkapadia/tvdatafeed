"""Tests for authentication, token caching, and session refresh."""

from __future__ import annotations

import base64
import json
import time
from unittest.mock import MagicMock, patch

import requests

from tvDatafeed import TvDatafeed


def make_jwt(exp: int) -> str:
    """Build a minimal JWT with the given expiry (no real signature)."""
    header = base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).rstrip(b"=").decode()
    return f"{header}.{payload}.signature"


def anon_tv(tmp_path) -> TvDatafeed:
    """Construct an anonymous client with an isolated (empty) cache file."""
    return TvDatafeed(token_cache_file=tmp_path / ".tv_token.json")


# --------------------------------------------------------------------------- #
# WebSocket host selection + bar counting (the 20k-bar fix)
# --------------------------------------------------------------------------- #


class TestWsEndpoint:
    def test_anonymous_uses_public_data_host(self, tmp_path):
        tv = anon_tv(tmp_path)
        tv.token = None
        url, _ = tv._ws_endpoint()
        assert "wss://data.tradingview.com" in url
        assert "prodata" not in url

    def test_authenticated_uses_prodata_host(self, tmp_path):
        tv = anon_tv(tmp_path)
        tv.token = "SOME_JWT"
        url, header = tv._ws_endpoint()
        assert "wss://prodata.tradingview.com" in url
        assert header["Origin"] == "https://www.tradingview.com"


class TestCountUniqueBars:
    def test_counts_distinct_bar_timestamps(self):
        # Two distinct 10-digit unix timestamps, one repeated.
        raw = "[1609459200.0,1.0,2.0][1609459260.0,3.0][1609459200.0,1.0,2.0]"
        assert TvDatafeed._count_unique_bars(raw) == 2

    def test_empty_payload_is_zero(self):
        assert TvDatafeed._count_unique_bars("") == 0


# --------------------------------------------------------------------------- #
# JWT validation
# --------------------------------------------------------------------------- #


class TestTokenValidation:
    def test_valid_token(self, tmp_path):
        tv = anon_tv(tmp_path)
        assert tv._is_token_valid(make_jwt(int(time.time()) + 10_000)) is True

    def test_expired_token(self, tmp_path):
        tv = anon_tv(tmp_path)
        assert tv._is_token_valid(make_jwt(int(time.time()) - 10)) is False

    def test_malformed_token(self, tmp_path):
        tv = anon_tv(tmp_path)
        assert tv._is_token_valid("not-a-jwt") is False

    def test_token_without_exp(self, tmp_path):
        tv = anon_tv(tmp_path)
        header = base64.urlsafe_b64encode(b"{}").rstrip(b"=").decode()
        payload = base64.urlsafe_b64encode(b'{"foo":"bar"}').rstrip(b"=").decode()
        assert tv._is_token_valid(f"{header}.{payload}.sig") is False


# --------------------------------------------------------------------------- #
# Cache round-trip + cookie persistence
# --------------------------------------------------------------------------- #


class TestCacheAndCookies:
    def test_save_and_load_roundtrip_with_cookies(self, tmp_path):
        tv = anon_tv(tmp_path)
        token = make_jwt(int(time.time()) + 10_000)
        tv._cookies = {"sessionid": "abc", "sessionid_sign": "def"}
        tv._save_token(token)

        loaded = tv._load_cache()
        assert loaded["token"] == token
        assert loaded["cookies"] == {"sessionid": "abc", "sessionid_sign": "def"}

    def test_load_missing_file_returns_empty(self, tmp_path):
        tv = anon_tv(tmp_path)
        tv.token_cache_file = tmp_path / "does-not-exist.json"
        assert tv._load_cache() == {}

    def test_load_corrupt_file_returns_empty(self, tmp_path):
        tv = anon_tv(tmp_path)
        tv.token_cache_file.write_text("{ not valid json")
        assert tv._load_cache() == {}

    def test_store_cookies_keeps_only_session_cookies(self, tmp_path):
        tv = anon_tv(tmp_path)
        tv._cookies = {}
        jar = requests.cookies.RequestsCookieJar()
        jar.set("sessionid", "S1")
        jar.set("sessionid_sign", "S2")
        jar.set("irrelevant", "nope")
        tv._store_cookies(jar)
        assert tv._cookies == {"sessionid": "S1", "sessionid_sign": "S2"}

    def test_store_cookies_merges_without_wiping(self, tmp_path):
        tv = anon_tv(tmp_path)
        tv._cookies = {"sessionid": "old", "sessionid_sign": "keep"}
        jar = requests.cookies.RequestsCookieJar()
        jar.set("sessionid", "rotated")  # only sessionid re-set
        tv._store_cookies(jar)
        # sessionid updated, sessionid_sign preserved
        assert tv._cookies == {"sessionid": "rotated", "sessionid_sign": "keep"}


# --------------------------------------------------------------------------- #
# Token refresh from session cookie
# --------------------------------------------------------------------------- #


class TestRefreshFromSession:
    def test_refresh_no_cookies_returns_none(self, tmp_path):
        tv = anon_tv(tmp_path)
        tv._cookies = {}
        # Should short-circuit without touching the network.
        with patch("tvDatafeed.main.requests.Session") as sess:
            assert tv._refresh_token_from_session() is None
            sess.assert_not_called()

    def test_refresh_scrapes_homepage_token(self, tmp_path):
        # Primary path: auth_token is embedded in the homepage bootstrap.
        tv = anon_tv(tmp_path)
        tv._cookies = {"sessionid": "S", "sessionid_sign": "X"}
        session = MagicMock()
        session.get.return_value.text = 'window.initData={"auth_token":"eyJFRESH","username":"u"};'
        session.get.return_value.raise_for_status.return_value = None
        session.cookies.get.return_value = None
        with patch("tvDatafeed.main.requests.Session", return_value=session):
            assert tv._refresh_token_from_session() == "eyJFRESH"

    def test_refresh_falls_back_to_legacy_json(self, tmp_path):
        # Homepage carries no token -> fall back to the legacy JSON endpoint.
        tv = anon_tv(tmp_path)
        tv._cookies = {"sessionid": "S", "sessionid_sign": "X"}
        session = MagicMock()
        session.get.return_value.text = "<html>no token here</html>"
        session.get.return_value.raise_for_status.return_value = None
        session.get.return_value.json.return_value = {"user": {"auth_token": "NESTED"}}
        session.cookies.get.return_value = None
        with patch("tvDatafeed.main.requests.Session", return_value=session):
            assert tv._refresh_token_from_session() == "NESTED"

    def test_refresh_ambiguous_miss_keeps_cookies(self, tmp_path):
        # Homepage carries no token and the legacy endpoint does not 401: this
        # is indistinguishable from a transient markup change, so the durable
        # cookies must be KEPT for a later retry (not wiped, which would force a
        # CAPTCHA-prone re-login).
        tv = anon_tv(tmp_path)
        tv._cookies = {"sessionid": "S", "sessionid_sign": "X"}
        session = MagicMock()
        session.get.return_value.text = "<html>no token</html>"
        session.get.return_value.status_code = 200
        session.get.return_value.ok = True
        session.get.return_value.json.return_value = {}
        session.get.return_value.raise_for_status.return_value = None
        with patch("tvDatafeed.main.requests.Session", return_value=session):
            assert tv._refresh_token_from_session() is None
        assert tv._cookies == {"sessionid": "S", "sessionid_sign": "X"}

    def test_refresh_explicit_unauthorized_clears_cookies(self, tmp_path):
        # The legacy endpoint explicitly rejects the session cookie (401), so
        # the session really is dead -> drop the cookies.
        tv = anon_tv(tmp_path)
        tv._cookies = {"sessionid": "S", "sessionid_sign": "X"}
        homepage = MagicMock()
        homepage.text = "<html>no token</html>"
        homepage.raise_for_status.return_value = None
        unauthorized = MagicMock()
        unauthorized.status_code = 401
        session = MagicMock()
        session.get.side_effect = [homepage, unauthorized]
        with patch("tvDatafeed.main.requests.Session", return_value=session):
            assert tv._refresh_token_from_session() is None
        assert tv._cookies == {}

    def test_refresh_network_error_returns_none(self, tmp_path):
        tv = anon_tv(tmp_path)
        tv._cookies = {"sessionid": "S"}
        session = MagicMock()
        session.get.side_effect = requests.RequestException("boom")
        with patch("tvDatafeed.main.requests.Session", return_value=session):
            assert tv._refresh_token_from_session() is None


# --------------------------------------------------------------------------- #
# _try_refresh_token concurrency guard
# --------------------------------------------------------------------------- #


class TestTryRefreshToken:
    def test_skips_when_already_refreshed_by_other_thread(self, tmp_path):
        tv = anon_tv(tmp_path)
        tv.token = "NEW"
        # Caller saw "STALE"; current token is already "NEW" -> no refresh.
        with patch.object(tv, "_refresh_token_from_session") as refresh:
            assert tv._try_refresh_token(stale_token="STALE") is True
            refresh.assert_not_called()

    def test_refreshes_and_saves(self, tmp_path):
        tv = anon_tv(tmp_path)
        tv.token = "STALE"
        with patch.object(tv, "_refresh_token_from_session", return_value="FRESH"):
            assert tv._try_refresh_token(stale_token="STALE") is True
        assert tv.token == "FRESH"
        assert tv._load_cache()["token"] == "FRESH"

    def test_falls_back_to_login(self, tmp_path):
        tv = anon_tv(tmp_path)
        tv.token = "STALE"
        tv._credentials = ("user", "pass")
        with (
            patch.object(tv, "_refresh_token_from_session", return_value=None),
            patch.object(tv, "_login_and_get_token", return_value="LOGIN") as login,
        ):
            assert tv._try_refresh_token(stale_token="STALE") is True
            login.assert_called_once()
        assert tv.token == "LOGIN"

    def test_returns_false_when_nothing_works(self, tmp_path):
        tv = anon_tv(tmp_path)
        tv.token = "STALE"
        tv._credentials = (None, None)
        with patch.object(tv, "_refresh_token_from_session", return_value=None):
            assert tv._try_refresh_token(stale_token="STALE") is False


# --------------------------------------------------------------------------- #
# __init__ auth resolution order
# --------------------------------------------------------------------------- #


class TestInitResolutionOrder:
    def test_anonymous_when_no_creds_no_cache(self, tmp_path):
        tv = TvDatafeed(token_cache_file=tmp_path / ".tv_token.json")
        assert tv.token is None

    def test_uses_valid_cached_token(self, tmp_path):
        cache = tmp_path / ".tv_token.json"
        token = make_jwt(int(time.time()) + 10_000)
        cache.write_text(json.dumps({"token": token}))
        tv = TvDatafeed(token_cache_file=cache)
        assert tv.token == token

    def test_refreshes_expired_token_from_session(self, tmp_path):
        cache = tmp_path / ".tv_token.json"
        cache.write_text(
            json.dumps(
                {
                    "token": make_jwt(int(time.time()) - 10),
                    "cookies": {"sessionid": "S", "sessionid_sign": "X"},
                }
            )
        )
        session = MagicMock()
        session.get.return_value.text = '{"auth_token":"eyJREFRESHED"}'
        session.get.return_value.raise_for_status.return_value = None
        session.cookies.get.return_value = None
        with patch("tvDatafeed.main.requests.Session", return_value=session):
            tv = TvDatafeed(token_cache_file=cache)
            # Lazy: __init__ defers the (blocking) refresh so construction never
            # blocks the network; it runs on the first call that needs auth.
            assert tv.token is None
            tv._ensure_authenticated()
        assert tv.token == "eyJREFRESHED"

    def test_login_when_no_session(self, tmp_path):
        cache = tmp_path / ".tv_token.json"
        with patch.object(TvDatafeed, "_login_and_get_token", return_value="LOGIN_TOK") as login:
            tv = TvDatafeed(username="u", password="p", token_cache_file=cache)
            login.assert_called_once()
        assert tv.token == "LOGIN_TOK"


# --------------------------------------------------------------------------- #
# __auth captures session cookies (uses requests.Session, not requests.post)
# --------------------------------------------------------------------------- #


class TestAuthCapturesCookies:
    def test_login_captures_session_cookies(self, tmp_path, mock_requests_session):
        tv = TvDatafeed(
            username="user", password="pass", token_cache_file=tmp_path / ".tv_token.json"
        )
        # mock_requests_session returns auth_token "test_token_123" + cookies
        assert tv.token == "test_token_123"
        assert tv._cookies == {"sessionid": "sess-123", "sessionid_sign": "sign-456"}
