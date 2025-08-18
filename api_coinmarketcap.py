import os
import requests
from typing import List, Dict

class CoinMarketCapAPI:
    API_BASE = "https://pro-api.coinmarketcap.com/v1"
    API_ENDPOINT = "/cryptocurrency/quotes/latest"

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.environ.get("COINMARKETCAP_API_KEY")
        if not self.api_key:
            raise RuntimeError("Не найден COINMARKETCAP_API_KEY")

    def get_prices_info(self, symbols: List[str], convert: str = "USD") -> Dict[str, Dict[str, any]]:
        headers = {
            "Accepts": "application/json",
            "X-CMC_PRO_API_KEY": self.api_key
        }
        params = {
            "symbol": ",".join(symbols),
            "convert": convert,
            "skip_invalid": "true"
        }
        url = self.API_BASE + self.API_ENDPOINT
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data["status"].get("error_code", 0) != 0:
            raise RuntimeError(f"API error: {data['status'].get('error_message')}")

        result = {}
        for sym, info in data.get("data", {}).items():
            quote = info.get("quote", {}).get(convert)
            if quote and "price" in quote:
                # Обычно базовая цена это 1 (1BTC = price BTC in USD), но сохраним явно
                result[sym] = {
                    "base_price": 1.0,
                    "converted_price": float(quote["price"]),
                    "convert_currency": convert
                }
        return result


