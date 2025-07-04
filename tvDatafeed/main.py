import datetime
import enum
import json
import logging
import os
import random
import re
import string
import threading
import pandas as pd
from websocket import create_connection
import requests
import json

logger = logging.getLogger(__name__)


class Interval(enum.Enum):
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


class TvDatafeed:
    __user_url = "https://www.tradingview.com/accounts/current/"
    __sign_in_url = "https://www.tradingview.com/accounts/signin/"
    __search_url = "https://symbol-search.tradingview.com/symbol_search/?text={}&hl=1&exchange={}&lang=en&type=&domain=production"
    __ws_headers = json.dumps({"Origin": "https://data.tradingview.com"})
    __signin_headers = {"Referer": "https://www.tradingview.com"}
    __ws_timeout = 5

    def __init__(
        self,
        username=None,
        password=None,
        token_cache_file="~/.tv_token.json",
    ):
        self.ws_debug = False

        self.token_cache_file = os.path.expanduser(token_cache_file)
        self._lock = threading.Lock()

        token = self._load_token()

        if token:
            self.token = token
        else:
            if username and password:
                self.token = self._login_and_get_token(username, password)
                self._save_token(self.token)
            else:
                raise ValueError("Must provide either token or username/password")

        self.ws = None
        self.session = self.__generate_session()
        self.chart_session = self.__generate_chart_session()

    def _load_token(self):
        if os.path.exists(self.token_cache_file):
            try:
                with open(self.token_cache_file, "r") as f:
                    return json.load(f).get("token")
            except Exception:
                return None
        return None

    def _save_token(self, token):
        try:
            with open(self.token_cache_file, "w") as f:
                json.dump({"token": token}, f)
        except Exception as e:
            print(f"Warning: Failed to save token - {e}")

    def _login_and_get_token(self, username, password):
        # Placeholder for real login logic
        # Replace this with real login request to get a token from TradingView
        token = self.__auth(username, password)
        if not token:
            raise ValueError("Login failed, could not retrieve token")
        return token

    def __auth(self, username=None, password=None):

        # -- 2.  Username / password fallback --------------------------------
        if username and password:
            try:
                r = requests.post(
                    self.__sign_in_url,
                    data={"username": username, "password": password, "remember": "on"},
                    headers={"Referer": "https://www.tradingview.com"},
                    timeout=5,
                )
                return r.json()["user"]["auth_token"]
            except Exception as e:
                logger.error("password-auth failed: %s", e)

        # -- 3.  Anonymous ----------------------------------------------------
        return None

    def __create_connection(self):
        logging.debug("creating websocket connection")
        self.ws = create_connection(
            "wss://data.tradingview.com/socket.io/websocket",
            headers=self.__ws_headers,
            timeout=self.__ws_timeout,
        )

    @staticmethod
    def __filter_raw_message(text):
        try:
            found = re.search('"m":"(.+?)",', text).group(1)
            found2 = re.search('"p":(.+?"}"])}', text).group(1)

            return found, found2
        except AttributeError:
            logger.error("error in filter_raw_message")

    @staticmethod
    def __generate_session():
        stringLength = 12
        letters = string.ascii_lowercase
        random_string = "".join(random.choice(letters) for i in range(stringLength))
        return "qs_" + random_string

    @staticmethod
    def __generate_chart_session():
        stringLength = 12
        letters = string.ascii_lowercase
        random_string = "".join(random.choice(letters) for i in range(stringLength))
        return "cs_" + random_string

    @staticmethod
    def __prepend_header(st):
        return "~m~" + str(len(st)) + "~m~" + st

    @staticmethod
    def __construct_message(func, param_list):
        return json.dumps({"m": func, "p": param_list}, separators=(",", ":"))

    def __create_message(self, func, paramList):
        return self.__prepend_header(self.__construct_message(func, paramList))

    def __send_message(self, func, args):
        m = self.__create_message(func, args)
        if self.ws_debug:
            print(m)
        self.ws.send(m)

    @staticmethod
    def __create_df(raw_data, symbol):
        try:
            out = re.search('"s":\[(.+?)\}\]', raw_data).group(1)
            x = out.split(',{"')
            data = list()
            volume_data = True

            for xi in x:
                xi = re.split("\[|:|,|\]", xi)
                ts = datetime.datetime.fromtimestamp(float(xi[4]))

                row = [ts]

                for i in range(5, 10):

                    # skip converting volume data if does not exists
                    if not volume_data and i == 9:
                        row.append(0.0)
                        continue
                    try:
                        row.append(float(xi[i]))

                    except ValueError:
                        volume_data = False
                        row.append(0.0)
                        logger.debug("no volume data")

                data.append(row)

            data = pd.DataFrame(
                data, columns=["datetime", "open", "high", "low", "close", "volume"]
            ).set_index("datetime")
            data.insert(0, "symbol", value=symbol)
            return data
        except AttributeError:
            logger.error("no data, please check the exchange and symbol")

    @staticmethod
    def __format_symbol(symbol, exchange, contract: int = None):

        if ":" in symbol:
            pass
        elif contract is None:
            symbol = f"{exchange}:{symbol}"

        elif isinstance(contract, int):
            symbol = f"{exchange}:{symbol}{contract}!"

        else:
            raise ValueError("not a valid contract")

        return symbol

    def get_hist(
        self,
        symbol: str,
        exchange: str = "NSE",
        interval: Interval = Interval.in_daily,
        n_bars: int = 10,
        fut_contract: int = None,
        extended_session: bool = False,
    ) -> pd.DataFrame:
        """get historical data

        Args:
            symbol (str): symbol name
            exchange (str, optional): exchange, not required if symbol is in format EXCHANGE:SYMBOL. Defaults to None.
            interval (str, optional): chart interval. Defaults to 'D'.
            n_bars (int, optional): no of bars to download, max 5000. Defaults to 10.
            fut_contract (int, optional): None for cash, 1 for continuous current contract in front, 2 for continuous next contract in front . Defaults to None.
            extended_session (bool, optional): regular session if False, extended session if True, Defaults to False.

        Returns:
            pd.Dataframe: dataframe with sohlcv as columns
        """
        symbol = self.__format_symbol(
            symbol=symbol, exchange=exchange, contract=fut_contract
        )

        interval = interval.value

        self.__create_connection()

        self.__send_message("set_auth_token", [self.token])
        self.__send_message("chart_create_session", [self.chart_session, ""])
        self.__send_message("quote_create_session", [self.session])
        self.__send_message(
            "quote_set_fields",
            [
                self.session,
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
            ],
        )

        self.__send_message(
            "quote_add_symbols", [self.session, symbol, {"flags": ["force_permission"]}]
        )
        self.__send_message("quote_fast_symbols", [self.session, symbol])

        self.__send_message(
            "resolve_symbol",
            [
                self.chart_session,
                "symbol_1",
                '={"symbol":"'
                + symbol
                + '","adjustment":"splits","session":'
                + ('"regular"' if not extended_session else '"extended"')
                + "}",
            ],
        )
        self.__send_message(
            "create_series",
            [self.chart_session, "s1", "s1", "symbol_1", interval, n_bars],
        )
        self.__send_message("switch_timezone", [self.chart_session, "exchange"])

        raw_data = ""

        logger.debug(f"getting data for {symbol}...")
        while True:
            try:
                result = self.ws.recv()
                raw_data = raw_data + result + "\n"
            except Exception as e:
                logger.error(e)
                break

            if "series_completed" in result:
                break

        return self.__create_df(raw_data, symbol)

    def search_symbol(self, text: str, exchange: str = ""):
        url = self.__search_url.format(text, exchange)

        symbols_list = []
        try:
            resp = requests.get(url)

            symbols_list = json.loads(
                resp.text.replace("</em>", "").replace("<em>", "")
            )
        except Exception as e:
            logger.error(e)

        return symbols_list

    def get_token(self):
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
