
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
        resp = self._session.get(url, headers=headers, params=params, timeout=self.request_timeout)

        # Обработка rate-limit
        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            delay = int(retry_after) if retry_after and retry_after.isdigit() else max(5, self._backoff_sec or 10)
            if self.verbose:
                print(f"[CMC] rate-limited, sleep {delay}s")
            time.sleep(delay)
            # Повтор
            resp = self._session.get(url, headers=headers, params=params, timeout=self.request_timeout)

        resp.raise_for_status()
        payload = resp.json()
        status = payload.get("status", {})
        if status.get("error_code", 0) != 0:
            raise RuntimeError(f"API error: {status.get('error_message')}")

        all_cryptos = payload.get("data") or []
        convert_upper = convert.upper()

        new_list: List[CryptoBrief] = []
        for c in all_cryptos:
            q = (c.get("quote") or {}).get(convert_upper)
            if not q:
                continue
            new_list.append(
                CryptoBrief(
                    id=int(c["id"]),
                    name=c["name"],
                    symbol=c["symbol"].upper(),
                    price=float(q["price"]),
                    convert_currency=convert_upper,
                    last_updated=c.get("last_updated") or "",
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
        }


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









