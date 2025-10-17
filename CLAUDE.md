# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**tvdatafeed** is a Python library for downloading historical and live market data from TradingView. This is a fork of the original StreamAlpha project with live data retrieval features added. The library provides two main classes:

- **TvDatafeed**: Downloads historical OHLCV data from TradingView (up to 5000 bars per request)
- **TvDatafeedLive**: Extends TvDatafeed to provide real-time data streaming via threaded callback architecture

## Installation & Setup

Install the package from the repository:
```bash
pip install --upgrade --no-cache-dir git+https://github.com/rongardF/tvdatafeed.git
```

Install dependencies:
```bash
pip install -r requirements.txt
```

Build the package:
```bash
python setup.py sdist bdist_wheel
```

## Architecture

### Core Components

**main.py (TvDatafeed)**
- Base class providing historical data retrieval via TradingView WebSocket API
- Session-based authentication with token caching (`~/.tv_token.json`)
- WebSocket connection management and message parsing
- Symbol search functionality

**datafeed.py (TvDatafeedLive)**
- Extends TvDatafeed with live data streaming
- Thread-based architecture for monitoring multiple symbol-exchange-interval sets (Seis)
- Main loop waits for interval expirations and retrieves new bars
- Consumer callback pattern for processing new data

**seis.py (Seis)**
- Encapsulates a symbol-exchange-interval set
- Manages Consumer instances for each data stream
- Provides convenience methods that delegate to parent TvDatafeedLive instance

**consumer.py (Consumer)**
- Threading.Thread subclass that processes data via callbacks
- Queue-based buffering for incoming data bars
- Error handling and graceful shutdown

### Key Design Patterns

**Threading Architecture**
- Main loop thread (`_main_loop`) in TvDatafeedLive monitors all Seis intervals
- Separate Consumer threads for each callback function
- Lock-based synchronization (`self._lock`) for thread-safe operations
- All public methods support optional timeout parameter for lock acquisition

**Interval Management (_SeisesAndTrigger)**
- Internal dict-like structure groups Seis by interval
- Calculates next expiry times and waits efficiently
- Interrupt mechanism for dynamic Seis addition/removal during waits

**Token Caching**
- Authentication tokens saved to `~/.tv_token.json` to avoid repeated logins
- Load token on init, fallback to username/password login if not found

**WebSocket Protocol**
- Custom message framing: `~m~<length>~m~<json_message>`
- Session and chart session IDs generated randomly
- Message filtering with regex to extract ticker data from responses

## Common Development Commands

Run the example usage:
```bash
python tvDatafeed/main.py
```

Test basic functionality:
```python
from tvDatafeed import TvDatafeed, Interval
tv = TvDatafeed(username='your_username', password='your_password')
data = tv.get_hist('NIFTY', 'NSE', interval=Interval.in_1_hour, n_bars=1000)
```

Test live feed:
```python
from tvDatafeed import TvDatafeedLive, Interval

def callback(seis, data):
    print(f"New bar for {seis.symbol}: {data}")

tvl = TvDatafeedLive(username='your_username', password='your_password')
seis = tvl.new_seis('ETHUSDT', 'BINANCE', Interval.in_1_hour)
consumer = seis.new_consumer(callback)
```

## Important Implementation Notes

**Thread Safety**
- Always acquire `self._lock` before modifying `_sat` or Seis/Consumer lists
- Timeout parameter on all public methods prevents deadlocks
- Use `with self._lock:` context manager where appropriate

**Data Retrieval Logic**
- `get_hist(n_bars=2)` returns bars with index [0] = most recent closed, [1] = currently open
- Live feed drops the open bar (index [1]) before passing to consumers
- `is_new_data()` compares datetime to prevent duplicate processing
- Retry logic (RETRY_LIMIT=50) for failed TradingView requests

**Interval Expiry Calculation**
- Intervals stored as relativedelta objects in `_timeframes` dict
- Next expiry = last bar datetime + interval duration
- Main loop waits until soonest expiry across all intervals

**Consumer Callback Requirements**
- Callback signature must be: `callback(seis, data)`
- `seis` is the Seis instance, `data` is pandas DataFrame
- Exceptions in callbacks cause Consumer removal and re-raise

**Authentication**
- Token-based auth preferred (cached to filesystem)
- Username/password fallback via POST to `__sign_in_url`
- Anonymous usage possible but may have symbol limitations

## File Structure

```
tvDatafeed/
├── __init__.py           # Package exports: TvDatafeed, TvDatafeedLive, Interval, Seis, Consumer
├── main.py               # TvDatafeed base class, Interval enum, WebSocket data retrieval
├── datafeed.py           # TvDatafeedLive class, _SeisesAndTrigger helper
├── seis.py               # Seis class (symbol-exchange-interval set)
└── consumer.py           # Consumer class (threaded callback processor)
```

## Version Information

Current version: 2.1.1 (per setup.py)

Version 2.0.0 was a major breaking change that removed Selenium dependency.
