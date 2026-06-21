"""TradingView live data feed with real-time streaming capabilities."""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime as dt
from datetime import timezone
from typing import TYPE_CHECKING

from dateutil.relativedelta import relativedelta as rd

from .main import Interval, TvDatafeed

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    import pandas as pd

    from .consumer import Consumer
    from .seis import Seis

logger = logging.getLogger(__name__)

RETRY_LIMIT = 50  # Maximum number of retries for data retrieval
MAX_BACKOFF = 5  # Maximum backoff exponent for exponential backoff


class TvDatafeedLive(TvDatafeed):
    """Live data feed for TradingView with real-time streaming.

    Extends TvDatafeed to provide real-time data streaming via threaded
    callback architecture. Users can monitor multiple symbol-exchange-interval
    sets (Seis) and register callback functions to process new data bars.

    Args:
        username: TradingView username (optional)
        password: TradingView password (optional)

    Example:
        >>> tvl = TvDatafeedLive(username='user', password='pass')
        >>> def callback(seis, data):
        ...     print(f"New bar: {data}")
        >>> seis = tvl.new_seis('ETHUSDT', 'BINANCE', Interval.in_1_hour)
        >>> consumer = seis.new_consumer(callback)
    """

    class _SeisesAndTrigger(dict):
        """Internal class to manage Seis objects and interval timing.

        Tracks symbol-exchange-interval sets and their expiry times
        for efficient polling of new data bars.
        """

        def __init__(self) -> None:
            """Initialize interval tracker."""
            super().__init__()

            self._trigger_quit = False
            self._trigger_dt: dt | None = None
            self._trigger_interrupt = threading.Event()

            # Time periods available in TradingView
            self._timeframes = {
                "1": rd(minutes=1),
                "3": rd(minutes=3),
                "5": rd(minutes=5),
                "15": rd(minutes=15),
                "30": rd(minutes=30),
                "45": rd(minutes=45),
                "1H": rd(hours=1),
                "2H": rd(hours=2),
                "3H": rd(hours=3),
                "4H": rd(hours=4),
                "1D": rd(days=1),
                "1W": rd(weeks=1),
                "1M": rd(months=1),
                "3M": rd(months=3),
                "6M": rd(months=6),
                "12M": rd(months=12),
            }

        def _next_trigger_dt(self) -> dt | None:
            """Get the next closest expiry datetime.

            Returns:
                Next expiry datetime or None if empty
            """
            if not self.values():
                return None

            interval_dt_list = [values[1] for values in self.values()]
            interval_dt_list.sort()
            return interval_dt_list[0]

        def get_seis(self, symbol: str, exchange: str, interval: Interval) -> Seis | None:
            """Get Seis by symbol, exchange, and interval.

            Args:
                symbol: Symbol name
                exchange: Exchange name
                interval: Time interval

            Returns:
                Matching Seis or None if not found
            """
            for seis in self:
                if (
                    seis.symbol == symbol
                    and seis.exchange == exchange
                    and seis.interval == interval
                ):
                    return seis
            return None

        def wait(self) -> bool:
            """Wait until next interval expires.

            Returns:
                True after waiting, False if interrupted for shutdown
            """
            if not self._trigger_quit:
                self._trigger_interrupt.clear()

            self._trigger_dt = self._next_trigger_dt()
            if self._trigger_dt is None:
                return True

            while True:
                # Bar datetimes from TradingView are tz-aware (UTC), so
                # compare against a tz-aware "now" to avoid mixing naive and
                # aware datetimes (which raises TypeError).
                wait_time = self._trigger_dt - dt.now(timezone.utc)

                interrupted = self._trigger_interrupt.wait(max(wait_time.total_seconds(), 0))

                if not interrupted:
                    # Timed out naturally: the soonest trigger has fired.
                    self._trigger_interrupt.clear()
                    break

                if self._trigger_quit:
                    return False

                # Woken by a dynamic Seis add/remove that changed the soonest
                # trigger. Clear the (still-set) event and re-wait against the
                # refreshed trigger time; without the clear the still-set event
                # would make wait() return instantly and busy-spin the loop.
                self._trigger_interrupt.clear()
                self._trigger_dt = self._next_trigger_dt()
                if self._trigger_dt is None:
                    return True

            return True

        def get_expired(self) -> list[str]:
            """Get list of expired intervals and update their expiry times.

            Returns:
                List of interval strings that have expired
            """
            expired_intervals = []
            now = dt.now(timezone.utc)
            for interval, values in self.items():
                if now >= values[1]:
                    expired_intervals.append(interval)
                    values[1] = values[1] + self._timeframes[interval]

            return expired_intervals

        def quit(self) -> None:
            """Signal shutdown and interrupt waiting."""
            self._trigger_quit = True
            self._trigger_interrupt.set()

        def clear(self) -> None:
            """Clear all interval groups and Seises."""
            raise NotImplementedError("Clear operation not supported")

        def append(self, seis: Seis, update_dt: dt | None = None) -> None:
            """Append new Seis instance to tracker.

            Args:
                seis: Seis instance to add
                update_dt: Last update datetime (required for new intervals)
            """
            if not self:  # Reset flags when adding first item
                self._trigger_quit = False
                self._trigger_interrupt.clear()

            interval_key = seis.interval.value

            if interval_key in self.keys():
                # Interval group already exists
                super().__getitem__(interval_key)[0].append(seis)
            else:
                # Create new interval group
                if update_dt is None:
                    raise ValueError("Missing update datetime for new interval group")

                # Calculate next update time
                next_update_dt = update_dt + self._timeframes[interval_key]
                self.__setitem__(interval_key, [[seis], next_update_dt])

                # Check if we need to interrupt current wait
                if (trigger_dt := self._next_trigger_dt()) != self._trigger_dt:
                    self._trigger_dt = trigger_dt
                    self._trigger_interrupt.set()

        def discard(self, seis: Seis) -> None:
            """Remove Seis instance from tracker.

            Args:
                seis: Seis instance to remove

            Raises:
                KeyError: If Seis not in tracker
            """
            if seis not in self:
                raise KeyError("Seis not found in tracker")

            interval_key = seis.interval.value
            super().__getitem__(interval_key)[0].remove(seis)

            # Remove interval group if now empty
            if not super().__getitem__(interval_key)[0]:
                self.pop(interval_key)

                # Update trigger if needed
                if (
                    trigger_dt := self._next_trigger_dt()
                ) != self._trigger_dt and not self._trigger_quit:
                    self._trigger_dt = trigger_dt
                    self._trigger_interrupt.set()

        def intervals(self) -> dict.KeysView:
            """Get list of interval groups.

            Returns:
                View of interval keys
            """
            return self.keys()

        def __getitem__(self, interval_key: str) -> list[Seis]:
            """Get list of Seis for an interval.

            Args:
                interval_key: Interval string

            Returns:
                List of Seis instances
            """
            return super().__getitem__(interval_key)[0]

        def __iter__(self):
            """Iterate over all Seis instances."""
            seises_list = []
            for seis_list in super().values():
                seises_list += seis_list[0]
            return seises_list.__iter__()

        def __contains__(self, seis: Seis) -> bool:
            """Check if Seis is in tracker.

            Args:
                seis: Seis instance to check

            Returns:
                True if present, False otherwise
            """
            return any(seis in seis_list[0] for seis_list in super().values())

    def __init__(
        self,
        username: str | None = None,
        password: str | None = None,
        token_cache_file: str | Path = "~/.tv_token.json",
    ) -> None:
        """Initialize live data feed.

        Args:
            username: TradingView username
            password: TradingView password
            token_cache_file: Path to cache authentication token
        """
        super().__init__(username, password, token_cache_file)

        self._lock = threading.Lock()
        self._main_thread: threading.Thread | None = None
        self._sat = self._SeisesAndTrigger()

    def _args_invalid(self, symbol: str, exchange: str) -> bool:
        """Validate symbol and exchange combination.

        Args:
            symbol: Symbol name
            exchange: Exchange name

        Returns:
            True if invalid, False if valid
        """
        result_list = self.search_symbol(symbol, exchange)

        if not result_list:
            return True

        for item in result_list:
            if item["symbol"] == symbol and item["exchange"] == exchange:
                return False

        return True

    def new_seis(
        self, symbol: str, exchange: str, interval: Interval, timeout: int = -1
    ) -> Seis | bool:
        """Create and add new Seis to live feed.

        Args:
            symbol: Ticker symbol
            exchange: Exchange name
            interval: Time interval
            timeout: Maximum wait time in seconds (-1 for blocking)

        Returns:
            Seis instance (existing or new), or False if timeout

        Raises:
            ValueError: If symbol/exchange combination invalid
        """
        if self._args_invalid(symbol, exchange):
            raise ValueError(f"Symbol '{symbol}' on exchange '{exchange}' not found in TradingView")

        # Return existing Seis if already tracked
        if seis := self._sat.get_seis(symbol, exchange, interval):
            return seis

        # Import here to avoid circular import
        from .seis import Seis as SeisClass

        new_seis = SeisClass(symbol, exchange, interval)

        if not self._lock.acquire(timeout=timeout if timeout > 0 else None):
            return False

        try:
            new_seis.tvdatafeed = self

            # Check again after acquiring lock
            if new_seis in self._sat:
                return self._sat.get_seis(symbol, exchange, interval)

            # Get initial data to establish baseline
            interval_key = new_seis.interval.value
            if interval_key not in self._sat.intervals():
                ticker_data = super().get_hist(
                    new_seis.symbol, new_seis.exchange, new_seis.interval, n_bars=2
                )

                if ticker_data is None or len(ticker_data) == 0:
                    raise ValueError(f"Failed to get initial data for {symbol} on {exchange}")

                update_dt = ticker_data.index.to_pydatetime()[0]
                self._sat.append(new_seis, update_dt)
            else:
                self._sat.append(new_seis)

            # Start main loop if not running
            if self._main_thread is None:
                self._main_thread = threading.Thread(
                    name="tvdatafeed_main_loop", target=self._main_loop, daemon=True
                )
                self._main_thread.start()

            return new_seis

        finally:
            self._lock.release()

    def del_seis(self, seis: Seis, timeout: int = -1) -> bool:
        """Remove Seis from live feed.

        Args:
            seis: Seis to remove
            timeout: Maximum wait time in seconds (-1 for blocking)

        Returns:
            True if successful, False if timeout

        Raises:
            ValueError: If Seis not in live feed
        """
        if not self._lock.acquire(timeout=timeout if timeout > 0 else None):
            return False

        try:
            # Re-check membership under the lock to avoid a TOCTOU race
            # with another thread removing the same Seis.
            if seis not in self._sat:
                raise ValueError("Seis not in live feed")

            # Stop all consumers for this Seis
            for consumer in seis.get_consumers():
                consumer.put(None)

            # Remove from tracker
            self._sat.discard(seis)
            del seis.tvdatafeed

            # Shutdown if no more Seises
            if not self._sat:
                self._sat.quit()

            return True

        finally:
            self._lock.release()

    def new_consumer(self, seis: Seis, callback: Callable, timeout: int = -1) -> Consumer | bool:
        """Create new Consumer for Seis with callback function.

        Args:
            seis: Seis to consume data from
            callback: Function(seis, data) to call with new data
            timeout: Maximum wait time in seconds (-1 for blocking)

        Returns:
            Consumer instance, or False if timeout

        Raises:
            ValueError: If Seis not in live feed
        """
        # Import here to avoid circular import
        from .consumer import Consumer as ConsumerClass

        consumer = ConsumerClass(seis, callback)

        if not self._lock.acquire(timeout=timeout if timeout > 0 else None):
            return False

        try:
            # Re-check membership under the lock (the Seis could have been
            # removed between the caller's check and acquiring the lock).
            if seis not in self._sat:
                raise ValueError("Seis not in live feed")

            seis.add_consumer(consumer)
            consumer.start()
            return consumer

        finally:
            self._lock.release()

    def del_consumer(self, consumer: Consumer, timeout: int = -1) -> bool:
        """Remove Consumer from its Seis.

        Args:
            consumer: Consumer to remove
            timeout: Maximum wait time in seconds (-1 for blocking)

        Returns:
            True if successful, False if timeout
        """
        if not self._lock.acquire(timeout=timeout if timeout > 0 else None):
            return False

        try:
            # Check if seis is still valid
            if consumer.seis is not None:
                consumer.seis.pop_consumer(consumer)
            consumer.stop()
            return True

        finally:
            self._lock.release()

    def _main_loop(self) -> None:
        """Main loop for retrieving and distributing live data.

        Continuously monitors tracked Seises and retrieves new data bars
        when intervals expire. Distributes data to registered consumers.

        The lock is held only to snapshot the expired work and advance the
        interval triggers - never across the (potentially slow) network
        retrieval, so public methods stay responsive.
        """
        while self._sat.wait():
            # Snapshot the expired Seises under the lock, then release it
            # before doing any network I/O. get_expired() also advances the
            # interval trigger times, so it must run under the lock.
            with self._lock:
                expired_work = [list(self._sat[interval]) for interval in self._sat.get_expired()]

            for seis_list in expired_work:
                for seis in seis_list:
                    data = self._retrieve_new_bar(seis)
                    if data is None:
                        continue

                    # Snapshot consumers - a consumer may remove itself
                    # concurrently from its own thread.
                    for consumer in list(seis.get_consumers()):
                        consumer.put(data)

        self._shutdown_consumers()

    def _retrieve_new_bar(self, seis: Seis) -> pd.DataFrame | None:
        """Fetch the latest closed bar for a Seis, retrying transiently.

        Distinguishes "the next bar hasn't been published yet" (normal -
        skip this cycle and try again on the next interval) from a hard
        failure. Neither case tears down the whole feed; the Seis is simply
        retried at its next expiry.

        Args:
            seis: Seis to retrieve data for

        Returns:
            DataFrame with the newly closed bar, or None if no new bar
        """
        for attempt in range(RETRY_LIMIT):
            try:
                data = super().get_hist(
                    seis.symbol,
                    seis.exchange,
                    interval=seis.interval,
                    n_bars=2,
                )
            except Exception as e:
                logger.warning(
                    "Attempt %d/%d errored for %s: %s",
                    attempt + 1,
                    RETRY_LIMIT,
                    seis,
                    e,
                )
                data = None

            if data is not None:
                if not seis.is_new_data(data):
                    # The new bar isn't available yet; wait briefly and retry.
                    time.sleep(0.1 * (2 ** min(attempt, MAX_BACKOFF)))
                    continue

                # Drop the unclosed (currently forming) bar if present.
                if len(data) > 1:
                    data = data.drop(labels=data.index[1])
                return data

            # Request failed; back off and retry.
            time.sleep(0.1 * (2 ** min(attempt, MAX_BACKOFF)))

        logger.warning(
            "No new bar for %s after %d attempts - will retry next interval",
            seis,
            RETRY_LIMIT,
        )
        return None

    def _shutdown_consumers(self) -> None:
        """Stop all consumers and clear tracked Seises on shutdown."""
        with self._lock:
            for seis in list(self._sat):  # Create list copy for safe iteration
                # Copy the consumer list too: pop_consumer mutates it, so
                # iterating the live list would skip every other consumer.
                for consumer in list(seis.get_consumers()):
                    seis.pop_consumer(consumer)
                    consumer.stop()

                self._sat.discard(seis)

            self._main_thread = None

    def get_hist(
        self,
        symbol: str,
        exchange: str = "NSE",
        interval: Interval = Interval.in_daily,
        n_bars: int = 10,
        fut_contract: int | None = None,
        extended_session: bool = False,
        timeout: int = -1,
    ) -> pd.DataFrame | bool:
        """Get historical data (thread-safe version).

        Args:
            symbol: Symbol name
            exchange: Exchange name
            interval: Time interval
            n_bars: Number of bars to fetch
            fut_contract: Futures contract number
            extended_session: Include extended hours
            timeout: Maximum wait time in seconds (-1 for blocking)

        Returns:
            DataFrame with OHLCV data, or False if timeout
        """
        if not self._lock.acquire(timeout=timeout if timeout > 0 else None):
            return False

        try:
            data = super().get_hist(
                symbol, exchange, interval, n_bars, fut_contract, extended_session
            )
            return data

        finally:
            self._lock.release()

    def __del__(self) -> None:
        """Cleanup when object is destroyed."""
        try:
            # Try to acquire lock, but don't block to avoid deadlock
            if self._lock.acquire(blocking=False):
                try:
                    self._sat.quit()
                finally:
                    self._lock.release()
            else:
                # Force quit without lock if already held
                self._sat.quit()

            if self._main_thread is not None:
                self._main_thread.join(timeout=5)
        except Exception as e:
            logger.debug("Error during cleanup: %s", e)

    def del_tvdatafeed(self) -> None:
        """Explicitly stop and delete live feed."""
        if self._main_thread is not None:
            self.__del__()
