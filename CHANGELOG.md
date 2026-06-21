# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- 🐛 **Paged data silently truncated to the first ~5k bars**: `__parse_data`
  extracted bars with `re.search` (first match only), so only the first
  `timescale_update` frame was parsed while every `request_more_data` page was
  discarded — the loop *counted* all pages but *returned* one, so large
  `n_bars` requests issued up to 20 wasted round-trips and still returned ~5k
  rows. The parser now collects bars from every frame and dedups by timestamp
  (newest values win), sorted oldest-first. Regression tests in
  `tests/test_parsing.py`.
- 🐛 **`get_hist` crashed on an empty/invalid symbol**: a `series_completed`
  with no data block made `re.search(...).group(1)` raise `AttributeError`,
  escaping the public API. It now returns `None` as documented.
- 🐛 **Auth-error payloads parsed as valid data**: on an auth error that could
  not be refreshed, `get_hist` no longer parses a partial/error payload — it
  returns `None`.
- 🐛 **Live `wait()` could wedge the main loop**: a Seis add/remove that changed
  the soonest trigger woke `wait()` without clearing the interrupt event,
  busy-spinning and never processing another bar. It now clears the event and
  re-parks against the refreshed trigger.
- 🐛 **`_shutdown_consumers` stopped only half the consumers**: it iterated the
  live consumer list while `pop_consumer` mutated it. It now iterates a copy.
- ⚡ **Async fetches no longer stall on a token refresh**: the blocking refresh
  in the async path runs via `asyncio.to_thread`, so one auth failure no longer
  freezes all concurrent `get_hist_async` fetches.
- ⚡ **Construction no longer blocks on the network**: the session-cookie
  refresh is now lazy (runs on first use), so anonymous/offline callers are not
  stalled by up to two 10s HTTP GETs.
- 🐛 **A transient refresh miss no longer discards the session**: cookies are
  dropped only on an explicit `401`/`403`, not on a transient homepage scrape
  miss, so a healthy long-lived session isn't nuked into a CAPTCHA-prone login.
- 🐛 **Torn token reads**: the data host and `set_auth_token` now use a single
  captured token, so a concurrent refresh can't send a token to the wrong host.
- 📦 **Declared the `websocket-client` runtime dependency** (imported by the
  sync path but previously undeclared, breaking clean installs and CI).
- 🧰 Centralized the WebSocket setup sequence and 24 quote fields so the sync
  and async paths can't drift; made `Seis` hashable; un-gitignored the test
  suite; refreshed `CLAUDE.md` and `MANIFEST.in`.

- 🐛 **`get_hist` capped at ~5k bars regardless of `n_bars` or plan**: two
  causes, both fixed. (1) The client always connected to the public
  `wss://data.tradingview.com` host, which caps history at ~5k bars even for
  Premium/Pro accounts — authenticated sessions now use
  `wss://prodata.tradingview.com`, which serves the account's full entitlement
  (e.g. ~20k bars). (2) Only TradingView's initial `create_series` chunk (~5k)
  was read; the fetch now pages back with `request_more_data` until `n_bars` is
  reached, the series is exhausted, or a safety cap is hit. Applied to both the
  sync and async paths; the async `connect` also gets `max_size=None` so the
  larger multi-megabyte series frames are not rejected by the `websockets` 1 MB
  default. Anonymous sessions are unchanged (still the public host).

- 🐛 **Session refresh hitting a retired endpoint**: `_refresh_token_from_session`
  exchanged the durable `sessionid` cookie for a fresh `auth_token` via
  `https://www.tradingview.com/accounts/current/`, which TradingView has retired
  (it now returns a 404 HTML page), so every refresh failed and an expired JWT
  fell back to anonymous access. The token is now scraped from the homepage
  bootstrap (`"auth_token":"…"`), the same source the web app uses, with the
  legacy JSON endpoint kept as a fallback. A browser `User-Agent` is now sent on
  these requests (TradingView 404s plain `python-requests`). With the session
  cookie cached, an expired token self-heals on init — no validity window.
- 🐛 **Authenticated `get_hist` returning `None`**: `quote_add_symbols` was sent
  with an extra `{"flags": ["force_permission"]}` argument that TradingView now
  rejects as `invalid_parameters` (a `critical_error`). Because `get_hist`
  treats any `critical_error` as an auth failure and stops, the fetch aborted
  *before* the historical `series_completed` payload arrived, so every
  authenticated request returned `None`. The quote channel only carries live
  prices (never the bars), so the flag is removed from both the sync and async
  paths. Covered by a regression test in `tests/test_live.py`.

## [2.2.0] - 2025-10-17

### Added
- ⚡ **Async Operations**: Concurrent data fetching for multiple symbols using `websockets` library
  - New `get_hist_multi()` method supports both single and multiple symbols
  - New `get_hist_async()` async method for advanced users
  - **10-50x faster** when fetching multiple symbols (concurrent vs sequential)
  - **Built-in rate limiting** with configurable `max_concurrent` parameter (default: 20)
  - Maintains backward compatibility with existing `get_hist()` method
- ✅ **Token Caching**: Automatic token persistence to `~/.tv_token.json`
- ✅ **JWT Validation**: Smart token expiration checking without API calls
- ✅ **CAPTCHA Support**: Browser-based authentication fallback with user guidance
- ✅ **New Intervals**: Added `in_3_monthly`, `in_6_monthly`, and `in_yearly` timeframes
- ✅ **Helper Script**: Interactive `token_helper.py` for token management
- ✅ **Documentation**: Added QUICKSTART.md and TOKEN_SETUP_GUIDE.md
- ✅ **Comprehensive Test Suite**: 70+ tests with pytest, GitHub Actions CI/CD

### Changed
- 📦 **PyPI Package Name**: Changed from `tvdatafeed` to `tvdatafeed-enhanced` (module name remains `tvDatafeed`)
- 🔧 **Dependencies**: Migrated from `websocket-client` to `websockets` library for async support
- Updated authentication flow to use JWT expiration validation
- Improved error handling and connection reliability
- Modernized codebase for Python 3.10+ with type hints
- Enhanced WebSocket connection management with context managers
- Updated all documentation with modern Python conventions
- Refactored data parsing into separate `__parse_data()` method for better code reuse

### Fixed
- Anonymous authentication now properly uses "unauthorized_user_token"
- Token validation no longer relies on unreliable HTTP endpoints
- Improved thread safety with proper lock management
- Fixed various edge cases in authentication flow

## [2.1.1] - Previous Release

### Changed
- Various bug fixes and improvements
- Updated dependencies

## [2.0.0] - Major Release

### Changed
- Removed Selenium dependency (thanks to @stefanomorni)
- Not backward compatible - breaking changes

### Added
- Live data streaming feature (TvDatafeedLive)
- Consumer and Seis architecture for real-time data

---

For more details, see the [README.md](README.md) and [GitHub releases](https://github.com/rongardF/tvdatafeed/releases).
