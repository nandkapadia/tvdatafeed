"""TradingView data feed client for historical and real-time market data."""

from __future__ import annotations

import asyncio
import datetime
import enum
import json
import logging
import random
import re
import string
import threading
import webbrowser
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

import pandas as pd
import requests
from websocket import WebSocket, create_connection
from websockets import connect

if TYPE_CHECKING:
    from collections.abc import Generator

logger = logging.getLogger(__name__)

# Sentinel so _ws_endpoint/_websocket_connection can distinguish "use the
# current self.token" from an explicitly-passed token (which may be None for an
# anonymous fetch). Passing the captured token explicitly avoids a torn read
# where the host is chosen from one token value and set_auth_token sends another.
_USE_CURRENT_TOKEN = object()


class Interval(enum.Enum):
    """Supported time intervals for market data."""

    in_1_minute = "1"
    in_3_minute = "3"
    in_5_minute = "5"
    in_15_minute = "15"
    in_30_minute = "30"
    in_45_minute = "45"
    in_1_hour = "1H"
    in_2_hour = "2H"
    in_3_hour = "3H"
    in_4_hour = "4H"
    in_daily = "1D"
    in_weekly = "1W"
    in_monthly = "1M"
    in_3_monthly = "3M"
    in_6_monthly = "6M"
    in_yearly = "12M"


class TvDatafeed:
    """TradingView data feed client for downloading historical market data.

    Supports both authenticated and anonymous access to TradingView data.
    Authenticated access provides more data and fewer restrictions.

    Args:
        username: TradingView username (optional for anonymous access)
        password: TradingView password (optional for anonymous access)
        token_cache_file: Path to cache authentication token
    """

    __user_url: ClassVar[str] = "https://www.tradingview.com/accounts/current/"
    __home_url: ClassVar[str] = "https://www.tradingview.com/"
    __sign_in_url: ClassVar[str] = "https://www.tradingview.com/accounts/signin/"
    __search_url: ClassVar[str] = (
        "https://symbol-search.tradingview.com/symbol_search/?text={}&hl=1&exchange={}&lang=en&type=&domain=production"
    )
    # A browser-like User-Agent is required: TradingView serves a 404 HTML page
    # to plain `python-requests` for authenticated HTML endpoints.
    __browser_ua: ClassVar[str] = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    )
    __ws_headers: ClassVar[dict[str, str]] = {"Origin": "https://data.tradingview.com"}
    __signin_headers: ClassVar[dict[str, str]] = {
        "Referer": "https://www.tradingview.com",
        "User-Agent": __browser_ua,
    }
    # Max number of request_more_data pages per fetch (each yields ~5k bars).
    __max_more_requests: ClassVar[int] = 20
    __ws_timeout: ClassVar[int] = 30

    # Durable login cookies that can be exchanged for fresh auth tokens.
    # `sessionid` (with "remember me") is long-lived, just like the browser
    # session, so we persist it and re-mint short-lived auth_tokens from it
    # instead of logging in (and risking CAPTCHA) every time the JWT expires.
    _SESSION_COOKIES: ClassVar[tuple[str, ...]] = ("sessionid", "sessionid_sign")

    # Quote fields requested for every series fetch. Defined once so the sync
    # and async fetch paths cannot drift apart.
    _QUOTE_FIELDS: ClassVar[tuple[str, ...]] = (
        "ch",
        "chp",
        "current_session",
        "description",
        "local_description",
        "language",
        "exchange",
        "fractional",
        "is_tradable",
        "lp",
        "lp_time",
        "minmov",
        "minmove2",
        "original_name",
        "pricescale",
        "pro_name",
        "short_name",
        "type",
        "update_mode",
        "volume",
        "currency_code",
        "rchp",
        "rtc",
    )

    def __init__(
        self,
        username: str | None = None,
        password: str | None = None,
        token_cache_file: str | Path = "~/.tv_token.json",
    ) -> None:
        """Initialize TradingView data feed client."""
        self.ws_debug: bool = False
        self.token_cache_file = Path(token_cache_file).expanduser()
        self._lock = threading.Lock()
        self._ws_lock = threading.Lock()
        self._token_lock = threading.Lock()

        # Durable login cookies and credentials, used to refresh the
        # short-lived auth_token without a full (CAPTCHA-prone) re-login.
        self._cookies: dict[str, str] = {}
        self._credentials: tuple[str | None, str | None] = (username, password)

        # Load whatever we cached previously (token + session cookies).
        cached = self._load_cache()
        cached_token = cached.get("token")
        self._cookies = cached.get("cookies") or {}

        # Whether self.token reflects a finished auth attempt. When False, a
        # session-cookie refresh is still pending and runs lazily on first use
        # (see _ensure_authenticated), so construction never blocks on the
        # network for anonymous/offline callers.
        self._token_initialized = True
        self.token: str | None = None

        if cached_token and self._is_token_valid(cached_token):
            # Fast path: the cached JWT is still good.
            self.token = cached_token
            logger.info("Using cached authentication token")
        elif username and password:
            # Explicit credentials: authenticate eagerly, as requested.
            self.token = self._login_and_get_token(username, password)
            self._save_token(self.token)
            logger.info("Logged in successfully and cached token")
        elif self._cookies:
            # JWT expired but we have saved session cookies; defer the
            # (network) refresh to first use instead of blocking __init__.
            self._token_initialized = False
        else:
            logger.warning("Using anonymous access - data may be limited")

    def _load_cache(self) -> dict:
        """Load cached authentication state from disk.

        Returns the raw cache payload (``token`` and ``cookies``) without
        validating the token - an expired token is fine here because the
        cached session cookies can still be used to refresh it.

        Returns:
            Cache dict (possibly empty)
        """
        if not self.token_cache_file.exists():
            return {}

        try:
            data = json.loads(self.token_cache_file.read_text())
            return data if isinstance(data, dict) else {}
        except Exception as e:
            logger.debug("Failed to load token cache: %s", e)
            return {}

    def _is_token_valid(self, token: str) -> bool:
        """Validate authentication token by checking JWT expiration.

        Args:
            token: Authentication token to validate

        Returns:
            True if token is valid and not expired, False otherwise
        """
        try:
            import base64

            # Decode JWT payload (middle part between dots)
            parts = token.split(".")
            if len(parts) != 3:
                logger.debug("Invalid JWT format")
                return False

            payload = parts[1]

            # Add padding if needed for base64 decoding
            padding = 4 - len(payload) % 4
            if padding != 4:
                payload += "=" * padding

            # Decode and parse payload
            decoded = base64.urlsafe_b64decode(payload)
            data = json.loads(decoded)

            # Check expiration
            exp = data.get("exp")
            if not exp:
                logger.debug("Token has no expiration claim")
                return False

            # Compare with current time (use timezone-aware datetime)
            exp_time = datetime.datetime.fromtimestamp(exp, tz=datetime.timezone.utc)
            now = datetime.datetime.now(datetime.timezone.utc)

            is_valid = now < exp_time
            if not is_valid:
                logger.debug("Token expired at %s", exp_time)

            return is_valid

        except Exception as e:
            logger.debug("Token validation failed: %s", e)
            return False

    def _save_token(self, token: str) -> None:
        """Save authentication token (and session cookies) to cache file.

        Args:
            token: Authentication token to cache
        """
        try:
            self.token_cache_file.parent.mkdir(parents=True, exist_ok=True)
            payload: dict = {"token": token}
            if self._cookies:
                payload["cookies"] = self._cookies
            self.token_cache_file.write_text(json.dumps(payload))
        except Exception as e:
            logger.warning("Failed to save token: %s", e)

    def _store_cookies(self, cookie_jar) -> None:
        """Merge durable session cookies from a response into the cache.

        Only the long-lived session cookies are kept. Existing values are
        preserved when a response doesn't re-set them (TradingView only
        rotates the session cookie occasionally).

        Args:
            cookie_jar: A requests CookieJar from a login/refresh response
        """
        for name in self._SESSION_COOKIES:
            value = cookie_jar.get(name)
            if value:
                self._cookies[name] = value

    def _refresh_token_from_session(self) -> str | None:
        """Mint a fresh auth_token from the saved session cookies.

        Mirrors how the TradingView web app exchanges the long-lived
        ``sessionid`` cookie for a short-lived auth_token, so an expired
        JWT does not force a username/password login (and possible CAPTCHA).

        Returns:
            Fresh auth_token, or None if there is no usable session
        """
        if not self._cookies:
            return None

        session = requests.Session()
        session.cookies.update(self._cookies)

        # Primary path: the auth_token is embedded in the homepage bootstrap
        # for a logged-in session. TradingView retired the older JSON endpoint
        # (`accounts/current/`), which now returns a 404 HTML page, so we scrape
        # the token the same way the web app bootstraps itself. A browser
        # User-Agent is mandatory or TradingView serves a 404.
        try:
            response = session.get(
                self.__home_url,
                headers=self.__signin_headers,
                timeout=10,
            )
            response.raise_for_status()
            match = re.search(r'"auth_token":"(eyJ[^"]+)"', response.text)
            token = match.group(1) if match else None
        except requests.RequestException as e:
            logger.warning("Failed to refresh token from session: %s", e)
            return None

        # Fallback: if the homepage scrape found nothing, try the legacy JSON
        # endpoint in case TradingView restores it.
        if not token:
            try:
                response = session.get(
                    self.__user_url,
                    headers=self.__signin_headers,
                    timeout=10,
                )
                if response.status_code in (401, 403):
                    # The server explicitly rejected the session cookie, so it
                    # really is dead - drop it and fall back to a full login.
                    logger.info("Saved session rejected by server - re-login required")
                    self._cookies = {}
                    return None
                if response.ok:
                    data = response.json()
                    token = data.get("auth_token") or data.get("user", {}).get("auth_token")
            except (requests.RequestException, ValueError):
                return None

        if not token:
            # We could not mint a token but the server never explicitly
            # rejected the session (most likely a transient homepage markup
            # change or rate-limit). Keep the cookies so a later attempt can
            # retry instead of forcing a CAPTCHA-prone re-login.
            logger.info("Could not refresh token from session; keeping cookies for retry")
            return None

        # Persist any rotated session cookie so the session stays alive.
        self._store_cookies(session.cookies)
        return token

    def _ensure_authenticated(self) -> None:
        """Lazily mint a token from saved session cookies on first use.

        Construction defers the (blocking) session refresh so anonymous/offline
        callers are not stalled; the first call that needs auth triggers it
        exactly once, thread-safely.
        """
        if self._token_initialized:
            return

        with self._token_lock:
            if self._token_initialized:
                return
            refreshed = self._refresh_token_from_session()
            if refreshed:
                self.token = refreshed
                self._save_token(self.token)
                logger.info("Refreshed authentication token from saved session")
            else:
                logger.warning("Saved session could not be refreshed - using anonymous access")
            self._token_initialized = True

    def _try_refresh_token(self, stale_token: str | None = None) -> bool:
        """Refresh the auth_token in-place after it was rejected.

        Thread-safe: concurrent callers that observed the same stale token
        only trigger a single refresh. Falls back to a full login when the
        session cookie is also dead but credentials are available.

        Args:
            stale_token: The token that was just rejected, if known

        Returns:
            True if ``self.token`` now holds a usable token
        """
        with self._token_lock:
            # Another thread may have already refreshed since we failed.
            if stale_token is not None and self.token != stale_token:
                return True

            token = self._refresh_token_from_session()

            if not token:
                username, password = self._credentials
                if username and password:
                    try:
                        token = self._login_and_get_token(username, password)
                    except ValueError as e:
                        logger.error("Re-login failed: %s", e)
                        token = None

            if token:
                self.token = token
                self._save_token(token)
                return True

        return False

    def _login_and_get_token(self, username: str, password: str) -> str:
        """Authenticate with TradingView and get token.

        Args:
            username: TradingView username
            password: TradingView password

        Returns:
            Authentication token

        Raises:
            ValueError: If login fails
        """
        token = self.__auth(username, password)
        if not token:
            raise ValueError("Login failed - check your credentials")
        return token

    def _handle_captcha_login(self, username: str) -> str | None:
        """Handle login when CAPTCHA is required.

        Opens browser for user to complete CAPTCHA and login manually.
        Attempts to extract token from browser cookies or prompts user.

        Args:
            username: TradingView username

        Returns:
            Authentication token or None on failure
        """
        logger.info("Opening browser for manual login with CAPTCHA...")

        # Open TradingView login page in browser
        login_url = "https://www.tradingview.com/accounts/signin/"
        try:
            webbrowser.open(login_url)
            logger.info("Browser opened. Please complete login with CAPTCHA.")
        except Exception as e:
            logger.warning("Failed to open browser automatically: %s", e)
            logger.info("Please open this URL manually: %s", login_url)

        # Try to extract token from browser cookies
        token = self._extract_token_from_browser()
        if token:
            logger.info("Successfully extracted token from browser!")
            return token

        # Fallback: Instruct user to provide token manually
        print("\n" + "=" * 70)
        print("CAPTCHA REQUIRED - Manual Authentication Needed")
        print("=" * 70)
        print("\n⚠️  NOTE: Browser sessionid does NOT work for API authentication!")
        print("You need to extract the auth_token from the login API response.")
        print("\nA browser window has been opened (or open this URL manually):")
        print(f"  {login_url}")
        print("\nOption 1: Use Network Tab (Recommended):")
        print("  1. Open browser DevTools BEFORE logging in:")
        print("     - Chrome/Edge: Press F12 or Ctrl+Shift+I (Cmd+Option+I on Mac)")
        print("     - Firefox: Press F12 or Ctrl+Shift+I (Cmd+Option+I on Mac)")
        print("  2. Go to the 'Network' tab")
        print("  3. Keep DevTools open and complete CAPTCHA + login")
        print("  4. After login, find the 'signin' request in Network tab")
        print("  5. Click it, go to 'Response' tab")
        print('  6. Look for: {"user":{"auth_token":"..."')
        print("  7. Copy the auth_token value (long string)")
        print("\nOption 2: Use Console (if login already complete):")
        print("  1. Open browser DevTools")
        print("  2. Go to the 'Console' tab")
        print("  3. Paste and run this command:")
        print()
        print("     (function() {")
        print("       // Check cookies")
        print("       const cookieMatch = document.cookie.match(/authToken=([^;]+)/);")
        print("       if (cookieMatch) return cookieMatch[1];")
        print("       ")
        print("       // Check localStorage")
        print("       for (let key of Object.keys(localStorage)) {")
        print(
            '         if (key.toLowerCase().includes("auth") || key.toLowerCase().includes("token")) {'
        )
        print("           const val = localStorage.getItem(key);")
        print("           if (val && val.length > 50) return val;")
        print("         }")
        print("       }")
        print("       ")
        print("       // Check sessionStorage")
        print("       for (let key of Object.keys(sessionStorage)) {")
        print(
            '         if (key.toLowerCase().includes("auth") || key.toLowerCase().includes("token")) {'
        )
        print("           const val = sessionStorage.getItem(key);")
        print("           if (val && val.length > 50) return val;")
        print("         }")
        print("       }")
        print("       ")
        print('       return "Token not found. Run the commands below to see all storage.";')
        print("     })();")
        print()
        print("  5. If token not found, run these to see all storage:")
        print("     Object.keys(localStorage);")
        print("     Object.keys(sessionStorage);")
        print()
        print("  6. Copy the token (long string) that appears")
        print("     (If you see 'Token not found', look for keys with 'auth' or 'token')")
        print("\nAlternatively, if you have browser_cookie3 installed,")
        print("the token will be automatically extracted after you login.")
        print("=" * 70 + "\n")

        # Wait for user to complete login and optionally enter token
        try:
            user_input = input(
                "Enter auth token (or press Enter to retry auto-extraction): "
            ).strip()

            if user_input:
                # Validate token format. auth_tokens are JWTs: three
                # base64url segments (chars A-Za-z0-9-_) joined by dots.
                if (
                    len(user_input) > 20
                    and user_input.replace("-", "").replace("_", "").replace(".", "").isalnum()
                ):
                    logger.info("Token received from user input")
                    return user_input
                else:
                    logger.error("Invalid token format")
                    return None
            else:
                # Retry extraction
                logger.info("Retrying token extraction from browser...")
                token = self._extract_token_from_browser()
                if token:
                    logger.info("Successfully extracted token on retry!")
                    return token
                else:
                    logger.error("Failed to extract token. Please try manual entry.")
                    return None

        except (KeyboardInterrupt, EOFError):
            logger.warning("Login cancelled by user")
            return None

    def _extract_token_from_browser(self) -> str | None:
        """Extract TradingView auth token from browser cookies.

        Requires browser_cookie3 package (optional dependency).
        Looks for: authToken or auth_token cookies.

        NOTE: sessionid is NOT extracted as it only works for browser sessions,
        not for API/WebSocket authentication. The API requires a specific
        auth_token which is only available in the POST response body.

        Returns:
            Auth token if found, None otherwise
        """
        try:
            import browser_cookie3

            # Try different browsers
            browsers = [
                ("Chrome", browser_cookie3.chrome),
                ("Firefox", browser_cookie3.firefox),
                ("Edge", browser_cookie3.edge),
                ("Safari", browser_cookie3.safari),
            ]

            for browser_name, browser_func in browsers:
                try:
                    logger.debug("Trying to extract token from %s...", browser_name)
                    cookies = browser_func(domain_name=".tradingview.com")

                    # Look for various auth-related cookies in order of preference
                    auth_cookies = {}
                    for cookie in cookies:
                        auth_cookies[cookie.name] = cookie.value

                    # Priority order: authToken > auth_token. These are the
                    # JWT used directly for WebSocket auth. (The sessionid
                    # cookie can't be sent to the WS, but it is captured
                    # separately to refresh the JWT - see _store_cookies.)
                    if "authToken" in auth_cookies:
                        logger.info("Found authToken in %s cookies", browser_name)
                        return auth_cookies["authToken"]
                    elif "auth_token" in auth_cookies:
                        logger.info("Found auth_token in %s cookies", browser_name)
                        return auth_cookies["auth_token"]

                except Exception as e:
                    logger.debug("Could not access %s cookies: %s", browser_name, e)
                    continue

            logger.debug("No auth-related cookies found in browser")
            return None

        except ImportError:
            logger.debug("browser_cookie3 not installed. Install with: pip install browser-cookie3")
            return None
        except Exception as e:
            logger.debug("Error extracting token from browser: %s", e)
            return None

    def __auth(self, username: str, password: str) -> str | None:
        """Authenticate with TradingView.

        Args:
            username: TradingView username
            password: TradingView password

        Returns:
            Authentication token or None on failure
        """
        try:
            # Use a Session so the durable login cookies (sessionid) are
            # captured from the response and can later refresh the token.
            session = requests.Session()
            response = session.post(
                self.__sign_in_url,
                data={"username": username, "password": password, "remember": "on"},
                headers=self.__signin_headers,
                timeout=10,
            )
            response.raise_for_status()

            data = response.json()

            # Check for CAPTCHA requirement
            if "error" in data and "captcha" in str(data.get("error", "")).lower():
                logger.warning("CAPTCHA required for login")
                return self._handle_captcha_login(username)

            if "user" not in data or "auth_token" not in data["user"]:
                logger.error("Invalid login response format: %s", data)
                # Try browser-based fallback
                return self._handle_captcha_login(username)

            # Persist the session cookies for future token refreshes.
            self._store_cookies(session.cookies)
            return data["user"]["auth_token"]

        except requests.RequestException as e:
            logger.error("Network error during authentication: %s", e)
            return None
        except (KeyError, ValueError) as e:
            logger.error("Authentication failed: %s", e)
            return None

    @contextmanager
    def _websocket_connection(
        self, token: object = _USE_CURRENT_TOKEN
    ) -> Generator[WebSocket, None, None]:
        """Create and manage WebSocket connection lifecycle.

        Args:
            token: Auth token used to pick the data host. Pass the value
                captured for this fetch (even ``None``) so the host and the
                later ``set_auth_token`` agree under a concurrent refresh.

        Yields:
            Active WebSocket connection

        Example:
            with self._websocket_connection(token) as ws:
                ws.send(message)
        """
        ws = None
        try:
            with self._ws_lock:
                logger.debug("Creating WebSocket connection")
                url, header = self._ws_endpoint(token)
                ws = create_connection(
                    url,
                    header=header,
                    timeout=self.__ws_timeout,
                )
            yield ws
        finally:
            if ws:
                try:
                    ws.close()
                except Exception as e:
                    logger.debug("Error closing WebSocket: %s", e)

    def _ws_endpoint(self, token: object = _USE_CURRENT_TOKEN) -> tuple[str, dict]:
        """Pick the WebSocket data host based on auth status.

        Authenticated (Premium/Pro) sessions use the ``prodata`` host, which
        serves the account's full history entitlement (e.g. ~20k bars).
        Anonymous sessions use the public ``data`` host, which caps history at
        ~5k bars no matter how many are requested.

        Args:
            token: Token to base the choice on. Omitted -> use ``self.token``;
                pass it explicitly (even ``None``) to avoid a torn read.
        """
        if token is _USE_CURRENT_TOKEN:
            token = self.token
        if token:
            return (
                "wss://prodata.tradingview.com/socket.io/websocket",
                {"Origin": "https://www.tradingview.com"},
            )
        return ("wss://data.tradingview.com/socket.io/websocket", dict(self.__ws_headers))

    def _series_setup_messages(
        self,
        token: str | None,
        session: str,
        chart_session: str,
        symbol: str,
        interval_value: str,
        n_bars: int,
        extended_session: bool,
    ) -> list[tuple[str, list]]:
        """Build the ordered (func, params) WebSocket setup messages.

        Shared by the sync and async fetch paths so the protocol sequence and
        the quote-field list cannot drift between them.
        """
        auth_token = token if token else "unauthorized_user_token"
        session_type = "extended" if extended_session else "regular"
        symbol_config = f'={{"symbol":"{symbol}","adjustment":"splits","session":"{session_type}"}}'
        return [
            ("set_auth_token", [auth_token]),
            ("chart_create_session", [chart_session, ""]),
            ("quote_create_session", [session]),
            ("quote_set_fields", [session, *self._QUOTE_FIELDS]),
            ("quote_add_symbols", [session, symbol]),
            ("quote_fast_symbols", [session, symbol]),
            ("resolve_symbol", [chart_session, "symbol_1", symbol_config]),
            ("create_series", [chart_session, "s1", "s1", "symbol_1", interval_value, n_bars]),
            ("switch_timezone", [chart_session, "exchange"]),
        ]

    @staticmethod
    def _bar_timestamps(raw: str) -> set[str]:
        """Extract unique bar-timestamp strings from a raw series payload.

        Used to count bars across paged frames without re-parsing them.
        """
        return set(re.findall(r"\[(\d{9,10})\.", raw))

    @staticmethod
    def _count_unique_bars(raw: str) -> int:
        """Count unique bar timestamps in a raw TradingView series payload."""
        return len(TvDatafeed._bar_timestamps(raw))

    @staticmethod
    def __generate_session() -> str:
        """Generate random session ID for quote session.

        Returns:
            Session ID string (format: qs_<random>)
        """
        random_string = "".join(random.choice(string.ascii_lowercase) for _ in range(12))
        return f"qs_{random_string}"

    @staticmethod
    def __generate_chart_session() -> str:
        """Generate random session ID for chart session.

        Returns:
            Chart session ID string (format: cs_<random>)
        """
        random_string = "".join(random.choice(string.ascii_lowercase) for _ in range(12))
        return f"cs_{random_string}"

    @staticmethod
    def __prepend_header(st: str) -> str:
        """Prepend TradingView protocol header to message.

        Args:
            st: Message string

        Returns:
            Message with protocol header
        """
        return f"~m~{len(st)}~m~{st}"

    @staticmethod
    def __construct_message(func: str, param_list: list) -> str:
        """Construct JSON message for WebSocket.

        Args:
            func: Function name
            param_list: List of parameters

        Returns:
            JSON-encoded message
        """
        return json.dumps({"m": func, "p": param_list}, separators=(",", ":"))

    def __create_message(self, func: str, param_list: list) -> str:
        """Create complete WebSocket message with header.

        Args:
            func: Function name
            param_list: List of parameters

        Returns:
            Complete message ready to send
        """
        return self.__prepend_header(self.__construct_message(func, param_list))

    def __send_message(self, ws: WebSocket, func: str, args: list) -> None:
        """Send message through WebSocket.

        Args:
            ws: WebSocket connection
            func: Function name
            args: Message arguments
        """
        message = self.__create_message(func, args)
        if self.ws_debug:
            print(f"Sending: {message}")
        ws.send(message)

    @staticmethod
    def __parse_data(raw_data: str, is_return_dataframe: bool) -> list[list]:
        """Parse raw WebSocket data into a list of OHLCV rows.

        The paging loop accumulates one ``"s":[...]`` block per timescale_update
        frame, so we collect bars from EVERY block (not just the first) and
        dedup by timestamp - request_more_data can resend overlapping bars.

        Args:
            raw_data: Raw WebSocket response data
            is_return_dataframe: Whether to format timestamp for DataFrame

        Returns:
            List of [timestamp, open, high, low, close, volume] rows sorted
            oldest-first. Empty if the response carried no series data.
        """
        bars_by_epoch: dict[int, list] = {}

        for block in re.findall('"s":\\[(.+?)\\}\\]', raw_data):
            for xi in block.split(',{"'):
                parts = re.split("\\[|:|,|\\]", xi)
                try:
                    epoch = int(float(parts[4]))
                except (ValueError, IndexError):
                    continue

                # Indices 5-9 are open, high, low, close, volume. Evaluate each
                # value independently so a missing volume on one bar doesn't
                # zero out the others (or subsequent bars).
                values = []
                for i in range(5, 10):
                    try:
                        values.append(float(parts[i]))
                    except (ValueError, IndexError):
                        values.append(0.0)
                        if i == 9:
                            logger.debug("No volume data available")

                ts = (
                    datetime.datetime.fromtimestamp(epoch, tz=datetime.timezone.utc)
                    if is_return_dataframe
                    else epoch
                )
                # Later frames carry newer values for a repeated timestamp.
                bars_by_epoch[epoch] = [ts, *values]

        return [bars_by_epoch[epoch] for epoch in sorted(bars_by_epoch)]

    @staticmethod
    def __create_df(parsed_data: list[list], symbol: str) -> pd.DataFrame | None:
        """Create pandas DataFrame from parsed OHLCV data.

        Args:
            parsed_data: List of [timestamp, open, high, low, close, volume] rows
            symbol: Symbol name for the data

        Returns:
            DataFrame with OHLCV data or None on error
        """
        try:
            df = pd.DataFrame(
                parsed_data, columns=["datetime", "open", "high", "low", "close", "volume"]
            ).set_index("datetime")
            df.insert(0, "symbol", value=symbol)
            return df

        except (AttributeError, IndexError, ValueError) as e:
            logger.error("Failed to create DataFrame - check exchange and symbol: %s", e)
            return None

    @staticmethod
    def __format_symbol(symbol: str, exchange: str, contract: int | None = None) -> str:
        """Format symbol string for TradingView.

        Args:
            symbol: Symbol name
            exchange: Exchange name
            contract: Futures contract number (None for spot)

        Returns:
            Formatted symbol string

        Raises:
            ValueError: If contract type is invalid
        """
        match (symbol, contract):
            case (s, _) if ":" in s:
                return s
            case (s, None):
                return f"{exchange}:{s}"
            case (s, c) if isinstance(c, int):
                return f"{exchange}:{s}{c}!"
            case _:
                raise ValueError("Invalid contract - must be int or None")

    def get_hist(
        self,
        symbol: str,
        exchange: str = "NSE",
        interval: Interval = Interval.in_daily,
        n_bars: int = 10,
        fut_contract: int | None = None,
        extended_session: bool = False,
    ) -> pd.DataFrame | None:
        """Get historical market data from TradingView.

        Args:
            symbol: Symbol name (e.g., 'NIFTY', 'AAPL')
            exchange: Exchange name (e.g., 'NSE', 'NASDAQ')
            interval: Time interval for bars
            n_bars: Number of bars to fetch
            fut_contract: Futures contract number (None for spot, 1 for front month)
            extended_session: Include extended trading hours

        Returns:
            DataFrame with columns: symbol, open, high, low, close, volume
            Returns None on error

        Raises:

        Example:
            >>> tv = TvDatafeed(username='user', password='pass')
            >>> data = tv.get_hist('AAPL', 'NASDAQ', Interval.in_1_hour, n_bars=100)
        """
        symbol = self.__format_symbol(symbol=symbol, exchange=exchange, contract=fut_contract)
        interval_value = interval.value
        self._ensure_authenticated()

        # One initial attempt plus one retry after a token refresh, in case
        # the cached auth_token was rejected as expired/invalid.
        for attempt in range(2):
            token_used = self.token
            raw_data, auth_error = self._fetch_series(
                symbol, interval_value, n_bars, extended_session
            )

            if auth_error:
                if attempt == 0 and self._try_refresh_token(token_used):
                    logger.info("Auth token rejected for %s - refreshed, retrying", symbol)
                    continue
                # Don't parse a partial/error payload as if it were valid data.
                logger.error("TradingView rejected the request for %s", symbol)
                return None

            if not raw_data or "series_completed" not in raw_data:
                logger.error("No valid data received for %s", symbol)
                return None

            parsed_data = self.__parse_data(raw_data, is_return_dataframe=True)
            if not parsed_data:
                logger.error("No series data in response for %s", symbol)
                return None
            return self.__create_df(parsed_data, symbol)

        return None

    def _fetch_series(
        self,
        symbol: str,
        interval_value: str,
        n_bars: int,
        extended_session: bool,
    ) -> tuple[str, bool]:
        """Run one WebSocket fetch for a symbol's series.

        Args:
            symbol: Fully-formatted symbol (e.g. "NASDAQ:AAPL")
            interval_value: TradingView interval string
            n_bars: Number of bars to request
            extended_session: Include extended trading hours

        Returns:
            Tuple of (raw_data, auth_error). ``auth_error`` is True when
            TradingView rejected the request (e.g. an expired token), which
            signals the caller to refresh the token and retry.
        """
        session = self.__generate_session()
        chart_session = self.__generate_chart_session()
        raw_data = ""
        auth_error = False
        # Capture the token once so the host choice and set_auth_token agree
        # even if another thread refreshes the token mid-fetch.
        token = self.token

        try:
            with self._websocket_connection(token) as ws:
                for func, params in self._series_setup_messages(
                    token,
                    session,
                    chart_session,
                    symbol,
                    interval_value,
                    n_bars,
                    extended_session,
                ):
                    self.__send_message(ws, func, params)

                # Collect response data, paging back with request_more_data:
                # TradingView's initial series response is capped (~5k bars),
                # so we keep asking for more until we have n_bars, the series is
                # exhausted (no growth between pages), or we hit a safety cap.
                # Bar timestamps are counted incrementally (per frame) rather
                # than re-scanning the whole accumulated buffer each page.
                logger.debug("Fetching data for %s...", symbol)
                seen_bars: set[str] = set()
                more_requests = 0
                prev_bars = -1

                while True:
                    try:
                        result = ws.recv()
                    except Exception as e:
                        logger.error("WebSocket receive error for %s: %s", symbol, e)
                        break

                    raw_data += result + "\n"

                    # The server rejected us (commonly an expired token);
                    # stop and let the caller decide whether to refresh.
                    if "protocol_error" in result or "critical_error" in result:
                        auth_error = True
                        logger.warning("TradingView reported an error for %s: %s", symbol, result)
                        break

                    seen_bars.update(self._bar_timestamps(result))

                    if "series_completed" in result:
                        bars = len(seen_bars)
                        if (
                            bars >= n_bars
                            or bars == prev_bars
                            or more_requests >= self.__max_more_requests
                        ):
                            break
                        prev_bars = bars
                        more_requests += 1
                        self.__send_message(ws, "request_more_data", [chart_session, "s1", 10000])

        except Exception as e:
            logger.error("Failed to get historical data for %s: %s", symbol, e)

        return raw_data, auth_error

    async def __fetch_symbol_data(
        self,
        symbol: str,
        exchange: str,
        interval: Interval,
        n_bars: int,
        fut_contract: int | None,
        extended_session: bool,
        dataFrame: bool,
        semaphore: asyncio.Semaphore | None = None,
    ) -> pd.DataFrame | list[list] | None:
        """Asynchronously fetch historical data for a single symbol.

        Args:
            symbol: Symbol name
            exchange: Exchange name
            interval: Time interval
            n_bars: Number of bars to fetch
            fut_contract: Futures contract number
            extended_session: Include extended trading hours
            dataFrame: Return as DataFrame (True) or list (False)
            semaphore: Optional semaphore for rate limiting

        Returns:
            DataFrame or list of OHLCV data, or None on error
        """
        # Use semaphore if provided for rate limiting
        if semaphore:
            async with semaphore:
                return await self._do_fetch_symbol_data(
                    symbol, exchange, interval, n_bars, fut_contract, extended_session, dataFrame
                )
        else:
            return await self._do_fetch_symbol_data(
                symbol, exchange, interval, n_bars, fut_contract, extended_session, dataFrame
            )

    async def _do_fetch_symbol_data(
        self,
        symbol: str,
        exchange: str,
        interval: Interval,
        n_bars: int,
        fut_contract: int | None,
        extended_session: bool,
        dataFrame: bool,
    ) -> pd.DataFrame | list[list] | None:
        """Internal method to actually fetch symbol data."""
        symbol_formatted = self.__format_symbol(symbol, exchange, fut_contract)
        interval_value = interval.value
        # Lazy auth refresh is blocking; run it off the event loop.
        await asyncio.to_thread(self._ensure_authenticated)

        # One initial attempt plus one retry after a token refresh.
        for attempt in range(2):
            token_used = self.token
            raw_data, auth_error = await self._async_fetch_series(
                symbol_formatted, interval_value, n_bars, extended_session
            )

            if auth_error:
                # The refresh does blocking network I/O - keep it off the loop
                # so other concurrent fetches aren't stalled.
                if attempt == 0 and await asyncio.to_thread(self._try_refresh_token, token_used):
                    logger.info("Auth token rejected for %s - refreshed, retrying", symbol)
                    continue
                logger.error("TradingView rejected the request for %s", symbol)
                return None

            if not raw_data or "series_completed" not in raw_data:
                logger.error("No valid data received for %s", symbol)
                return None

            parsed_data = self.__parse_data(raw_data, dataFrame)
            if not parsed_data:
                logger.error("No series data in response for %s", symbol)
                return None
            if dataFrame:
                return self.__create_df(parsed_data, symbol_formatted)
            return parsed_data

        return None

    async def _async_fetch_series(
        self,
        symbol_formatted: str,
        interval_value: str,
        n_bars: int,
        extended_session: bool,
    ) -> tuple[str, bool]:
        """Run one async WebSocket fetch for a symbol's series.

        Returns:
            Tuple of (raw_data, auth_error) - see :meth:`_fetch_series`.
        """
        session = self.__generate_session()
        chart_session = self.__generate_chart_session()
        raw_data = ""
        auth_error = False
        # Capture the token once so the host choice and set_auth_token agree
        # even if another coroutine refreshes the token mid-fetch.
        token = self.token

        try:
            ws_url, ws_header = self._ws_endpoint(token)
            ws_origin = ws_header["Origin"]
            async with connect(
                ws_url,
                origin=ws_origin,
                open_timeout=self.__ws_timeout,
                close_timeout=10,
                # TradingView sends large series frames (>1 MB for big n_bars);
                # disable the websockets library's default 1 MB frame cap.
                max_size=None,
            ) as websocket:
                for func, params in self._series_setup_messages(
                    token,
                    session,
                    chart_session,
                    symbol_formatted,
                    interval_value,
                    n_bars,
                    extended_session,
                ):
                    await websocket.send(self.__create_message(func, params))

                # Fetch and parse raw data asynchronously, paging back with
                # request_more_data until we have n_bars (see _fetch_series).
                # Bar timestamps are counted incrementally per frame.
                logger.debug("Fetching async data for %s...", symbol_formatted)
                seen_bars: set[str] = set()
                more_requests = 0
                prev_bars = -1

                while True:
                    try:
                        result = await asyncio.wait_for(websocket.recv(), timeout=self.__ws_timeout)
                    except asyncio.TimeoutError:
                        logger.error("Timed out waiting for data for %s", symbol_formatted)
                        break
                    except Exception as e:
                        logger.error("WebSocket receive error for %s: %s", symbol_formatted, e)
                        break

                    raw_data += result + "\n"

                    if "protocol_error" in result or "critical_error" in result:
                        auth_error = True
                        logger.warning(
                            "TradingView reported an error for %s: %s", symbol_formatted, result
                        )
                        break

                    seen_bars.update(self._bar_timestamps(result))

                    if "series_completed" in result:
                        bars = len(seen_bars)
                        if (
                            bars >= n_bars
                            or bars == prev_bars
                            or more_requests >= self.__max_more_requests
                        ):
                            break
                        prev_bars = bars
                        more_requests += 1
                        await websocket.send(
                            self.__create_message("request_more_data", [chart_session, "s1", 10000])
                        )

        except Exception as e:
            logger.error("Error fetching async data for %s: %s", symbol_formatted, e)

        return raw_data, auth_error

    async def get_hist_async(
        self,
        symbols: list[str],
        exchange: str = "NSE",
        interval: Interval = Interval.in_daily,
        n_bars: int = 10,
        dataFrame: bool = True,
        fut_contract: int | None = None,
        extended_session: bool = False,
        max_concurrent: int = 20,
    ) -> dict[str, pd.DataFrame | list[list] | None]:
        """Fetch historical data for multiple symbols asynchronously.

        This method fetches data for all symbols concurrently, which is much
        faster than fetching them sequentially. Rate limiting prevents overwhelming
        the server or hitting API limits.

        Args:
            symbols: List of symbol names
            exchange: Exchange name (applies to all symbols)
            interval: Time interval for bars
            n_bars: Number of bars to fetch
            dataFrame: Return as DataFrame (True) or list (False)
            fut_contract: Futures contract number
            extended_session: Include extended trading hours
            max_concurrent: Maximum number of concurrent connections (default: 20)
                           Recommended values:
                           - Conservative: 10-15 (safest, unlikely to hit limits)
                           - Moderate: 20-30 (balanced, good for most use cases)
                           - Aggressive: 40-50 (faster but higher risk of rate limiting)

        Returns:
            Dictionary mapping symbol names to their DataFrames or lists

        Example:
            >>> tv = TvDatafeed()
            >>> symbols = ['AAPL', 'GOOGL', 'MSFT']
            >>> # Default rate limiting (20 concurrent)
            >>> data = asyncio.run(tv.get_hist_async(symbols, 'NASDAQ', n_bars=100))
            >>>
            >>> # Conservative rate limiting (10 concurrent)
            >>> data = asyncio.run(tv.get_hist_async(symbols, 'NASDAQ', n_bars=100, max_concurrent=10))
            >>>
            >>> # Or use the synchronous wrapper:
            >>> data = tv.get_hist_multi(symbols, 'NASDAQ', n_bars=100, max_concurrent=15)
        """
        # Create semaphore for rate limiting
        semaphore = asyncio.Semaphore(max_concurrent)
        logger.info(
            "Fetching %d symbols with max %d concurrent connections",
            len(symbols),
            max_concurrent,
        )

        tasks = [
            self.__fetch_symbol_data(
                symbol,
                exchange,
                interval,
                n_bars,
                fut_contract,
                extended_session,
                dataFrame,
                semaphore,
            )
            for symbol in symbols
        ]
        results = await asyncio.gather(*tasks)

        return dict(zip(symbols, results, strict=True))

    def get_hist_multi(
        self,
        symbols: list[str] | str,
        exchange: str = "NSE",
        interval: Interval = Interval.in_daily,
        n_bars: int = 10,
        dataFrame: bool = True,
        fut_contract: int | None = None,
        extended_session: bool = False,
        max_concurrent: int = 20,
    ) -> pd.DataFrame | dict[str, pd.DataFrame | list[list] | None] | list[list] | None:
        """Get historical data for single or multiple symbols.

        This method supports both single symbol and multiple symbols. When
        multiple symbols are provided, data is fetched concurrently for better
        performance with rate limiting to prevent API throttling.

        Args:
            symbols: Single symbol name or list of symbol names
            exchange: Exchange name (applies to all symbols)
            interval: Time interval for bars
            n_bars: Number of bars to fetch
            dataFrame: Return as DataFrame (True) or list (False)
            fut_contract: Futures contract number
            extended_session: Include extended trading hours
            max_concurrent: Maximum concurrent connections (default: 20)
                           **Recommended Settings:**
                           - **Conservative (10-15)**: Safest, unlikely to hit limits
                           - **Moderate (20-30)**: Balanced, good for most use cases
                           - **Aggressive (40-50)**: Faster but higher risk

        Returns:
            - Single symbol: DataFrame or list
            - Multiple symbols: Dict mapping symbol names to DataFrames or lists

        Raises:

        Examples:
            >>> tv = TvDatafeed()
            >>> # Single symbol
            >>> data = tv.get_hist_multi('AAPL', 'NASDAQ', n_bars=100)
            >>>
            >>> # Multiple symbols with default rate limiting (20 concurrent)
            >>> symbols = ['AAPL', 'GOOGL', 'MSFT', 'TSLA', 'AMZN']
            >>> data = tv.get_hist_multi(symbols, 'NASDAQ', n_bars=100)
            >>> # Returns: {'AAPL': DataFrame, 'GOOGL': DataFrame, ...}
            >>>
            >>> # Conservative rate limiting for large batches
            >>> symbols = [f'SYM{i}' for i in range(100)]
            >>> data = tv.get_hist_multi(symbols, 'NASDAQ', n_bars=100, max_concurrent=15)
            >>>
            >>> # Return as lists instead of DataFrames
            >>> data = tv.get_hist_multi(symbols, 'NASDAQ', n_bars=100, dataFrame=False)
            >>> # Returns: {'AAPL': [[ts, o, h, l, c, v], ...], 'GOOGL': [...], ...}
        """
        # Single symbol: use async method (no semaphore needed)
        if isinstance(symbols, str):
            return asyncio.run(
                self.__fetch_symbol_data(
                    symbols, exchange, interval, n_bars, fut_contract, extended_session, dataFrame
                )
            )

        # Multiple symbols: use async gather with rate limiting
        return asyncio.run(
            self.get_hist_async(
                symbols,
                exchange,
                interval,
                n_bars,
                dataFrame,
                fut_contract,
                extended_session,
                max_concurrent,
            )
        )

    def search_symbol(self, text: str, exchange: str = "") -> list[dict]:
        """Search for symbols on TradingView.

        Args:
            text: Search text
            exchange: Filter by exchange (optional)

        Returns:
            List of matching symbols with metadata

        Example:
            >>> tv = TvDatafeed()
            >>> results = tv.search_symbol('CRUDE', 'MCX')
        """
        url = self.__search_url.format(text, exchange)

        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()

            # Remove HTML tags from response
            clean_text = resp.text.replace("</em>", "").replace("<em>", "")
            return json.loads(clean_text)

        except requests.RequestException as e:
            logger.error("Symbol search failed: %s", e)
            return []
        except json.JSONDecodeError as e:
            logger.error("Failed to parse search results: %s", e)
            return []

    def get_token(self) -> str | None:
        """Get current authentication token.

        Returns:
            Authentication token or None if not authenticated
        """
        return self.token


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    tv = TvDatafeed()
    print(tv.get_hist("CRUDEOIL", "MCX", fut_contract=1))
    print(tv.get_hist("NIFTY", "NSE", fut_contract=1))
    print(
        tv.get_hist(
            "EICHERMOT",
            "NSE",
            interval=Interval.in_1_hour,
            n_bars=500,
            extended_session=False,
        )
    )
