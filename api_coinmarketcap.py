
import os
import time
import threading
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any, Iterable, Union
from control.data_models import CryptoBrief
from tools.tools import get_simvol

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
        cache_limit: int = 999999,
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
                prev = -1

            change = get_simvol(prev, price)

            new_list.append(
                CryptoBrief(
                    id=int(c["id"]),
                    name=c["name"],
                    symbol=sym,
                    price=price,
                    convert_currency=convert_upper,
                    last_updated=c.get("last_updated") or "",
                    price_change=change,
                    previous_price=prev,
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
    

    def find_coin(self, name_or_symbol: Union[str, List[str]], *, convert: Optional[str] = None) -> Union[Optional[CryptoBrief], List[CryptoBrief]]:
        """
        Поиск по символу (BTC) или имени (bitcoin). Возвращает CryptoBrief или список.
        Теперь: если монета найдена и её нет в кеше — она добавляется в кеш в валюте self.default_convert.
        """
        if not name_or_symbol:
            return None

        queries = [name_or_symbol] if isinstance(name_or_symbol, str) else name_or_symbol
        queries = [q.strip().lower() for q in queries if q]

        found_results: List[CryptoBrief] = []

        if not self._cache_data:
            self._refresh_once_blocking(convert=self.default_convert)

        def _ensure_in_cache_from_symbol_data(symbol_data: Dict[str, Any], src_convert_upper: str, last_updated: str) -> None:
            """
            Гарантированно добавляет монету в кеш в self.default_convert, если её там ещё нет.
            Использует id из symbol_data для запроса цены в нужной валюте кеша.
            """
            try:
                default_upper = self.default_convert.upper()
                symbol_upper = str(symbol_data["symbol"]).upper()

                with self._lock:
                    already = symbol_upper in self._index_by_symbol
                if already:
                    return

                # Получаем цену в валюте кеша (self.default_convert)
                cache_price: Optional[float] = None
                if src_convert_upper == default_upper:
                    quote_src = (symbol_data.get("quote") or {}).get(default_upper)
                    if quote_src and "price" in quote_src:
                        cache_price = float(quote_src["price"])
                else:
                    # Дозапрос quotes/latest по id в нужной валюте кеша
                    url_quotes = self.API_BASE + self.ENDPOINT_QUOTES
                    headers = {
                        "Accepts": "application/json",
                        "X-CMC_PRO_API_KEY": self.api_key,
                    }
                    params_cache = {"id": symbol_data["id"], "convert": default_upper}
                    resp_cache = self._session.get(url_quotes, headers=headers, params=params_cache, timeout=self.request_timeout)
                    resp_cache.raise_for_status()
                    payload_cache = resp_cache.json()
                    symbol_cache = (payload_cache.get("data") or {}).get(str(symbol_data["id"]))
                    if symbol_cache:
                        quote_cache = (symbol_cache.get("quote") or {}).get(default_upper)
                        if quote_cache and "price" in quote_cache:
                            cache_price = float(quote_cache["price"])

                if cache_price is None:
                    return  # нечего класть

                # Вычисляем индикатор изменения цены относительно (если) предыдущей
                with self._lock:
                    prev = None
                    if symbol_upper in self._index_by_symbol:
                        # уже кто-то успел добавить
                        return
                    # предыдущей цены нет, так как монеты в кеше не было
                    change = "*️⃣"

                    # Собираем элемент кеша в валюте default_convert
                    cb_cache = CryptoBrief(
                        id=int(symbol_data["id"]),
                        name=symbol_data["name"],
                        symbol=symbol_upper,
                        price=cache_price,
                        convert_currency=default_upper,
                        last_updated=last_updated or "",
                        price_change=change,
                        previous_price=prev,
                    )

                    current_list = list(self._cache_data)
                    current_list.append(cb_cache)
                    new_tuple = tuple(current_list)
                    new_index = {c.symbol: i for i, c in enumerate(new_tuple)}
                    self._cache_data = new_tuple
                    self._index_by_symbol = new_index
                    self._last_update_ts = time.time()

            except Exception as ex:
                if self.verbose:
                    print(f"find_coin cache add error: {ex}")

        for lookup in queries:
            # 1) поиск по символу в кеше
            cb = self.get_by_symbol(lookup.upper())
            if cb:
                found_results.append(cb)
                continue

            # 2) поиск по имени в кеше
            found_in_cache = False
            with self._lock:
                for coin in self._cache_data:
                    if coin.name.lower() == lookup:
                        found_results.append(coin)
                        found_in_cache = True
                        break
            if found_in_cache:
                continue

            # 3) запросы к API (quotes/latest, затем map -> id при необходимости)
            try:
                url = self.API_BASE + self.ENDPOINT_QUOTES
                headers = {
                    "Accepts": "application/json",
                    "X-CMC_PRO_API_KEY": self.api_key,
                }
                convert_upper = (convert or self.default_convert).upper()

                # Попытка по символу
                params = {"symbol": lookup.upper(), "convert": convert_upper}
                resp = self._session.get(url, headers=headers, params=params, timeout=self.request_timeout)
                resp.raise_for_status()
                payload = resp.json()
                data = payload.get("data", {})
                symbol_data = data.get(lookup.upper())
                if symbol_data:
                    quote = (symbol_data.get("quote") or {}).get(convert_upper)
                    if quote and "price" in quote:
                        ret_cb = CryptoBrief(
                            id=int(symbol_data["id"]),
                            name=symbol_data["name"],
                            symbol=str(symbol_data["symbol"]).upper(),
                            price=float(quote["price"]),
                            convert_currency=convert_upper,
                            last_updated=symbol_data.get("last_updated") or "",
                            price_change="",
                            previous_price=-1
                        )
                        found_results.append(ret_cb)
                        # гарантируем добавление в кеш (в валюте self.default_convert)
                        _ensure_in_cache_from_symbol_data(symbol_data, convert_upper, ret_cb.last_updated)
                        continue

                # Фоллбэк: поиск по slug через MAP -> id
                url_map = self.API_BASE + "/cryptocurrency/map"  # исправлено: без повторного /v1
                params_map = {"listing_status": "active", "symbol": "", "slug": lookup}
                resp_map = self._session.get(url_map, headers=headers, params=params_map, timeout=self.request_timeout)
                resp_map.raise_for_status()
                map_data = resp_map.json().get("data", [])
                if map_data:
                    coin_id = map_data[0].get("id")
                    params_id = {"id": coin_id, "convert": convert_upper}
                    resp_id = self._session.get(url, headers=headers, params=params_id, timeout=self.request_timeout)
                    resp_id.raise_for_status()
                    payload_id = resp_id.json()
                    symbol_data = (payload_id.get("data") or {}).get(str(coin_id))
                    if symbol_data:
                        quote = (symbol_data.get("quote") or {}).get(convert_upper)
                        if quote and "price" in quote:
                            ret_cb = CryptoBrief(
                                id=int(symbol_data["id"]),
                                name=symbol_data["name"],
                                symbol=str(symbol_data["symbol"]).upper(),
                                price=float(quote["price"]),
                                convert_currency=convert_upper,
                                last_updated=symbol_data.get("last_updated") or "",
                                price_change="",
                                previous_price=-1
                            )
                            found_results.append(ret_cb)
                            _ensure_in_cache_from_symbol_data(symbol_data, convert_upper, ret_cb.last_updated)
            except Exception as ex:
                if self.verbose:
                    print(f"find_coin error: {ex}")

        if isinstance(name_or_symbol, str):
            return found_results[0] if found_results else None
        return found_results






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
        
        :param symbols: Итерабель со строковыми тикерами или именами, напр. ['BTC', 'TON', 'bitcoin'].
        :param convert: Игнорируется для кеша; используется self.default_convert.
        :param replace_existing: Если True — обновляет существующие записи; если False — добавляет только новые.
        :return: Полный снимок кеша (tuple[CryptoBrief, ...]) после обновления.

        Будет обращаться к API только по отсутствующим тикерам!
        Если quotes/latest вернул не все — дозакажем недостающее через find_coin(..),
        поддерживающую поиск по символу/имени/slug.
        """
        # 1) Нормализация входа (сохраняем исходные токены — они могут быть именами)
        raw_tokens = [(s or "").strip() for s in symbols if s and s.strip()]
        unique_tokens = []
        seen = set()
        for t in raw_tokens:
            key = t.lower()
            if key not in seen:
                seen.add(key)
                unique_tokens.append(t)
        if not unique_tokens:
            return self.get_all_cached(as_dicts=False)

        # 2) Инициализация кеша при необходимости
        if not self._cache_data:
            self._refresh_once_blocking(convert=self.default_convert)

        convert_upper = self.default_convert.upper()
        if convert and convert.strip().upper() != convert_upper and self.verbose:
            print(f"[CMC] add_symbols_to_cache: requested convert '{convert}' != default '{convert_upper}', using default.")

        # 3) Отделяем уже закешированные символы (ищем и по symbol, и по name)
        with self._lock:
            symbol_index = dict(self._index_by_symbol)  # symbol -> pos
            name_index = {c.name.lower(): i for i, c in enumerate(self._cache_data)}
            prev_prices = {cb.symbol: cb.price for cb in self._cache_data}

        tokens_to_query: list[str] = []
        for tok in unique_tokens:
            sym = tok.strip().upper()
            if sym in symbol_index:
                continue
            # проверим имя
            if tok.strip().lower() in name_index:
                continue
            tokens_to_query.append(tok)

        # Если всё уже есть — отдадим снимок кеша
        if not tokens_to_query:
            return self.get_all_cached(as_dicts=False)

        # 4) Пытаемся сначала одним батчем через quotes/latest по тем, что выглядят как символы (A-Z, 0-9, дефисы)
        #    Имена/slug оставим для fallback через find_coin.
        def is_probable_symbol(x: str) -> bool:
            # «Похоже на тикер»: не содержит пробелов и содержит буквы/цифры/-. У CMC символы обычно латинские и без пробелов.
            y = x.strip()
            return (" " not in y) and all(ch.isalnum() or ch in "-._" for ch in y)

        probable_symbols = sorted({tok.strip().upper() for tok in tokens_to_query if is_probable_symbol(tok)})
        new_items: Dict[str, CryptoBrief] = {}
        found_now_symbols: set[str] = set()

        if probable_symbols:
            headers = {
                "Accepts": "application/json",
                "X-CMC_PRO_API_KEY": self.api_key,
            }
            params = {
                "symbol": ",".join(probable_symbols),
                "convert": convert_upper,
                "skip_invalid": "true",
            }
            # ВАЖНО: ENDPOINT_QUOTES должен быть '/cryptocurrency/quotes/latest'
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
            # data: dict[str, {...}] — ключи это символы
            for sym, info in data.items():
                quote = (info.get("quote") or {}).get(convert_upper)
                if not quote or "price" not in quote:
                    continue
                price = float(quote["price"])
                prev = prev_prices.get(sym)
            
                if prev is None:
                    prev = -1

                change = get_simvol(prev, price)

                new_items[sym] = CryptoBrief(
                id=int(info["id"]),
                name=info["name"],
                symbol=sym,
                price=price,
                convert_currency=convert_upper,
                last_updated=info.get("last_updated") or "",
                price_change=change,
                previous_price=prev,
                )
                found_now_symbols.add(sym.upper())

        # 5) Fallback: всё, что не удалось получить через quotes/latest, достанем точечно через find_coin(...)
        #    find_coin должен уметь принимать либо символ, либо имя/slug и возвращать CryptoBrief или None.
        unresolved_tokens: list[str] = []
        got_keys_upper = set(found_now_symbols)
        # Составим список «не покрытых» токенов
        for tok in tokens_to_query:
            # если токен выглядел как символ и он уже пришёл — пропускаем
            if tok.strip().upper() in got_keys_upper:
                continue
            unresolved_tokens.append(tok)

        for tok in unresolved_tokens:
            try:
                cb = self.find_coin(tok, convert=self.default_convert)
            except Exception as ex:
                if self.verbose:
                    print(f"[CMC] add_symbols_to_cache fallback find_coin error for '{tok}': {ex}")
                cb = None

            if not cb:
                # не нашли — просто пропустим
                if self.verbose:
                    print(f"[CMC] add_symbols_to_cache: not found via fallback: '{tok}'")
                continue

            # Проставим change относительно предыдущей цены (если была)
            prev = prev_prices.get(cb.symbol)
            if prev is None:
                prev = -1

            change = get_simvol(prev, price)

            # Гарантируем, что валюта совпадает с кешевой (мы вызывали find_coin с self.default_convert)
            new_items[cb.symbol] = CryptoBrief(
                id=int(cb.id),
                name=cb.name,
                symbol=cb.symbol,
                price=float(cb.price),
                convert_currency=convert_upper,
                last_updated=cb.last_updated or "",
                price_change=change,
            )
            got_keys_upper.add(cb.symbol.upper())

        # 6) Если всё равно нечего добавлять/обновлять — вернём снимок кеша
        if not new_items:
            return self.get_all_cached(as_dicts=False)

        # 7) Атомарно обновим кеш
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









