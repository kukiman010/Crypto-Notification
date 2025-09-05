
import os
import time
import threading
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any, Iterable
from control.data_models import CryptoBrief

import requests


class CoinMarketCapApi:
    """
    Клиент CoinMarketCapApi с безопасным кешем без автообновления.

    Возможности:
      - get_top(): быстро возвращает топ-N монет из кеша (по умолчанию 20)
      - get_prices_info(symbols): точные котировки по списку символов
      - get_by_symbol(): быстрый доступ к монете из кеша
      - get_all_cached(): получить снимок кеша
      - force_refresh(): синхронно обновить кеш по запросу
      - get_cmc_api_limits() / parse_cmc_api_limits(): лимиты ключа

    Безопасность и производительность:
      - Никаких фоновых потоков и автообновлений
      - Потокобезопасность через RLock (на случай многопоточности со стороны приложения)
      - Возвращаются frozen dataclass (только чтение)
    """

    API_BASE = "https://pro-api.coinmarketcap.com/v1"
    ENDPOINT_QUOTES = "/cryptocurrency/quotes/latest"
    ENDPOINT_LISTINGS = "/cryptocurrency/listings/latest"
    ENDPOINT_KEY_INFO = "/key/info"

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        default_convert: str = "USD",
        # refresh_interval: int = 60,      # параметр сохранён для обратной совместимости, не используется
        cache_limit: int = 200,
        # stale_ttl: int = 180,            # параметр сохранён для обратной совместимости, не используется
        request_timeout: int = 10,
        session: Optional[requests.Session] = None,
        read_api_key_from: Optional[str] = "./configs/coinmarketcap.key",
        sort: str = "market_cap",
        sort_dir: str = "desc",
        verbose: bool = False,
    ):
        """
        :param api_key: Ключ CMC; если не указан — возьмём из окружения
                        COINMARKETCAP_API_KEY или из файла read_api_key_from.
        :param default_convert: Валюта конвертации для листинга (USD по умолчанию).
        :param refresh_interval: (не используется, сохранён для обратной совместимости)
        :param cache_limit: Сколько монет запрашивать и держать в кеше (макс. листинга)
        :param stale_ttl: (не используется, сохранён для обратной совместимости)
        :param request_timeout: Таймаут HTTP-запросов (сек.)
        :param session: Опционально передайте свой requests.Session
        :param read_api_key_from: Путь к файлу с ключом, если не задан api_key/env
        :param sort: Поле сортировки листинга (market_cap, volume_24h, price и т.п.)
        :param sort_dir: Направление сортировки ('desc' | 'asc')
        :param verbose: Печатать лог-сообщения
        """
        self.verbose = verbose

        env_key = os.environ.get("COINMARKETCAP_API_KEY")
        file_key = None
        if not api_key and not env_key and read_api_key_from and os.path.exists(read_api_key_from):
            try:
                with open(read_api_key_from, "r", encoding="utf-8") as f:
                    file_key = f.read().strip()
            except Exception:
                                file_key = None

        self.api_key = api_key or env_key or file_key
        if not self.api_key:
            raise RuntimeError("Не найден COINMARKETCAP_API_KEY")

        self.default_convert = default_convert
        self.cache_limit = max(1, int(cache_limit))
        self.request_timeout = request_timeout
        self.sort = sort
        self.sort_dir = sort_dir

        self._session = session or requests.Session()
        self._lock = threading.RLock()

        # Кеш: кортеж иммутабельных записей и индекс по символам
        self._cache_data: Tuple[CryptoBrief, ...] = tuple()
        self._index_by_symbol: Dict[str, int] = {}
        self._last_update_ts: float = 0.0

        # Простой контроль ошибок/бэкофф (используется только внутри запроса)
        self._backoff_sec = 0

    # ------------------------- Публичный API -------------------------

    def get_top(self, limit: int = 20, convert: Optional[str] = None) -> Tuple[CryptoBrief, ...]:
        """
        Вернёт топ-N монет из кеша. Быстро и безопасно.
        Если кеш пуст — выполнит синхронное одноразовое обновление.
        """
        convert = convert or self.default_convert
        if not self._cache_data:
            # Первая загрузка — блокирующая
            self._refresh_once_blocking(convert=convert)

        with self._lock:
            if convert != self.default_convert:
                # Для иного convert подтянем точные котировки через quotes/latest
                symbols = [cb.symbol for cb in self._cache_data[:limit]]
                prices = self.get_prices_info(symbols, convert=convert)
                result = []
                for sym in symbols:
                    info = prices.get(sym)
                    if not info:
                        continue
                    cb = self._cache_data[self._index_by_symbol.get(sym, -1)]
                    result.append(
                        CryptoBrief(
                            id=cb.id,
                            name=cb.name,
                            symbol=cb.symbol,
                            price=float(info["converted_price"]),
                            convert_currency=convert,
                            last_updated=cb.last_updated,
                            price_change=cb.price_change,   # переносим уже вычисленный флаг
                        )
                    )
                return tuple(result)
            return self._cache_data[:limit]

    def get_all_cached(self, as_dicts: bool = False) -> Tuple[CryptoBrief, ...] | List[Dict[str, Any]]:
        """
        Полный снимок кеша. По умолчанию — кортеж CryptoBrief (immutable).
        Можно вернуть как список словарей: as_dicts=True.
        Если кеш пуст — будет выполнено блокирующее обновление.
        """
        if not self._cache_data:
            self._refresh_once_blocking(convert=self.default_convert)

        with self._lock:
            if not as_dicts:
                return self._cache_data
            return [self._brief_to_dict(cb) for cb in self._cache_data]

    def get_by_symbol(self, symbol: str) -> Optional[CryptoBrief]:
        """
        Быстрый доступ к монете из кеша по символу.
        """
        if not symbol:
            return None
        if not self._cache_data:
            self._refresh_once_blocking(convert=self.default_convert)

        idx = self._index_by_symbol.get(symbol.upper())
        if idx is None:
            return None
        return self._cache_data[idx]

    def get_prices_info(self, symbols: Iterable[str], convert: str = "USD") -> Dict[str, Dict[str, Any]]:
        """
        Точные котировки по списку символов через /quotes/latest.
        Возвращает {SYM: {"base_price": 1.0, "converted_price": float, "convert_currency": convert}}
        """
        symbols = [s.upper() for s in symbols if s]
        if not symbols:
            return {}

        headers = {
            "Accepts": "application/json",
            "X-CMC_PRO_API_KEY": self.api_key
        }
        params = {
            "symbol": ",".join(symbols),
            "convert": convert,
            "skip_invalid": "true"
        }
        url = self.API_BASE + self.ENDPOINT_QUOTES
        resp = self._session.get(url, headers=headers, params=params, timeout=self.request_timeout)
        resp.raise_for_status()
        data = resp.json()
        status = data.get("status", {})
        if status.get("error_code", 0) != 0:
            raise RuntimeError(f"API error: {status.get('error_message')}")

        result: Dict[str, Dict[str, Any]] = {}
        for sym, info in (data.get("data") or {}).items():
            quote = (info.get("quote") or {}).get(convert)
            if quote and "price" in quote:
                result[sym] = {
                    "base_price": 1.0,
                    "converted_price": float(quote["price"]),
                    "convert_currency": convert
                }
        return result

    def get_cmc_api_limits(self) -> Dict[str, Any]:
        """Сырые лимиты ключа с /key/info."""
        url = self.API_BASE + self.ENDPOINT_KEY_INFO
        headers = {
            "X-CMC_PRO_API_KEY": self.api_key,
            "Accepts": "application/json"
        }
        response = self._session.get(url, headers=headers, timeout=self.request_timeout)
        if response.status_code == 200:
            return response.json()
        else:
            raise RuntimeError(f"Ошибка запроса: {response.status_code} - {response.text}")

    @staticmethod
    def parse_cmc_api_limits(response_json: Dict[str, Any]) -> Dict[str, Any]:
        """
        Нормализованный разбор структуры /key/info.
        Возвращает поля: is_working, limit, error_code, error_message, reset_time, extra_info
        """
        status = response_json.get("status", {})
        is_working = (status.get("error_code", 1) == 0)
        error_code = status.get("error_code")
        error_message = status.get("error_message")

        limit_data = None
        reset_time = None
        extra_info: Dict[str, Any] = {}

        if "plan" in response_json:
            plan = response_json["plan"]
            limit_data = {
                "monthly": plan.get("credit_limit_monthly"),
                "minute": plan.get("rate_limit_minute"),
            }
            reset_time = plan.get("credit_limit_monthly_reset")
        elif "data" in response_json:
            plan = (response_json["data"] or {}).get("plan", {})
            limit_data = {
                "monthly": plan.get("credit_limit_monthly"),
                "minute": plan.get("rate_limit_minute"),
            }
            reset_time = plan.get("credit_limit_monthly_reset")

        usage = None
        if "usage" in response_json:
            usage = response_json.get("usage", {})
        elif "data" in response_json:
            usage = (response_json["data"] or {}).get("usage", {})

        if usage:
            try:
                minute_used = (usage.get("current_minute") or {}).get("credit_used")
                month_used = (usage.get("current_month") or {}).get("credit_used")
                month_left = (limit_data["monthly"] - month_used) if (limit_data and limit_data.get("monthly") and month_used is not None) else None
                extra_info["credit_used_minute"] = minute_used
                extra_info["credit_left_month"] = month_left
            except Exception:
                pass

        return {
            "is_working": is_working,
            "limit": limit_data,
            "error_code": error_code,
            "error_message": error_message,
            "reset_time": reset_time,
            "extra_info": extra_info,
        }

    def force_refresh(self, *, convert: Optional[str] = None) -> None:
        """
        Синхронно обновить кеш по запросу. Никаких фоновых событий.
        """
        self._refresh_once_blocking(convert=convert or self.default_convert)

    # ------------------------- Внутреннее -------------------------

    def _refresh_once_blocking(self, *, convert: str) -> None:
        """Первичная загрузка/ручное обновление — блокирующее."""
        try:
            self._refresh_once(convert=convert)
        except Exception as e:
            raise RuntimeError(f"Не удалось получить листинг: {e}") from e

    def _refresh_once(self, *, convert: str) -> None:
        """
        Разовая загрузка листинга с CMC и установка кеша.
        """
        params = {
            "start": "1",
            "limit": str(self.cache_limit),
            "convert": convert,
            "sort": self.sort,
            "sort_dir": self.sort_dir,
        }
        headers = {
            "Accepts": "application/json",
            "X-CMC_PRO_API_KEY": self.api_key,
        }
        url = self.API_BASE + self.ENDPOINT_LISTINGS

        # Обработка rate-limit
        resp = self._session.get(url, headers=headers, params=params, timeout=self.request_timeout)
        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            delay = int(retry_after) if retry_after and retry_after.isdigit() else max(5, self._backoff_sec or 10)
            if self.verbose:
                print(f"[CMC] rate-limited, sleep {delay}s")
            time.sleep(delay)
            resp = self._session.get(url, headers=headers, params=params, timeout=self.request_timeout)

        resp.raise_for_status()
        payload = resp.json()
        status = payload.get("status", {})
        if status.get("error_code", 0) != 0:
            raise RuntimeError(f"API error: {status.get('error_message')}")

        all_cryptos = payload.get("data") or []
        convert_upper = convert.upper()

        # Снимок предыдущих цен (по символу) для сравнения
        with self._lock:
            prev_prices = {cb.symbol: cb.price for cb in self._cache_data}

        new_list: List[CryptoBrief] = []
        for c in all_cryptos:
            q = (c.get("quote") or {}).get(convert_upper)
            if not q:
                continue

            sym = c["symbol"].upper()
            price = float(q["price"])
            prev = prev_prices.get(sym)

            if prev is None:
                change = ""           # первая загрузка или новая монета
            elif price > prev:
                change = "⬆"
            elif price < prev:
                change = "⬇"
            else:
                change = ""           # без изменения

            new_list.append(
                CryptoBrief(
                    id=int(c["id"]),
                    name=c["name"],
                    symbol=sym,
                    price=price,
                    convert_currency=convert_upper,
                    last_updated=c.get("last_updated") or "",
                    price_change=change,
                )
            )
            # Установка нового кеша — под локом, атомарно

        with self._lock:
            new_tuple = tuple(new_list)
            new_index = {cb.symbol: i for i, cb in enumerate(new_tuple)}
            self._cache_data = new_tuple
            self._index_by_symbol = new_index
            self._last_update_ts = time.time()

        # if self.verbose:
            # print(f"[CMC] cache refreshed: {len(new_list)} assets @ {convert_upper}")

    @staticmethod
    def _brief_to_dict(cb: CryptoBrief) -> Dict[str, Any]:
        return {
            "id": cb.id,
            "name": cb.name,
            "symbol": cb.symbol,
            "price": cb.price,
            "convert_currency": cb.convert_currency,
            "last_updated": cb.last_updated,
            "price_change": cb.price_change,
        }
    

    def find_coin(self, name_or_symbol: str, *, convert: Optional[str] = None) -> Optional[CryptoBrief]:
        """
        Поиск монеты по тикеру (BTC) или названию (bitcoin).
        Сначала ищет в кеше. Если не нашёл — запрос к CoinMarketCap API (listings).
        Возвращает CryptoBrief или None.
        """
        if not name_or_symbol:
            return None

        lookup = name_or_symbol.strip().lower()
        if not self._cache_data:
            self._refresh_once_blocking(convert=convert or self.default_convert)

        # 1. Пробуем по символу в кеше
        cb = self.get_by_symbol(lookup.upper())
        if cb:
            return cb

        # 2. Пробуем по имени в кеше
        with self._lock:
            for coin in self._cache_data:
                if coin.name.lower() == lookup:
                    return coin

        # 3. Если не нашли — запрос к API (listings)
        try:
            # Используем стандартный механизм обновления с ограничением в 1000 (максимум по нужде)
            params = {
                "start": "1",
                "limit": "300",  # Магия: достаточно для поиска по названию
                "convert": convert or self.default_convert,
                "sort": self.sort,
                "sort_dir": self.sort_dir,
            }
            headers = {
                "Accepts": "application/json",
                "X-CMC_PRO_API_KEY": self.api_key,
            }
            url = self.API_BASE + self.ENDPOINT_LISTINGS

            resp = self._session.get(url, headers=headers, params=params, timeout=self.request_timeout)
            resp.raise_for_status()
            payload = resp.json()
            coins = payload.get("data") or []
            convert_upper = (convert or self.default_convert).upper()
            for c in coins:
                if (
                    c["symbol"].lower() == lookup
                    or c["name"].lower() == lookup
                ):
                    q = c.get("quote", {}).get(convert_upper)
                    if not q:
                        continue
                    return CryptoBrief(
                        id=int(c["id"]),
                        name=c["name"],
                        symbol=c["symbol"].upper(),
                        price=float(q["price"]),
                        convert_currency=convert_upper,
                        last_updated=c.get("last_updated") or "",
                        price_change="",  # поиск не меняет кеш — оставляем пусто
                    )
        except Exception as ex:
            if self.verbose:
                print(f"find_coin error: {ex}")
            return None

        return None



    def add_symbols_to_cache(
        self,
        symbols: Iterable[str],
        *,
        convert: Optional[str] = None,
        replace_existing: bool = True,
    ) -> Tuple[CryptoBrief, ...]:
        """
        Добавить/обновить в общем кеше монеты по списку тикеров с помощью /cryptocurrency/quotes/latest.

        Важно:
          - Кеш в этом клиенте всегда хранится в self.default_convert для согласованности.
            Если передан другой convert, он будет проигнорирован (с предупреждением в verbose).
          - Сетевая часть выполняется вне лока; установка кеша — атомарно под RLock.
        
        :param symbols: Итерабель со строковыми тикерами, напр. ['BTC', 'TON'].
        :param convert: Игнорируется для кеша; используется self.default_convert.
        :param replace_existing: Если True — обновляет существующие записи; если False — добавляет только новые.
        :return: Полный снимок кеша (tuple[CryptoBrief, ...]) после обновления.

        Добавить/обновить в общем кеше монеты по списку тикеров с помощью /cryptocurrency/quotes/latest.
        Будет обращаться к API только по отсутствующим тикерам!

        """
        # 1. Нормализация входа
        unique_symbols = sorted({(s or "").strip().upper() for s in symbols if s and s.strip()})
        if not unique_symbols:
            return self.get_all_cached(as_dicts=False)

        if not self._cache_data:
            self._refresh_once_blocking(convert=self.default_convert)

        convert_upper = self.default_convert.upper()
        if convert and convert.strip().upper() != convert_upper and self.verbose:
            print(f"[CMC] add_symbols_to_cache: requested convert '{convert}' != default '{convert_upper}', using default.")

        with self._lock:
            already_in_cache = set(self._index_by_symbol.keys())
            prev_prices = {cb.symbol: cb.price for cb in self._cache_data}
        symbols_to_query = [sym for sym in unique_symbols if sym not in already_in_cache]

        if not symbols_to_query:
            return self.get_all_cached(as_dicts=False)

        headers = {
            "Accepts": "application/json",
            "X-CMC_PRO_API_KEY": self.api_key,
        }
        params = {
            "symbol": ",".join(symbols_to_query),
            "convert": convert_upper,
            "skip_invalid": "true",
        }
        url = self.API_BASE + self.ENDPOINT_QUOTES

        resp = self._session.get(url, headers=headers, params=params, timeout=self.request_timeout)
        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            delay = int(retry_after) if retry_after and retry_after.isdigit() else max(5, self._backoff_sec or 10)
            if self.verbose:
                print(f"[CMC] add_symbols_to_cache rate-limited, sleep {delay}s")
            time.sleep(delay)
            resp = self._session.get(url, headers=headers, params=params, timeout=self.request_timeout)

        resp.raise_for_status()
        payload = resp.json()
        status = payload.get("status", {})
        if status.get("error_code", 0) != 0:
            raise RuntimeError(f"API error: {status.get('error_message')}")

        data = payload.get("data") or {}
        new_items: Dict[str, CryptoBrief] = {}

        for sym, info in data.items():
            quote = (info.get("quote") or {}).get(convert_upper)
            if not quote or "price" not in quote:
                continue
            price = float(quote["price"])
            prev = prev_prices.get(sym)
            if prev is None:
                change = ""
            elif price > prev:
                change = "⬆"
            elif price < prev:
                change = "⬇"
            else:
                change = ""
            new_items[sym] = CryptoBrief(
                id=int(info["id"]),
                name=info["name"],
                symbol=sym,
                price=price,
                convert_currency=convert_upper,
                last_updated=info.get("last_updated") or "",
                price_change=change,
            )

        if not new_items:
            return self.get_all_cached(as_dicts=False)

        with self._lock:
            current_list = list(self._cache_data)
            index = dict(self._index_by_symbol)

            for sym, cb in new_items.items():
                if sym in index:
                    if replace_existing:
                        pos = index[sym]
                        current_list[pos] = cb
                else:
                    index[sym] = len(current_list)
                    current_list.append(cb)

            new_tuple = tuple(current_list)
            new_index = {c.symbol: i for i, c in enumerate(new_tuple)}
            self._cache_data = new_tuple
            self._index_by_symbol = new_index
            self._last_update_ts = time.time()

            return self._cache_data
        


    def get_by_symbols(self, symbols: list[str]) -> Tuple[CryptoBrief, ...]:
        """
        Быстрый доступ к монетам из кеша по массиву символов.
        Не делает сетевые запросы. Возвращает tuple найденных CryptoBrief в порядке передачи.
        Символы нормализуются к верхнему регистру.

        :param symbols: list[str] тикеров, например ['BTC', 'ETH', 'TON']
        :return: tuple[CryptoBrief, ...] только найденные в кеше
        """
        if not symbols:
            return tuple()
        if not self._cache_data:
            self._refresh_once_blocking(convert=self.default_convert)

        result = []
        for sym in symbols:
            idx = self._index_by_symbol.get((sym or "").upper())
            if idx is not None:
                result.append(self._cache_data[idx])
        return tuple(result)


# ------------------------- Пример использования -------------------------

# if __name__ == "__main__":
#     client = CoinMarketCapApi( default_convert="USD", cache_limit=200, verbose=True )

#     # Обновить данные вручную (необязательно — первый вызов сам подгрузит кеш)
#     client.force_refresh()

#     # Топ-10 из кеша (первая загрузка выполнится лениво и блокирующе)
#     top10 = client.get_top(limit=10)
#     print(f"TOP10: {[(c.symbol, round(c.price, 2)) for c in top10[:10]]} ...")

#     # Быстрый доступ к монете из кеша
#     btc = client.get_by_symbol("BTC")
#     print("BTC from cache:", btc)

#     # Полный снимок (как dict-ы)
#     snapshot_dicts = client.get_all_cached(as_dicts=True)
#     print("Cache sample:", snapshot_dicts[0] if snapshot_dicts else None)

#     # Ручной рефреш по кнопке/по событию приложения
#     # client.force_refresh()









