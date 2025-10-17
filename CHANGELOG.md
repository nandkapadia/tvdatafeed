# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
